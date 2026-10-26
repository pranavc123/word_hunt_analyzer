import Foundation

/// One sample row (fixtures/samples/README.md): column name → value; missing values are NaN.
public typealias SampleRow = [String: Double]

public enum Screen: String, Sendable {
    case board, end, allWords = "all_words", other
}

/// Port of server/whcore/oracle/screens.py `classify_row`. Thresholds are in the colour domain of
/// the source (screen recordings for the fixtures).
public enum Screens {
    static func mean(_ row: SampleRow, _ key: String) -> Double {
        ((row["\(key)_r"] ?? .nan) + (row["\(key)_g"] ?? .nan) + (row["\(key)_b"] ?? .nan)) / 3
    }

    public static func classify(_ row: SampleRow) -> Screen {
        let banner = mean(row, "banner"), bannerStd = row["banner_std"] ?? .nan
        let timer = mean(row, "timer")
        if banner > 185 && bannerStd > 70 && timer < 112 { return .board }
        if banner < 115 && bannerStd < 25 && (row["end_banner_std"] ?? .nan) > 60
            && mean(row, "end_list") < 110 {
            return .end
        }
        if 105 < banner && banner < 135 && 38 < bannerStd && bannerStd < 62 && timer > 140
            && (row["timer_std"] ?? .nan) > 60 {
            return .allWords
        }
        return .other
    }
}

/// Port of server/whcore/oracle/traces.py tile colour states.
public struct TileStates: Sendable {
    /// (code, RGB centroid) in priority order (ties go to the first).
    public var centroids: [(Character, [Double])]
    public var tolerance: Double = 22

    /// Screen-recording domain (measurements.md). The phone domain differs: resting (251,217,163).
    public static let recording = TileStates(centroids: [
        ("R", [247.4, 209.3, 150.5]),
        ("W", [252.0, 252.0, 252.0]),
        ("G", [128.0, 250.0, 128.0]),
        ("Y", [248.0, 248.0, 116.0]),
        ("X", [252.0, 140.0, 140.0]),
    ])

    public init(centroids: [(Character, [Double])], tolerance: Double = 22) {
        self.centroids = centroids
        self.tolerance = tolerance
    }

    /// 16 single-char codes (R/W/G/Y/X, or "?" for transitional colours).
    public func codes(_ row: SampleRow) -> [Character] {
        (0..<16).map { k in
            let rgb = ["r", "g", "b"].map { row["t\(k)_\($0)"] ?? .nan }
            var best: Character = "?", bestD = Double.infinity
            for (code, c) in centroids {
                let d = zip(rgb, c).map { abs($0 - $1) }.max() ?? .infinity
                if d < bestD { bestD = d; best = code }
            }
            return bestD <= tolerance ? best : "?"
        }
    }

    public static let selected: Set<Character> = ["W", "G", "Y", "X"]
}
