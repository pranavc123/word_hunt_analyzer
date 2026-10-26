import Foundation
import XCTest
@testable import WHCapture

final class SchemaTests: XCTestCase {
    static let root = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()

    /// Every record fixture as (label, JSON data): the schema examples, plus each entry of
    /// `records` in the state-machine outputs `fixtures/expected/*.json` (labels.json excluded).
    func recordBlobs() throws -> [(String, Data)] {
        var blobs: [(String, Data)] = []
        let fm = FileManager.default
        let schemaDir = Self.root.appendingPathComponent("fixtures/schema")
        for url in try fm.contentsOfDirectory(at: schemaDir, includingPropertiesForKeys: nil)
        where url.pathExtension == "json" && url.lastPathComponent != "v1.json" {
            blobs.append((url.lastPathComponent, try Data(contentsOf: url)))
        }
        let expectedDir = Self.root.appendingPathComponent("fixtures/expected")
        if let items = try? fm.contentsOfDirectory(at: expectedDir, includingPropertiesForKeys: nil) {
            for url in items where url.pathExtension == "json" && url.lastPathComponent != "labels.json" {
                let obj = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: Any]
                for (k, rec) in (obj["records"] as? [Any] ?? []).enumerated() {
                    blobs.append(("\(url.lastPathComponent)#\(k)", try JSONSerialization.data(withJSONObject: rec)))
                }
            }
        }
        XCTAssertGreaterThanOrEqual(blobs.count, 2, "no record fixtures found")
        return blobs.sorted { $0.0 < $1.0 }
    }

    /// JSON value with dates compared as instants (Python writes µs, Swift writes ms).
    func normalised(_ v: Any) -> Any {
        if let d = v as? [String: Any] { return d.mapValues(normalised) }
        if let a = v as? [Any] { return a.map(normalised) }
        if let s = v as? String, s.count >= 20, let date = WHJSON.parseDate(s) {
            return (date.timeIntervalSince1970 * 1000).rounded()
        }
        return v
    }

    func testRoundTripFixtures() throws {
        for (name, data) in try recordBlobs() {
            let rec = try WHJSON.decoder().decode(Record.self, from: data)
            let out = try WHJSON.encoder().encode(rec)
            XCTAssertEqual(try WHJSON.decoder().decode(Record.self, from: out), rec, name)
            let a = normalised(try JSONSerialization.jsonObject(with: data)) as! NSDictionary
            let b = normalised(try JSONSerialization.jsonObject(with: out)) as! NSDictionary
            XCTAssertEqual(a, b, "lossy round trip: \(name)")
        }
    }

    func testKindsDecode() throws {
        let kinds = try recordBlobs().map { _, data -> String in
            switch try WHJSON.decoder().decode(Record.self, from: data) {
            case .board: return "board"
            case .allWords: return "all_words"
            }
        }
        XCTAssertEqual(Set(kinds), ["board", "all_words"])
    }

    func testRejectsWrongSchemaAndKind() throws {
        let url = Self.root.appendingPathComponent("fixtures/schema/board_example.json")
        var obj = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: Any]
        for (k, v) in [("schema", "v2"), ("kind", "nope"), ("status", "won")] {
            var bad = obj
            bad[k] = v
            let data = try JSONSerialization.data(withJSONObject: bad)
            XCTAssertThrowsError(try WHJSON.decoder().decode(Record.self, from: data), k)
        }
        obj["opened_at"] = "2026-10-24T20:15:03Z"
        XCTAssertNoThrow(try WHJSON.decoder().decode(Record.self, from: JSONSerialization.data(withJSONObject: obj)))
    }

    /// Every Swift model's keys equal the exported JSON Schema's properties.
    func testKeysMatchJSONSchema() throws {
        let schemaURL = Self.root.appendingPathComponent("fixtures/schema/v1.json")
        let schema = try JSONSerialization.jsonObject(with: Data(contentsOf: schemaURL)) as! [String: Any]
        let defs = schema["$defs"] as! [String: [String: Any]]
        let attempt = Attempt(seq: 0, t_start_ms: 1, t_end_ms: 2, tiles_seen: [0, 1, 2],
                              release_state: .validNew, banner_words_after: 1, confidence: 1)
        let diag = Diagnostics(fps_processed: 30, frames_dropped: 0, mem_peak_mb: 20)
        let board = BoardRecord(board_id: newRecordID(), session_id: newRecordID(), seq: 0, device: "d",
                                app_version: "0", calibration_version: "c", opened_at: Date(timeIntervalSince1970: 1_793_000_000.123), view_ms: 1,
                                status: .played, board_image: "b", end_banner_image: "e",
                                end_list_image: "l", attempts: [attempt], diagnostics: diag)
        let all = AllWordsRecord(record_id: newRecordID(), session_id: newRecordID(), captured_at: Date(timeIntervalSince1970: 1_793_000_100),
                                 frames: ["f"], shifts_px: [0], gap_flags: [false], bounced_at_end: true)
        let samples: [(String, Data)] = [
            ("BoardRecord", try WHJSON.encoder().encode(board)),
            ("AllWordsRecord", try WHJSON.encoder().encode(all)),
            ("Attempt", try WHJSON.encoder().encode(attempt)),
            ("Diagnostics", try WHJSON.encoder().encode(diag)),
        ]
        for (name, data) in samples {
            let keys = Set((try JSONSerialization.jsonObject(with: data) as! [String: Any]).keys)
            let def = try XCTUnwrap(defs[name], name)
            XCTAssertEqual(keys, Set((def["properties"] as! [String: Any]).keys), name)
            XCTAssertTrue(Set(def["required"] as! [String]).isSubset(of: keys), name)
        }
        // the Python side must accept what Swift encodes: round-trip via Record
        XCTAssertEqual(try WHJSON.decoder().decode(Record.self, from: samples[0].1), .board(board))
    }
}
