import Foundation
import ImageIO
import XCTest
@testable import WHCapture

/// Captures requests and answers with scripted status codes (or a network error for code 0).
final class StubProtocol: URLProtocol {
    static var responses: [Int] = []
    static var requests: [URLRequest] = []
    static var bodies: [Data] = []

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.requests.append(request)
        Self.bodies.append(request.httpBody ?? Self.readStream(request.httpBodyStream))
        let code = Self.responses.isEmpty ? 200 : Self.responses.removeFirst()
        if code == 0 {
            client?.urlProtocol(self, didFailWithError: URLError(.notConnectedToInternet))
            return
        }
        let resp = HTTPURLResponse(url: request.url!, statusCode: code, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: resp, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data("{}".utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}

    static func readStream(_ s: InputStream?) -> Data {
        guard let s else { return Data() }
        s.open()
        defer { s.close() }
        var data = Data()
        var buf = [UInt8](repeating: 0, count: 4096)
        while s.hasBytesAvailable {
            let n = s.read(&buf, maxLength: buf.count)
            if n <= 0 { break }
            data.append(buf, count: n)
        }
        return data
    }
}

final class UploaderTests: XCTestCase {
    var dir: URL!
    var session: URLSession!

    override func setUp() {
        dir = FileManager.default.temporaryDirectory.appendingPathComponent("whq-\(UUID().uuidString)")
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [StubProtocol.self]
        session = URLSession(configuration: cfg)
        StubProtocol.responses = []
        StubProtocol.requests = []
        StubProtocol.bodies = []
    }

    override func tearDown() {
        try? FileManager.default.removeItem(at: dir)
    }

    func board(_ seq: Int) -> Record {
        .board(BoardRecord(board_id: uuid5(namespace: "0b7d9e10-2c3a-4f5b-8e6d-7a8b9c0d1e2f", name: "board-\(seq)"),
                           session_id: "0b7d9e10-2c3a-4f5b-8e6d-7a8b9c0d1e2f", seq: seq, device: "test",
                           app_version: "0", calibration_version: "c", opened_at: Date(timeIntervalSince1970: 1_793_000_000),
                           view_ms: 500, status: .skipped, board_image: "board_\(seq).jpg", attempts: [],
                           diagnostics: Diagnostics(fps_processed: 60, frames_dropped: 0, mem_peak_mb: 8)))
    }

    func allWords() -> Record {
        .allWords(AllWordsRecord(record_id: newRecordID(), session_id: newRecordID(),
                                 captured_at: Date(timeIntervalSince1970: 1_793_000_100), frames: ["allwords_0_0.jpg"],
                                 shifts_px: [0], gap_flags: [false], bounced_at_end: true))
    }

    func testQueueIsOrderedAtomicAndIdempotent() throws {
        var now = 1_793_000_000.0  // a real epoch: ms values overflow 32-bit formatting
        let q = try RecordQueue(directory: dir, clock: { now += 1; return Date(timeIntervalSince1970: now) })
        try q.enqueue(board(0), images: ["board_0.jpg": Data([1, 2, 3])])
        try q.enqueue(allWords(), images: ["allwords_0_0.jpg": Data([4])])
        try q.enqueue(board(0), images: ["board_0.jpg": Data([9])])  // same id → replaced, moved to the back
        let items = q.pending()
        XCTAssertEqual(items.map(\.kind), ["all_words", "board"])
        XCTAssertEqual(Int(items[0].directory.lastPathComponent.prefix(13)), 1_793_000_002_000)
        XCTAssertEqual(try Data(contentsOf: items[1].images()[0]), Data([9]))
        XCTAssertFalse(try FileManager.default.contentsOfDirectory(atPath: dir.path).contains { $0.hasPrefix(".tmp") })
        let rec = try WHJSON.decoder().decode(Record.self, from: Data(contentsOf: items[1].recordURL))
        XCTAssertEqual(rec, board(0))
    }

    func testUploadsMultipartWithBearerToken() async throws {
        let q = try RecordQueue(directory: dir)
        try q.enqueue(board(3), images: ["board_3.jpg": Data("JPEGDATA".utf8)])
        try q.enqueue(allWords(), images: ["allwords_0_0.jpg": Data("LIST".utf8)])
        let up = Uploader(baseURL: URL(string: "https://example.test")!, token: "secret", queue: q, session: session)
        let first = await up.uploadNext()
        guard case .uploaded = first else { return XCTFail("\(first)") }
        _ = await up.uploadNext()
        XCTAssertEqual(StubProtocol.requests.map { $0.url!.path }, ["/v1/boards", "/v1/allwords"])
        let req = StubProtocol.requests[0]
        XCTAssertEqual(req.value(forHTTPHeaderField: "Authorization"), "Bearer secret")
        XCTAssertTrue(req.value(forHTTPHeaderField: "Content-Type")!.hasPrefix("multipart/form-data; boundary="))
        let body = String(decoding: StubProtocol.bodies[0], as: UTF8.self)
        XCTAssertTrue(body.contains("name=\"record\"; filename=\"record.json\""))
        XCTAssertTrue(body.contains("\"board_image\":\"board_3.jpg\""))
        XCTAssertTrue(body.contains("name=\"files\"; filename=\"board_3.jpg\""))
        XCTAssertTrue(body.contains("JPEGDATA"))
        XCTAssertTrue(q.pending().isEmpty)
        let done = await up.uploadNext()
        XCTAssertEqual(done, .empty)
    }

    func testRetriesWithBackoffThenSucceeds() async throws {
        let q = try RecordQueue(directory: dir)
        try q.enqueue(board(1), images: [:])
        StubProtocol.responses = [500, 0, 404, 200]  // 0 = network error; 404 = endpoint not deployed yet
        let up = Uploader(baseURL: URL(string: "https://example.test")!, token: "t", queue: q, session: session,
                          jitter: { 1.0 })
        var waits: [TimeInterval] = []
        let out = await up.drain(sleep: { waits.append($0) })
        XCTAssertEqual(out, .empty)
        XCTAssertEqual(waits, [1, 2, 4])
        XCTAssertEqual(StubProtocol.requests.count, 4)
        XCTAssertEqual(up.failures, 0)
    }

    func testDuplicateIsDoneUnauthorizedStopsMalformedIsParked() async throws {
        let q = try RecordQueue(directory: dir)
        try q.enqueue(board(1), images: [:])
        try q.enqueue(board(2), images: [:])
        try q.enqueue(board(3), images: [:])
        let up = Uploader(baseURL: URL(string: "https://example.test")!, token: "t", queue: q, session: session)
        StubProtocol.responses = [409, 422, 401]
        let a = await up.uploadNext(), b = await up.uploadNext(), c = await up.uploadNext()
        guard case .uploaded = a, case .rejected(_, 422) = b else { return XCTFail("\(a) \(b)") }
        XCTAssertEqual(c, .unauthorized)
        XCTAssertEqual(q.pending().count, 1)  // board 3 waits for a fixed token
        let failed = try FileManager.default.contentsOfDirectory(atPath: dir.appendingPathComponent("failed").path)
        XCTAssertEqual(failed.count, 1)
    }

    func testBackoffCapsAtFiveMinutes() async throws {
        let q = try RecordQueue(directory: dir)
        try q.enqueue(board(1), images: [:])
        StubProtocol.responses = Array(repeating: 500, count: 12)
        let up = Uploader(baseURL: URL(string: "https://example.test")!, token: "t", queue: q, session: session,
                          jitter: { 1.0 })
        var waits: [TimeInterval] = []
        _ = await up.drain(maxAttempts: 12, sleep: { waits.append($0) })
        XCTAssertEqual(waits.last, 300)
        XCTAssertEqual(Array(waits.prefix(4)), [1, 2, 4, 8])
    }
}

final class CropTests: XCTestCase {
    func testJPEGRoundTrip() throws {
        let img = GrayImage(width: 64, height: 32, pixels: (0..<(64 * 32)).map { UInt8($0 % 256) })
        let data = try XCTUnwrap(CropStore.jpeg(img))
        XCTAssertEqual(Array(data.prefix(2)), [0xFF, 0xD8])  // JPEG SOI
    }

    func testStoreResolvesLiveAndPastFrames() throws {
        let cal = SamplerTests.calibration
        let store = CropStore(calibration: cal)
        let white = SamplerTests.frame(fill: [250, 250, 250], patches: [])
        let pb = SamplerTests.bgraBuffer(white)
        CVPixelBufferLockBaseAddress(pb, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pb, .readOnly) }
        let v = try XCTUnwrap(FrameView(pb))
        for f in 0..<40 { store.observe(frame: f, screen: .end, label: .end, still: false, view: v) }
        store.observe(frame: 40, screen: .board, label: .board, still: false, view: v)
        store.observe(frame: 41, screen: .board, label: .board, still: false, view: v)  // throttled
        store.capture(frame: 41, rect: "list_band", view: v)
        XCTAssertNil(store.image(for: CropRequest(name: "e", frame: 2, rect: "roi_end_list")))  // fell out of the ring
        XCTAssertNotNil(store.image(for: CropRequest(name: "e", frame: 38, rect: "roi_end_list")))
        let board = try XCTUnwrap(store.image(for: CropRequest(name: "b", frame: 41, rect: "board")))  // nearest earlier
        XCTAssertEqual(board.width, cal.boardRect[2])
        let jpegs = store.jpegs(for: [CropRequest(name: "allwords_0_0.jpg", frame: 41, rect: "list_band")])
        XCTAssertEqual(Array(jpegs.keys), ["allwords_0_0.jpg"])
        XCTAssertNil(store.image(for: CropRequest(name: "x", frame: 41, rect: "list_band")))  // released
    }

    func testBoardCropStacksALaterLook() throws {
        let cal = SamplerTests.calibration
        let store = CropStore(calibration: cal)
        let pb = SamplerTests.bgraBuffer(SamplerTests.frame(fill: [240, 220, 170], patches: []))
        CVPixelBufferLockBaseAddress(pb, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pb, .readOnly) }
        let v = try XCTUnwrap(FrameView(pb))
        store.capture(frame: 50, rect: "board", view: v)  // settled look
        for f in stride(from: 50, through: 200, by: 6) {
            store.observe(frame: f, screen: .board, label: .board, still: false, view: v)
        }
        let jpeg = try XCTUnwrap(store.jpegs(for: [CropRequest(name: "board_0.jpg", frame: 50, rect: "board")])["board_0.jpg"])
        let src = try XCTUnwrap(CGImageSourceCreateWithData(jpeg as CFData, nil))
        let img = try XCTUnwrap(CGImageSourceCreateImageAtIndex(src, 0, nil))
        XCTAssertEqual(img.height, 2 * cal.boardRect[3])
        XCTAssertEqual(img.width, cal.boardRect[2])
        // a quick skip (no later frame) stays a single look
        let quick = CropStore(calibration: cal)
        quick.observe(frame: 10, screen: .board, label: .board, still: false, view: v)
        let one = try XCTUnwrap(quick.jpegs(for: [CropRequest(name: "b.jpg", frame: 12, rect: "board")])["b.jpg"])
        let i1 = try XCTUnwrap(CGImageSourceCreateImageAtIndex(CGImageSourceCreateWithData(one as CFData, nil)!, 0, nil))
        XCTAssertEqual(i1.height, cal.boardRect[3])
    }
}
