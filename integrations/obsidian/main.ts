import { App, Plugin, PluginSettingTab, Setting, Notice, Modal, TFile } from 'obsidian';

interface NexusSettings {
    serverUrl: string;
    apiKey: string;
    autoSync: boolean;
}

const DEFAULT_SETTINGS: NexusSettings = {
    serverUrl: 'http://localhost:8000',
    apiKey: '',
    autoSync: false
};

export default class NexusPlugin extends Plugin {
    settings: NexusSettings;

    async onload() {
        await this.loadSettings();

        // Add ribbon icon
        this.addRibbonIcon('brain', 'Nexus AI', async () => {
            new NexusSearchModal(this.app, this).open();
        });

        // Add commands
        this.addCommand({
            id: 'nexus-store-note',
            name: 'Store current note in Nexus',
            callback: () => this.storeCurrentNote()
        });

        this.addCommand({
            id: 'nexus-search',
            name: 'Search Nexus knowledge base',
            callback: () => new NexusSearchModal(this.app, this).open()
        });

        this.addCommand({
            id: 'nexus-ask-ai',
            name: 'Ask Nexus AI',
            callback: () => new NexusAskModal(this.app, this).open()
        });

        this.addCommand({
            id: 'nexus-sync-vault',
            name: 'Sync entire vault to Nexus',
            callback: () => this.syncVault()
        });

        // Auto-sync on file change
        if (this.settings.autoSync) {
            this.registerEvent(
                this.app.vault.on('modify', (file) => {
                    if (file instanceof TFile && file.extension === 'md') {
                        this.storeNote(file);
                    }
                })
            );
        }

        // Settings tab
        this.addSettingTab(new NexusSettingTab(this.app, this));
    }

    async loadSettings() {
        this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
    }

    async saveSettings() {
        await this.saveData(this.settings);
    }

    async apiRequest(path: string, method: string = 'GET', body?: any): Promise<any> {
        const response = await fetch(`${this.settings.serverUrl}${path}`, {
            method,
            headers: {
                'Authorization': `Bearer ${this.settings.apiKey}`,
                'Content-Type': 'application/json'
            },
            body: body ? JSON.stringify(body) : undefined
        });
        return response.json();
    }

    async storeCurrentNote() {
        const file = this.app.workspace.getActiveFile();
        if (!file) {
            new Notice('No active file');
            return;
        }
        await this.storeNote(file);
        new Notice(`Stored: ${file.basename}`);
    }

    async storeNote(file: TFile) {
        const content = await this.app.vault.read(file);
        const key = `obsidian:${this.app.vault.getName()}:${file.path.replace(/\//g, ':')}`;

        // Extract tags from frontmatter or content
        const tags = this.extractTags(content);

        await this.apiRequest('/api/v1/memory', 'POST', {
            key,
            value: {
                file_path: file.path,
                vault: this.app.vault.getName(),
                basename: file.basename,
                extension: file.extension
            },
            text_content: `Note: ${file.basename}\n\n${content.substring(0, 5000)}`,
            tags: ['obsidian', 'note', ...tags],
            scope: 'shared'
        });
    }

    extractTags(content: string): string[] {
        const tagRegex = /#[\w-]+/g;
        const matches = content.match(tagRegex) || [];
        return matches.map(t => t.slice(1)).slice(0, 10);
    }

    async searchMemory(query: string): Promise<any> {
        return this.apiRequest('/api/v1/memory/search', 'POST', {
            query,
            limit: 10,
            include_shared: true
        });
    }

    async syncVault() {
        const files = this.app.vault.getMarkdownFiles();
        let synced = 0;

        new Notice(`Syncing ${files.length} files...`);

        for (const file of files) {
            try {
                await this.storeNote(file);
                synced++;
            } catch (e) {
                console.error(`Failed to sync ${file.path}:`, e);
            }
        }

        new Notice(`Synced ${synced}/${files.length} files to Nexus`);
    }
}

class NexusSearchModal extends Modal {
    plugin: NexusPlugin;
    results: any[] = [];

    constructor(app: App, plugin: NexusPlugin) {
        super(app);
        this.plugin = plugin;
    }

    onOpen() {
        const { contentEl } = this;
        contentEl.createEl('h2', { text: 'Search Nexus' });

        const input = contentEl.createEl('input', {
            type: 'text',
            placeholder: 'Search...',
            cls: 'nexus-search-input'
        });
        input.style.width = '100%';
        input.style.marginBottom = '16px';

        const resultsDiv = contentEl.createDiv({ cls: 'nexus-results' });

        input.addEventListener('keyup', async (e) => {
            if (e.key === 'Enter' && input.value) {
                resultsDiv.empty();
                resultsDiv.createEl('p', { text: 'Searching...' });

                try {
                    const response = await this.plugin.searchMemory(input.value);
                    resultsDiv.empty();

                    if (!response.results?.length) {
                        resultsDiv.createEl('p', { text: 'No results found' });
                        return;
                    }

                    for (const r of response.results) {
                        const item = resultsDiv.createDiv({ cls: 'nexus-result-item' });
                        item.style.padding = '8px';
                        item.style.marginBottom = '8px';
                        item.style.backgroundColor = 'var(--background-secondary)';
                        item.style.borderRadius = '4px';

                        item.createEl('strong', { text: r.memory.key });
                        item.createEl('br');
                        item.createEl('small', {
                            text: `Score: ${r.score.toFixed(2)} | Tags: ${r.memory.tags?.join(', ') || 'none'}`
                        });
                    }
                } catch (e) {
                    resultsDiv.empty();
                    resultsDiv.createEl('p', { text: `Error: ${e.message}` });
                }
            }
        });

        input.focus();
    }

    onClose() {
        this.contentEl.empty();
    }
}

class NexusAskModal extends Modal {
    plugin: NexusPlugin;

    constructor(app: App, plugin: NexusPlugin) {
        super(app);
        this.plugin = plugin;
    }

    onOpen() {
        const { contentEl } = this;
        contentEl.createEl('h2', { text: 'Ask Nexus AI' });

        const input = contentEl.createEl('textarea', {
            placeholder: 'Ask anything...',
            cls: 'nexus-ask-input'
        });
        input.style.width = '100%';
        input.style.height = '100px';
        input.style.marginBottom = '16px';

        const button = contentEl.createEl('button', { text: 'Ask' });
        const responseDiv = contentEl.createDiv({ cls: 'nexus-response' });

        button.addEventListener('click', async () => {
            if (!input.value) return;

            responseDiv.empty();
            responseDiv.createEl('p', { text: 'Thinking...' });

            try {
                // Get context
                const context = await this.plugin.searchMemory(input.value);
                const contextText = context.results?.slice(0, 3).map(
                    (r: any) => `Context: ${r.memory.key}`
                ).join('\n') || '';

                // Find AI agent
                const agents = await this.plugin.apiRequest('/api/v1/discover/capabilities/code-assist');

                if (!agents.agents?.length) {
                    responseDiv.empty();
                    responseDiv.createEl('p', { text: 'No AI agents available' });
                    return;
                }

                // Invoke
                const result = await this.plugin.apiRequest(
                    `/api/v1/invoke/${agents.agents[0].id}/code-assist`,
                    'POST',
                    { input: { question: input.value, context: contextText } }
                );

                responseDiv.empty();
                responseDiv.createEl('p', { text: `Request submitted: ${result.invocation_id}` });
                responseDiv.createEl('p', { text: 'Check back for the response.' });

            } catch (e) {
                responseDiv.empty();
                responseDiv.createEl('p', { text: `Error: ${e.message}` });
            }
        });

        input.focus();
    }

    onClose() {
        this.contentEl.empty();
    }
}

class NexusSettingTab extends PluginSettingTab {
    plugin: NexusPlugin;

    constructor(app: App, plugin: NexusPlugin) {
        super(app, plugin);
        this.plugin = plugin;
    }

    display(): void {
        const { containerEl } = this;
        containerEl.empty();

        containerEl.createEl('h2', { text: 'Nexus Settings' });

        new Setting(containerEl)
            .setName('Server URL')
            .setDesc('Nexus server URL')
            .addText(text => text
                .setPlaceholder('http://localhost:8000')
                .setValue(this.plugin.settings.serverUrl)
                .onChange(async (value) => {
                    this.plugin.settings.serverUrl = value;
                    await this.plugin.saveSettings();
                }));

        new Setting(containerEl)
            .setName('API Key')
            .setDesc('Your Nexus API key')
            .addText(text => text
                .setPlaceholder('nex_...')
                .setValue(this.plugin.settings.apiKey)
                .onChange(async (value) => {
                    this.plugin.settings.apiKey = value;
                    await this.plugin.saveSettings();
                }));

        new Setting(containerEl)
            .setName('Auto-sync')
            .setDesc('Automatically sync notes when modified')
            .addToggle(toggle => toggle
                .setValue(this.plugin.settings.autoSync)
                .onChange(async (value) => {
                    this.plugin.settings.autoSync = value;
                    await this.plugin.saveSettings();
                }));
    }
}
