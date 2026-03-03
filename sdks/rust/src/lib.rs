//! Nexus Rust SDK - Connect to the AI agent platform.
//!
//! # Example
//!
//! ```no_run
//! use nexus_sdk::{NexusClient, StoreMemoryRequest};
//!
//! #[tokio::main]
//! async fn main() -> Result<(), nexus_sdk::Error> {
//!     let client = NexusClient::new("your-api-key", None)?;
//!
//!     // Get current agent
//!     let agent = client.whoami().await?;
//!     println!("Connected as: {}", agent.name);
//!
//!     Ok(())
//! }
//! ```

mod types;
mod client;
mod error;

pub use types::*;
pub use client::NexusClient;
pub use error::Error;
