import Foundation
import XCTest
@testable import WHCapture

final class DebugTests: XCTestCase {
    func img(_ v: UInt8) -> GrayImage { GrayImage(width: 16, height: 8, pixels: Array(repeating: v, count: 128)) }

    func testKeepsWindowAroundFlaggedEvent() {
        let rec = DebugRecorder(width: 16, windowMs: 100)
        for f in 0..<30 {  // 30 fps
            rec.add(frame: f, tMs: f * 33, image: img(UInt8(f)))
            if f == 10 { rec.flag(frame: 10, tMs: 330, reason: "colour≠words") }
        }
        let names = rec.take().keys.sorted { Int($0.dropFirst(6).dropLast(4))! < Int($1.dropFirst(6).dropLast(4))! }
        // ring covers 100 ms before (frames 7–10), then 100 ms after (11–13)
        XCTAssertEqual(names, (7...13).map { "debug_\($0).jpg" })
        XCTAssertEqual(rec.reasons[10], "colour≠words")
        XCTAssertTrue(rec.take().isEmpty)  // handed out once
    }

    func testSessionCap() {
        let rec = DebugRecorder(width: 16, windowMs: 1000, capBytes: 1500)
        for f in 0..<20 { rec.add(frame: f, tMs: f * 33, image: img(UInt8(f * 10))) }
        rec.flag(frame: 19, tMs: 19 * 33, reason: "x")
        let out = rec.take()
        XCTAssertFalse(out.isEmpty)
        XCTAssertLessThanOrEqual(out.values.reduce(0) { $0 + $1.count }, 1500)
        XCTAssertLessThan(out.count, 20)
    }

    func testThumbnailSize() throws {
        let frame = SamplerTests.frame(fill: [10, 200, 10], patches: [], width: 884, height: 1920)
        let pb = SamplerTests.bgraBuffer(frame)
        CVPixelBufferLockBaseAddress(pb, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pb, .readOnly) }
        let t = DebugRecorder.thumbnail(try XCTUnwrap(FrameView(pb)), width: 160)
        XCTAssertEqual(t.width, 160)
        XCTAssertEqual(t.height, 348)
        XCTAssertEqual(t.pixels[0], cvGray(10, 200, 10))
    }

    func testMachineFlagsColourWordsDisagreement() {
        // board frames; a green release that does NOT raise WORDS → low confidence
        func row(_ green: Bool, words: Double) -> SampleRow {
            var r: SampleRow = ["banner_r": 205, "banner_g": 205, "banner_b": 205, "banner_std": 85,
                                "timer_r": 92, "timer_g": 92, "timer_b": 92, "timer_std": 54, "words": words]
            for k in 0..<16 {
                let c: [Double] = (green && k < 3) ? [128, 250, 128] : [247.4, 209.3, 150.5]
                r["t\(k)_r"] = c[0]; r["t\(k)_g"] = c[1]; r["t\(k)_b"] = c[2]
            }
            return r
        }
        let m = Machine(sessionID: newRecordID(), startedAt: Date())
        var flagged: [String] = []
        m.onLowConfidence = { _, reason in flagged.append(reason) }
        var rows = Array(repeating: row(false, words: 0), count: 30) + Array(repeating: row(true, words: 0), count: 3)
        rows += Array(repeating: row(false, words: 0), count: 10)
        for (i, var r) in rows.enumerated() { r["t_ms"] = Double(i * 33); m.feed(r) }
        XCTAssertEqual(flagged, ["colour≠words"])
    }
}
