import axios, { AxiosInstance } from 'axios';

export interface MemoryResponse {
    id: string;
    key: string;
}

export interface MemorySearchResult {
    memory: {
        id: string;
        key: string;
        value: Record<string, any>;
        tags: string[];
    };
    score: number;
    owner_agent_id?: string;
}

export interface MemorySearchResponse {
    results: MemorySearchResult[];
    total: number;
}

export interface AgentInfo {
    id: string;
    name: string;
    slug: string;
    description?: string;
}

export interface InvocationResponse {
    invocation_id: string;
    status: string;
    output?: Record<string, any>;
}

export class NexusClient {
    private client: AxiosInstance;

    constructor(baseURL: string, apiKey: string) {
        this.client = axios.create({
            baseURL,
            headers: {
                'Authorization': `Bearer ${apiKey}`,
                'Content-Type': 'application/json'
            }
        });
    }

    // Memory Operations
    async storeMemory(
        key: string,
        value: Record<string, any>,
        textContent: string,
        tags: string[] = [],
        scope: string = 'shared'
    ): Promise<MemoryResponse> {
        const response = await this.client.post('/api/v1/memory', {
            key,
            value,
            text_content: textContent,
            tags,
            scope
        });
        return response.data;
    }

    async searchMemory(
        query: string,
        limit: number = 10,
        includeShared: boolean = true
    ): Promise<MemorySearchResponse> {
        const response = await this.client.post('/api/v1/memory/search', {
            query,
            limit,
            include_shared: includeShared
        });
        return response.data;
    }

    // Code Context
    async storeCodeContext(
        filePath: string,
        content: string,
        language: string,
        projectName: string
    ): Promise<MemoryResponse> {
        const key = `code:${projectName}:${filePath.replace(/\//g, ':')}`;
        const value = {
            file_path: filePath,
            language,
            project: projectName,
            line_count: content.split('\n').length,
            timestamp: new Date().toISOString()
        };
        const textContent = `File: ${filePath}\nLanguage: ${language}\nProject: ${projectName}\n\n${content.substring(0, 3000)}`;

        return this.storeMemory(key, value, textContent, ['code', language, projectName], 'shared');
    }

    // Agent Discovery
    async discoverAgents(capability: string): Promise<AgentInfo[]> {
        const response = await this.client.get(`/api/v1/discover/capabilities/${capability}`);
        return response.data.agents || [];
    }

    async listCapabilities(): Promise<any[]> {
        const response = await this.client.get('/api/v1/discover/capabilities');
        return response.data;
    }

    // Invocations
    async invoke(
        agentId: string,
        capability: string,
        input: Record<string, any>
    ): Promise<InvocationResponse> {
        const response = await this.client.post(`/api/v1/invoke/${agentId}/${capability}`, {
            input
        });
        return response.data;
    }

    async getInvocationStatus(invocationId: string): Promise<any> {
        const response = await this.client.get(`/api/v1/invocations/${invocationId}`);
        return response.data;
    }

    // Team
    async getTeamActivity(): Promise<MemorySearchResponse> {
        return this.searchMemory('recent activity changes updates', 20, true);
    }

    // Health check
    async healthCheck(): Promise<boolean> {
        try {
            const response = await this.client.get('/health');
            return response.data.status === 'healthy';
        } catch {
            return false;
        }
    }
}
