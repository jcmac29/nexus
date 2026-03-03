"""Configuration management for Nexus CLI."""

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class NexusConfig(BaseModel):
    """CLI configuration."""
    api_url: str = "http://localhost:8000"
    api_key: str | None = None
    agent_id: str | None = None
    agent_slug: str | None = None


def get_config_path() -> Path:
    """Get the config file path."""
    config_dir = Path.home() / ".nexus"
    config_dir.mkdir(exist_ok=True)
    return config_dir / "config.json"


def load_config() -> NexusConfig:
    """Load configuration from file and environment."""
    config_path = get_config_path()

    # Start with defaults
    config_data: dict[str, Any] = {}

    # Load from file if exists
    if config_path.exists():
        with open(config_path) as f:
            config_data = json.load(f)

    # Override with environment variables
    if url := os.environ.get("NEXUS_API_URL"):
        config_data["api_url"] = url
    if key := os.environ.get("NEXUS_API_KEY"):
        config_data["api_key"] = key

    return NexusConfig(**config_data)


def save_config(config: NexusConfig) -> None:
    """Save configuration to file."""
    config_path = get_config_path()
    with open(config_path, "w") as f:
        json.dump(config.model_dump(), f, indent=2)


def clear_config() -> None:
    """Clear saved configuration."""
    config_path = get_config_path()
    if config_path.exists():
        config_path.unlink()
