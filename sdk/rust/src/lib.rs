//! # CortexDB Client
//!
//! Official Rust client library for CortexDB. Provides async access to core
//! database operations (query, write, health) and authenticated super-admin
//! endpoints (agents, tasks, chat, marketplace).
//!
//! # Quick Start
//!
//! ```rust,no_run
//! use cortexdb_client::CortexDBClient;
//!
//! #[tokio::main]
//! async fn main() -> Result<(), Box<dyn std::error::Error>> {
//!     let client = CortexDBClient::new("http://localhost:3001");
//!     let health = client.health().await?;
//!     println!("Status: {}", health.status);
//!     Ok(())
//! }
//! ```

use std::time::Duration;

use reqwest::header::{HeaderMap, HeaderValue, ACCEPT, AUTHORIZATION, CONTENT_TYPE};
use serde::{Deserialize, Serialize};
use serde_json::Value;

// ---------------------------------------------------------------------------
// Error types
// ---------------------------------------------------------------------------

/// Errors returned by the CortexDB client.
#[derive(Debug, thiserror::Error)]
pub enum CortexDBError {
    /// A network or connection-level failure.
    #[error("connection error: {0}")]
    Connection(#[from] reqwest::Error),

    /// Authentication or authorization failure (HTTP 401/403).
    #[error("auth error ({status}): {body}")]
    Auth { status: u16, body: String },

    /// The server rejected or failed to execute a query.
    #[error("query error ({status}): {body}")]
    Query { status: u16, body: String },

    /// A general API error with status code and response body.
    #[error("api error ({0}): {1}")]
    Api(u16, String),

    /// Failed to serialize or deserialize JSON.
    #[error("serialization error: {0}")]
    Serialization(#[from] serde_json::Error),
}

// ---------------------------------------------------------------------------
// Domain types
// ---------------------------------------------------------------------------

/// Result of a CortexQL read query.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueryResult {
    pub rows: Vec<Value>,
    #[serde(default)]
    pub columns: Vec<String>,
    #[serde(default)]
    pub count: usize,
}

/// Result of a CortexQL write operation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WriteResult {
    pub rows_affected: usize,
    #[serde(default)]
    pub inserted_id: Option<Value>,
}

/// Readiness status of a CortexDB instance.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HealthResponse {
    pub status: String,
    #[serde(default)]
    pub timestamp: String,
    #[serde(default)]
    pub version: Option<String>,
}

/// A CortexDB managed agent.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Agent {
    pub id: String,
    pub name: String,
    pub tier: String,
    pub department: String,
    pub role: String,
    pub status: String,
    #[serde(default)]
    pub config: Option<Value>,
    #[serde(default)]
    pub created_at: String,
    #[serde(default)]
    pub updated_at: String,
}

/// Payload for creating a new task.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreateTask {
    pub agent_id: String,
    #[serde(rename = "type")]
    pub task_type: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub priority: Option<String>,
    pub instruction: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub input: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parent_id: Option<String>,
}

/// A CortexDB task.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Task {
    pub id: String,
    pub agent_id: String,
    #[serde(rename = "type")]
    pub task_type: String,
    pub status: String,
    #[serde(default)]
    pub priority: String,
    #[serde(default)]
    pub instruction: String,
    #[serde(default)]
    pub input: Option<Value>,
    #[serde(default)]
    pub output: Option<Value>,
    #[serde(default)]
    pub parent_id: Option<String>,
    #[serde(default)]
    pub created_at: String,
    #[serde(default)]
    pub updated_at: String,
}

/// Response from an agent chat interaction.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatResponse {
    pub response: String,
    pub agent_id: String,
    #[serde(default)]
    pub tool_calls: Vec<ToolCall>,
    #[serde(default)]
    pub metadata: Option<Value>,
}

/// A single tool invocation made during chat.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCall {
    pub name: String,
    #[serde(default)]
    pub input: Option<Value>,
    #[serde(default)]
    pub output: Option<Value>,
}

/// A marketplace capability or integration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Capability {
    pub id: String,
    pub name: String,
    pub description: String,
    pub category: String,
    pub enabled: bool,
    #[serde(default)]
    pub version: Option<String>,
}

// ---------------------------------------------------------------------------
// Internal request payloads
// ---------------------------------------------------------------------------

#[derive(Serialize)]
struct QueryPayload<'a> {
    cortexql: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    params: Option<Value>,
}

#[derive(Serialize)]
struct ChatPayload<'a> {
    agent_id: &'a str,
    message: &'a str,
}

#[derive(Serialize)]
struct LoginPayload<'a> {
    passphrase: &'a str,
}

#[derive(Deserialize)]
struct LoginResponse {
    token: String,
}

// ---------------------------------------------------------------------------
// CortexDBClient
// ---------------------------------------------------------------------------

/// Client for CortexDB core operations (query, write, health).
///
/// # Example
///
/// ```rust,no_run
/// use cortexdb_client::CortexDBClient;
///
/// # async fn example() -> Result<(), cortexdb_client::CortexDBError> {
/// let client = CortexDBClient::with_api_key("http://localhost:3001", "my-key");
/// let result = client.query("SELECT 1", None).await?;
/// println!("{:?}", result);
/// # Ok(())
/// # }
/// ```
#[derive(Debug, Clone)]
pub struct CortexDBClient {
    base_url: String,
    api_key: Option<String>,
    client: reqwest::Client,
}

impl CortexDBClient {
    /// Create a new client without an API key.
    pub fn new(base_url: &str) -> Self {
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .expect("failed to build HTTP client");

        Self {
            base_url: base_url.trim_end_matches('/').to_string(),
            api_key: None,
            client,
        }
    }

    /// Create a new client with an API key.
    pub fn with_api_key(base_url: &str, api_key: &str) -> Self {
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .expect("failed to build HTTP client");

        Self {
            base_url: base_url.trim_end_matches('/').to_string(),
            api_key: Some(api_key.to_string()),
            client,
        }
    }

    /// Create a client with a custom reqwest::Client for advanced configuration.
    pub fn with_client(base_url: &str, api_key: Option<&str>, client: reqwest::Client) -> Self {
        Self {
            base_url: base_url.trim_end_matches('/').to_string(),
            api_key: api_key.map(String::from),
            client,
        }
    }

    /// Execute a read CortexQL query.
    pub async fn query(
        &self,
        cortexql: &str,
        params: Option<Value>,
    ) -> Result<QueryResult, CortexDBError> {
        let payload = QueryPayload { cortexql, params };
        self.post("/v1/query", &payload).await
    }

    /// Execute a write CortexQL statement (INSERT, UPDATE, DELETE).
    pub async fn write(
        &self,
        cortexql: &str,
        params: Option<Value>,
    ) -> Result<WriteResult, CortexDBError> {
        let payload = QueryPayload { cortexql, params };
        self.post("/v1/write", &payload).await
    }

    /// Check instance readiness.
    pub async fn health(&self) -> Result<HealthResponse, CortexDBError> {
        self.get("/health/ready").await
    }

    /// Get detailed health information from all CortexDB cores.
    pub async fn deep_health(&self) -> Result<Value, CortexDBError> {
        self.get("/health/deep").await
    }

    // -- internal helpers ---------------------------------------------------

    fn default_headers(&self) -> HeaderMap {
        let mut headers = HeaderMap::new();
        headers.insert(ACCEPT, HeaderValue::from_static("application/json"));
        if let Some(ref key) = self.api_key {
            if let Ok(val) = HeaderValue::from_str(key) {
                headers.insert("X-API-Key", val);
            }
        }
        headers
    }

    async fn get<T: serde::de::DeserializeOwned>(&self, path: &str) -> Result<T, CortexDBError> {
        let url = format!("{}{}", self.base_url, path);
        let resp = self
            .client
            .get(&url)
            .headers(self.default_headers())
            .send()
            .await?;
        handle_response(resp).await
    }

    async fn post<T: serde::de::DeserializeOwned, B: Serialize>(
        &self,
        path: &str,
        body: &B,
    ) -> Result<T, CortexDBError> {
        let url = format!("{}{}", self.base_url, path);
        let resp = self
            .client
            .post(&url)
            .headers(self.default_headers())
            .header(CONTENT_TYPE, "application/json")
            .json(body)
            .send()
            .await?;
        handle_response(resp).await
    }
}

// ---------------------------------------------------------------------------
// SuperAdminClient
// ---------------------------------------------------------------------------

/// Client for authenticated super-admin operations.
///
/// # Example
///
/// ```rust,no_run
/// use cortexdb_client::SuperAdminClient;
///
/// # async fn example() -> Result<(), cortexdb_client::CortexDBError> {
/// let mut admin = SuperAdminClient::new("http://localhost:3001", Some("my-key"));
/// admin.login("my-passphrase").await?;
/// let agents = admin.list_agents().await?;
/// for a in &agents {
///     println!("{}: {}", a.id, a.name);
/// }
/// # Ok(())
/// # }
/// ```
#[derive(Debug, Clone)]
pub struct SuperAdminClient {
    inner: CortexDBClient,
    token: Option<String>,
}

impl SuperAdminClient {
    /// Create a new super-admin client. Call [`login`](Self::login) before
    /// using admin endpoints.
    pub fn new(base_url: &str, api_key: Option<&str>) -> Self {
        let inner = match api_key {
            Some(key) => CortexDBClient::with_api_key(base_url, key),
            None => CortexDBClient::new(base_url),
        };
        Self {
            inner,
            token: None,
        }
    }

    /// Access the underlying [`CortexDBClient`] for core operations.
    pub fn core(&self) -> &CortexDBClient {
        &self.inner
    }

    /// Authenticate with the super-admin passphrase.
    pub async fn login(&mut self, passphrase: &str) -> Result<(), CortexDBError> {
        let payload = LoginPayload { passphrase };
        let url = format!("{}/api/v1/auth/login", self.inner.base_url);
        let resp = self
            .inner
            .client
            .post(&url)
            .headers(self.inner.default_headers())
            .header(CONTENT_TYPE, "application/json")
            .json(&payload)
            .send()
            .await?;
        let login: LoginResponse = handle_response(resp).await?;
        self.token = Some(login.token);
        Ok(())
    }

    /// List all registered agents.
    pub async fn list_agents(&self) -> Result<Vec<Agent>, CortexDBError> {
        self.admin_get("/api/v1/agents").await
    }

    /// Get a single agent by ID.
    pub async fn get_agent(&self, id: &str) -> Result<Agent, CortexDBError> {
        self.admin_get(&format!("/api/v1/agents/{}", id)).await
    }

    /// Create a new task.
    pub async fn create_task(&self, task: &CreateTask) -> Result<Task, CortexDBError> {
        self.admin_post("/api/v1/tasks", task).await
    }

    /// List all tasks.
    pub async fn list_tasks(&self) -> Result<Vec<Task>, CortexDBError> {
        self.admin_get("/api/v1/tasks").await
    }

    /// Chat with an agent.
    pub async fn chat(
        &self,
        agent_id: &str,
        message: &str,
    ) -> Result<ChatResponse, CortexDBError> {
        let payload = ChatPayload { agent_id, message };
        self.admin_post("/api/v1/agents/chat", &payload).await
    }

    /// List marketplace capabilities.
    pub async fn marketplace_list(&self) -> Result<Vec<Capability>, CortexDBError> {
        self.admin_get("/api/v1/marketplace/capabilities").await
    }

    /// Enable a marketplace capability.
    pub async fn marketplace_enable(&self, id: &str) -> Result<(), CortexDBError> {
        let url = format!(
            "{}/api/v1/marketplace/capabilities/{}/enable",
            self.inner.base_url, id
        );
        let resp = self
            .inner
            .client
            .post(&url)
            .headers(self.auth_headers())
            .send()
            .await?;
        handle_response_unit(resp).await
    }

    /// Disable a marketplace capability.
    pub async fn marketplace_disable(&self, id: &str) -> Result<(), CortexDBError> {
        let url = format!(
            "{}/api/v1/marketplace/capabilities/{}/disable",
            self.inner.base_url, id
        );
        let resp = self
            .inner
            .client
            .post(&url)
            .headers(self.auth_headers())
            .send()
            .await?;
        handle_response_unit(resp).await
    }

    // -- internal helpers ---------------------------------------------------

    fn auth_headers(&self) -> HeaderMap {
        let mut headers = self.inner.default_headers();
        if let Some(ref token) = self.token {
            if let Ok(val) = HeaderValue::from_str(&format!("Bearer {}", token)) {
                headers.insert(AUTHORIZATION, val);
            }
        }
        headers
    }

    async fn admin_get<T: serde::de::DeserializeOwned>(
        &self,
        path: &str,
    ) -> Result<T, CortexDBError> {
        let url = format!("{}{}", self.inner.base_url, path);
        let resp = self
            .inner
            .client
            .get(&url)
            .headers(self.auth_headers())
            .send()
            .await?;
        handle_response(resp).await
    }

    async fn admin_post<T: serde::de::DeserializeOwned, B: Serialize>(
        &self,
        path: &str,
        body: &B,
    ) -> Result<T, CortexDBError> {
        let url = format!("{}{}", self.inner.base_url, path);
        let resp = self
            .inner
            .client
            .post(&url)
            .headers(self.auth_headers())
            .header(CONTENT_TYPE, "application/json")
            .json(body)
            .send()
            .await?;
        handle_response(resp).await
    }
}

// ---------------------------------------------------------------------------
// Shared response handling
// ---------------------------------------------------------------------------

async fn handle_response<T: serde::de::DeserializeOwned>(
    resp: reqwest::Response,
) -> Result<T, CortexDBError> {
    let status = resp.status().as_u16();
    if status == 401 || status == 403 {
        let body = resp.text().await.unwrap_or_default();
        return Err(CortexDBError::Auth { status, body });
    }
    if status >= 400 {
        let body = resp.text().await.unwrap_or_default();
        if status == 422 || (400..500).contains(&status) {
            return Err(CortexDBError::Query {
                status,
                body,
            });
        }
        return Err(CortexDBError::Api(status, body));
    }
    let body = resp.text().await.unwrap_or_default();
    let parsed: T = serde_json::from_str(&body)?;
    Ok(parsed)
}

async fn handle_response_unit(resp: reqwest::Response) -> Result<(), CortexDBError> {
    let status = resp.status().as_u16();
    if status == 401 || status == 403 {
        let body = resp.text().await.unwrap_or_default();
        return Err(CortexDBError::Auth { status, body });
    }
    if status >= 400 {
        let body = resp.text().await.unwrap_or_default();
        return Err(CortexDBError::Api(status, body));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_client_new() {
        let client = CortexDBClient::new("http://localhost:3001/");
        assert_eq!(client.base_url, "http://localhost:3001");
        assert!(client.api_key.is_none());
    }

    #[test]
    fn test_client_with_api_key() {
        let client = CortexDBClient::with_api_key("http://localhost:3001", "test-key");
        assert_eq!(client.api_key.as_deref(), Some("test-key"));
    }

    #[test]
    fn test_super_admin_new() {
        let admin = SuperAdminClient::new("http://localhost:3001", Some("key"));
        assert!(admin.token.is_none());
        assert_eq!(admin.core().api_key.as_deref(), Some("key"));
    }

    #[test]
    fn test_create_task_serialization() {
        let task = CreateTask {
            agent_id: "T1-OPS-POS-001".to_string(),
            task_type: "analysis".to_string(),
            priority: Some("high".to_string()),
            instruction: "Analyze performance".to_string(),
            input: None,
            parent_id: None,
        };
        let json = serde_json::to_value(&task).unwrap();
        assert_eq!(json["agent_id"], "T1-OPS-POS-001");
        assert_eq!(json["type"], "analysis");
        assert!(json.get("input").is_none());
    }

    #[test]
    fn test_error_display() {
        let err = CortexDBError::Auth {
            status: 401,
            body: "unauthorized".to_string(),
        };
        assert!(err.to_string().contains("401"));
        assert!(err.to_string().contains("unauthorized"));

        let err = CortexDBError::Api(500, "internal error".to_string());
        assert!(err.to_string().contains("500"));
    }
}
