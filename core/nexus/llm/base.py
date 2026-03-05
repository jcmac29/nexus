"""Base classes for LLM providers."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator


class MessageRole(str, Enum):
    """Role of a message in a conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class LLMMessage:
    """A message in a conversation."""

    role: MessageRole
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        d = {"role": self.role.value, "content": self.content}
        if self.name:
            d["name"] = self.name
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d


@dataclass
class ToolDefinition:
    """Definition of a tool that can be called by the LLM."""

    name: str
    description: str
    parameters: dict[str, Any]

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI function format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }

    def to_anthropic_format(self) -> dict[str, Any]:
        """Convert to Anthropic tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


@dataclass
class ToolCall:
    """A tool call made by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Response from an LLM."""

    content: str
    model: str
    provider: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str | None = None
    raw_response: Any = None

    @property
    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls."""
        return len(self.tool_calls) > 0

    @property
    def input_tokens(self) -> int:
        """Get input token count."""
        return self.usage.get("input_tokens", 0)

    @property
    def output_tokens(self) -> int:
        """Get output token count."""
        return self.usage.get("output_tokens", 0)

    @property
    def total_tokens(self) -> int:
        """Get total token count."""
        return self.input_tokens + self.output_tokens


@dataclass
class LLMConfig:
    """Configuration for LLM requests."""

    model: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 1.0
    stop_sequences: list[str] | None = None
    tools: list[ToolDefinition] | None = None
    system_prompt: str | None = None

    # Streaming
    stream: bool = False

    # Provider-specific options
    extra_params: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    name: str = "base"

    def __init__(self, api_key: str | None = None):
        """Initialize the provider.

        Args:
            api_key: API key for the provider. If not provided,
                    will attempt to read from environment.
        """
        self.api_key = api_key or self._get_api_key()

    @abstractmethod
    def _get_api_key(self) -> str:
        """Get API key from environment."""
        pass

    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        """Generate a completion for the given messages.

        Args:
            messages: List of messages in the conversation.
            config: Configuration for the request.

        Returns:
            LLMResponse containing the completion.
        """
        pass

    @abstractmethod
    async def stream(
        self,
        messages: list[LLMMessage],
        config: LLMConfig | None = None,
    ) -> AsyncIterator[str]:
        """Stream a completion for the given messages.

        Args:
            messages: List of messages in the conversation.
            config: Configuration for the request.

        Yields:
            Chunks of the completion text.
        """
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in text.

        Args:
            text: Text to count tokens for.

        Returns:
            Number of tokens.
        """
        pass

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Get the default model for this provider."""
        pass

    @property
    @abstractmethod
    def available_models(self) -> list[str]:
        """Get list of available models for this provider."""
        pass
