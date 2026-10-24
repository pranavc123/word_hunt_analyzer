// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "WHCapture",
    platforms: [.macOS(.v14), .iOS(.v17)],
    products: [.library(name: "WHCapture", targets: ["WHCapture"])],
    targets: [
        .target(name: "WHCapture"),
        .testTarget(name: "WHCaptureTests", dependencies: ["WHCapture"]),
    ]
)
