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
    private let picker = PickerHandle()

    var body: some View {
        VStack(spacing: 24) {
            Text("Word Hunt Capture").font(.title2.bold())
            VStack(spacing: 6) {
                Text(AppConfig.serverURL).font(.footnote.monospaced()).foregroundStyle(.secondary)
                Label(health, systemImage: healthy ? "checkmark.circle.fill" : "xmark.octagon")
                    .foregroundStyle(healthy ? .green : .red)
                Button("Re-check") { Task { await checkHealth() } }.font(.footnote)
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
            Text("Then choose Start Broadcast and turn on the Word Hunt Focus.")
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
