import Foundation

/// Reads the expiry of a free-team signing profile (PLAN §11). `embedded.mobileprovision` is a
/// CMS-signed blob whose payload is a plain XML plist; we locate the plist and read ExpirationDate.
public enum Provisioning {
    public struct Profile: Equatable, Sendable {
        public let name: String?
        public let teamID: String?
        public let expires: Date
    }

    public static func parse(_ data: Data) -> Profile? {
        guard let start = data.range(of: Data("<?xml".utf8)),
              let end = data.range(of: Data("</plist>".utf8), in: start.lowerBound..<data.endIndex)
        else { return nil }
        let xml = data[start.lowerBound..<end.upperBound]
        guard let plist = try? PropertyListSerialization.propertyList(from: xml, format: nil) as? [String: Any],
              let expires = plist["ExpirationDate"] as? Date else { return nil }
        return Profile(name: plist["Name"] as? String,
                       teamID: (plist["TeamIdentifier"] as? [String])?.first,
                       expires: expires)
    }

    /// Whole days left (rounded down); negative once expired.
    public static func daysLeft(_ p: Profile, now: Date = Date()) -> Int {
        Int((p.expires.timeIntervalSince(now) / 86_400).rounded(.down))
    }

    /// Red on the last day (and after).
    public static func isUrgent(_ p: Profile, now: Date = Date()) -> Bool {
        p.expires.timeIntervalSince(now) < 86_400
    }

    /// The running app's profile (nil in the simulator / when not provisioned).
    public static func current(bundle: Bundle = .main) -> Profile? {
        guard let url = bundle.url(forResource: "embedded", withExtension: "mobileprovision"),
              let data = try? Data(contentsOf: url) else { return nil }
        return parse(data)
    }
}
