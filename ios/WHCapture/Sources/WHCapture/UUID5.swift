import CryptoKit
import Foundation

/// RFC 4122 name-based UUID (version 5, SHA-1), lowercase — matches Python's uuid.uuid5.
public func uuid5(namespace: String, name: String) -> String {
    guard let ns = UUID(uuidString: namespace) else { return newRecordID() }
    var bytes = withUnsafeBytes(of: ns.uuid) { Array($0) }
    bytes.append(contentsOf: Array(name.utf8))
    var h = Array(Insecure.SHA1.hash(data: bytes).prefix(16))
    h[6] = (h[6] & 0x0F) | 0x50
    h[8] = (h[8] & 0x3F) | 0x80
    let u = UUID(uuid: (h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7],
                        h[8], h[9], h[10], h[11], h[12], h[13], h[14], h[15]))
    return u.uuidString.lowercased()
}
