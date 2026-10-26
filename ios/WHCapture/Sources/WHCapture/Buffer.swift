import Foundation

/// On-disk upload queue (PLAN §2.7). One directory per record:
/// `<queue>/<created_ms>_<record id>/record.json` + its images. Writes are atomic (a temp directory
/// renamed into place); re-enqueueing the same record id replaces the old entry, so uploads stay
/// idempotent on board_id / record_id. Items that the server rejects as malformed go to `failed/`.
public final class RecordQueue {
    public struct Item: Equatable {
        public let id: String
        public let kind: String  // "board" | "all_words"
        public let directory: URL
        public var recordURL: URL { directory.appendingPathComponent("record.json") }

        public func images() -> [URL] {
            ((try? FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)) ?? [])
                .filter { $0.lastPathComponent != "record.json" }
                .sorted { $0.lastPathComponent < $1.lastPathComponent }
        }
    }

    public let directory: URL
    private let fm = FileManager.default
    private let clock: () -> Date

    public init(directory: URL, clock: @escaping () -> Date = Date.init) throws {
        self.directory = directory
        self.clock = clock
        try fm.createDirectory(at: directory, withIntermediateDirectories: true)
        try fm.createDirectory(at: directory.appendingPathComponent("failed"), withIntermediateDirectories: true)
    }

    static func identity(_ record: Record) -> (String, String) {
        switch record {
        case .board(let b): return (b.board_id, "board")
        case .allWords(let a): return (a.record_id, "all_words")
        }
    }

    @discardableResult
    public func enqueue(_ record: Record, images: [String: Data]) throws -> Item {
        let (id, kind) = Self.identity(record)
        let existing = pending()
        for old in existing where old.id == id { try? fm.removeItem(at: old.directory) }
        // strictly increasing keys keep queue order even within one millisecond / across restarts
        let newest = existing.compactMap { Int($0.directory.lastPathComponent.prefix(13)) }.max() ?? 0
        let ms = max(Int(clock().timeIntervalSince1970 * 1000), newest + 1)
        let name = String(format: "%013d_%@_%@", ms, kind, id)
        let tmp = directory.appendingPathComponent(".tmp-\(UUID().uuidString)")
        try fm.createDirectory(at: tmp, withIntermediateDirectories: true)
        try WHJSON.encoder().encode(record).write(to: tmp.appendingPathComponent("record.json"))
        for (file, data) in images {
            try data.write(to: tmp.appendingPathComponent((file as NSString).lastPathComponent))
        }
        let final = directory.appendingPathComponent(name)
        try fm.moveItem(at: tmp, to: final)
        return Item(id: id, kind: kind, directory: final)
    }

    /// Oldest first.
    public func pending() -> [Item] {
        let dirs = (try? fm.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)) ?? []
        return dirs.compactMap { url -> Item? in
            let parts = url.lastPathComponent.split(separator: "_", maxSplits: 1)
            guard parts.count == 2, Int(parts[0]) != nil else { return nil }
            let rest = String(parts[1])
            let kind = rest.hasPrefix("all_words_") ? "all_words" : "board"
            let id = String(rest.dropFirst(kind.count + 1))
            return Item(id: id, kind: kind, directory: url)
        }.sorted { $0.directory.lastPathComponent < $1.directory.lastPathComponent }
    }

    public func remove(_ item: Item) {
        try? fm.removeItem(at: item.directory)
    }

    public func markFailed(_ item: Item) {
        let dest = directory.appendingPathComponent("failed").appendingPathComponent(item.directory.lastPathComponent)
        try? fm.removeItem(at: dest)
        try? fm.moveItem(at: item.directory, to: dest)
    }
}
