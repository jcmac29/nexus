"""API routes for LLM execution."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from nexus.auth import get_current_agent
from nexus.cache import get_cache
from nexus.identity.models import Agent
from nexus.llm.base import LLMConfig, LLMMessage, MessageRole, ToolDefinition
from nexus.llm.router import get_llm_router

router = APIRouter(prefix="/llm", tags=["llm"])


# --- Rate Limiting for LLM Execution ---

async def llm_rate_limit(request: Request, agent: Agent = Depends(get_current_agent)):
    """
    SECURITY: Rate limit LLM execution to prevent cost abuse.
    Limit: 30 completions per minute per agent (expensive operations).
    """
    cache = await get_cache()

    key = f"ratelimit:llm:completions:{agent.id}"

    allowed, current, remaining = await cache.rate_limit_check(
        key=key,
        limit=30,  # 30 completions per minute
        window_seconds=60,
    )

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": "LLM rate limit exceeded. Please try again later.",
                "retry_after": 60,
                "limit": 30,
                "used": current,
            },
            headers={"Retry-After": "60"},
        )


# =============================================================================
# Request/Response Schemas
# =============================================================================


class MessageInput(BaseModel):
    """Input message for completion."""

    role: str = Field(..., description="Message role: system, user, assistant, tool")
    content: str = Field(..., description="Message content")
    name: str | None = Field(None, description="Name for the message sender")
    tool_call_id: str | None = Field(None, description="Tool call ID for tool responses")


class ToolInput(BaseModel):
    """Tool definition input."""

    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    parameters: dict[str, Any] = Field(..., description="JSON Schema for parameters")


class CompletionRequest(BaseModel):
    """Request for LLM completion."""

    messages: list[MessageInput] = Field(..., description="Conversation messages")
    provider: str | None = Field(None, description="LLM provider (anthropic, openai)")
    model: str | None = Field(None, description="Model to use")
    max_tokens: int = Field(4096, description="Maximum tokens to generate")
    temperature: float = Field(0.7, ge=0, le=2, description="Sampling temperature")
    system_prompt: str | None = Field(None, description="System prompt")
    tools: list[ToolInput] | None = Field(None, description="Tools for function calling")
    stream: bool = Field(False, description="Stream the response")


class ChatRequest(BaseModel):
    """Simple chat request."""

    message: str = Field(..., description="User message")
    system_prompt: str | None = Field(None, description="System prompt")
    provider: str | None = Field(None, description="LLM provider")
    model: str | None = Field(None, description="Model to use")
    max_tokens: int = Field(4096, description="Maximum tokens")
    temperature: float = Field(0.7, ge=0, le=2, description="Temperature")


class ToolCallOutput(BaseModel):
    """Tool call in response."""

    id: str
    name: str
    arguments: dict[str, Any]


class CompletionResponse(BaseModel):
    """Response from LLM completion."""

    content: str = Field(..., description="Generated text")
    model: str = Field(..., description="Model used")
    provider: str = Field(..., description="Provider used")
    tool_calls: list[ToolCallOutput] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)
    finish_reason: str | None = None


class ChatResponse(BaseModel):
    """Simple chat response."""

    response: str = Field(..., description="Assistant's response")
    model: str = Field(..., description="Model used")
    provider: str = Field(..., description="Provider used")


class ProviderInfo(BaseModel):
    """Information about an LLM provider."""

    name: str
    default_model: str
    available_models: list[str]


# =============================================================================
# Routes
# =============================================================================


@router.get(
    "/providers",
    response_model=list[str],
    summary="List available LLM providers",
)
async def list_providers(
    agent: Agent = Depends(get_current_agent),
) -> list[str]:
    """List LLM providers that are configured and available."""
    llm = get_llm_router()
    return llm.get_available_providers()


@router.get(
    "/providers/{provider}",
    response_model=ProviderInfo,
    summary="Get provider info",
)
async def get_provider_info(
    provider: str,
    agent: Agent = Depends(get_current_agent),
) -> ProviderInfo:
    """Get information about a specific provider including available models."""
    llm = get_llm_router()
    try:
        info = llm.get_provider_info(provider)
        return ProviderInfo(**info)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/complete",
    response_model=CompletionResponse,
    summary="Generate LLM completion",
)
async def complete(
    request: CompletionRequest,
    agent: Agent = Depends(get_current_agent),
    _: None = Depends(llm_rate_limit),  # SECURITY: Rate limit expensive operations
) -> CompletionResponse:
    """Generate a completion using the specified LLM provider.

    This is the core execution endpoint that allows agents to
    leverage any configured AI model.
    """
    llm = get_llm_router()

    # Convert input messages to LLMMessage objects
    messages = []
    for msg in request.messages:
        try:
            role = MessageRole(msg.role)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid role: {msg.role}. Must be system, user, assistant, or tool"
            )
        messages.append(LLMMessage(
            role=role,
            content=msg.content,
            name=msg.name,
            tool_call_id=msg.tool_call_id,
        ))

    # Build config
    config = LLMConfig(
        model=request.model,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        system_prompt=request.system_prompt,
    )

    # Add tools if provided
    if request.tools:
        config.tools = [
            ToolDefinition(
                name=t.name,
                description=t.description,
                parameters=t.parameters,
            )
            for t in request.tools
        ]

    try:
        response = await llm.complete(messages, config, request.provider)

        return CompletionResponse(
            content=response.content,
            model=response.model,
            provider=response.provider,
            tool_calls=[
                ToolCallOutput(
                    id=tc.id,
                    name=tc.name,
                    arguments=tc.arguments,
                )
                for tc in response.tool_calls
            ],
            usage=response.usage,
            finish_reason=response.finish_reason,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Simple chat completion",
)
async def chat(
    request: ChatRequest,
    agent: Agent = Depends(get_current_agent),
    _: None = Depends(llm_rate_limit),  # SECURITY: Rate limit expensive operations
) -> ChatResponse:
    """Simple single-turn chat interface.

    Use this for quick queries without managing message history.
    """
    llm = get_llm_router()

    config = LLMConfig(
        model=request.model,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
    )

    try:
        response_text = await llm.chat(
            user_message=request.message,
            system_prompt=request.system_prompt,
            config=config,
            provider=request.provider,
        )

        # Get provider info for response
        provider_name = request.provider or llm._default_provider
        provider = llm._get_provider(provider_name)

        return ChatResponse(
            response=response_text,
            model=request.model or provider.default_model,
            provider=provider.name,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/analyze",
    response_model=ChatResponse,
    summary="Analyze content with AI",
)
async def analyze(
    content: str,
    instruction: str = "Analyze this content and provide insights.",
    provider: str | None = None,
    agent: Agent = Depends(get_current_agent),
    _: None = Depends(llm_rate_limit),  # SECURITY: Rate limit expensive operations
) -> ChatResponse:
    """Analyze content using AI.

    Useful for summarization, extraction, classification, etc.
    """
    llm = get_llm_router()

    system_prompt = """You are a helpful AI assistant skilled at analyzing content.
Provide clear, structured analysis based on the user's instructions."""

    message = f"""Instruction: {instruction}

Content to analyze:
{content}"""

    try:
        response_text = await llm.chat(
            user_message=message,
            system_prompt=system_prompt,
            provider=provider,
        )

        provider_name = provider or llm._default_provider
        provider_instance = llm._get_provider(provider_name)

        return ChatResponse(
            response=response_text,
            model=provider_instance.default_model,
            provider=provider_instance.name,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
