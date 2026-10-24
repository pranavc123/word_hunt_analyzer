import ReplayKit
import SwiftUI

@main
struct CompanionApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }
    }
}

enum AppConfig {
    static var serverURL: String { Bundle.main.object(forInfoDictionaryKey: "WHServerURL") as? String ?? "" }
    static var extensionBundleID: String { (Bundle.main.bundleIdentifier ?? "") + ".broadcast" }
}

struct ContentView: View {
    @State private var health = "checking…"
    @State private var healthy = false

    var body: some View {
        VStack(spacing: 24) {
            Text("Word Hunt Capture").font(.title2.bold())
            VStack(spacing: 6) {
                Text(AppConfig.serverURL).font(.footnote.monospaced()).foregroundStyle(.secondary)
                Label(health, systemImage: healthy ? "checkmark.circle.fill" : "xmark.octagon")
                    .foregroundStyle(healthy ? .green : .red)
                Button("Re-check") { Task { await checkHealth() } }.font(.footnote)
            }
            BroadcastPicker(extensionID: AppConfig.extensionBundleID)
                .frame(width: 80, height: 80)
            Text("Tap to start capture, then turn on the Word Hunt Focus.")
                .font(.footnote).foregroundStyle(.secondary).multilineTextAlignment(.center)
        }
        .padding()
        .preferredColorScheme(.dark)
        .task { await checkHealth() }
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
}

struct BroadcastPicker: UIViewRepresentable {
    let extensionID: String

    func makeUIView(context: Context) -> RPSystemBroadcastPickerView {
        let picker = RPSystemBroadcastPickerView(frame: CGRect(x: 0, y: 0, width: 80, height: 80))
        picker.preferredExtension = extensionID
        picker.showsMicrophoneButton = false
        return picker
    }

    func updateUIView(_ view: RPSystemBroadcastPickerView, context: Context) {}
}
