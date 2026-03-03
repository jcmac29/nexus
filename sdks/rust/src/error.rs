//! Error types for the Nexus SDK.

use thiserror::Error;

/// Errors that can occur when using the Nexus SDK.
#[derive(Error, Debug)]
pub enum Error {
    /// HTTP request error.
    #[error("HTTP error: {0}")]
    Http(#[from] reqwest::Error),

    /// API error with status code and message.
    #[error("API error ({status}): {message}")]
    Api { status: u16, message: String },

    /// JSON serialization/deserialization error.
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),

    /// Invalid configuration.
    #[error("Invalid configuration: {0}")]
    Config(String),
}
