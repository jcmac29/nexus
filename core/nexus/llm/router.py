"""LLM Router - Routes requests to the appropriate provider."""

from __future__ import annotations

import os
from typing import Any, AsyncIterator

from nexus.llm.base import (
    LLMConfig,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    MessageRole,
)
from nexus.llm.providers.anthropic import AnthropicProvider
from nexus.llm.providers.openai import OpenAIProvider


class LLMRouter:
    """Routes LLM requests to the appropriate provider.

    This is the core of "The Bridge" - enabling agents to use
    multiple AI providers seamlessly.
    """

    PROVIDERS: dict[str, type[LLMProvider]] = {
        "anthropic": AnthropicProvider,
        "claude": AnthropicProvider,  # Alias
        "openai": OpenAIProvider,
        "gpt": OpenAIProvider,  # Alias
    }

    def __init__(self):
        """Initialize the router with available providers."""
        self._providers: dict[str, LLMProvider] = {}
        self._default_provider = os.getenv("DEFAULT_LLM_PROVIDER", "anthropic")

    def _get_provider(self, name: str) -> LLMProvider:
        """Get or create a provider instance.

        Args:
            name: Provider name (anthropic, openai, etc.)

        Returns:
            Provider instance.

        Raises:
            ValueError: If provider is not supported.
        """
        name = name.lower()

        if name not in self._providers:
            if name not in self.PROVIDERS:
                raise ValueError(
                    f"Unknown provider: {name}. "
                    f"Available: {list(self.PROVIDERS.keys())}"
                )
            self._providers[name] = self.PROVIDERS[name]()

        return self._providers[name]

    @property
    def default_provider(self) -> LLMProvider:
        """Get the default provider."""
        return self._get_provider(self._default_provider)

    async def complete(
        self,
        messages: list[LLMMessage],
        config: LLMConfig | None = None,
        provider: str | None = None,
    ) -> LLMResponse:
        """Generate a completion.

        Args:
            messages: Conversation messages.
            config: LLM configuration.
            provider: Provider to use (defaults to DEFAULT_LLM_PROVIDER).

        Returns:
            LLM response.
        """
        provider_instance = (
            self._get_provider(provider) if provider else self.default_provider
        )
        return await provider_instance.complete(messages, config)

    async def stream(
        self,
        messages: list[LLMMessage],
        config: LLMConfig | None = None,
        provider: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream a completion.

        Args:
            messages: Conversation messages.
            config: LLM configuration.
            provider: Provider to use.

        Yields:
            Completion text chunks.
        """
        provider_instance = (
            self._get_provider(provider) if provider else self.default_provider
        )
        async for chunk in provider_instance.stream(messages, config):
            yield chunk

    async def chat(
        self,
        user_message: str,
        system_prompt: str | None = None,
        config: LLMConfig | None = None,
        provider: str | None = None,
    ) -> str:
        """Simple chat interface for single-turn conversations.

        Args:
            user_message: The user's message.
            system_prompt: Optional system prompt.
            config: LLM configuration.
            provider: Provider to use.

        Returns:
            Assistant's response text.
        """
        messages = []
        if system_prompt:
            messages.append(LLMMessage(role=MessageRole.SYSTEM, content=system_prompt))
        messages.append(LLMMessage(role=MessageRole.USER, content=user_message))

        response = await self.complete(messages, config, provider)
        return response.content

    def get_available_providers(self) -> list[str]:
        """Get list of available provider names."""
        available = []
        for name, provider_class in self.PROVIDERS.items():
            try:
                provider_class()
                available.append(name)
            except ValueError:
                # API key not configured
                pass
        return available

    def get_provider_info(self, name: str) -> dict[str, Any]:
        """Get information about a provider.

        Args:
            name: Provider name.

        Returns:
            Provider info including available models.
        """
        provider = self._get_provider(name)
        return {
            "name": provider.name,
            "default_model": provider.default_model,
            "available_models": provider.available_models,
        }


# Singleton instance
_router: LLMRouter | None = None


def get_llm_router() -> LLMRouter:
    """Get the global LLM router instance."""
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router
