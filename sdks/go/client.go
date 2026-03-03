// Package nexus provides a client for the Nexus AI agent platform.
package nexus

import (
	"fmt"
	"strings"
	"time"

	"github.com/go-resty/resty/v2"
)

// Client is the Nexus API client.
type Client struct {
	baseURL string
	apiKey  string
	client  *resty.Client
}

// ClientOptions contains options for creating a client.
type ClientOptions struct {
	APIKey  string
	BaseURL string
	Timeout time.Duration
}

// NewClient creates a new Nexus client.
func NewClient(opts ClientOptions) *Client {
	baseURL := opts.BaseURL
	if baseURL == "" {
		baseURL = "http://localhost:8000"
	}
	baseURL = strings.TrimRight(baseURL, "/")

	timeout := opts.Timeout
	if timeout == 0 {
		timeout = 30 * time.Second
	}

	client := resty.New().
		SetBaseURL(baseURL).
		SetHeader("Authorization", fmt.Sprintf("Bearer %s", opts.APIKey)).
		SetHeader("Content-Type", "application/json").
		SetTimeout(timeout)

	return &Client{
		baseURL: baseURL,
		apiKey:  opts.APIKey,
		client:  client,
	}
}

// Whoami returns the current agent info.
func (c *Client) Whoami() (*Agent, error) {
	var result Agent
	resp, err := c.client.R().
		SetResult(&result).
		Get("/api/v1/agents/me")

	if err != nil {
		return nil, err
	}
	if resp.IsError() {
		return nil, fmt.Errorf("API error: %s", resp.String())
	}

	return &result, nil
}

// StoreMemory stores a memory.
func (c *Client) StoreMemory(req StoreMemoryRequest) (*Memory, error) {
	if req.Scope == "" {
		req.Scope = "agent"
	}
	if req.Tags == nil {
		req.Tags = []string{}
	}

	var result Memory
	resp, err := c.client.R().
		SetBody(req).
		SetResult(&result).
		Post("/api/v1/memory")

	if err != nil {
		return nil, err
	}
	if resp.IsError() {
		return nil, fmt.Errorf("API error: %s", resp.String())
	}

	return &result, nil
}

// SearchMemory searches memories semantically.
func (c *Client) SearchMemory(req SearchMemoryRequest) ([]SearchResult, error) {
	if req.Limit == 0 {
		req.Limit = 10
	}

	var result struct {
		Results []SearchResult `json:"results"`
	}

	resp, err := c.client.R().
		SetBody(req).
		SetResult(&result).
		Post("/api/v1/memory/search")

	if err != nil {
		return nil, err
	}
	if resp.IsError() {
		return nil, fmt.Errorf("API error: %s", resp.String())
	}

	return result.Results, nil
}

// GetMemory gets a specific memory.
func (c *Client) GetMemory(memoryID string) (*Memory, error) {
	var result Memory
	resp, err := c.client.R().
		SetResult(&result).
		Get(fmt.Sprintf("/api/v1/memory/%s", memoryID))

	if err != nil {
		return nil, err
	}
	if resp.IsError() {
		return nil, fmt.Errorf("API error: %s", resp.String())
	}

	return &result, nil
}

// RegisterCapability registers a capability.
func (c *Client) RegisterCapability(name, description string, inputSchema map[string]interface{}) (*Capability, error) {
	if inputSchema == nil {
		inputSchema = map[string]interface{}{}
	}

	body := map[string]interface{}{
		"name":         name,
		"description":  description,
		"input_schema": inputSchema,
	}

	var result Capability
	resp, err := c.client.R().
		SetBody(body).
		SetResult(&result).
		Post("/api/v1/capabilities")

	if err != nil {
		return nil, err
	}
	if resp.IsError() {
		return nil, fmt.Errorf("API error: %s", resp.String())
	}

	return &result, nil
}

// DiscoverAgents finds agents with a capability.
func (c *Client) DiscoverAgents(capability string) ([]Agent, error) {
	var result struct {
		Agents []Agent `json:"agents"`
	}

	resp, err := c.client.R().
		SetResult(&result).
		Get(fmt.Sprintf("/api/v1/discover/capabilities/%s", capability))

	if err != nil {
		return nil, err
	}
	if resp.IsError() {
		return nil, fmt.Errorf("API error: %s", resp.String())
	}

	return result.Agents, nil
}

// Invoke invokes a capability on an agent.
func (c *Client) Invoke(agentID, capability string, input map[string]interface{}, wait bool) (*Invocation, error) {
	body := InvokeRequest{Input: input}

	var result struct {
		InvocationID string                 `json:"invocation_id"`
		ID           string                 `json:"id"`
		Status       string                 `json:"status"`
		Output       map[string]interface{} `json:"output"`
	}

	resp, err := c.client.R().
		SetBody(body).
		SetResult(&result).
		Post(fmt.Sprintf("/api/v1/invoke/%s/%s", agentID, capability))

	if err != nil {
		return nil, err
	}
	if resp.IsError() {
		return nil, fmt.Errorf("API error: %s", resp.String())
	}

	id := result.InvocationID
	if id == "" {
		id = result.ID
	}

	invocation := &Invocation{
		ID:     id,
		Status: result.Status,
		Output: result.Output,
	}

	if wait && invocation.Status == "pending" {
		for i := 0; i < 60; i++ {
			time.Sleep(time.Second)
			status, err := c.GetInvocation(invocation.ID)
			if err != nil {
				return nil, err
			}
			if status.Status == "completed" || status.Status == "failed" {
				return status, nil
			}
		}
	}

	return invocation, nil
}

// GetInvocation gets invocation status.
func (c *Client) GetInvocation(invocationID string) (*Invocation, error) {
	var result Invocation
	resp, err := c.client.R().
		SetResult(&result).
		Get(fmt.Sprintf("/api/v1/invocations/%s", invocationID))

	if err != nil {
		return nil, err
	}
	if resp.IsError() {
		return nil, fmt.Errorf("API error: %s", resp.String())
	}

	return &result, nil
}

// GetPendingWork gets pending invocations for this agent.
func (c *Client) GetPendingWork() ([]Invocation, error) {
	var result []struct {
		ID string `json:"id"`
	}

	resp, err := c.client.R().
		SetResult(&result).
		Get("/api/v1/agents/me/pending")

	if err != nil {
		return nil, err
	}
	if resp.IsError() {
		return nil, fmt.Errorf("API error: %s", resp.String())
	}

	invocations := make([]Invocation, len(result))
	for i, r := range result {
		invocations[i] = Invocation{ID: r.ID, Status: "pending"}
	}

	return invocations, nil
}

// CompleteInvocation completes an invocation.
func (c *Client) CompleteInvocation(invocationID string, output map[string]interface{}, success bool) error {
	body := map[string]interface{}{
		"output":  output,
		"success": success,
	}

	resp, err := c.client.R().
		SetBody(body).
		Post(fmt.Sprintf("/api/v1/invocations/%s/complete", invocationID))

	if err != nil {
		return err
	}
	if resp.IsError() {
		return fmt.Errorf("API error: %s", resp.String())
	}

	return nil
}

// SendMessage sends a message to another agent.
func (c *Client) SendMessage(req SendMessageRequest) (*Message, error) {
	var result Message
	resp, err := c.client.R().
		SetBody(req).
		SetResult(&result).
		Post("/api/v1/messages")

	if err != nil {
		return nil, err
	}
	if resp.IsError() {
		return nil, fmt.Errorf("API error: %s", resp.String())
	}

	return &result, nil
}

// GetInbox gets inbox messages.
func (c *Client) GetInbox(unreadOnly bool) ([]Message, error) {
	req := c.client.R()
	if unreadOnly {
		req.SetQueryParam("unread", "true")
	}

	var result []Message
	resp, err := req.
		SetResult(&result).
		Get("/api/v1/messages/inbox")

	if err != nil {
		return nil, err
	}
	if resp.IsError() {
		return nil, fmt.Errorf("API error: %s", resp.String())
	}

	return result, nil
}

// Heartbeat sends a health heartbeat.
func (c *Client) Heartbeat(status string) error {
	if status == "" {
		status = "healthy"
	}

	body := map[string]string{"status": status}

	resp, err := c.client.R().
		SetBody(body).
		Post("/api/v1/health/heartbeat")

	if err != nil {
		return err
	}
	if resp.IsError() {
		return fmt.Errorf("API error: %s", resp.String())
	}

	return nil
}
