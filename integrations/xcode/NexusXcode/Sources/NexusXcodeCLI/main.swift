import Foundation
import ArgumentParser
import NexusKit

@main
struct NexusXcodeCLI: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "nexus-xcode",
        abstract: "Nexus integration for Xcode - AI-powered development assistant",
        subcommands: [
            StoreContext.self,
            Search.self,
            AskAI.self,
            BuildError.self,
            Sync.self
        ]
    )
}

// MARK: - Store Context Command

struct StoreContext: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "store",
        abstract: "Store current file context in Nexus"
    )

    @Option(name: .shortAndLong, help: "File path")
    var file: String

    @Option(name: .shortAndLong, help: "Project name")
    var project: String

    @Option(name: .shortAndLong, help: "Programming language")
    var language: String = "swift"

    func run() async throws {
        let client = createClient()
        let content = try String(contentsOfFile: file, encoding: .utf8)

        let response = try await client.storeCodeContext(
            filePath: file,
            content: content,
            language: language,
            projectName: project
        )

        print("✓ Stored context: \(response.key)")
    }
}

// MARK: - Search Command

struct Search: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "search",
        abstract: "Search for relevant context"
    )

    @Argument(help: "Search query")
    var query: String

    @Option(name: .shortAndLong, help: "Project filter")
    var project: String?

    func run() async throws {
        let client = createClient()
        let results = try await client.searchCodeContext(query: query, project: project)

        print("Found \(results.total) results:\n")
        for result in results.results {
            print("[\(String(format: "%.2f", result.score))] \(result.memory.key)")
            if let tags = result.memory.tags as [String]? {
                print("    Tags: \(tags.joined(separator: ", "))")
            }
            print()
        }
    }
}

// MARK: - Ask AI Command

struct AskAI: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "ask",
        abstract: "Ask AI for help with code"
    )

    @Argument(help: "Your question")
    var question: String

    @Option(name: .shortAndLong, help: "File for context")
    var file: String?

    func run() async throws {
        let client = createClient()

        // Get relevant context first
        let context = try await client.searchMemory(query: question, limit: 3)

        // Find a code-assist agent
        let agents = try await client.discoverAgents(capability: "code-assist")

        if agents.isEmpty {
            print("No AI agents available for code assistance.")
            print("Register an agent with 'code-assist' capability.")
            return
        }

        var contextText = ""
        for result in context.results {
            contextText += "Context: \(result.memory.key)\n"
        }

        if let filePath = file {
            let fileContent = try String(contentsOfFile: filePath, encoding: .utf8)
            contextText += "\nCurrent file:\n\(fileContent.prefix(1500))"
        }

        let response = try await client.invoke(
            agentId: agents[0].id,
            capability: "code-assist",
            input: [
                "question": question,
                "context": contextText
            ]
        )

        print("Invocation ID: \(response.invocationId)")
        print("Status: \(response.status)")

        if let output = response.output {
            print("\nResponse:")
            for (key, value) in output {
                print("  \(key): \(value.value)")
            }
        }
    }
}

// MARK: - Build Error Command

struct BuildError: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "error",
        abstract: "Report a build error for AI analysis"
    )

    @Argument(help: "Error message")
    var error: String

    @Option(name: .shortAndLong, help: "File path")
    var file: String?

    @Option(name: .shortAndLong, help: "Line number")
    var line: Int?

    @Option(name: .shortAndLong, help: "Project name")
    var project: String = "unknown"

    func run() async throws {
        let client = createClient()

        // Store the error
        let stored = try await client.storeBuildError(
            error: error,
            filePath: file,
            line: line,
            projectName: project
        )
        print("✓ Error stored: \(stored.key)")

        // Get file context if available
        var context = ""
        if let filePath = file {
            if let content = try? String(contentsOfFile: filePath, encoding: .utf8) {
                context = content
            }
        }

        // Try to get AI help
        if let response = try await client.requestErrorHelp(error: error, context: context) {
            print("\n🤖 AI Analysis requested: \(response.invocationId)")
            print("Check back for results or poll the invocation status.")
        }
    }
}

// MARK: - Sync Command

struct Sync: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "sync",
        abstract: "Sync entire project to Nexus memory"
    )

    @Option(name: .shortAndLong, help: "Project directory")
    var directory: String

    @Option(name: .shortAndLong, help: "Project name")
    var project: String

    @Option(name: .shortAndLong, help: "File extensions to include")
    var extensions: [String] = ["swift", "m", "h", "mm"]

    func run() async throws {
        let client = createClient()
        let fileManager = FileManager.default
        let dirURL = URL(fileURLWithPath: directory)

        var count = 0

        if let enumerator = fileManager.enumerator(at: dirURL, includingPropertiesForKeys: nil) {
            while let fileURL = enumerator.nextObject() as? URL {
                let ext = fileURL.pathExtension
                guard extensions.contains(ext) else { continue }

                // Skip build directories
                let path = fileURL.path
                if path.contains("/Build/") || path.contains("/DerivedData/") || path.contains(".build/") {
                    continue
                }

                do {
                    let content = try String(contentsOf: fileURL, encoding: .utf8)
                    let relativePath = path.replacingOccurrences(of: directory, with: "")

                    _ = try await client.storeCodeContext(
                        filePath: relativePath,
                        content: content,
                        language: ext,
                        projectName: project
                    )
                    count += 1
                    print("✓ \(relativePath)")
                } catch {
                    print("✗ \(fileURL.lastPathComponent): \(error.localizedDescription)")
                }
            }
        }

        print("\n✓ Synced \(count) files to Nexus")
    }
}

// MARK: - Helpers

func createClient() -> NexusClient {
    let baseURL = ProcessInfo.processInfo.environment["NEXUS_URL"] ?? "http://localhost:8000"
    let apiKey = ProcessInfo.processInfo.environment["NEXUS_API_KEY"] ?? ""

    if apiKey.isEmpty {
        print("Warning: NEXUS_API_KEY not set")
    }

    return NexusClient(baseURL: baseURL, apiKey: apiKey)
}
