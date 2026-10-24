import CoreMedia
import CoreVideo
import Foundation
import ReplayKit

/// S0.T14 device probe: samples the 16 tile patches from every frame it can keep up with
/// (one frame in flight, the rest dropped) and POSTs diagnostics to `/diag` every 10 s.
final class SampleHandler: RPBroadcastSampleHandler {
    private let work = DispatchQueue(label: "wh.sample", qos: .userInitiated)
    private let lock = NSLock()
    private var busy = false
    private var stats = Stats()
    private var timer: DispatchSourceTimer?
    private let calibration = Calibration.load()
    private let config = Config()

    struct Stats {
        var received = 0
        var processed = 0
        var dropped = 0
        var windowProcessed = 0
        var windowStart = Date()
        var started = Date()
        var memPeakMB = 0.0
        var lastTiles: [[Int]] = []
        var bufferSize = (0, 0)
        var pixelFormat = ""
    }

    override func broadcastStarted(withSetupInfo setupInfo: [String: NSObject]?) {
        lock.withLock { stats = Stats() }
        let t = DispatchSource.makeTimerSource(queue: DispatchQueue.global(qos: .utility))
        t.schedule(deadline: .now() + 10, repeating: 10)
        t.setEventHandler { [weak self] in self?.postDiag(event: "tick") }
        t.resume()
        timer = t
        postDiag(event: "start")
    }

    override func broadcastFinished() {
        timer?.cancel()
        timer = nil
        postDiag(event: "finish", wait: true)
    }

    override func processSampleBuffer(_ sampleBuffer: CMSampleBuffer, with type: RPSampleBufferType) {
        guard type == .video else { return }
        let take: Bool = lock.withLock {
            stats.received += 1
            if busy { stats.dropped += 1; return false }
            busy = true
            return true
        }
        guard take else { return }
        work.async { [self] in
            let result = CMSampleBufferGetImageBuffer(sampleBuffer).flatMap { sample($0) }
            lock.withLock {
                busy = false
                stats.processed += 1
                stats.windowProcessed += 1
                if let r = result {
                    stats.lastTiles = r.tiles
                    stats.bufferSize = r.size
                    stats.pixelFormat = r.format
                }
            }
        }
    }

    // MARK: sampling

    struct SampleResult {
        let tiles: [[Int]]
        let size: (Int, Int)
        let format: String
    }

    private func sample(_ pb: CVPixelBuffer) -> SampleResult? {
        guard let cal = calibration else { return nil }
        CVPixelBufferLockBaseAddress(pb, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pb, .readOnly) }
        let w = CVPixelBufferGetWidth(pb), h = CVPixelBufferGetHeight(pb)
        let fmt = CVPixelBufferGetPixelFormatType(pb)
        let sx = Double(w) / Double(cal.width), sy = Double(h) / Double(cal.height)
        var tiles: [[Int]] = []
        tiles.reserveCapacity(cal.sample_rects.count)
        for r in cal.sample_rects {
            let x0 = Int(Double(r[0]) * sx), y0 = Int(Double(r[1]) * sy)
            let x1 = max(x0 + 1, Int(Double(r[0] + r[2]) * sx))
            let y1 = max(y0 + 1, Int(Double(r[1] + r[3]) * sy))
            guard x1 <= w, y1 <= h else { return nil }
            switch fmt {
            case kCVPixelFormatType_32BGRA:
                tiles.append(meanBGRA(pb, x0, y0, x1, y1))
            case kCVPixelFormatType_420YpCbCr8BiPlanarFullRange,
                 kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange:
                tiles.append(meanYUV(pb, x0, y0, x1, y1,
                                     fullRange: fmt == kCVPixelFormatType_420YpCbCr8BiPlanarFullRange))
            default:
                return SampleResult(tiles: [], size: (w, h), format: fourCC(fmt))
            }
        }
        return SampleResult(tiles: tiles, size: (w, h), format: fourCC(fmt))
    }

    private func meanBGRA(_ pb: CVPixelBuffer, _ x0: Int, _ y0: Int, _ x1: Int, _ y1: Int) -> [Int] {
        guard let base = CVPixelBufferGetBaseAddress(pb) else { return [0, 0, 0] }
        let stride = CVPixelBufferGetBytesPerRow(pb)
        let p = base.assumingMemoryBound(to: UInt8.self)
        var r = 0, g = 0, b = 0
        for y in y0..<y1 {
            let row = p + y * stride
            for x in x0..<x1 {
                b += Int(row[4 * x]); g += Int(row[4 * x + 1]); r += Int(row[4 * x + 2])
            }
        }
        let n = max(1, (x1 - x0) * (y1 - y0))
        return [r / n, g / n, b / n]
    }

    private func meanYUV(_ pb: CVPixelBuffer, _ x0: Int, _ y0: Int, _ x1: Int, _ y1: Int,
                         fullRange: Bool) -> [Int] {
        guard let yb = CVPixelBufferGetBaseAddressOfPlane(pb, 0),
              let cb = CVPixelBufferGetBaseAddressOfPlane(pb, 1) else { return [0, 0, 0] }
        let ys = CVPixelBufferGetBytesPerRowOfPlane(pb, 0)
        let cs = CVPixelBufferGetBytesPerRowOfPlane(pb, 1)
        let yp = yb.assumingMemoryBound(to: UInt8.self), cp = cb.assumingMemoryBound(to: UInt8.self)
        let bt709 = (CVBufferCopyAttachment(pb, kCVImageBufferYCbCrMatrixKey, nil) as? String)
            == (kCVImageBufferYCbCrMatrix_ITU_R_709_2 as String)
        var r = 0.0, g = 0.0, b = 0.0
        for y in y0..<y1 {
            for x in x0..<x1 {
                var Y = Double(yp[y * ys + x])
                var U = Double(cp[(y / 2) * cs + (x / 2) * 2]) - 128
                var V = Double(cp[(y / 2) * cs + (x / 2) * 2 + 1]) - 128
                if !fullRange { Y = (Y - 16) * 255 / 219; U *= 255 / 224; V *= 255 / 224 }
                if bt709 {
                    r += Y + 1.5748 * V; g += Y - 0.1873 * U - 0.4681 * V; b += Y + 1.8556 * U
                } else {
                    r += Y + 1.402 * V; g += Y - 0.344136 * U - 0.714136 * V; b += Y + 1.772 * U
                }
            }
        }
        let n = Double(max(1, (x1 - x0) * (y1 - y0)))
        return [r, g, b].map { Int(min(255, max(0, $0 / n)).rounded()) }
    }

    private func fourCC(_ v: OSType) -> String {
        let bytes = [24, 16, 8, 0].map { UInt8((v >> $0) & 0xFF) }
        return String(bytes: bytes, encoding: .ascii) ?? "\(v)"
    }

    // MARK: diagnostics

    private func postDiag(event: String, wait: Bool = false) {
        let mem = Self.memoryMB()
        let body: [String: Any] = lock.withLock {
            stats.memPeakMB = max(stats.memPeakMB, mem)
            let now = Date()
            let window = now.timeIntervalSince(stats.windowStart)
            let fps = window > 0 ? Double(stats.windowProcessed) / window : 0
            stats.windowProcessed = 0
            stats.windowStart = now
            return [
                "event": event,
                "fps_processed": (fps * 10).rounded() / 10,
                "frames_received": stats.received,
                "frames_processed": stats.processed,
                "frames_dropped": stats.dropped,
                "mem_mb": (mem * 10).rounded() / 10,
                "mem_peak_mb": (stats.memPeakMB * 10).rounded() / 10,
                "uptime_s": Int(now.timeIntervalSince(stats.started)),
                "app_group_configured": !config.appGroup.isEmpty,
                "app_group_available": config.appGroupAvailable,
                "calibration_loaded": calibration != nil,
                "buffer_w": stats.bufferSize.0,
                "buffer_h": stats.bufferSize.1,
                "pixel_format": stats.pixelFormat,
                "tiles_rgb": stats.lastTiles,
            ]
        }
        guard let url = URL(string: config.serverURL + "/diag"),
              let data = try? JSONSerialization.data(withJSONObject: body) else { return }
        var req = URLRequest(url: url, timeoutInterval: 8)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if !config.token.isEmpty { req.setValue("Bearer \(config.token)", forHTTPHeaderField: "Authorization") }
        req.httpBody = data
        let done = DispatchSemaphore(value: 0)
        URLSession.shared.dataTask(with: req) { _, _, _ in done.signal() }.resume()
        if wait { _ = done.wait(timeout: .now() + 3) }
    }

    static func memoryMB() -> Double {
        var info = task_vm_info_data_t()
        var count = mach_msg_type_number_t(MemoryLayout<task_vm_info_data_t>.size / MemoryLayout<natural_t>.size)
        let kr = withUnsafeMutablePointer(to: &info) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &count)
            }
        }
        return kr == KERN_SUCCESS ? Double(info.phys_footprint) / 1_048_576 : -1
    }
}

struct Calibration: Decodable {
    let version: String
    let width: Int
    let height: Int
    let sample_rects: [[Int]]

    static func load() -> Calibration? {
        guard let url = Bundle(for: SampleHandler.self).url(forResource: "iphone-1206x2622", withExtension: "json"),
              let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(Calibration.self, from: data)
    }
}

struct Config {
    let serverURL: String
    let token: String
    let appGroup: String

    init(bundle: Bundle = Bundle(for: SampleHandler.self)) {
        serverURL = bundle.object(forInfoDictionaryKey: "WHServerURL") as? String ?? ""
        token = bundle.object(forInfoDictionaryKey: "WHToken") as? String ?? ""
        appGroup = bundle.object(forInfoDictionaryKey: "WHAppGroup") as? String ?? ""
    }

    var appGroupAvailable: Bool {
        !appGroup.isEmpty
            && FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroup) != nil
    }
}
