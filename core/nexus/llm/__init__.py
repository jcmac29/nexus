"""LLM abstraction layer - The Bridge.

This module provides a unified interface for multiple AI model providers,
enabling agents to leverage Claude, GPT, and other models interchangeably.
"""

from nexus.llm.base import (
    LLMProvider,
    LLMMessage,
    LLMResponse,
    LLMConfig,
    ToolDefinition,
    ToolCall,
)
from nexus.llm.router import LLMRouter, get_llm_router

__all__ = [
    "LLMProvider",
    "LLMMessage",
    "LLMResponse",
    "LLMConfig",
    "ToolDefinition",
    "ToolCall",
    "LLMRouter",
    "get_llm_router",
]
