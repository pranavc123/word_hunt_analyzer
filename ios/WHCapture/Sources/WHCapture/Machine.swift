import Foundation

/// Line-by-line port of server/whcore/oracle/machine.py (PLAN §2.2–2.6): a streaming state machine
/// from sample rows to records. Crops are emitted as requests (frame index + rect name).
public struct CropRequest: Equatable, Sendable {
    public let name: String
    public let frame: Int
    public let rect: String  // calibration key, "board" (tile area) or "list_band"
}

public enum MachineConfig {
    public static let confirmFrames = 3
    public static let mergeGapMs = 700
    public static let endWithinMs = 4000
    public static let settleMs = 800
    public static let firstCropMs = 200
    public static let afterFrames = 4
    public static let endCropBackMs = 200
    public static let allWordsMergeMs = 1500
    public static let bandPx = 2600 - 612
    public static let cropEveryPx = bandPx / 2
    public static let gapPx = bandPx - 300
}

private final class PendingAttempt {
    let first: Int
    var last: Int
    var tiles: [Int] = []
    var release: Character = "W"
    let wordsBefore: Double
    var wordsAfter: Double?

    init(first: Int, wordsBefore: Double) {
        self.first = first
        self.last = first
        self.wordsBefore = wordsBefore
    }
}

private final class BoardState {
    let seq: Int
    let first: Int
    var last: Int
    var attempts: [PendingAttempt] = []
    var openAttempt: PendingAttempt?
    var pending: PendingAttempt?  // released, waiting for its WORDS read
    var prevCodes: [Character]?
    var words: Double = 0
    var cropFrame: Int?
    var endFirst: Int?
    var endLast: Int?

    init(seq: Int, first: Int) {
        self.seq = seq
        self.first = first
        self.last = first
    }
}

private final class AllWordsState {
    let first: Int
    var last: Int
    var shifts: [Int] = []
    var offset = 0
    var gapSinceCrop = false
    var sinceCrop = 0
    var cropFrames: [Int] = []
    var cropOffsets: [Int] = []
    var cropGaps: [Bool] = []
    var base = 0
    var stills: [(Int, Int)] = []  // recent (frame, offset), at most 90

    init(first: Int) {
        self.first = first
        self.last = first
    }
}

public final class Machine {
    public let sessionID: String
    public let startedAt: Date
    public let device: String
    public let appVersion: String
    public let calibrationVersion: String
    public let states: TileStates

    private var screen: Screen = .other
    private var candidate: Screen = .other
    private var candidateN = 0
    private var candidateFirst = 0
    private var board: BoardState?
    private var closed: BoardState?
    private var aw: AllWordsState?
    private var seq = 0
    private var t: [Int] = []
    private var recent: [(Int, SampleRow, Screen)] = []

    public private(set) var records: [Record] = []
    public private(set) var crops: [CropRequest] = []
    /// Called when the machine decides to crop the CURRENT frame (frame index, rect name), so a
    /// live capture can grab it before the frame is gone. Requests for past frames are served from
    /// `CropStore`'s rings. Not used by the oracle/parity path.
    public var onCropFrame: ((Int, String) -> Void)?
    /// Called (frame index, reason) when a release resolves with low confidence: the release colour
    /// disagrees with the WORDS count, or WORDS could not be read. Used by debug capture.
    public var onLowConfidence: ((Int, String) -> Void)?
    /// Screen the machine is on, and the raw label of the last frame (for `CropStore.observe`).
    public var currentScreen: Screen { screen }
    public private(set) var lastLabel: Screen = .other

    public init(sessionID: String, startedAt: Date, device: String = "oracle",
                appVersion: String = "oracle", calibrationVersion: String = "iphone-1206x2622@1",
                states: TileStates = .recording) {
        self.sessionID = sessionID
        self.startedAt = startedAt
        self.device = device
        self.appVersion = appVersion
        self.calibrationVersion = calibrationVersion
        self.states = states
    }

    // MARK: screen confirmation

    private func confirm(_ label: Screen, _ i: Int) -> (Screen, Int)? {
        if label == candidate {
            candidateN += 1
        } else {
            candidate = label
            candidateN = 1
            candidateFirst = i
        }
        if candidate != screen && candidateN >= MachineConfig.confirmFrames {
            screen = candidate
            return (screen, candidateFirst)
        }
        return nil
    }

    // MARK: main entry

    public func feed(_ row: SampleRow) {
        let i = t.count
        t.append(Int(row["t_ms"] ?? 0))
        let label = Screens.classify(row)
        lastLabel = label
        if let change = confirm(label, i) {
            onScreenChange(change.0, change.1)
            for (j, r, lab) in recent where j >= change.1 {
                dispatch(j, r, lab)
            }
        }
        dispatch(i, row, label)
        recent.append((i, row, label))
        if recent.count > MachineConfig.confirmFrames { recent.removeFirst() }
        maybeFinalise(i)
    }

    private func dispatch(_ i: Int, _ row: SampleRow, _ label: Screen) {
        if screen == .board, board != nil {
            if label == .board { boardFrame(i, row) }
        } else if screen == .end, let c = closed, c.endFirst != nil {
            c.endLast = i
        } else if screen == .allWords, aw != nil {
            allWordsFrame(i, row)
        }
    }

    private func onScreenChange(_ newScreen: Screen, _ first: Int) {
        let t0 = t[first]
        if newScreen == .board {
            if let c = closed, c.endFirst == nil, t0 - t[c.last] < MachineConfig.mergeGapMs {
                board = c  // brief interruption: same board
                closed = nil
            } else {
                finaliseClosed()
                board = BoardState(seq: seq, first: first)
                seq += 1
            }
            return
        }
        if let b = board {  // leaving a board
            closeAttempt(b)
            closed = b
            board = nil
        }
        if newScreen == .end, let c = closed, c.endFirst == nil, t0 - t[c.last] <= MachineConfig.endWithinMs {
            c.endFirst = first
            c.endLast = first
        }
        if newScreen == .allWords {
            if let a = aw, t0 - t[a.last] < MachineConfig.allWordsMergeMs {
                // same capture
            } else {
                finaliseAllWords()
                aw = AllWordsState(first: first)
            }
        }
    }

    // MARK: boards

    private func boardFrame(_ i: Int, _ row: SampleRow) {
        guard let b = board else { return }
        b.last = i
        if b.cropFrame == nil && t[i] - t[b.first] >= MachineConfig.settleMs {
            b.cropFrame = i
            if i == t.count - 1 { onCropFrame?(i, "board") }
        }
        let words = row["words"] ?? .nan
        let codes = states.codes(row)
        let active = codes.contains { TileStates.selected.contains($0) }
        if let p = b.pending, i - p.last >= MachineConfig.afterFrames || active {
            let readAt = active ? b.words : words
            p.wordsAfter = readAt.isNaN ? nil : readAt
            b.attempts.append(p)
            b.pending = nil
            if let hook = onLowConfidence {
                if let after = p.wordsAfter {
                    if (after == p.wordsBefore + 1) != (p.release == "G") { hook(i, "colour≠words") }
                } else {
                    hook(i, "words unreadable")
                }
            }
        }
        if !words.isNaN && !active { b.words = words }
        var a = b.openAttempt
        if active {
            if a == nil || i - a!.last > 2 {
                if a != nil { closeAttempt(b) }
                a = PendingAttempt(first: i, wordsBefore: b.words)
                b.openAttempt = a
            }
            let attempt = a!
            attempt.last = i
            for (tile, c) in codes.enumerated() where !attempt.tiles.contains(tile) {
                let fresh = c == "?" && b.prevCodes != nil && b.prevCodes![tile] == "R"
                if TileStates.selected.contains(c) || (fresh && i > attempt.first) {
                    attempt.tiles.append(tile)
                }
            }
            let rel = codes.filter { TileStates.selected.contains($0) }
            attempt.release = Machine.majority(rel)
        } else if let open = a, i - open.last > 2 {
            closeAttempt(b)
        }
        b.prevCodes = codes
    }

    /// Python `max("GYWX", key=rel.count)`: the first of G, Y, W, X with the highest count.
    static func majority(_ rel: [Character]) -> Character {
        if rel.isEmpty { return "W" }
        var best: Character = "G", bestN = -1
        for c in ["G", "Y", "W", "X"] as [Character] {
            let n = rel.filter { $0 == c }.count
            if n > bestN { bestN = n; best = c }
        }
        return best
    }

    private func closeAttempt(_ b: BoardState) {
        guard let open = b.openAttempt else { return }
        if let p = b.pending {
            p.wordsAfter = b.words
            b.attempts.append(p)
        }
        b.pending = open
        b.openAttempt = nil
    }

    // MARK: all words

    private func allWordsFrame(_ i: Int, _ row: SampleRow) {
        guard let a = aw else { return }
        a.last = i
        let raw = row["list_shift"] ?? .nan
        if raw.isNaN { return }
        let s = Int(raw)
        a.shifts.append(s)
        a.offset += s
        a.gapSinceCrop = a.gapSinceCrop || abs(s) > MachineConfig.gapPx
        a.sinceCrop += abs(s)
        let still = abs(s) <= 2
        if still {
            a.stills.append((i, a.offset))
            if a.stills.count > 90 { a.stills.removeFirst() }
        }
        if a.cropFrames.isEmpty {
            if still && t[i] - t[a.first] >= MachineConfig.firstCropMs {
                a.base = a.offset
                Machine.cropAllWords(a, i, a.offset)
                if i == t.count - 1 { onCropFrame?(i, "list_band") }
            }
            return
        }
        if (a.sinceCrop >= MachineConfig.cropEveryPx && still) || a.sinceCrop >= MachineConfig.gapPx - 200 {
            Machine.cropAllWords(a, i, a.offset)
            if i == t.count - 1 { onCropFrame?(i, "list_band") }
        }
    }

    private static func cropAllWords(_ a: AllWordsState, _ i: Int, _ offset: Int) {
        let hadCrops = !a.cropFrames.isEmpty
        a.cropFrames.append(i)
        a.cropOffsets.append(offset - a.base)
        a.cropGaps.append(hadCrops ? a.gapSinceCrop : false)
        a.sinceCrop = 0
        a.gapSinceCrop = false
    }

    // MARK: finalisation

    private func maybeFinalise(_ i: Int) {
        if let c = closed, screen != .end, screen != .board {
            let waited = t[i] - t[c.endFirst != nil ? c.endLast! : c.last]
            if c.endFirst != nil || waited > MachineConfig.endWithinMs {
                finaliseClosed()
            }
        }
        if let a = aw, screen != .allWords, t[i] - t[a.last] >= MachineConfig.allWordsMergeMs {
            finaliseAllWords()
        }
    }

    private func date(_ ms: Int) -> Date {
        startedAt.addingTimeInterval(Double(ms) / 1000)
    }

    private func finaliseClosed() {
        guard let b = closed else { return }
        closed = nil
        if let p = b.pending {
            p.wordsAfter = b.words
            b.attempts.append(p)
            b.pending = nil
        }
        let played = b.endFirst != nil
        let bid = uuid5(namespace: sessionID, name: "board-\(b.seq)")
        crops.append(CropRequest(name: "board_\(b.seq).jpg", frame: b.cropFrame ?? b.last, rect: "board"))
        var endBanner: String?, endList: String?
        if played, let ef = b.endFirst, let el = b.endLast {
            var fe = el  // the end screen slides away: step back endCropBackMs (frame-rate independent)
            while fe > ef && t[el] - t[fe] < MachineConfig.endCropBackMs { fe -= 1 }
            endBanner = "end_banner_\(b.seq).jpg"
            endList = "end_list_\(b.seq).jpg"
            crops.append(CropRequest(name: endBanner!, frame: fe, rect: "roi_end_banner"))
            crops.append(CropRequest(name: endList!, frame: fe, rect: "roi_end_list"))
        }
        let attempts: [Attempt] = b.attempts.enumerated().map { k, a in
            let accepted = a.wordsAfter != nil && a.wordsAfter! == a.wordsBefore + 1
            let state: ReleaseState = accepted ? .validNew : (a.release == "Y" ? .alreadyFound : .notAWord)
            let colourAgrees = accepted == (a.release == "G")
            return Attempt(seq: k, t_start_ms: t[a.first], t_end_ms: t[a.last], tiles_seen: a.tiles,
                           release_state: state, banner_words_after: a.wordsAfter.map { Int($0) },
                           confidence: colourAgrees ? 1.0 : 0.5)
        }
        let n = b.last - b.first + 1
        let dur = max(1, t[b.last] - t[b.first])
        let fps = (1000 * Double(n - 1) / Double(dur) * 10).rounded(.toNearestOrEven) / 10
        records.append(.board(BoardRecord(
            board_id: bid, session_id: sessionID, seq: b.seq, device: device, app_version: appVersion,
            calibration_version: calibrationVersion, opened_at: date(t[b.first]),
            view_ms: t[b.last] - t[b.first], status: played ? .played : .skipped,
            board_image: "board_\(b.seq).jpg", end_banner_image: endBanner, end_list_image: endList,
            attempts: attempts,
            diagnostics: Diagnostics(fps_processed: fps, frames_dropped: 0, mem_peak_mb: 0))))
    }

    private func finaliseAllWords() {
        guard let a = aw else { return }
        aw = nil
        let settled = a.stills.filter { t[a.last] - t[$0.0] >= MachineConfig.firstCropMs }
        if let last = settled.last, a.cropFrames.isEmpty || a.cropFrames.last! < last.0 {
            Machine.cropAllWords(a, last.0, last.1)
        }
        if a.cropFrames.isEmpty { return }
        let k = records.filter { if case .allWords = $0 { return true } else { return false } }.count
        var names: [String] = []
        for (j, f) in a.cropFrames.enumerated() {
            names.append("allwords_\(k)_\(j).jpg")
            crops.append(CropRequest(name: names.last!, frame: f, rect: "list_band"))
        }
        let moved = a.shifts.suffix(60).filter { $0 != 0 }
        let bounced = moved.count >= 2 && moved.contains { $0 > 0 } && moved.contains { $0 < 0 }
        records.append(.allWords(AllWordsRecord(
            record_id: uuid5(namespace: sessionID, name: "allwords-\(k)"), session_id: sessionID,
            captured_at: date(t[a.first]), frames: names, shifts_px: a.cropOffsets,
            gap_flags: a.cropGaps, bounced_at_end: bounced)))
    }

    public func finish() {
        if let b = board {
            closeAttempt(b)
            closed = b
            board = nil
        }
        finaliseClosed()
        finaliseAllWords()
        // stable sort by time (Python's sort is stable); records already handed out stay put
        let tail = records[takenRecords...].enumerated().sorted { l, r in
            let tl = Machine.time(l.element), tr = Machine.time(r.element)
            return tl != tr ? tl < tr : l.offset < r.offset
        }.map(\.element)
        records.replaceSubrange(takenRecords..., with: tail)
    }

    private var takenRecords = 0
    private var takenCrops = 0

    /// Records and crop requests produced since the last call (live capture drains these).
    public func takeNew() -> (records: [Record], crops: [CropRequest]) {
        defer { takenRecords = records.count; takenCrops = crops.count }
        return (Array(records[takenRecords...]), Array(crops[takenCrops...]))
    }

    static func time(_ r: Record) -> Date {
        switch r {
        case .board(let b): return b.opened_at
        case .allWords(let a): return a.captured_at
        }
    }

    /// Batch wrapper.
    public static func run(_ rows: [SampleRow], sessionID: String, startedAt: Date,
                           states: TileStates = .recording) -> ([Record], [CropRequest]) {
        let m = Machine(sessionID: sessionID, startedAt: startedAt, states: states)
        for r in rows { m.feed(r) }
        m.finish()
        return (m.records, m.crops)
    }
}
