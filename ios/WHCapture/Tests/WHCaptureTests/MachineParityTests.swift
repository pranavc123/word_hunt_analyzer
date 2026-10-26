import Foundation
import XCTest
@testable import WHCapture

/// S2.T2: the Swift machine on fixtures/samples/*.csv.gz must reproduce the Python machine's
/// output in fixtures/expected/*.json (records + crop requests).
final class MachineParityTests: XCTestCase {
    static let root = SchemaTests.root

    static func gunzip(_ url: URL) throws -> String {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/gunzip")
        p.arguments = ["-c", url.path]
        let out = Pipe()
        p.standardOutput = out
        try p.run()
        let data = out.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        return String(decoding: data, as: UTF8.self)
    }

    static func loadRows(_ url: URL) throws -> [SampleRow] {
        let lines = try gunzip(url).split(whereSeparator: \.isNewline)  // "\r\n" is one Character
        let header = lines[0].split(separator: ",").map(String.init)
        return lines.dropFirst().map { line in
            var row = SampleRow(minimumCapacity: header.count)
            for (k, v) in zip(header, line.split(separator: ",", omittingEmptySubsequences: false)) {
                row[k] = Double(v) ?? .nan
            }
            return row
        }
    }

    func fixtures() throws -> [String] {
        let dir = Self.root.appendingPathComponent("fixtures/samples")
        let names = try FileManager.default.contentsOfDirectory(atPath: dir.path)
            .filter { $0.hasSuffix(".csv.gz") }
            .map { String($0.dropLast(".csv.gz".count)) }
            .sorted()
        XCTAssertGreaterThanOrEqual(names.count, 6)
        return names
    }

    func normalised(_ v: Any) -> Any {
        SchemaTests().normalised(v)
    }

    func testMachineMatchesPythonOnFixtures() throws {
        for name in try fixtures() {
            let rows = try Self.loadRows(Self.root.appendingPathComponent("fixtures/samples/\(name).csv.gz"))
            let expURL = Self.root.appendingPathComponent("fixtures/expected/\(name).json")
            let expected = try JSONSerialization.jsonObject(with: Data(contentsOf: expURL)) as! [String: Any]
            let source = expected["source"] as! [String: Any]
            let started = try XCTUnwrap(WHJSON.parseDate(source["started_at"] as! String))
            let (records, crops) = Machine.run(rows, sessionID: source["session_id"] as! String, startedAt: started)

            let got = try records.map { try JSONSerialization.jsonObject(with: WHJSON.encoder().encode($0)) }
            XCTAssertEqual(normalised(got) as! NSArray, normalised(expected["records"]!) as! NSArray,
                           "records differ: \(name)")
            let gotCrops = crops.map { ["name": $0.name, "frame": $0.frame, "rect": $0.rect] as [String: Any] }
            if let dir = ProcessInfo.processInfo.environment["WH_PARITY_DUMP"] {  // debugging aid
                let dump: [String: Any] = ["records": got, "crops": gotCrops]
                try JSONSerialization.data(withJSONObject: dump, options: [.sortedKeys])
                    .write(to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).json"))
            }
            XCTAssertEqual(gotCrops as NSArray, expected["crops"] as! NSArray, "crops differ: \(name)")
        }
    }

    func testMajorityMatchesPythonTieBreak() {
        XCTAssertEqual(Machine.majority([]), "W")
        XCTAssertEqual(Machine.majority(["W", "G"]), "G")  // tie → first of G, Y, W, X
        XCTAssertEqual(Machine.majority(["Y", "W", "W"]), "W")
    }

    func testUUID5MatchesPython() {
        // python: uuid.uuid5(uuid.UUID("0b7d9e10-2c3a-4f5b-8e6d-7a8b9c0d1e2f"), "board-0")
        XCTAssertEqual(uuid5(namespace: "0b7d9e10-2c3a-4f5b-8e6d-7a8b9c0d1e2f", name: "board-0"),
                       PythonValues.boardZeroID)
    }
}

enum PythonValues {
    static let boardZeroID = "46ec7ec4-5112-5686-bfca-1fda2248e6e1"
}
