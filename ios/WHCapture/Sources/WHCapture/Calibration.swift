import Foundation

/// The parts of fixtures/calibration/iphone-1206x2622.json the phone needs. Rects are [x, y, w, h].
public struct Calibration: Codable, Sendable {
    public var version: String
    public var width: Int
    public var height: Int
    public var sample_rects: [[Int]]
    public var roi_banner: [Int]
    public var roi_banner_words: [Int]
    public var roi_banner_score: [Int]
    public var roi_timer: [Int]
    public var roi_end_banner: [Int]
    public var roi_end_list: [Int]
    public var tile_centers: [[Double]]
    public var pitch: [Double]

    public static let roiKeys = ["banner", "banner_words", "banner_score", "timer", "end_banner", "end_list"]

    public func roi(_ key: String) -> [Int] {
        switch key {
        case "banner": return roi_banner
        case "banner_words": return roi_banner_words
        case "banner_score": return roi_banner_score
        case "timer": return roi_timer
        case "end_banner": return roi_end_banner
        default: return roi_end_list
        }
    }

    /// Board crop rect (tile area plus half a pitch), as in tools/make_review.py.
    public var boardRect: [Int] {
        let m = pitch[0] / 2
        let x0 = (tile_centers[0][0] - m).rounded(.toNearestOrEven)
        let y0 = (tile_centers[0][1] - m).rounded(.toNearestOrEven)
        let x1 = (tile_centers[15][0] + m).rounded(.toNearestOrEven)
        let y1 = (tile_centers[15][1] + m).rounded(.toNearestOrEven)
        return [Int(x0), Int(y0), Int(x1 - x0), Int(y1 - y0)]
    }

    /// The all-words list band the phone crops (whcore.allwords.LIST_BAND_RECT).
    public static let listBandRect = [300, 612, 680, 1988]

    /// Rect scaled to a buffer of size w×h (Python `scale_calibration`, half-to-even rounding).
    public func scaled(_ r: [Int], toWidth w: Int, height h: Int) -> [Int] {
        if w == width && h == height { return r }
        let sx = Double(w) / Double(width), sy = Double(h) / Double(height)
        func rnd(_ v: Double) -> Int { Int(v.rounded(.toNearestOrEven)) }
        return [rnd(Double(r[0]) * sx), rnd(Double(r[1]) * sy),
                max(1, rnd(Double(r[2]) * sx)), max(1, rnd(Double(r[3]) * sy))]
    }

    public static func load(_ url: URL) throws -> Calibration {
        try JSONDecoder().decode(Calibration.self, from: Data(contentsOf: url))
    }
}
