// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "CP4AICore",
    platforms: [.macOS(.v15)],
    products: [
        .library(name: "CP4AICore", targets: ["CP4AICore"]),
    ],
    targets: [
        .target(name: "CP4AICore"),
        .testTarget(
            name: "CP4AICoreTests",
            dependencies: ["CP4AICore"],
            resources: [.copy("Fixtures")]
        ),
    ],
    swiftLanguageModes: [.v5]
)
