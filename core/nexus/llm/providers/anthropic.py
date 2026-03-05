"""Anthropic Claude LLM provider."""

from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator

import httpx

from nexus.llm.base import (
    LLMConfig,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    MessageRole,
    ToolCall,
)


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider implementation."""

    name = "anthropic"
    API_BASE = "https://api.anthropic.com/v1"
    API_VERSION = "2023-06-01"

    MODELS = [
        "claude-sonnet-4-20250514",
        "claude-opus-4-20250514",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
    ]

    def _get_api_key(self) -> str:
        """Get API key from environment."""
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError(
                "ANTHROPIC_API_KEY not found in environment. "
                "Set it to use the Anthropic provider."
            )
        return key

    @property
    def default_model(self) -> str:
        """Get the default model."""
        return os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

    @property
    def available_models(self) -> list[str]:
        """Get available models."""
        return self.MODELS

    def _build_messages(
        self, messages: list[LLMMessage]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Build Anthropic message format.

        Returns:
            Tuple of (system_prompt, messages).
        """
        system_prompt = None
        formatted_messages = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system_prompt = msg.content
            elif msg.role == MessageRole.TOOL:
                # Tool results in Anthropic format
                formatted_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content,
                    }]
                })
            elif msg.role == MessageRole.ASSISTANT and msg.tool_calls:
                # Assistant message with tool calls
                content = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                formatted_messages.append({
                    "role": "assistant",
                    "content": content,
                })
            else:
                formatted_messages.append({
                    "role": msg.role.value,
                    "content": msg.content,
                })

        return system_prompt, formatted_messages

    def _parse_response(self, data: dict[str, Any], model: str) -> LLMResponse:
        """Parse Anthropic API response."""
        content = ""
        tool_calls = []

        for block in data.get("content", []):
            if block["type"] == "text":
                content += block["text"]
            elif block["type"] == "tool_use":
                tool_calls.append(ToolCall(
                    id=block["id"],
                    name=block["name"],
                    arguments=block["input"],
                ))

        usage = data.get("usage", {})

        return LLMResponse(
            content=content,
            model=model,
            provider=self.name,
            tool_calls=tool_calls,
            usage={
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            },
            finish_reason=data.get("stop_reason"),
            raw_response=data,
        )

    async def complete(
        self,
        messages: list[LLMMessage],
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        """Generate a completion using Claude."""
        config = config or LLMConfig()
        model = config.model or self.default_model

        system_prompt, formatted_messages = self._build_messages(messages)

        # Override with config system prompt if provided
        if config.system_prompt:
            system_prompt = config.system_prompt

        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": config.max_tokens,
            "messages": formatted_messages,
        }

        if system_prompt:
            payload["system"] = system_prompt

        if config.temperature is not None:
            payload["temperature"] = config.temperature

        if config.top_p is not None:
            payload["top_p"] = config.top_p

        if config.stop_sequences:
            payload["stop_sequences"] = config.stop_sequences

        if config.tools:
            payload["tools"] = [t.to_anthropic_format() for t in config.tools]

        # Merge extra params
        payload.update(config.extra_params)

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.API_BASE}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": self.API_VERSION,
                    "content-type": "application/json",
                },
                json=payload,
            )

            if response.status_code != 200:
                error_data = response.json()
                raise Exception(
                    f"Anthropic API error: {error_data.get('error', {}).get('message', response.text)}"
                )

            return self._parse_response(response.json(), model)

    async def stream(
        self,
        messages: list[LLMMessage],
        config: LLMConfig | None = None,
    ) -> AsyncIterator[str]:
        """Stream a completion using Claude."""
        config = config or LLMConfig()
        model = config.model or self.default_model

        system_prompt, formatted_messages = self._build_messages(messages)

        if config.system_prompt:
            system_prompt = config.system_prompt

        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": config.max_tokens,
            "messages": formatted_messages,
            "stream": True,
        }

        if system_prompt:
            payload["system"] = system_prompt

        if config.temperature is not None:
            payload["temperature"] = config.temperature

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.API_BASE}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": self.API_VERSION,
                    "content-type": "application/json",
                },
                json=payload,
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        if data["type"] == "content_block_delta":
                            delta = data.get("delta", {})
                            if delta.get("type") == "text_delta":
                                yield delta.get("text", "")

    def count_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Note: This is an approximation. For exact counts,
        use the Anthropic tokenizer API.
        """
        # Rough estimate: ~4 characters per token for English text
        return len(text) // 4
