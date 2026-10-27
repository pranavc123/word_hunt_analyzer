import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

/// Grayscale crops for records (PLAN §2.3, 2.5, 2.6).
///
/// The phone cannot go back to an earlier frame, but the machine asks for some crops after the
/// fact (end screen 3 frames before it left, the last board frame of a quick skip, the last still
/// list frame). `CropStore` therefore keeps small rings of raw gray crops and resolves the
/// machine's `CropRequest`s from them; JPEG encoding happens only when a record is finalised.
public final class CropStore {
    public struct Entry {
        public let frame: Int
        public let image: GrayImage
    }

    private let calibration: Calibration
    private(set) var lastBoard: Entry?
    private(set) var wanted: [String: [Int: GrayImage]] = [:]  // rect → frame → crop
    private(set) var endRing: [Int: (GrayImage, GrayImage)] = [:]  // frame → (banner, list)
    private(set) var stillRing: [Int: GrayImage] = [:]  // still all-words frames
    public let endRingSize = 30  // ≥ 0.5 s of end frames at 60 fps (crop is taken 200 ms back)
    public let stillRingSize = 10
    public let boardEvery = 6

    public init(calibration: Calibration) {
        self.calibration = calibration
    }

    private func rect(_ name: String, _ v: FrameView) -> [Int] {
        let r: [Int]
        switch name {
        case "board": r = calibration.boardRect
        case "list_band": r = Calibration.listBandRect
        case "roi_end_banner": r = calibration.roi_end_banner
        default: r = calibration.roi_end_list
        }
        return calibration.scaled(r, toWidth: v.width, height: v.height)
    }

    /// Call once per frame after `Machine.feed`, with the screen the machine is on.
    public func observe(frame: Int, screen: Screen, label: Screen, still: Bool, view v: FrameView) {
        // the board is static: a recent frame serves quick skips (cheap: every 6th frame)
        if screen == .board && label == .board && frame - (lastBoard?.frame ?? Int.min / 2) >= boardEvery {
            lastBoard = Entry(frame: frame, image: v.gray(rect("board", v)))
        }
        if screen == .end {
            endRing[frame] = (v.gray(rect("roi_end_banner", v)), v.gray(rect("roi_end_list", v)))
            if endRing.count > endRingSize, let oldest = endRing.keys.min() { endRing[oldest] = nil }
        }
        if screen == .allWords && still {
            stillRing[frame] = v.gray(rect("list_band", v))
            if stillRing.count > stillRingSize, let oldest = stillRing.keys.min() { stillRing[oldest] = nil }
        }
    }

    /// The machine decided to crop the current frame (`Machine.onCropFrame`).
    public func capture(frame: Int, rect name: String, view v: FrameView) {
        wanted[name, default: [:]][frame] = v.gray(rect(name, v))
    }

    /// Resolve a request to a gray crop (nil if that frame was not kept).
    public func image(for r: CropRequest) -> GrayImage? {
        if let img = wanted[r.rect]?[r.frame] { return img }
        switch r.rect {
        case "board":  // nearest kept board frame at or before the request
            guard let b = lastBoard, b.frame <= r.frame, r.frame - b.frame < 4 * boardEvery else { return nil }
            return b.image
        case "roi_end_banner": return endRing[r.frame]?.0
        case "roi_end_list": return endRing[r.frame]?.1
        case "list_band": return stillRing[r.frame]
        default: return nil
        }
    }

    /// Resolve and encode every request of a finished record, then forget crops it no longer needs.
    public func jpegs(for requests: [CropRequest], quality: Double = 0.8) -> [String: Data] {
        var out: [String: Data] = [:]
        for r in requests {
            if let img = image(for: r), let data = CropStore.jpeg(img, quality: quality) { out[r.name] = data }
            wanted[r.rect]?[r.frame] = nil
        }
        return out
    }

    /// Drop captured crops older than `frame` that no pending record can still ask for.
    public func prune(before frame: Int) {
        for k in wanted.keys { wanted[k] = wanted[k]?.filter { $0.key >= frame } }
    }

    public static func jpeg(_ img: GrayImage, quality: Double = 0.8) -> Data? {
        guard img.width > 0, img.height > 0 else { return nil }
        let data = NSMutableData()
        let provider = CGDataProvider(data: Data(img.pixels) as CFData)!
        guard let cg = CGImage(width: img.width, height: img.height, bitsPerComponent: 8, bitsPerPixel: 8,
                               bytesPerRow: img.width, space: CGColorSpaceCreateDeviceGray(),
                               bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.none.rawValue),
                               provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent),
              let dest = CGImageDestinationCreateWithData(data, UTType.jpeg.identifier as CFString, 1, nil)
        else { return nil }
        CGImageDestinationAddImage(dest, cg, [kCGImageDestinationLossyCompressionQuality: quality] as CFDictionary)
        return CGImageDestinationFinalize(dest) ? data as Data : nil
    }
}
