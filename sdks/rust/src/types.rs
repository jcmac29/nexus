//! Type definitions for the Nexus SDK.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// An AI agent in Nexus.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Agent {
    pub id: String,
    pub name: String,
    pub slug: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
}

/// A stored memory.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Memory {
    pub id: String,
    pub key: String,
    pub value: HashMap<String, serde_json::Value>,
    #[serde(default)]
    pub tags: Vec<String>,
}

/// An agent capability.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Capability {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub input_schema: Option<HashMap<String, serde_json::Value>>,
}

/// A capability invocation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Invocation {
    pub id: String,
    pub status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub output: Option<HashMap<String, serde_json::Value>>,
}

/// A message between agents.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    pub id: String,
    pub from_agent_id: String,
    pub subject: String,
    pub body: String,
}

/// A memory search result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    pub memory: Memory,
    pub score: f64,
}

/// Request to store a memory.
#[derive(Debug, Clone, Serialize)]
pub struct StoreMemoryRequest {
    pub key: String,
    pub value: HashMap<String, serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub text_content: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tags: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub scope: Option<String>,
}

/// Request to search memories.
#[derive(Debug, Clone, Serialize)]
pub struct SearchMemoryRequest {
    pub query: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub limit: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub include_shared: Option<bool>,
}

/// Request to send a message.
#[derive(Debug, Clone, Serialize)]
pub struct SendMessageRequest {
    pub to_agent_id: String,
    pub subject: String,
    pub body: String,
}
