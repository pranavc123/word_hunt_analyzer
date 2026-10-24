import Foundation

// Event schema v1 — must match server/whcore/schema.py (fixtures/schema/v1.json).
// Property names are the JSON keys. IDs are lowercase UUID strings.

public let schemaVersion = "v1"

public enum ReleaseState: String, Codable, Sendable {
    case validNew = "valid_new"
    case alreadyFound = "already_found"
    case notAWord = "not_a_word"
}

public enum BoardStatus: String, Codable, Sendable {
    case played, skipped
}

public struct Attempt: Codable, Equatable, Sendable {
    public var seq: Int
    public var t_start_ms: Int
    public var t_end_ms: Int
    public var tiles_seen: [Int]
    public var release_state: ReleaseState
    public var banner_words_after: Int?
    public var confidence: Double

    public init(seq: Int, t_start_ms: Int, t_end_ms: Int, tiles_seen: [Int],
                release_state: ReleaseState, banner_words_after: Int? = nil, confidence: Double) {
        self.seq = seq
        self.t_start_ms = t_start_ms
        self.t_end_ms = t_end_ms
        self.tiles_seen = tiles_seen
        self.release_state = release_state
        self.banner_words_after = banner_words_after
        self.confidence = confidence
    }
}

public struct Diagnostics: Codable, Equatable, Sendable {
    public var fps_processed: Double
    public var frames_dropped: Int
    public var mem_peak_mb: Double

    public init(fps_processed: Double, frames_dropped: Int, mem_peak_mb: Double) {
        self.fps_processed = fps_processed
        self.frames_dropped = frames_dropped
        self.mem_peak_mb = mem_peak_mb
    }
}

public struct BoardRecord: Codable, Equatable, Sendable {
    public var schema = schemaVersion
    public var kind = "board"
    public var board_id: String
    public var session_id: String
    public var seq: Int
    public var device: String
    public var app_version: String
    public var calibration_version: String
    public var opened_at: Date
    public var view_ms: Int
    public var status: BoardStatus
    public var board_image: String
    public var end_banner_image: String?
    public var end_list_image: String?
    public var attempts: [Attempt]
    public var diagnostics: Diagnostics

    public init(board_id: String, session_id: String, seq: Int, device: String, app_version: String,
                calibration_version: String, opened_at: Date, view_ms: Int, status: BoardStatus,
                board_image: String, end_banner_image: String? = nil, end_list_image: String? = nil,
                attempts: [Attempt], diagnostics: Diagnostics) {
        self.board_id = board_id
        self.session_id = session_id
        self.seq = seq
        self.device = device
        self.app_version = app_version
        self.calibration_version = calibration_version
        self.opened_at = opened_at
        self.view_ms = view_ms
        self.status = status
        self.board_image = board_image
        self.end_banner_image = end_banner_image
        self.end_list_image = end_list_image
        self.attempts = attempts
        self.diagnostics = diagnostics
    }
}

public struct AllWordsRecord: Codable, Equatable, Sendable {
    public var schema = schemaVersion
    public var kind = "all_words"
    public var record_id: String
    public var session_id: String
    public var captured_at: Date
    public var frames: [String]
    public var shifts_px: [Int]
    public var gap_flags: [Bool]
    public var bounced_at_end: Bool

    public init(record_id: String, session_id: String, captured_at: Date, frames: [String],
                shifts_px: [Int], gap_flags: [Bool], bounced_at_end: Bool) {
        self.record_id = record_id
        self.session_id = session_id
        self.captured_at = captured_at
        self.frames = frames
        self.shifts_px = shifts_px
        self.gap_flags = gap_flags
        self.bounced_at_end = bounced_at_end
    }
}

/// A record discriminated on `kind`.
public enum Record: Codable, Equatable, Sendable {
    case board(BoardRecord)
    case allWords(AllWordsRecord)

    private enum Keys: String, CodingKey { case kind, schema }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Keys.self)
        let schema = try c.decode(String.self, forKey: .schema)
        guard schema == schemaVersion else {
            throw DecodingError.dataCorruptedError(forKey: .schema, in: c, debugDescription: "schema \(schema)")
        }
        switch try c.decode(String.self, forKey: .kind) {
        case "board": self = .board(try BoardRecord(from: decoder))
        case "all_words": self = .allWords(try AllWordsRecord(from: decoder))
        case let k: throw DecodingError.dataCorruptedError(forKey: .kind, in: c, debugDescription: "kind \(k)")
        }
    }

    public func encode(to encoder: Encoder) throws {
        switch self {
        case .board(let r): try r.encode(to: encoder)
        case .allWords(let r): try r.encode(to: encoder)
        }
    }
}

public func newRecordID() -> String { UUID().uuidString.lowercased() }

// MARK: JSON coding (ISO 8601 UTC, millisecond precision on encode; with or without fraction on decode)

public enum WHJSON {
    private static func formatter(fractional: Bool) -> ISO8601DateFormatter {
        let f = ISO8601DateFormatter()
        f.formatOptions = fractional ? [.withInternetDateTime, .withFractionalSeconds] : [.withInternetDateTime]
        return f
    }

    /// Dates on the wire have millisecond precision; use this for record timestamps.
    public static func roundedToMs(_ d: Date) -> Date {
        Date(timeIntervalSince1970: (d.timeIntervalSince1970 * 1000).rounded() / 1000)
    }

    public static func now() -> Date { roundedToMs(Date()) }

    /// Parses RFC 3339 with any number of fractional digits (Python emits microseconds),
    /// rounded to milliseconds.
    public static func parseDate(_ s: String) -> Date? {
        if let d = formatter(fractional: false).date(from: s) { return d }
        guard let dot = s.firstIndex(of: "."),
              let end = s[dot...].firstIndex(where: { $0 == "Z" || $0 == "+" || $0 == "-" }) else { return nil }
        let frac = s[s.index(after: dot)..<end]
        guard let base = formatter(fractional: false).date(from: String(s[..<dot]) + String(s[end...])),
              let value = Double("0." + frac) else { return nil }
        return roundedToMs(base.addingTimeInterval(value))
    }

    public static func formatDate(_ d: Date) -> String {
        formatter(fractional: true).string(from: d)
    }

    public static func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .custom { dec in
            let c = try dec.singleValueContainer()
            let s = try c.decode(String.self)
            guard let date = parseDate(s) else {
                throw DecodingError.dataCorruptedError(in: c, debugDescription: "bad date \(s)")
            }
            return date
        }
        return d
    }

    public static func encoder() -> JSONEncoder {
        let e = JSONEncoder()
        e.outputFormatting = [.sortedKeys]
        e.dateEncodingStrategy = .custom { date, enc in
            var c = enc.singleValueContainer()
            try c.encode(formatDate(date))
        }
        return e
    }
}
