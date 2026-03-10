// Package cortexdb provides a Go client for the CortexDB API.
//
// It supports core database operations (query, write, health checks) as well as
// authenticated super-admin operations (agent management, task creation, chat,
// and marketplace control).
package cortexdb

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// ---------------------------------------------------------------------------
// Error types
// ---------------------------------------------------------------------------

// CortexDBError is the base error returned by the client for non-HTTP issues.
type CortexDBError struct {
	Message string
	Cause   error
}

func (e *CortexDBError) Error() string {
	if e.Cause != nil {
		return fmt.Sprintf("cortexdb: %s: %v", e.Message, e.Cause)
	}
	return fmt.Sprintf("cortexdb: %s", e.Message)
}

func (e *CortexDBError) Unwrap() error { return e.Cause }

// AuthError indicates an authentication or authorization failure (HTTP 401/403).
type AuthError struct {
	StatusCode int
	Body       string
}

func (e *AuthError) Error() string {
	return fmt.Sprintf("cortexdb auth error (%d): %s", e.StatusCode, e.Body)
}

// QueryError indicates that the server rejected or failed to execute a query.
type QueryError struct {
	StatusCode int
	Body       string
}

func (e *QueryError) Error() string {
	return fmt.Sprintf("cortexdb query error (%d): %s", e.StatusCode, e.Body)
}

// ---------------------------------------------------------------------------
// Response / domain types
// ---------------------------------------------------------------------------

// QueryResult holds the response from a CortexQL read query.
type QueryResult struct {
	Rows    []map[string]any `json:"rows"`
	Columns []string         `json:"columns"`
	Count   int              `json:"count"`
}

// WriteResult holds the response from a CortexQL write operation.
type WriteResult struct {
	RowsAffected int `json:"rows_affected"`
	InsertedID   any `json:"inserted_id,omitempty"`
}

// HealthResponse describes the readiness status of a CortexDB instance.
type HealthResponse struct {
	Status    string `json:"status"`
	Timestamp string `json:"timestamp"`
	Version   string `json:"version,omitempty"`
}

// Agent represents a CortexDB managed agent.
type Agent struct {
	ID         string         `json:"id"`
	Name       string         `json:"name"`
	Tier       string         `json:"tier"`
	Department string         `json:"department"`
	Role       string         `json:"role"`
	Status     string         `json:"status"`
	Config     map[string]any `json:"config,omitempty"`
	CreatedAt  string         `json:"created_at"`
	UpdatedAt  string         `json:"updated_at"`
}

// CreateTaskInput is the payload for creating a new task.
type CreateTaskInput struct {
	AgentID     string         `json:"agent_id"`
	Type        string         `json:"type"`
	Priority    string         `json:"priority,omitempty"`
	Instruction string         `json:"instruction"`
	Input       map[string]any `json:"input,omitempty"`
	ParentID    string         `json:"parent_id,omitempty"`
}

// Task represents a CortexDB task.
type Task struct {
	ID          string         `json:"id"`
	AgentID     string         `json:"agent_id"`
	Type        string         `json:"type"`
	Status      string         `json:"status"`
	Priority    string         `json:"priority"`
	Instruction string         `json:"instruction"`
	Input       map[string]any `json:"input,omitempty"`
	Output      map[string]any `json:"output,omitempty"`
	ParentID    string         `json:"parent_id,omitempty"`
	CreatedAt   string         `json:"created_at"`
	UpdatedAt   string         `json:"updated_at"`
}

// ChatResponse holds the result of an agent chat interaction.
type ChatResponse struct {
	Response  string         `json:"response"`
	AgentID   string         `json:"agent_id"`
	ToolCalls []ToolCall     `json:"tool_calls,omitempty"`
	Metadata  map[string]any `json:"metadata,omitempty"`
}

// ToolCall describes a single tool invocation made during chat.
type ToolCall struct {
	Name   string         `json:"name"`
	Input  map[string]any `json:"input,omitempty"`
	Output map[string]any `json:"output,omitempty"`
}

// Capability represents a marketplace capability/integration.
type Capability struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Description string `json:"description"`
	Category    string `json:"category"`
	Enabled     bool   `json:"enabled"`
	Version     string `json:"version,omitempty"`
}

// ---------------------------------------------------------------------------
// Functional options
// ---------------------------------------------------------------------------

// Option configures the Client.
type Option func(*Client)

// WithAPIKey sets the API key used in the X-API-Key header.
func WithAPIKey(key string) Option {
	return func(c *Client) {
		c.apiKey = key
	}
}

// WithTimeout overrides the default HTTP client timeout.
func WithTimeout(d time.Duration) Option {
	return func(c *Client) {
		c.httpClient.Timeout = d
	}
}

// WithHTTPClient replaces the default http.Client entirely.
func WithHTTPClient(hc *http.Client) Option {
	return func(c *Client) {
		c.httpClient = hc
	}
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

// Client provides access to CortexDB core endpoints (query, write, health).
type Client struct {
	baseURL    string
	apiKey     string
	httpClient *http.Client
}

// NewClient creates a Client for the given CortexDB base URL.
//
//	c := cortexdb.NewClient("http://localhost:3001",
//	    cortexdb.WithAPIKey("my-key"),
//	    cortexdb.WithTimeout(10*time.Second),
//	)
func NewClient(baseURL string, opts ...Option) *Client {
	c := &Client{
		baseURL: strings.TrimRight(baseURL, "/"),
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
	for _, o := range opts {
		o(c)
	}
	return c
}

// Close releases any resources held by the Client. It is safe to call
// multiple times.
func (c *Client) Close() {
	c.httpClient.CloseIdleConnections()
}

// Query executes a read CortexQL statement and returns the result rows.
func (c *Client) Query(ctx context.Context, cortexql string, params map[string]any) (*QueryResult, error) {
	body := map[string]any{"cortexql": cortexql}
	if params != nil {
		body["params"] = params
	}
	var result QueryResult
	if err := c.post(ctx, "/v1/query", body, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

// Write executes a write CortexQL statement (INSERT, UPDATE, DELETE).
func (c *Client) Write(ctx context.Context, cortexql string, params map[string]any) (*WriteResult, error) {
	body := map[string]any{"cortexql": cortexql}
	if params != nil {
		body["params"] = params
	}
	var result WriteResult
	if err := c.post(ctx, "/v1/write", body, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

// Health returns the readiness status of the CortexDB instance.
func (c *Client) Health(ctx context.Context) (*HealthResponse, error) {
	var h HealthResponse
	if err := c.get(ctx, "/health/ready", &h); err != nil {
		return nil, err
	}
	return &h, nil
}

// DeepHealth returns detailed health information from all CortexDB cores.
func (c *Client) DeepHealth(ctx context.Context) (map[string]any, error) {
	var result map[string]any
	if err := c.get(ctx, "/health/deep", &result); err != nil {
		return nil, err
	}
	return result, nil
}

// ---------------------------------------------------------------------------
// SuperAdminClient
// ---------------------------------------------------------------------------

// SuperAdminClient extends Client with authenticated super-admin operations.
type SuperAdminClient struct {
	*Client
	token string
}

// NewSuperAdminClient creates a SuperAdminClient. Call Login before using
// admin endpoints.
func NewSuperAdminClient(baseURL string, opts ...Option) *SuperAdminClient {
	return &SuperAdminClient{
		Client: NewClient(baseURL, opts...),
	}
}

// Login authenticates with the super-admin passphrase and stores the session
// token for subsequent requests.
func (s *SuperAdminClient) Login(ctx context.Context, passphrase string) error {
	body := map[string]any{"passphrase": passphrase}
	var resp struct {
		Token string `json:"token"`
	}
	if err := s.post(ctx, "/api/v1/auth/login", body, &resp); err != nil {
		return err
	}
	if resp.Token == "" {
		return &AuthError{StatusCode: 0, Body: "login succeeded but no token returned"}
	}
	s.token = resp.Token
	return nil
}

// ListAgents returns all registered agents.
func (s *SuperAdminClient) ListAgents(ctx context.Context) ([]Agent, error) {
	var agents []Agent
	if err := s.adminGet(ctx, "/api/v1/agents", &agents); err != nil {
		return nil, err
	}
	return agents, nil
}

// GetAgent returns a single agent by ID.
func (s *SuperAdminClient) GetAgent(ctx context.Context, id string) (*Agent, error) {
	var agent Agent
	if err := s.adminGet(ctx, "/api/v1/agents/"+id, &agent); err != nil {
		return nil, err
	}
	return &agent, nil
}

// CreateTask creates a new task and returns it.
func (s *SuperAdminClient) CreateTask(ctx context.Context, task CreateTaskInput) (*Task, error) {
	var result Task
	if err := s.adminPost(ctx, "/api/v1/tasks", task, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

// ListTasks returns all tasks visible to the super-admin.
func (s *SuperAdminClient) ListTasks(ctx context.Context) ([]Task, error) {
	var tasks []Task
	if err := s.adminGet(ctx, "/api/v1/tasks", &tasks); err != nil {
		return nil, err
	}
	return tasks, nil
}

// Chat sends a message to the specified agent and returns the response.
func (s *SuperAdminClient) Chat(ctx context.Context, agentID string, message string) (*ChatResponse, error) {
	body := map[string]any{
		"agent_id": agentID,
		"message":  message,
	}
	var resp ChatResponse
	if err := s.adminPost(ctx, "/api/v1/agents/chat", body, &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}

// MarketplaceList returns all available marketplace capabilities.
func (s *SuperAdminClient) MarketplaceList(ctx context.Context) ([]Capability, error) {
	var caps []Capability
	if err := s.adminGet(ctx, "/api/v1/marketplace/capabilities", &caps); err != nil {
		return nil, err
	}
	return caps, nil
}

// MarketplaceEnable activates a marketplace capability by ID.
func (s *SuperAdminClient) MarketplaceEnable(ctx context.Context, id string) error {
	return s.adminPost(ctx, "/api/v1/marketplace/capabilities/"+id+"/enable", nil, nil)
}

// MarketplaceDisable deactivates a marketplace capability by ID.
func (s *SuperAdminClient) MarketplaceDisable(ctx context.Context, id string) error {
	return s.adminPost(ctx, "/api/v1/marketplace/capabilities/"+id+"/disable", nil, nil)
}

// ---------------------------------------------------------------------------
// Internal HTTP helpers
// ---------------------------------------------------------------------------

func (c *Client) newRequest(ctx context.Context, method, path string, body io.Reader) (*http.Request, error) {
	req, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, body)
	if err != nil {
		return nil, &CortexDBError{Message: "failed to create request", Cause: err}
	}
	if c.apiKey != "" {
		req.Header.Set("X-API-Key", c.apiKey)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	req.Header.Set("Accept", "application/json")
	return req, nil
}

func (c *Client) do(req *http.Request, dest any) error {
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return &CortexDBError{Message: "request failed", Cause: err}
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return &CortexDBError{Message: "failed to read response body", Cause: err}
	}

	if resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden {
		return &AuthError{StatusCode: resp.StatusCode, Body: string(respBody)}
	}
	if resp.StatusCode >= 400 {
		return &QueryError{StatusCode: resp.StatusCode, Body: string(respBody)}
	}

	if dest != nil && len(respBody) > 0 {
		if err := json.Unmarshal(respBody, dest); err != nil {
			return &CortexDBError{Message: "failed to decode response", Cause: err}
		}
	}
	return nil
}

func (c *Client) get(ctx context.Context, path string, dest any) error {
	req, err := c.newRequest(ctx, http.MethodGet, path, nil)
	if err != nil {
		return err
	}
	return c.do(req, dest)
}

func (c *Client) post(ctx context.Context, path string, payload any, dest any) error {
	var body io.Reader
	if payload != nil {
		b, err := json.Marshal(payload)
		if err != nil {
			return &CortexDBError{Message: "failed to encode request body", Cause: err}
		}
		body = bytes.NewReader(b)
	}
	req, err := c.newRequest(ctx, http.MethodPost, path, body)
	if err != nil {
		return err
	}
	return c.do(req, dest)
}

func (s *SuperAdminClient) adminRequest(ctx context.Context, method, path string, body io.Reader) (*http.Request, error) {
	req, err := s.newRequest(ctx, method, path, body)
	if err != nil {
		return nil, err
	}
	if s.token != "" {
		req.Header.Set("Authorization", "Bearer "+s.token)
	}
	return req, nil
}

func (s *SuperAdminClient) adminGet(ctx context.Context, path string, dest any) error {
	req, err := s.adminRequest(ctx, http.MethodGet, path, nil)
	if err != nil {
		return err
	}
	return s.do(req, dest)
}

func (s *SuperAdminClient) adminPost(ctx context.Context, path string, payload any, dest any) error {
	var body io.Reader
	if payload != nil {
		b, err := json.Marshal(payload)
		if err != nil {
			return &CortexDBError{Message: "failed to encode request body", Cause: err}
		}
		body = bytes.NewReader(b)
	}
	req, err := s.adminRequest(ctx, http.MethodPost, path, body)
	if err != nil {
		return err
	}
	return s.do(req, dest)
}
