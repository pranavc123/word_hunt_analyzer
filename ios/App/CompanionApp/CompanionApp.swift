import ReplayKit
import SwiftUI
import WHCapture

@main
struct CompanionApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }
    }
}

enum AppConfig {
    static var serverURL: String { Bundle.main.object(forInfoDictionaryKey: "WHServerURL") as? String ?? "" }
    static var token: String { Bundle.main.object(forInfoDictionaryKey: "WHToken") as? String ?? "" }
    static var extensionBundleID: String { (Bundle.main.bundleIdentifier ?? "") + ".broadcast" }
}

struct ContentView: View {
    @State private var health = "checking…"
    @State private var healthy = false
    @State private var lastSession = "—"
    private let profile = Provisioning.current()
    private let picker = PickerHandle()

    var body: some View {
        VStack(spacing: 22) {
            Text("Word Hunt Capture").font(.title2.bold())

            VStack(spacing: 6) {
                Text(AppConfig.serverURL).font(.footnote.monospaced()).foregroundStyle(.secondary)
                Label(health, systemImage: healthy ? "checkmark.circle.fill" : "xmark.octagon")
                    .foregroundStyle(healthy ? .green : .red)
                Text(lastSession).font(.footnote).foregroundStyle(.secondary)
                Button("Re-check") { Task { await refresh() } }.font(.footnote)
            }

            // The system picker's own icon is dark-on-dark here, so a labelled button opens it.
            Button {
                picker.open()
            } label: {
                Label("Start / stop capture", systemImage: "record.circle")
                    .font(.headline)
                    .padding(.horizontal, 24)
                    .padding(.vertical, 14)
                    .background(Color.red.opacity(0.85), in: Capsule())
                    .foregroundStyle(.white)
            }
            BroadcastPicker(extensionID: AppConfig.extensionBundleID, handle: picker)
                .frame(width: 1, height: 1)
                .opacity(0.01)

            VStack(alignment: .leading, spacing: 6) {
                Label("Tailscale connected on this phone", systemImage: "network")
                Label("Word Hunt Focus on before you play", systemImage: "moon.fill")
                Label("Then choose Start Broadcast", systemImage: "dot.radiowaves.left.and.right")
            }
            .font(.footnote)
            .foregroundStyle(.secondary)

            signing
        }
        .padding()
        .preferredColorScheme(.dark)
        .task { await refresh() }
    }

    @ViewBuilder private var signing: some View {
        if let p = profile {
            let days = Provisioning.daysLeft(p)
            let urgent = Provisioning.isUrgent(p)
            Label(days < 0 ? "Signing expired — reinstall from Xcode"
                  : urgent ? "Signing expires today — reinstall from Xcode"
                  : "Signing: \(days) day\(days == 1 ? "" : "s") left",
                  systemImage: urgent ? "exclamationmark.triangle.fill" : "signature")
                .font(.footnote.bold())
                .foregroundStyle(urgent ? .red : .secondary)
        } else {
            Label("Signing expiry unknown (no embedded profile)", systemImage: "signature")
                .font(.footnote).foregroundStyle(.secondary)
        }
    }

    func refresh() async {
        await checkHealth()
        await checkLastSession()
    }

    func checkHealth() async {
        guard let url = URL(string: AppConfig.serverURL + "/v1/health") else {
            health = "bad server URL"; healthy = false; return
        }
        do {
            let (_, resp) = try await URLSession.shared.data(from: url)
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            healthy = code == 200
            health = healthy ? "server reachable" : "HTTP \(code)"
        } catch {
            healthy = false
            health = error.localizedDescription
        }
    }

    /// `GET /v1/sessions/latest` (S3); shows "not available yet" until the server has it.
    func checkLastSession() async {
        guard let url = URL(string: AppConfig.serverURL + "/v1/sessions/latest") else { return }
        var req = URLRequest(url: url, timeoutInterval: 8)
        if !AppConfig.token.isEmpty { req.setValue("Bearer \(AppConfig.token)", forHTTPHeaderField: "Authorization") }
        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            lastSession = "Last session: not available yet"
            return
        }
        let boards = obj["board_count"] as? Int ?? 0
        let verified = obj["verified_count"] as? Int
        let started = (obj["started_at"] as? String).flatMap(WHJSON.parseDate)
        let when = started.map { $0.formatted(date: .abbreviated, time: .shortened) } ?? "?"
        lastSession = "Last session \(when): \(boards) boards" + (verified.map { ", \($0) verified" } ?? "")
    }
}

/// Lets a SwiftUI button trigger the hidden system broadcast picker.
final class PickerHandle {
    weak var view: RPSystemBroadcastPickerView?

    func open() {
        view?.subviews.compactMap { $0 as? UIButton }.first?.sendActions(for: .touchUpInside)
    }
}

struct BroadcastPicker: UIViewRepresentable {
    let extensionID: String
    let handle: PickerHandle

    func makeUIView(context: Context) -> RPSystemBroadcastPickerView {
        let picker = RPSystemBroadcastPickerView(frame: CGRect(x: 0, y: 0, width: 44, height: 44))
        picker.preferredExtension = extensionID
        picker.showsMicrophoneButton = false
        handle.view = picker
        return picker
    }

    func updateUIView(_ view: RPSystemBroadcastPickerView, context: Context) {}
}
