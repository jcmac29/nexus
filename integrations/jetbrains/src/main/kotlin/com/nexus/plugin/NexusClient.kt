package com.nexus.plugin

import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse

data class MemoryResponse(val id: String, val key: String)
data class MemorySearchResult(val memory: Memory, val score: Double)
data class Memory(val id: String, val key: String, val value: Map<String, Any>, val tags: List<String>)
data class SearchResponse(val results: List<MemorySearchResult>, val total: Int)
data class AgentInfo(val id: String, val name: String, val slug: String)
data class InvocationResponse(val invocation_id: String, val status: String)

class NexusClient(
    private val baseUrl: String = "http://localhost:8000",
    private val apiKey: String
) {
    private val client = HttpClient.newHttpClient()
    private val gson = Gson()

    fun storeMemory(
        key: String,
        value: Map<String, Any>,
        textContent: String,
        tags: List<String> = emptyList(),
        scope: String = "shared"
    ): MemoryResponse {
        val body = mapOf(
            "key" to key,
            "value" to value,
            "text_content" to textContent,
            "tags" to tags,
            "scope" to scope
        )
        return post("/api/v1/memory", body)
    }

    fun searchMemory(query: String, limit: Int = 10, includeShared: Boolean = true): SearchResponse {
        val body = mapOf(
            "query" to query,
            "limit" to limit,
            "include_shared" to includeShared
        )
        return post("/api/v1/memory/search", body)
    }

    fun storeCodeContext(
        filePath: String,
        content: String,
        language: String,
        projectName: String
    ): MemoryResponse {
        val key = "code:$projectName:${filePath.replace("/", ":")}"
        val value = mapOf(
            "file_path" to filePath,
            "language" to language,
            "project" to projectName,
            "line_count" to content.lines().size
        )
        val textContent = "File: $filePath\nLanguage: $language\nProject: $projectName\n\n${content.take(3000)}"
        return storeMemory(key, value, textContent, listOf("code", language, projectName))
    }

    fun discoverAgents(capability: String): List<AgentInfo> {
        val response: Map<String, Any> = get("/api/v1/discover/capabilities/$capability")
        @Suppress("UNCHECKED_CAST")
        val agents = response["agents"] as? List<Map<String, Any>> ?: emptyList()
        return agents.map {
            AgentInfo(
                id = it["id"] as String,
                name = it["name"] as String,
                slug = it["slug"] as String
            )
        }
    }

    fun invoke(agentId: String, capability: String, input: Map<String, Any>): InvocationResponse {
        val body = mapOf("input" to input)
        return post("/api/v1/invoke/$agentId/$capability", body)
    }

    private inline fun <reified T> get(path: String): T {
        val request = HttpRequest.newBuilder()
            .uri(URI.create("$baseUrl$path"))
            .header("Authorization", "Bearer $apiKey")
            .GET()
            .build()

        val response = client.send(request, HttpResponse.BodyHandlers.ofString())
        return gson.fromJson(response.body(), T::class.java)
    }

    private inline fun <reified T> post(path: String, body: Any): T {
        val request = HttpRequest.newBuilder()
            .uri(URI.create("$baseUrl$path"))
            .header("Authorization", "Bearer $apiKey")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(gson.toJson(body)))
            .build()

        val response = client.send(request, HttpResponse.BodyHandlers.ofString())
        return gson.fromJson(response.body(), T::class.java)
    }
}
