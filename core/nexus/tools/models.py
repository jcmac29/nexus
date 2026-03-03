"""Tool models - Universal tool definitions for AI and external APIs."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, JSON, Boolean, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from nexus.database import Base


class ToolCategory(str, enum.Enum):
    """Category of tool."""
    API = "api"              # External REST/GraphQL API
    DATABASE = "database"    # Database query/mutation
    FILE = "file"            # File operations
    COMPUTE = "compute"      # Code execution
    AI = "ai"                # AI model calls
    MESSAGING = "messaging"  # Send messages/notifications
    SCRAPING = "scraping"    # Web scraping
    CUSTOM = "custom"        # Custom logic


class AuthType(str, enum.Enum):
    """Authentication type for external tools."""
    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    BASIC = "basic"
    OAUTH2 = "oauth2"
    CUSTOM = "custom"


class Tool(Base):
    """A tool definition that can be used by agents or connected to external APIs."""

    __tablename__ = "tools"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    category = Column(Enum(ToolCategory), default=ToolCategory.CUSTOM)

    # Who owns this tool
    owner_id = Column(UUID(as_uuid=True), nullable=False)
    owner_type = Column(String(50), default="agent")  # agent, team, system

    # Tool schema (OpenAI function format)
    input_schema = Column(JSON, default=dict)  # JSON Schema for inputs
    output_schema = Column(JSON, default=dict)  # JSON Schema for outputs

    # For API tools - endpoint configuration
    endpoint_url = Column(String(1024), nullable=True)
    http_method = Column(String(10), default="POST")
    headers = Column(JSON, default=dict)  # Static headers
    query_params = Column(JSON, default=dict)  # Static query params

    # Authentication
    auth_type = Column(Enum(AuthType), default=AuthType.NONE)
    auth_config = Column(JSON, default=dict)  # Encrypted auth details

    # Request/Response transformation
    request_template = Column(Text, nullable=True)  # Jinja2 template for request body
    response_mapping = Column(JSON, default=dict)  # Map response fields

    # Rate limiting
    rate_limit = Column(Integer, nullable=True)  # Requests per minute
    rate_limit_window = Column(Integer, default=60)  # Window in seconds

    # Retry configuration
    retry_count = Column(Integer, default=3)
    retry_delay = Column(Float, default=1.0)  # Seconds

    # Timeout
    timeout = Column(Float, default=30.0)  # Seconds

    # Caching
    cache_enabled = Column(Boolean, default=False)
    cache_ttl = Column(Integer, default=300)  # Seconds

    # Health/Status
    is_active = Column(Boolean, default=True)
    last_health_check = Column(DateTime, nullable=True)
    health_status = Column(String(50), default="unknown")

    # Usage stats
    total_executions = Column(Integer, default=0)
    successful_executions = Column(Integer, default=0)
    avg_latency_ms = Column(Float, default=0.0)

    # Versioning
    version = Column(String(50), default="1.0.0")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    executions = relationship("ToolExecution", back_populates="tool", cascade="all, delete-orphan")


class ToolExecution(Base):
    """Record of a tool execution."""

    __tablename__ = "tool_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tool_id = Column(UUID(as_uuid=True), ForeignKey("tools.id", ondelete="CASCADE"), nullable=False)

    # Who executed
    executor_id = Column(UUID(as_uuid=True), nullable=False)
    executor_type = Column(String(50), default="agent")

    # Execution context
    conversation_id = Column(UUID(as_uuid=True), nullable=True)
    invocation_id = Column(UUID(as_uuid=True), nullable=True)

    # Input/Output
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)

    # Status
    status = Column(String(50), default="pending")  # pending, running, success, failed
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Float, nullable=True)

    # For debugging
    request_log = Column(JSON, nullable=True)  # HTTP request details
    response_log = Column(JSON, nullable=True)  # HTTP response details

    tool = relationship("Tool", back_populates="executions")
