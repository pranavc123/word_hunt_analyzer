import Foundation

/// Debug capture (S3.T5, compiled in with WH_DEBUG=1): keeps small grayscale frames around
/// low-confidence events so failures can be inspected numerically on the server.
///
/// Every frame is downscaled to `width` px wide and kept in a ring covering the last `windowMs`.
/// `flag(...)` keeps the ring (event − windowMs) and the following `windowMs` of frames. `take()`
/// returns the kept frames as JPEGs named `debug_<frame>.jpg`, within a per-session byte cap.
public final class DebugRecorder {
    public let width: Int
    public let windowMs: Int
    public let capBytes: Int
    public private(set) var usedBytes = 0
    public private(set) var reasons: [Int: String] = [:]

    private var ring: [(frame: Int, tMs: Int, image: GrayImage)] = []
    private var keepUntilMs = Int.min
    private var kept: [Int: GrayImage] = [:]

    public init(width: Int = 160, windowMs: Int = 500, capBytes: Int = 20_000_000) {
        self.width = width
        self.windowMs = windowMs
        self.capBytes = capBytes
    }

    /// Nearest-neighbour gray thumbnail of the whole frame.
    public static func thumbnail(_ v: FrameView, width: Int) -> GrayImage {
        let height = max(1, Int((Double(v.height) * Double(width) / Double(v.width)).rounded()))
        var px = [UInt8](repeating: 0, count: width * height)
        for y in 0..<height {
            let sy = min(v.height - 1, y * v.height / height)
            for x in 0..<width {
                let (r, g, b) = v.rgb(min(v.width - 1, x * v.width / width), sy)
                px[y * width + x] = cvGray(r, g, b)
            }
        }
        return GrayImage(width: width, height: height, pixels: px)
    }

    public func add(frame: Int, tMs: Int, view: FrameView) {
        add(frame: frame, tMs: tMs, image: Self.thumbnail(view, width: width))
    }

    public func add(frame: Int, tMs: Int, image: GrayImage) {
        ring.append((frame, tMs, image))
        while let first = ring.first, tMs - first.tMs > windowMs { ring.removeFirst() }
        if tMs <= keepUntilMs { kept[frame] = image }
    }

    public func flag(frame: Int, tMs: Int, reason: String) {
        reasons[frame] = reason
        for f in ring where f.tMs >= tMs - windowMs { kept[f.frame] = f.image }
        keepUntilMs = max(keepUntilMs, tMs + windowMs)
    }

    /// Kept frames since the last call, as JPEGs (dropped once the session cap is reached).
    public func take(quality: Double = 0.6) -> [String: Data] {
        var out: [String: Data] = [:]
        for frame in kept.keys.sorted() {
            guard let data = CropStore.jpeg(kept[frame]!, quality: quality) else { continue }
            if usedBytes + data.count > capBytes { break }
            usedBytes += data.count
            out["debug_\(frame).jpg"] = data
        }
        kept.removeAll()
        return out
    }
}
