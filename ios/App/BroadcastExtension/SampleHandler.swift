import CoreMedia
import CoreVideo
import Foundation
import ReplayKit
import WHCapture

/// Broadcast upload extension (PLAN §2): sampler → state machine → crops → on-disk queue →
/// uploader. One frame in flight; frames that arrive while busy are dropped. Diagnostics are
/// posted to `/diag` every 10 s and stored in each record.
final class SampleHandler: RPBroadcastSampleHandler, @unchecked Sendable {
    private let work = DispatchQueue(label: "wh.capture", qos: .userInitiated)
    private let lock = NSLock()
    private var busy = false
    private let config = Config()

    // pipeline (touched only on `work`)
    private var sampler: Sampler?
    private var machine: Machine?
    private var crops: CropStore?
    private var queue: RecordQueue?
    private var uploader: Uploader?
    private var debug: DebugRecorder?
    private var currentTMs = 0
    private var uploading = false
    private var frameIndex = 0
    private var firstPTS: CMTime?
    private var lastRow: SampleRow = [:]

    // stats (guarded by `lock`)
    private var stats = Stats()
    private var timer: DispatchSourceTimer?

    struct Stats {
        var received = 0, processed = 0, dropped = 0, windowProcessed = 0
        var windowStart = Date(), started = Date()
        var memPeakMB = 0.0
        var queued = 0, uploaded = 0
        var lastUpload = ""
    }

    override func broadcastStarted(withSetupInfo setupInfo: [String: NSObject]?) {
        lock.withLock { stats = Stats() }
        work.sync { setUpPipeline() }
        let t = DispatchSource.makeTimerSource(queue: DispatchQueue.global(qos: .utility))
        t.schedule(deadline: .now() + 10, repeating: 10)
        t.setEventHandler { [weak self] in self?.postDiag(event: "tick") }
        t.resume()
        timer = t
        postDiag(event: "start")
    }

    override func broadcastFinished() {
        timer?.cancel()
        timer = nil
        work.sync {
            machine?.finish()
            flushRecords()
        }
        // give the uploader a few seconds; anything left uploads next session
        let done = DispatchSemaphore(value: 0)
        Task {
            _ = await uploader?.drain(maxAttempts: 20, sleep: { _ in })
            done.signal()
        }
        _ = done.wait(timeout: .now() + 8)
        postDiag(event: "finish", wait: true)
    }

    private func setUpPipeline() {
        let bundle = Bundle(for: SampleHandler.self)
        guard let calURL = bundle.url(forResource: "iphone-1206x2622", withExtension: "json"),
              let digitsURL = bundle.url(forResource: "digits", withExtension: "json"),
              let cal = try? Calibration.load(calURL),
              let digits = try? DigitReader(json: digitsURL) else { return }
        sampler = Sampler(calibration: cal, digits: digits, roiStride: 2, includeProfile: false)
        debug = config.debug ? DebugRecorder() : nil
        let m = Machine(sessionID: newRecordID(), startedAt: Date(), device: Config.deviceModel(),
                        appVersion: config.appVersion, calibrationVersion: cal.version, states: .phone)
        let store = CropStore(calibration: cal)
        crops = store
        machine = m
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("queue", isDirectory: true)
        queue = try? RecordQueue(directory: dir)
        if let q = queue, let url = URL(string: config.serverURL) {
            uploader = Uploader(baseURL: url, token: config.token, queue: q)
            lock.withLock { stats.queued = q.pending().count }
            startUploading()  // leftovers from an earlier session
        }
        frameIndex = 0
        firstPTS = nil
    }

    override func processSampleBuffer(_ sampleBuffer: CMSampleBuffer, with type: RPSampleBufferType) {
        guard type == .video else { return }
        let take: Bool = lock.withLock {
            stats.received += 1
            if busy { stats.dropped += 1; return false }
            busy = true
            return true
        }
        guard take else { return }
        work.async { [self] in
            if let pb = CMSampleBufferGetImageBuffer(sampleBuffer) {
                process(pb, pts: CMSampleBufferGetPresentationTimeStamp(sampleBuffer))
            }
            lock.withLock {
                busy = false
                stats.processed += 1
                stats.windowProcessed += 1
            }
        }
    }

    private func process(_ pb: CVPixelBuffer, pts: CMTime) {
        guard let sampler, let machine, let crops else { return }
        if firstPTS == nil { firstPTS = pts }
        let tMs = Int((CMTimeGetSeconds(CMTimeSubtract(pts, firstPTS!)) * 1000).rounded())
        CVPixelBufferLockBaseAddress(pb, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pb, .readOnly) }
        guard let view = FrameView(pb) else { return }
        let i = frameIndex
        frameIndex += 1
        let row = sampler.sample(view, frame: i, tMs: tMs)
        lastRow = row
        currentTMs = tMs
        if let debug {
            debug.add(frame: i, tMs: tMs, view: view)
            machine.onLowConfidence = { [unowned self] frame, reason in
                debug.flag(frame: frame, tMs: self.currentTMs, reason: reason)
            }
        }
        machine.onCropFrame = { frame, rect in crops.capture(frame: frame, rect: rect, view: view) }
        machine.feed(row)
        let shift = row["list_shift"] ?? .nan
        crops.observe(frame: i, screen: machine.currentScreen, label: machine.lastLabel,
                      still: !shift.isNaN && abs(shift) <= 2, view: view)
        flushRecords()
    }

    /// Finished records → JPEG crops + live diagnostics → disk queue → uploader.
    private func flushRecords() {
        guard let machine, let crops, let queue else { return }
        let (records, requests) = machine.takeNew()
        guard !records.isEmpty else { return }
        let images = crops.jpegs(for: requests)
        var debugFrames = debug?.take() ?? [:]  // attached once, to the first board record
        let diag = lock.withLock { () -> Diagnostics in
            let elapsed = max(1, Date().timeIntervalSince(stats.started))
            return Diagnostics(fps_processed: (Double(stats.processed) / elapsed * 10).rounded() / 10,
                               frames_dropped: stats.dropped, mem_peak_mb: (stats.memPeakMB * 10).rounded() / 10)
        }
        for var rec in records {
            var refs: [String] = []
            switch rec {
            case .board(var b):
                b.diagnostics = diag
                refs = [b.board_image, b.end_banner_image, b.end_list_image].compactMap { $0 }
                rec = .board(b)
            case .allWords(let a):
                refs = a.frames
            }
            var mine = images.filter { refs.contains($0.key) }
            if case .board = rec, !debugFrames.isEmpty {
                mine.merge(debugFrames) { a, _ in a }
                debugFrames = [:]
            }
            if (try? queue.enqueue(rec, images: mine)) != nil {
                lock.withLock { stats.queued += 1 }
            }
        }
        if let last = requests.map(\.frame).max() { crops.prune(before: last - 600) }
        startUploading()
    }

    private func startUploading() {
        guard let uploader, !uploading else { return }
        uploading = true
        Task.detached(priority: .utility) { [weak self] in
            let out = await uploader.drain()
            self?.work.async {
                guard let self else { return }
                self.uploading = false
                self.lock.withLock {
                    self.stats.lastUpload = "\(out)"
                    self.stats.queued = self.queue?.pending().count ?? 0
                }
            }
        }
    }

    // MARK: diagnostics

    private func postDiag(event: String, wait: Bool = false) {
        let mem = Config.memoryMB()
        let row = work.sync { lastRow }
        let body: [String: Any] = lock.withLock {
            stats.memPeakMB = max(stats.memPeakMB, mem)
            let now = Date()
            let window = now.timeIntervalSince(stats.windowStart)
            let fps = window > 0 ? Double(stats.windowProcessed) / window : 0
            stats.windowProcessed = 0
            stats.windowStart = now
            var b: [String: Any] = [
                "event": event,
                "fps_processed": (fps * 10).rounded() / 10,
                "frames_received": stats.received,
                "frames_processed": stats.processed,
                "frames_dropped": stats.dropped,
                "mem_mb": (mem * 10).rounded() / 10,
                "mem_peak_mb": (stats.memPeakMB * 10).rounded() / 10,
                "uptime_s": Int(now.timeIntervalSince(stats.started)),
                "app_group_configured": !config.appGroup.isEmpty,
                "app_group_available": config.appGroupAvailable,
                "queued": stats.queued,
                "last_upload": stats.lastUpload,
            ]
            // latest sample (colour domain check for the phone thresholds)
            var sample: [String: Double] = [:]
            for (k, v) in row where !v.isNaN && !k.hasPrefix("p") { sample[k] = (v * 10).rounded() / 10 }
            b["sample"] = sample
            return b
        }
        guard let url = URL(string: config.serverURL + "/diag"),
              let data = try? JSONSerialization.data(withJSONObject: body) else { return }
        var req = URLRequest(url: url, timeoutInterval: 8)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if !config.token.isEmpty { req.setValue("Bearer \(config.token)", forHTTPHeaderField: "Authorization") }
        req.httpBody = data
        let done = DispatchSemaphore(value: 0)
        URLSession.shared.dataTask(with: req) { _, _, _ in done.signal() }.resume()
        if wait { _ = done.wait(timeout: .now() + 3) }
    }
}

struct Config {
    let serverURL: String
    let token: String
    let appGroup: String
    let appVersion: String
    let debug: Bool

    init(bundle: Bundle = Bundle(for: SampleHandler.self)) {
        serverURL = bundle.object(forInfoDictionaryKey: "WHServerURL") as? String ?? ""
        token = bundle.object(forInfoDictionaryKey: "WHToken") as? String ?? ""
        appGroup = bundle.object(forInfoDictionaryKey: "WHAppGroup") as? String ?? ""
        appVersion = bundle.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0"
        debug = (bundle.object(forInfoDictionaryKey: "WHDebug") as? String) == "1"
    }

    var appGroupAvailable: Bool {
        !appGroup.isEmpty
            && FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroup) != nil
    }

    static func deviceModel() -> String {
        var info = utsname()
        uname(&info)
        return withUnsafeBytes(of: &info.machine) { String(decoding: $0.prefix { $0 != 0 }, as: UTF8.self) }
    }

    static func memoryMB() -> Double {
        var info = task_vm_info_data_t()
        var count = mach_msg_type_number_t(MemoryLayout<task_vm_info_data_t>.size / MemoryLayout<natural_t>.size)
        let kr = withUnsafeMutablePointer(to: &info) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &count)
            }
        }
        return kr == KERN_SUCCESS ? Double(info.phys_footprint) / 1_048_576 : -1
    }
}
