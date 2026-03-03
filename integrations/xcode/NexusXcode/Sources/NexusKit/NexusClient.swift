import Foundation

/// Nexus API client for Swift/Xcode integration
public class NexusClient {
    private let baseURL: URL
    private let apiKey: String
    private let session: URLSession

    public init(baseURL: String = "http://localhost:8000", apiKey: String) {
        self.baseURL = URL(string: baseURL)!
        self.apiKey = apiKey
        self.session = URLSession.shared
    }

    // MARK: - Memory Operations

    /// Store a memory in Nexus
    public func storeMemory(
        key: String,
        value: [String: Any],
        textContent: String,
        tags: [String] = [],
        scope: String = "agent"
    ) async throws -> MemoryResponse {
        let body: [String: Any] = [
            "key": key,
            "value": value,
            "text_content": textContent,
            "tags": tags,
            "scope": scope
        ]
        return try await post("/api/v1/memory", body: body)
    }

    /// Search memories semantically
    public func searchMemory(
        query: String,
        limit: Int = 10,
        includeShared: Bool = true
    ) async throws -> MemorySearchResponse {
        let body: [String: Any] = [
            "query": query,
            "limit": limit,
            "include_shared": includeShared
        ]
        return try await post("/api/v1/memory/search", body: body)
    }

    // MARK: - Agent Discovery

    /// Discover agents with specific capabilities
    public func discoverAgents(capability: String) async throws -> [AgentInfo] {
        let response: DiscoverResponse = try await get("/api/v1/discover/capabilities/\(capability)")
        return response.agents
    }

    /// Get all available capabilities
    public func listCapabilities() async throws -> [CapabilityInfo] {
        return try await get("/api/v1/discover/capabilities")
    }

    // MARK: - Invocations

    /// Invoke a capability on a target agent
    public func invoke(
        agentId: String,
        capability: String,
        input: [String: Any],
        async: Bool = false
    ) async throws -> InvocationResponse {
        var body: [String: Any] = ["input": input]
        if async {
            body["async"] = true
        }
        return try await post("/api/v1/invoke/\(agentId)/\(capability)", body: body)
    }

    /// Get pending work for this agent
    public func getPendingWork() async throws -> [PendingInvocation] {
        return try await get("/api/v1/agents/me/pending")
    }

    /// Complete an invocation
    public func completeInvocation(
        invocationId: String,
        output: [String: Any],
        success: Bool = true
    ) async throws -> CompletionResponse {
        let body: [String: Any] = [
            "output": output,
            "success": success
        ]
        return try await post("/api/v1/invocations/\(invocationId)/complete", body: body)
    }

    // MARK: - Code Context

    /// Store current file context
    public func storeCodeContext(
        filePath: String,
        content: String,
        language: String,
        projectName: String,
        symbols: [String] = []
    ) async throws -> MemoryResponse {
        let key = "code:\(projectName):\(filePath.replacingOccurrences(of: "/", with: ":"))"
        let value: [String: Any] = [
            "file_path": filePath,
            "language": language,
            "project": projectName,
            "symbols": symbols,
            "line_count": content.components(separatedBy: "\n").count
        ]
        let textContent = "File: \(filePath)\nLanguage: \(language)\nProject: \(projectName)\n\n\(content.prefix(2000))"

        return try await storeMemory(
            key: key,
            value: value,
            textContent: textContent,
            tags: ["code", language, projectName],
            scope: "shared"
        )
    }

    /// Search for relevant code context
    public func searchCodeContext(query: String, project: String? = nil) async throws -> MemorySearchResponse {
        var searchQuery = query
        if let project = project {
            searchQuery = "\(project) \(query)"
        }
        return try await searchMemory(query: searchQuery, limit: 5, includeShared: true)
    }

    // MARK: - Build & Error Context

    /// Store build error for AI analysis
    public func storeBuildError(
        error: String,
        filePath: String?,
        line: Int?,
        projectName: String
    ) async throws -> MemoryResponse {
        let key = "error:\(projectName):\(UUID().uuidString.prefix(8))"
        let value: [String: Any] = [
            "error": error,
            "file_path": filePath ?? "unknown",
            "line": line ?? 0,
            "project": projectName,
            "timestamp": ISO8601DateFormatter().string(from: Date())
        ]
        let textContent = "Build Error in \(projectName):\n\(error)\nFile: \(filePath ?? "unknown"), Line: \(line ?? 0)"

        return try await storeMemory(
            key: key,
            value: value,
            textContent: textContent,
            tags: ["error", "build", projectName],
            scope: "shared"
        )
    }

    /// Ask AI to help fix an error
    public func requestErrorHelp(
        error: String,
        context: String
    ) async throws -> InvocationResponse? {
        // Find an agent that can help with code
        let agents = try await discoverAgents(capability: "code-assist")
        guard let agent = agents.first else { return nil }

        return try await invoke(
            agentId: agent.id,
            capability: "code-assist",
            input: [
                "task": "fix_error",
                "error": error,
                "context": context
            ]
        )
    }

    // MARK: - HTTP Helpers

    private func get<T: Decodable>(_ path: String) async throws -> T {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = "GET"
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")

        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              200..<300 ~= httpResponse.statusCode else {
            throw NexusError.requestFailed
        }

        return try JSONDecoder().decode(T.self, from: data)
    }

    private func post<T: Decodable>(_ path: String, body: [String: Any]) async throws -> T {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = "POST"
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              200..<300 ~= httpResponse.statusCode else {
            throw NexusError.requestFailed
        }

        return try JSONDecoder().decode(T.self, from: data)
    }
}

// MARK: - Models

public struct MemoryResponse: Codable {
    public let id: String
    public let key: String
}

public struct MemorySearchResponse: Codable {
    public let results: [MemorySearchResult]
    public let total: Int
}

public struct MemorySearchResult: Codable {
    public let memory: MemoryItem
    public let score: Double
}

public struct MemoryItem: Codable {
    public let id: String
    public let key: String
    public let value: [String: AnyCodable]
    public let tags: [String]
}

public struct AgentInfo: Codable {
    public let id: String
    public let name: String
    public let slug: String
    public let description: String?
}

public struct CapabilityInfo: Codable {
    public let name: String
    public let description: String?
    public let agentCount: Int?

    enum CodingKeys: String, CodingKey {
        case name, description
        case agentCount = "agent_count"
    }
}

public struct DiscoverResponse: Codable {
    public let agents: [AgentInfo]
}

public struct InvocationResponse: Codable {
    public let invocationId: String
    public let status: String
    public let output: [String: AnyCodable]?

    enum CodingKeys: String, CodingKey {
        case invocationId = "invocation_id"
        case status, output
    }
}

public struct PendingInvocation: Codable {
    public let id: String
    public let capability: String
    public let input: [String: AnyCodable]
}

public struct CompletionResponse: Codable {
    public let status: String
}

public enum NexusError: Error {
    case requestFailed
    case invalidResponse
    case noAgentFound
}

// Helper for dynamic JSON
public struct AnyCodable: Codable {
    public let value: Any

    public init(_ value: Any) {
        self.value = value
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let string = try? container.decode(String.self) {
            value = string
        } else if let int = try? container.decode(Int.self) {
            value = int
        } else if let double = try? container.decode(Double.self) {
            value = double
        } else if let bool = try? container.decode(Bool.self) {
            value = bool
        } else if let array = try? container.decode([AnyCodable].self) {
            value = array.map { $0.value }
        } else if let dict = try? container.decode([String: AnyCodable].self) {
            value = dict.mapValues { $0.value }
        } else {
            value = NSNull()
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch value {
        case let string as String: try container.encode(string)
        case let int as Int: try container.encode(int)
        case let double as Double: try container.encode(double)
        case let bool as Bool: try container.encode(bool)
        default: try container.encodeNil()
        }
    }
}
