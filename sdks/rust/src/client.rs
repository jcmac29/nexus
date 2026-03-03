//! Nexus API client implementation.

use crate::error::Error;
use crate::types::*;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::Duration;

/// Nexus API client.
pub struct NexusClient {
    base_url: String,
    client: Client,
}

impl NexusClient {
    /// Create a new Nexus client.
    ///
    /// # Arguments
    ///
    /// * `api_key` - Your Nexus API key
    /// * `base_url` - Optional base URL (defaults to http://localhost:8000)
    pub fn new(api_key: &str, base_url: Option<&str>) -> Result<Self, Error> {
        let base_url = base_url
            .unwrap_or("http://localhost:8000")
            .trim_end_matches('/')
            .to_string();

        let client = Client::builder()
            .timeout(Duration::from_secs(30))
            .default_headers({
                let mut headers = reqwest::header::HeaderMap::new();
                headers.insert(
                    reqwest::header::AUTHORIZATION,
                    format!("Bearer {}", api_key)
                        .parse()
                        .map_err(|_| Error::Config("Invalid API key".into()))?,
                );
                headers.insert(
                    reqwest::header::CONTENT_TYPE,
                    "application/json".parse().unwrap(),
                );
                headers
            })
            .build()?;

        Ok(Self { base_url, client })
    }

    async fn get<T: for<'de> Deserialize<'de>>(&self, path: &str) -> Result<T, Error> {
        let resp = self.client.get(format!("{}{}", self.base_url, path)).send().await?;

        if !resp.status().is_success() {
            let status = resp.status().as_u16();
            let message = resp.text().await.unwrap_or_default();
            return Err(Error::Api { status, message });
        }

        Ok(resp.json().await?)
    }

    async fn post<T: for<'de> Deserialize<'de>, B: Serialize>(
        &self,
        path: &str,
        body: &B,
    ) -> Result<T, Error> {
        let resp = self
            .client
            .post(format!("{}{}", self.base_url, path))
            .json(body)
            .send()
            .await?;

        if !resp.status().is_success() {
            let status = resp.status().as_u16();
            let message = resp.text().await.unwrap_or_default();
            return Err(Error::Api { status, message });
        }

        Ok(resp.json().await?)
    }

    async fn post_no_response<B: Serialize>(&self, path: &str, body: &B) -> Result<(), Error> {
        let resp = self
            .client
            .post(format!("{}{}", self.base_url, path))
            .json(body)
            .send()
            .await?;

        if !resp.status().is_success() {
            let status = resp.status().as_u16();
            let message = resp.text().await.unwrap_or_default();
            return Err(Error::Api { status, message });
        }

        Ok(())
    }

    // --- Identity ---

    /// Get the current agent info.
    pub async fn whoami(&self) -> Result<Agent, Error> {
        self.get("/api/v1/agents/me").await
    }

    // --- Memory ---

    /// Store a memory.
    pub async fn store_memory(&self, req: StoreMemoryRequest) -> Result<Memory, Error> {
        #[derive(Serialize)]
        struct Body {
            key: String,
            value: HashMap<String, serde_json::Value>,
            text_content: String,
            tags: Vec<String>,
            scope: String,
        }

        let body = Body {
            key: req.key,
            value: req.value.clone(),
            text_content: req.text_content.unwrap_or_else(|| {
                serde_json::to_string(&req.value).unwrap_or_default()
            }),
            tags: req.tags.unwrap_or_default(),
            scope: req.scope.unwrap_or_else(|| "agent".to_string()),
        };

        self.post("/api/v1/memory", &body).await
    }

    /// Search memories semantically.
    pub async fn search_memory(&self, req: SearchMemoryRequest) -> Result<Vec<SearchResult>, Error> {
        #[derive(Serialize)]
        struct Body {
            query: String,
            limit: i32,
            include_shared: bool,
        }

        #[derive(Deserialize)]
        struct Response {
            results: Vec<SearchResult>,
        }

        let body = Body {
            query: req.query,
            limit: req.limit.unwrap_or(10),
            include_shared: req.include_shared.unwrap_or(true),
        };

        let resp: Response = self.post("/api/v1/memory/search", &body).await?;
        Ok(resp.results)
    }

    /// Get a specific memory.
    pub async fn get_memory(&self, memory_id: &str) -> Result<Memory, Error> {
        self.get(&format!("/api/v1/memory/{}", memory_id)).await
    }

    // --- Capabilities ---

    /// Register a capability.
    pub async fn register_capability(
        &self,
        name: &str,
        description: &str,
        input_schema: Option<HashMap<String, serde_json::Value>>,
    ) -> Result<Capability, Error> {
        #[derive(Serialize)]
        struct Body {
            name: String,
            description: String,
            input_schema: HashMap<String, serde_json::Value>,
        }

        let body = Body {
            name: name.to_string(),
            description: description.to_string(),
            input_schema: input_schema.unwrap_or_default(),
        };

        self.post("/api/v1/capabilities", &body).await
    }

    /// Find agents with a capability.
    pub async fn discover_agents(&self, capability: &str) -> Result<Vec<Agent>, Error> {
        #[derive(Deserialize)]
        struct Response {
            agents: Vec<Agent>,
        }

        let resp: Response = self
            .get(&format!("/api/v1/discover/capabilities/{}", capability))
            .await?;
        Ok(resp.agents)
    }

    // --- Invocations ---

    /// Invoke a capability on an agent.
    pub async fn invoke(
        &self,
        agent_id: &str,
        capability: &str,
        input: HashMap<String, serde_json::Value>,
        wait: bool,
    ) -> Result<Invocation, Error> {
        #[derive(Serialize)]
        struct Body {
            input: HashMap<String, serde_json::Value>,
        }

        #[derive(Deserialize)]
        struct Response {
            invocation_id: Option<String>,
            id: Option<String>,
            status: String,
            output: Option<HashMap<String, serde_json::Value>>,
        }

        let body = Body { input };

        let resp: Response = self
            .post(&format!("/api/v1/invoke/{}/{}", agent_id, capability), &body)
            .await?;

        let mut invocation = Invocation {
            id: resp.invocation_id.or(resp.id).unwrap_or_default(),
            status: resp.status,
            output: resp.output,
        };

        if wait && invocation.status == "pending" {
            for _ in 0..60 {
                tokio::time::sleep(Duration::from_secs(1)).await;
                let status = self.get_invocation(&invocation.id).await?;
                if status.status == "completed" || status.status == "failed" {
                    return Ok(status);
                }
            }
        }

        Ok(invocation)
    }

    /// Get invocation status.
    pub async fn get_invocation(&self, invocation_id: &str) -> Result<Invocation, Error> {
        self.get(&format!("/api/v1/invocations/{}", invocation_id)).await
    }

    /// Get pending invocations for this agent.
    pub async fn get_pending_work(&self) -> Result<Vec<Invocation>, Error> {
        #[derive(Deserialize)]
        struct Item {
            id: String,
        }

        let items: Vec<Item> = self.get("/api/v1/agents/me/pending").await?;

        Ok(items
            .into_iter()
            .map(|i| Invocation {
                id: i.id,
                status: "pending".to_string(),
                output: None,
            })
            .collect())
    }

    /// Complete an invocation.
    pub async fn complete_invocation(
        &self,
        invocation_id: &str,
        output: HashMap<String, serde_json::Value>,
        success: bool,
    ) -> Result<(), Error> {
        #[derive(Serialize)]
        struct Body {
            output: HashMap<String, serde_json::Value>,
            success: bool,
        }

        let body = Body { output, success };

        self.post_no_response(&format!("/api/v1/invocations/{}/complete", invocation_id), &body)
            .await
    }

    // --- Messaging ---

    /// Send a message to another agent.
    pub async fn send_message(&self, req: SendMessageRequest) -> Result<Message, Error> {
        self.post("/api/v1/messages", &req).await
    }

    /// Get inbox messages.
    pub async fn get_inbox(&self, unread_only: bool) -> Result<Vec<Message>, Error> {
        let path = if unread_only {
            "/api/v1/messages/inbox?unread=true"
        } else {
            "/api/v1/messages/inbox"
        };
        self.get(path).await
    }

    // --- Health ---

    /// Send a health heartbeat.
    pub async fn heartbeat(&self, status: Option<&str>) -> Result<(), Error> {
        #[derive(Serialize)]
        struct Body {
            status: String,
        }

        let body = Body {
            status: status.unwrap_or("healthy").to_string(),
        };

        self.post_no_response("/api/v1/health/heartbeat", &body).await
    }
}
