"""Connector models for external systems integration."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, JSON, Boolean, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from nexus.database import Base


class ConnectorType(str, enum.Enum):
    """Type of connector."""
    # Databases
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    MONGODB = "mongodb"
    REDIS = "redis"
    ELASTICSEARCH = "elasticsearch"
    SQLITE = "sqlite"

    # APIs
    REST = "rest"
    GRAPHQL = "graphql"
    GRPC = "grpc"
    SOAP = "soap"

    # Cloud Services
    AWS_S3 = "aws_s3"
    AWS_DYNAMODB = "aws_dynamodb"
    GCP_BIGQUERY = "gcp_bigquery"
    GCP_FIRESTORE = "gcp_firestore"
    AZURE_BLOB = "azure_blob"
    AZURE_COSMOS = "azure_cosmos"

    # Messaging
    KAFKA = "kafka"
    RABBITMQ = "rabbitmq"
    SQS = "sqs"
    PUBSUB = "pubsub"

    # File Systems
    FTP = "ftp"
    SFTP = "sftp"
    S3_COMPATIBLE = "s3_compatible"

    # Other
    WEBHOOK = "webhook"
    CUSTOM = "custom"


class Connector(Base):
    """A connector to an external system."""

    __tablename__ = "connectors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    connector_type = Column(Enum(ConnectorType), nullable=False)

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False)
    owner_type = Column(String(50), default="agent")

    # Connection configuration (encrypted in production)
    connection_config = Column(JSON, default=dict)
    # For databases: {"host": "...", "port": 5432, "database": "...", "user": "...", "password": "..."}
    # For REST APIs: {"base_url": "...", "auth_type": "bearer", "auth_config": {...}}
    # For S3: {"endpoint": "...", "bucket": "...", "access_key": "...", "secret_key": "..."}

    # Schema/structure information
    schema_info = Column(JSON, default=dict)  # Tables, collections, endpoints discovered

    # Operations allowed
    allowed_operations = Column(JSON, default=list)  # ["read", "write", "delete", "execute"]

    # Query templates for common operations
    query_templates = Column(JSON, default=dict)
    # {"get_user": {"query": "SELECT * FROM users WHERE id = :id", "params": ["id"]}}

    # Rate limiting
    rate_limit = Column(Integer, nullable=True)
    rate_limit_window = Column(Integer, default=60)

    # Connection pooling
    pool_size = Column(Integer, default=5)
    pool_timeout = Column(Integer, default=30)

    # Health
    is_active = Column(Boolean, default=True)
    health_status = Column(String(50), default="unknown")
    last_health_check = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)

    # Stats
    total_operations = Column(Integer, default=0)
    successful_operations = Column(Integer, default=0)
    failed_operations = Column(Integer, default=0)
    avg_latency_ms = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    executions = relationship("ConnectorExecution", back_populates="connector", cascade="all, delete-orphan")


class ConnectorExecution(Base):
    """Record of a connector operation."""

    __tablename__ = "connector_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connector_id = Column(UUID(as_uuid=True), ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False)

    # Who executed
    executor_id = Column(UUID(as_uuid=True), nullable=False)
    executor_type = Column(String(50), default="agent")

    # Operation details
    operation = Column(String(100), nullable=False)  # read, write, query, execute, etc.
    template_name = Column(String(255), nullable=True)  # If using a template
    query = Column(Text, nullable=True)  # The actual query/request
    params = Column(JSON, nullable=True)

    # Results
    status = Column(String(50), default="pending")  # pending, running, success, failed
    result = Column(JSON, nullable=True)
    rows_affected = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)

    # Timing
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Float, nullable=True)

    connector = relationship("Connector", back_populates="executions")
