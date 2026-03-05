"""OpenAI GPT LLM provider."""

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


class OpenAIProvider(LLMProvider):
    """OpenAI GPT provider implementation."""

    name = "openai"
    API_BASE = "https://api.openai.com/v1"

    MODELS = [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
        "o1-preview",
        "o1-mini",
    ]

    def _get_api_key(self) -> str:
        """Get API key from environment."""
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError(
                "OPENAI_API_KEY not found in environment. "
                "Set it to use the OpenAI provider."
            )
        return key

    @property
    def default_model(self) -> str:
        """Get the default model."""
        return os.getenv("OPENAI_MODEL", "gpt-4o")

    @property
    def available_models(self) -> list[str]:
        """Get available models."""
        return self.MODELS

    def _build_messages(
        self, messages: list[LLMMessage], system_prompt: str | None = None
    ) -> list[dict[str, Any]]:
        """Build OpenAI message format."""
        formatted_messages = []

        # Add system prompt first if provided
        if system_prompt:
            formatted_messages.append({
                "role": "system",
                "content": system_prompt,
            })

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                formatted_messages.append({
                    "role": "system",
                    "content": msg.content,
                })
            elif msg.role == MessageRole.TOOL:
                formatted_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content,
                })
            elif msg.role == MessageRole.ASSISTANT and msg.tool_calls:
                tool_calls_formatted = []
                for tc in msg.tool_calls:
                    tool_calls_formatted.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        }
                    })
                formatted_messages.append({
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": tool_calls_formatted,
                })
            else:
                formatted_messages.append({
                    "role": msg.role.value,
                    "content": msg.content,
                })

        return formatted_messages

    def _parse_response(self, data: dict[str, Any], model: str) -> LLMResponse:
        """Parse OpenAI API response."""
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})

        content = message.get("content", "") or ""
        tool_calls = []

        for tc in message.get("tool_calls", []):
            if tc["type"] == "function":
                tool_calls.append(ToolCall(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=json.loads(tc["function"]["arguments"]),
                ))

        usage = data.get("usage", {})

        return LLMResponse(
            content=content,
            model=model,
            provider=self.name,
            tool_calls=tool_calls,
            usage={
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
            },
            finish_reason=choice.get("finish_reason"),
            raw_response=data,
        )

    async def complete(
        self,
        messages: list[LLMMessage],
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        """Generate a completion using GPT."""
        config = config or LLMConfig()
        model = config.model or self.default_model

        formatted_messages = self._build_messages(messages, config.system_prompt)

        payload: dict[str, Any] = {
            "model": model,
            "messages": formatted_messages,
        }

        if config.max_tokens:
            payload["max_tokens"] = config.max_tokens

        if config.temperature is not None:
            payload["temperature"] = config.temperature

        if config.top_p is not None:
            payload["top_p"] = config.top_p

        if config.stop_sequences:
            payload["stop"] = config.stop_sequences

        if config.tools:
            payload["tools"] = [t.to_openai_format() for t in config.tools]

        # Merge extra params
        payload.update(config.extra_params)

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

            if response.status_code != 200:
                error_data = response.json()
                raise Exception(
                    f"OpenAI API error: {error_data.get('error', {}).get('message', response.text)}"
                )

            return self._parse_response(response.json(), model)

    async def stream(
        self,
        messages: list[LLMMessage],
        config: LLMConfig | None = None,
    ) -> AsyncIterator[str]:
        """Stream a completion using GPT."""
        config = config or LLMConfig()
        model = config.model or self.default_model

        formatted_messages = self._build_messages(messages, config.system_prompt)

        payload: dict[str, Any] = {
            "model": model,
            "messages": formatted_messages,
            "stream": True,
        }

        if config.max_tokens:
            payload["max_tokens"] = config.max_tokens

        if config.temperature is not None:
            payload["temperature"] = config.temperature

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        data = json.loads(line[6:])
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        if "content" in delta:
                            yield delta["content"]

    def count_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Note: This is an approximation. For exact counts,
        use tiktoken library.
        """
        # Rough estimate: ~4 characters per token for English text
        return len(text) // 4
