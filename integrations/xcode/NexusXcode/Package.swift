// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "NexusXcode",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "nexus-xcode", targets: ["NexusXcodeCLI"]),
        .library(name: "NexusKit", targets: ["NexusKit"])
    ],
    dependencies: [
        .package(url: "https://github.com/apple/swift-argument-parser", from: "1.2.0"),
    ],
    targets: [
        .target(
            name: "NexusKit",
            dependencies: []
        ),
        .executableTarget(
            name: "NexusXcodeCLI",
            dependencies: [
                "NexusKit",
                .product(name: "ArgumentParser", package: "swift-argument-parser")
            ]
        )
    ]
)
