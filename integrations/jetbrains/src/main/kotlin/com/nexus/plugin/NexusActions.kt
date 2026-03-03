package com.nexus.plugin

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.ui.Messages
import com.intellij.openapi.ui.InputValidator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.progress.ProgressIndicator

class StoreContextAction : AnAction("Store in Nexus") {
    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val editor = e.getData(CommonDataKeys.EDITOR) ?: return
        val file = e.getData(CommonDataKeys.VIRTUAL_FILE) ?: return

        val settings = NexusSettings.getInstance()
        if (settings.apiKey.isEmpty()) {
            Messages.showErrorDialog(project, "Please configure Nexus API key in Settings", "Nexus")
            return
        }

        val client = NexusClient(settings.serverUrl, settings.apiKey)
        val content = editor.document.text
        val language = file.extension ?: "unknown"
        val projectName = project.name
        val filePath = file.path

        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "Storing in Nexus") {
            override fun run(indicator: ProgressIndicator) {
                try {
                    val result = client.storeCodeContext(filePath, content, language, projectName)
                    Messages.showInfoMessage(project, "Stored: ${result.key}", "Nexus")
                } catch (ex: Exception) {
                    Messages.showErrorDialog(project, "Failed: ${ex.message}", "Nexus")
                }
            }
        })
    }
}

class SearchAction : AnAction("Search Nexus") {
    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return

        val settings = NexusSettings.getInstance()
        if (settings.apiKey.isEmpty()) {
            Messages.showErrorDialog(project, "Please configure Nexus API key in Settings", "Nexus")
            return
        }

        val query = Messages.showInputDialog(
            project,
            "Search query:",
            "Search Nexus",
            null
        ) ?: return

        val client = NexusClient(settings.serverUrl, settings.apiKey)

        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "Searching Nexus") {
            override fun run(indicator: ProgressIndicator) {
                try {
                    val results = client.searchMemory(query)
                    val message = if (results.results.isEmpty()) {
                        "No results found"
                    } else {
                        results.results.take(5).joinToString("\n\n") { r ->
                            "[${String.format("%.2f", r.score)}] ${r.memory.key}\n  Tags: ${r.memory.tags.joinToString(", ")}"
                        }
                    }
                    Messages.showInfoMessage(project, message, "Nexus Search Results")
                } catch (ex: Exception) {
                    Messages.showErrorDialog(project, "Search failed: ${ex.message}", "Nexus")
                }
            }
        })
    }
}

class AskAIAction : AnAction("Ask Nexus AI") {
    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val editor = e.getData(CommonDataKeys.EDITOR)

        val settings = NexusSettings.getInstance()
        if (settings.apiKey.isEmpty()) {
            Messages.showErrorDialog(project, "Please configure Nexus API key in Settings", "Nexus")
            return
        }

        val question = Messages.showInputDialog(
            project,
            "Ask AI:",
            "Nexus AI",
            null
        ) ?: return

        val selectedText = editor?.selectionModel?.selectedText ?: ""
        val client = NexusClient(settings.serverUrl, settings.apiKey)

        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "Asking Nexus AI") {
            override fun run(indicator: ProgressIndicator) {
                try {
                    // Get context
                    val context = client.searchMemory(question, 3)
                    val contextText = context.results.joinToString("\n") { r ->
                        "Context: ${r.memory.key}"
                    }

                    // Find agent
                    val agents = client.discoverAgents("code-assist")
                    if (agents.isEmpty()) {
                        Messages.showWarningDialog(project, "No AI agents available", "Nexus")
                        return
                    }

                    // Invoke
                    val result = client.invoke(
                        agents[0].id,
                        "code-assist",
                        mapOf(
                            "question" to question,
                            "context" to contextText,
                            "selected_code" to selectedText
                        )
                    )

                    Messages.showInfoMessage(
                        project,
                        "AI request submitted: ${result.invocation_id}",
                        "Nexus AI"
                    )
                } catch (ex: Exception) {
                    Messages.showErrorDialog(project, "Failed: ${ex.message}", "Nexus")
                }
            }
        })
    }
}
