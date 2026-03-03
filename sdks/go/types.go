// Package nexus provides a client for the Nexus AI agent platform.
package nexus

// Agent represents an AI agent in Nexus.
type Agent struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Slug        string `json:"slug"`
	Description string `json:"description,omitempty"`
}

// Memory represents a stored memory.
type Memory struct {
	ID    string                 `json:"id"`
	Key   string                 `json:"key"`
	Value map[string]interface{} `json:"value"`
	Tags  []string               `json:"tags"`
}

// Capability represents an agent capability.
type Capability struct {
	Name        string                 `json:"name"`
	Description string                 `json:"description,omitempty"`
	InputSchema map[string]interface{} `json:"input_schema,omitempty"`
}

// Invocation represents a capability invocation.
type Invocation struct {
	ID     string                 `json:"id"`
	Status string                 `json:"status"`
	Output map[string]interface{} `json:"output,omitempty"`
}

// Message represents a message between agents.
type Message struct {
	ID          string `json:"id"`
	FromAgentID string `json:"from_agent_id"`
	Subject     string `json:"subject"`
	Body        string `json:"body"`
}

// SearchResult represents a memory search result.
type SearchResult struct {
	Memory Memory  `json:"memory"`
	Score  float64 `json:"score"`
}

// StoreMemoryRequest contains options for storing memory.
type StoreMemoryRequest struct {
	Key         string                 `json:"key"`
	Value       map[string]interface{} `json:"value"`
	TextContent string                 `json:"text_content,omitempty"`
	Tags        []string               `json:"tags,omitempty"`
	Scope       string                 `json:"scope,omitempty"`
}

// SearchMemoryRequest contains options for searching memory.
type SearchMemoryRequest struct {
	Query         string `json:"query"`
	Limit         int    `json:"limit,omitempty"`
	IncludeShared bool   `json:"include_shared,omitempty"`
}

// InvokeRequest contains options for invoking a capability.
type InvokeRequest struct {
	Input map[string]interface{} `json:"input"`
}

// SendMessageRequest contains options for sending a message.
type SendMessageRequest struct {
	ToAgentID string `json:"to_agent_id"`
	Subject   string `json:"subject"`
	Body      string `json:"body"`
}
