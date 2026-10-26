import Foundation
import XCTest
@testable import WHCapture

final class ProvisioningTests: XCTestCase {
    /// A CMS-like blob: binary junk, the XML plist payload, more junk.
    func blob(expires: String) -> Data {
        let plist = """
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0"><dict>
        <key>Name</key><string>iOS Team Provisioning Profile: com.pranavc123.wordhunt</string>
        <key>TeamIdentifier</key><array><string>JB8BP4JKBT</string></array>
        <key>ExpirationDate</key><date>\(expires)</date>
        </dict></plist>
        """
        return Data([0x30, 0x80, 0x06, 0x09, 0x2A, 0x86, 0x00, 0xFF]) + Data(plist.utf8) + Data([0x00, 0xA0, 0x82])
    }

    func testParsesExpiryFromSignedBlob() throws {
        let p = try XCTUnwrap(Provisioning.parse(blob(expires: "2026-11-02T16:16:50Z")))
        XCTAssertEqual(p.teamID, "JB8BP4JKBT")
        XCTAssertEqual(p.expires, WHJSON.parseDate("2026-11-02T16:16:50Z"))
    }

    func testCountdownAndUrgency() throws {
        let p = try XCTUnwrap(Provisioning.parse(blob(expires: "2026-11-02T16:16:50Z")))
        let now = try XCTUnwrap(WHJSON.parseDate("2026-10-26T12:00:00Z"))
        XCTAssertEqual(Provisioning.daysLeft(p, now: now), 7)
        XCTAssertFalse(Provisioning.isUrgent(p, now: now))
        let lastDay = try XCTUnwrap(WHJSON.parseDate("2026-11-02T08:00:00Z"))
        XCTAssertEqual(Provisioning.daysLeft(p, now: lastDay), 0)
        XCTAssertTrue(Provisioning.isUrgent(p, now: lastDay))
        let after = try XCTUnwrap(WHJSON.parseDate("2026-11-03T08:00:00Z"))
        XCTAssertLessThan(Provisioning.daysLeft(p, now: after), 0)
    }

    func testRejectsGarbage() {
        XCTAssertNil(Provisioning.parse(Data("not a profile".utf8)))
    }

    func testParsesRealProfileIfBuilt() throws {
        // The device build embeds a real profile; skip when it has not been built on this Mac.
        let derived = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Developer/Xcode/DerivedData")
        guard let e = FileManager.default.enumerator(at: derived, includingPropertiesForKeys: nil) else {
            throw XCTSkip("no DerivedData")
        }
        for case let url as URL in e where url.lastPathComponent == "embedded.mobileprovision"
            && url.path.contains("CompanionApp.app") {
            let p = try XCTUnwrap(Provisioning.parse(Data(contentsOf: url)))
            XCTAssertNotNil(p.teamID)
            return
        }
        throw XCTSkip("no device build with an embedded profile")
    }
}
