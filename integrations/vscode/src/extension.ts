import * as vscode from 'vscode';
import { NexusClient } from './nexusClient';
import * as path from 'path';

let client: NexusClient | null = null;
let statusBarItem: vscode.StatusBarItem;

export function activate(context: vscode.ExtensionContext) {
    console.log('Nexus AI extension activated');

    // Initialize client
    initializeClient();

    // Status bar
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.text = '$(cloud) Nexus';
    statusBarItem.tooltip = 'Nexus AI - Click to search';
    statusBarItem.command = 'nexus.search';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('nexus.storeContext', storeContext),
        vscode.commands.registerCommand('nexus.search', searchKnowledge),
        vscode.commands.registerCommand('nexus.askAI', askAI),
        vscode.commands.registerCommand('nexus.explainCode', explainCode),
        vscode.commands.registerCommand('nexus.fixError', fixError),
        vscode.commands.registerCommand('nexus.syncProject', syncProject),
        vscode.commands.registerCommand('nexus.showTeamContext', showTeamContext)
    );

    // Auto-sync on save
    context.subscriptions.push(
        vscode.workspace.onDidSaveTextDocument(async (document) => {
            const config = vscode.workspace.getConfiguration('nexus');
            if (config.get('autoSync')) {
                const ext = path.extname(document.fileName).slice(1);
                const syncExtensions = config.get<string[]>('syncExtensions') || [];
                if (syncExtensions.includes(ext)) {
                    await autoSyncFile(document);
                }
            }
        })
    );

    // Listen for diagnostics (errors)
    context.subscriptions.push(
        vscode.languages.onDidChangeDiagnostics(async (e) => {
            for (const uri of e.uris) {
                const diagnostics = vscode.languages.getDiagnostics(uri);
                const errors = diagnostics.filter(d => d.severity === vscode.DiagnosticSeverity.Error);
                if (errors.length > 0) {
                    await storeErrors(uri, errors);
                }
            }
        })
    );

    // Check connection
    checkConnection();
}

function initializeClient() {
    const config = vscode.workspace.getConfiguration('nexus');
    const serverUrl = config.get<string>('serverUrl') || 'http://localhost:8000';
    const apiKey = config.get<string>('apiKey') || '';

    if (apiKey) {
        client = new NexusClient(serverUrl, apiKey);
    }
}

async function checkConnection() {
    if (!client) {
        statusBarItem.text = '$(cloud-offline) Nexus';
        statusBarItem.tooltip = 'Nexus: Not configured - Set API key in settings';
        return;
    }

    const healthy = await client.healthCheck();
    if (healthy) {
        statusBarItem.text = '$(cloud) Nexus';
        statusBarItem.tooltip = 'Nexus: Connected';
    } else {
        statusBarItem.text = '$(cloud-offline) Nexus';
        statusBarItem.tooltip = 'Nexus: Connection failed';
    }
}

async function storeContext() {
    if (!client) {
        vscode.window.showErrorMessage('Nexus: API key not configured');
        return;
    }

    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showWarningMessage('No active file');
        return;
    }

    const document = editor.document;
    const projectName = vscode.workspace.name || 'unknown';
    const relativePath = vscode.workspace.asRelativePath(document.fileName);
    const language = document.languageId;

    try {
        await client.storeCodeContext(
            relativePath,
            document.getText(),
            language,
            projectName
        );
        vscode.window.showInformationMessage(`Stored context: ${relativePath}`);
    } catch (error: any) {
        vscode.window.showErrorMessage(`Failed to store context: ${error.message}`);
    }
}

async function autoSyncFile(document: vscode.TextDocument) {
    if (!client) return;

    const projectName = vscode.workspace.name || 'unknown';
    const relativePath = vscode.workspace.asRelativePath(document.fileName);
    const language = document.languageId;

    try {
        await client.storeCodeContext(
            relativePath,
            document.getText(),
            language,
            projectName
        );
        console.log(`Auto-synced: ${relativePath}`);
    } catch (error) {
        console.error('Auto-sync failed:', error);
    }
}

async function searchKnowledge() {
    if (!client) {
        vscode.window.showErrorMessage('Nexus: API key not configured');
        return;
    }

    const query = await vscode.window.showInputBox({
        prompt: 'Search Nexus knowledge base',
        placeHolder: 'e.g., authentication logic, API endpoints, user model'
    });

    if (!query) return;

    try {
        const results = await client.searchMemory(query, 10, true);

        if (results.total === 0) {
            vscode.window.showInformationMessage('No results found');
            return;
        }

        const items = results.results.map(r => ({
            label: r.memory.key,
            description: `Score: ${r.score.toFixed(2)}`,
            detail: r.memory.tags.join(', '),
            memory: r.memory
        }));

        const selected = await vscode.window.showQuickPick(items, {
            placeHolder: `Found ${results.total} results`
        });

        if (selected) {
            // Show memory details in a new document
            const doc = await vscode.workspace.openTextDocument({
                content: JSON.stringify(selected.memory.value, null, 2),
                language: 'json'
            });
            await vscode.window.showTextDocument(doc);
        }
    } catch (error: any) {
        vscode.window.showErrorMessage(`Search failed: ${error.message}`);
    }
}

async function askAI() {
    if (!client) {
        vscode.window.showErrorMessage('Nexus: API key not configured');
        return;
    }

    const question = await vscode.window.showInputBox({
        prompt: 'Ask AI',
        placeHolder: 'e.g., How do I implement authentication?'
    });

    if (!question) return;

    try {
        // Get relevant context
        const context = await client.searchMemory(question, 3, true);
        const contextText = context.results.map(r =>
            `Context from ${r.memory.key}:\n${JSON.stringify(r.memory.value)}`
        ).join('\n\n');

        // Find an AI agent
        const agents = await client.discoverAgents('code-assist');

        if (agents.length === 0) {
            vscode.window.showWarningMessage('No AI agents available. Register a code-assist agent.');
            return;
        }

        // Get current file context
        const editor = vscode.window.activeTextEditor;
        let fileContext = '';
        if (editor) {
            const selection = editor.selection;
            if (!selection.isEmpty) {
                fileContext = editor.document.getText(selection);
            } else {
                fileContext = editor.document.getText().substring(0, 2000);
            }
        }

        const response = await client.invoke(agents[0].id, 'code-assist', {
            question,
            context: contextText,
            current_file: fileContext
        });

        vscode.window.showInformationMessage(
            `AI request submitted (${response.invocation_id}). Check for response.`
        );

    } catch (error: any) {
        vscode.window.showErrorMessage(`AI request failed: ${error.message}`);
    }
}

async function explainCode() {
    if (!client) {
        vscode.window.showErrorMessage('Nexus: API key not configured');
        return;
    }

    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.selection.isEmpty) {
        vscode.window.showWarningMessage('Select code to explain');
        return;
    }

    const selectedCode = editor.document.getText(editor.selection);
    const language = editor.document.languageId;

    try {
        const agents = await client.discoverAgents('code-explain');

        if (agents.length === 0) {
            vscode.window.showWarningMessage('No AI agents available for code explanation.');
            return;
        }

        const response = await client.invoke(agents[0].id, 'code-explain', {
            code: selectedCode,
            language
        });

        vscode.window.showInformationMessage(`Explanation requested (${response.invocation_id})`);

    } catch (error: any) {
        vscode.window.showErrorMessage(`Failed: ${error.message}`);
    }
}

async function fixError() {
    if (!client) {
        vscode.window.showErrorMessage('Nexus: API key not configured');
        return;
    }

    const editor = vscode.window.activeTextEditor;
    if (!editor) return;

    const diagnostics = vscode.languages.getDiagnostics(editor.document.uri);
    const errors = diagnostics.filter(d => d.severity === vscode.DiagnosticSeverity.Error);

    if (errors.length === 0) {
        vscode.window.showInformationMessage('No errors in current file');
        return;
    }

    const items = errors.map(e => ({
        label: e.message,
        description: `Line ${e.range.start.line + 1}`,
        error: e
    }));

    const selected = await vscode.window.showQuickPick(items, {
        placeHolder: 'Select error to fix'
    });

    if (!selected) return;

    try {
        const agents = await client.discoverAgents('code-assist');

        if (agents.length === 0) {
            vscode.window.showWarningMessage('No AI agents available.');
            return;
        }

        // Get surrounding code
        const errorLine = selected.error.range.start.line;
        const startLine = Math.max(0, errorLine - 5);
        const endLine = Math.min(editor.document.lineCount - 1, errorLine + 5);
        const surroundingCode = editor.document.getText(
            new vscode.Range(startLine, 0, endLine, 1000)
        );

        const response = await client.invoke(agents[0].id, 'code-assist', {
            task: 'fix_error',
            error: selected.error.message,
            code: surroundingCode,
            language: editor.document.languageId,
            line: errorLine
        });

        vscode.window.showInformationMessage(`Fix requested (${response.invocation_id})`);

    } catch (error: any) {
        vscode.window.showErrorMessage(`Failed: ${error.message}`);
    }
}

async function storeErrors(uri: vscode.Uri, errors: vscode.Diagnostic[]) {
    if (!client) return;

    const projectName = vscode.workspace.name || 'unknown';
    const relativePath = vscode.workspace.asRelativePath(uri);

    for (const error of errors.slice(0, 3)) { // Limit to 3 errors
        try {
            const key = `error:${projectName}:${Date.now()}`;
            await client.storeMemory(
                key,
                {
                    file: relativePath,
                    line: error.range.start.line,
                    message: error.message,
                    severity: error.severity
                },
                `Error in ${relativePath} at line ${error.range.start.line}: ${error.message}`,
                ['error', projectName],
                'agent'
            );
        } catch (e) {
            // Silently fail
        }
    }
}

async function syncProject() {
    if (!client) {
        vscode.window.showErrorMessage('Nexus: API key not configured');
        return;
    }

    const config = vscode.workspace.getConfiguration('nexus');
    const extensions = config.get<string[]>('syncExtensions') || ['ts', 'js', 'py'];
    const projectName = vscode.workspace.name || 'unknown';

    const pattern = `**/*.{${extensions.join(',')}}`;
    const files = await vscode.workspace.findFiles(pattern, '**/node_modules/**', 500);

    await vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: 'Syncing project to Nexus',
        cancellable: true
    }, async (progress, token) => {
        let synced = 0;
        for (const file of files) {
            if (token.isCancellationRequested) break;

            try {
                const document = await vscode.workspace.openTextDocument(file);
                const relativePath = vscode.workspace.asRelativePath(file);

                await client!.storeCodeContext(
                    relativePath,
                    document.getText(),
                    document.languageId,
                    projectName
                );

                synced++;
                progress.report({
                    message: `${synced}/${files.length} files`,
                    increment: 100 / files.length
                });
            } catch (e) {
                console.error(`Failed to sync ${file.path}:`, e);
            }
        }

        vscode.window.showInformationMessage(`Synced ${synced} files to Nexus`);
    });
}

async function showTeamContext() {
    if (!client) {
        vscode.window.showErrorMessage('Nexus: API key not configured');
        return;
    }

    try {
        const activity = await client.getTeamActivity();

        const panel = vscode.window.createWebviewPanel(
            'nexusTeam',
            'Nexus Team Activity',
            vscode.ViewColumn.Two,
            {}
        );

        const items = activity.results.map(r => `
            <div style="margin-bottom: 16px; padding: 12px; background: #1e1e1e; border-radius: 4px;">
                <strong>${r.memory.key}</strong>
                <br/>
                <small>Score: ${r.score.toFixed(2)} | Tags: ${r.memory.tags.join(', ')}</small>
                <pre style="background: #2d2d2d; padding: 8px; margin-top: 8px;">${JSON.stringify(r.memory.value, null, 2)}</pre>
            </div>
        `).join('');

        panel.webview.html = `
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 16px; }
                    pre { overflow-x: auto; }
                </style>
            </head>
            <body>
                <h2>Team Activity (${activity.total} items)</h2>
                ${items}
            </body>
            </html>
        `;

    } catch (error: any) {
        vscode.window.showErrorMessage(`Failed: ${error.message}`);
    }
}

export function deactivate() {}
