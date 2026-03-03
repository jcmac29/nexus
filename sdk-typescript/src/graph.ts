/**
 * Graph memory operations
 */

import { AxiosInstance } from 'axios';

export interface Relationship {
  id: string;
  source_type: 'memory' | 'agent' | 'capability';
  source_id: string;
  target_type: 'memory' | 'agent' | 'capability';
  target_id: string;
  relationship_type: string;
  weight: number;
  metadata: Record<string, unknown>;
  created_by_agent_id?: string;
  created_at: string;
}

export interface CreateRelationshipOptions {
  source_type: 'memory' | 'agent' | 'capability';
  source_id: string;
  target_type: 'memory' | 'agent' | 'capability';
  target_id: string;
  relationship_type: string;
  weight?: number;
  metadata?: Record<string, unknown>;
}

export interface TraverseOptions {
  start_type: 'memory' | 'agent' | 'capability';
  start_id: string;
  max_depth?: number;
  relationship_types?: string[];
  target_types?: string[];
}

export interface TraverseResult {
  nodes: Array<{
    type: string;
    id: string;
    depth: number;
  }>;
  edges: Relationship[];
}

export interface PathResult {
  path: Array<{
    type: string;
    id: string;
  }>;
  edges: Relationship[];
  length: number;
}

export interface RelatedMemory {
  memory_id: string;
  relationship_type: string;
  weight: number;
  depth: number;
}

/**
 * Graph memory client for relationship management.
 */
export class Graph {
  constructor(private client: AxiosInstance) {}

  /**
   * Create a relationship between two nodes.
   */
  async createRelationship(options: CreateRelationshipOptions): Promise<Relationship> {
    const response = await this.client.post<Relationship>('/graph/relationships', {
      source_type: options.source_type,
      source_id: options.source_id,
      target_type: options.target_type,
      target_id: options.target_id,
      relationship_type: options.relationship_type,
      weight: options.weight ?? 1.0,
      metadata: options.metadata ?? {},
    });
    return response.data;
  }

  /**
   * Delete a relationship by ID.
   */
  async deleteRelationship(relationshipId: string): Promise<void> {
    await this.client.delete(`/graph/relationships/${relationshipId}`);
  }

  /**
   * Get edges for a node.
   */
  async getEdges(
    nodeType: 'memory' | 'agent' | 'capability',
    nodeId: string,
    options?: {
      relationship_type?: string;
      direction?: 'outgoing' | 'incoming' | 'both';
    }
  ): Promise<Relationship[]> {
    const params: Record<string, unknown> = {
      direction: options?.direction ?? 'both',
    };
    if (options?.relationship_type) {
      params.relationship_type = options.relationship_type;
    }
    const response = await this.client.get<{ edges: Relationship[] }>(
      `/graph/nodes/${nodeType}/${nodeId}/edges`,
      { params }
    );
    return response.data.edges;
  }

  /**
   * Traverse the graph from a starting node.
   */
  async traverse(options: TraverseOptions): Promise<TraverseResult> {
    const response = await this.client.post<TraverseResult>('/graph/traverse', {
      start_type: options.start_type,
      start_id: options.start_id,
      max_depth: options.max_depth ?? 2,
      relationship_types: options.relationship_types,
      target_types: options.target_types,
    });
    return response.data;
  }

  /**
   * Find shortest path between two nodes.
   */
  async findPath(
    fromType: 'memory' | 'agent' | 'capability',
    fromId: string,
    toType: 'memory' | 'agent' | 'capability',
    toId: string,
    maxDepth: number = 5
  ): Promise<PathResult> {
    const response = await this.client.post<PathResult>('/graph/path', {
      from_type: fromType,
      from_id: fromId,
      to_type: toType,
      to_id: toId,
      max_depth: maxDepth,
    });
    return response.data;
  }

  /**
   * Get memories related to a given memory.
   */
  async getRelatedMemories(
    memoryId: string,
    options?: {
      relationship_types?: string[];
      max_depth?: number;
    }
  ): Promise<RelatedMemory[]> {
    const params: Record<string, unknown> = {
      max_depth: options?.max_depth ?? 1,
    };
    if (options?.relationship_types) {
      params.relationship_types = options.relationship_types;
    }
    const response = await this.client.get<{ memories: RelatedMemory[] }>(
      `/graph/memories/${memoryId}/related`,
      { params }
    );
    return response.data.memories;
  }
}
