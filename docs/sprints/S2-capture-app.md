# S2 — Capture app (Swift)

Goal: port the sampler and state machine to Swift and prove parity on the Mac, before any live play.
gate: `swift test --package-path ios/WHCapture` passes the parity tests AND the iOS build succeeds.

- [x] **S2.T1** WHCapture package + models
  - files: `ios/WHCapture/Package.swift` (macOS 14 + iOS 17), `Sources/WHCapture/Models.swift`, `Tests/WHCaptureTests/SchemaTests.swift`
  - do: Codable structs matching `fixtures/schema/v1.json`. The test decodes `fixtures/expected/*.json` and re-encodes it losslessly.
  - done: `swift test --package-path ios/WHCapture --filter SchemaTests`
  - deps: S1

- [ ] **S2.T2** State machine port `[parallel]`
  - files: `Sources/WHCapture/Machine.swift`, `Tests/WHCaptureTests/MachineParityTests.swift`
  - do: line-for-line port of `whcore/oracle/machine.py`. The test feeds `fixtures/samples/*.csv.gz` and compares against `fixtures/expected/*.json`, allowing ±1 frame on timestamps.
  - done: `swift test --package-path ios/WHCapture --filter MachineParityTests`
  - deps: T1

- [ ] **S2.T3** Sampler port `[parallel]`
  - files: `Sources/WHCapture/Sampler.swift`, `Tests/WHCaptureTests/SamplerTests.swift`
  - do: read patches straight from a locked `CVPixelBuffer` (BGRA and 420f), no copies. The test builds pixel buffers from `fixtures/crops/*.png` and matches the Python sampler within ±2 per channel.
  - done: `swift test --package-path ios/WHCapture --filter SamplerTests`
  - deps: T1

- [ ] **S2.T4** Crops + buffer + uploader `[parallel]`
  - files: `Sources/WHCapture/{Crops,Buffer,Uploader}.swift`, tests
  - do: grayscale JPEG crops (ImageIO); an on-disk queue in the extension container; multipart `POST /v1/boards` and `POST /v1/allwords` with `Authorization: Bearer $WH_TOKEN`; exponential backoff; idempotent on board_id. Test against a local `URLProtocol` stub.
  - done: `swift test --package-path ios/WHCapture --filter Uploader`
  - deps: T1

- [ ] **S2.T5** Wire the extension
  - files: `ios/App/BroadcastExtension/SampleHandler.swift`, `ios/App/project.yml`
  - do: one frame in flight (drop when busy); sampler → machine → crops → buffer → uploader. Keep diagnostics (fps, drops, mem) in each record. The server URL, token, and calibration are compiled in from the git-ignored `ios/App/Config.xcconfig` (+ a committed `Config.example.xcconfig`), so no App Group is needed. If S0 confirmed App Groups work, also read overrides from the shared suite.
  - done: iOS build succeeds (`xcodegen generate ... && xcodebuild ... -quiet build`)
  - deps: T2, T3, T4

- [ ] **S2.T6** Companion app
  - files: `ios/App/CompanionApp/*`
  - do: SwiftUI with a Start button (broadcast picker preset to the extension), the compiled server URL with a reachability check (`GET /v1/health`), a last-session status line (`GET /v1/sessions/latest`), and a signing-expiry countdown parsed from `embedded.mobileprovision` (red on the last day). Add a Focus reminder. Show editable settings only if App Groups work.
  - done: iOS build succeeds; unit test for the provision-date parser passes
  - deps: T1

- [ ] **S2.T7** Gate
  - done: `swift test --package-path ios/WHCapture` all green + iOS build OK; tick in PROGRESS
  - deps: T5, T6
