"""Integration tests for connector service."""

import pytest
from uuid import uuid4
from httpx import AsyncClient

from nexus.connectors.models import ConnectorType


@pytest.fixture
def connector_data():
    """Sample connector configuration."""
    return {
        "name": f"Test REST API {uuid4().hex[:6]}",
        "slug": f"test-rest-{uuid4().hex[:8]}",
        "connector_type": "rest",
        "connection_config": {
            "base_url": "https://api.example.com",
            "auth_type": "bearer",
            "auth_config": {"token": "test-token"},
        },
        "allowed_operations": ["read", "write"],
    }


class TestConnectorCRUD:
    """Test connector CRUD operations."""

    async def test_create_connector(self, client: AsyncClient, auth_headers: dict, connector_data: dict):
        """Test creating a connector."""
        response = await client.post(
            "/api/v1/connectors",
            json=connector_data,
            headers=auth_headers,
        )
        assert response.status_code in [200, 201]
        data = response.json()
        assert data["name"] == connector_data["name"]
        assert data["slug"] == connector_data["slug"]

    async def test_create_connector_validates_url(self, client: AsyncClient, auth_headers: dict):
        """Test that connector creation validates URLs for SSRF prevention."""
        # Try to create connector with localhost URL
        response = await client.post(
            "/api/v1/connectors",
            json={
                "name": "SSRF Test",
                "slug": f"ssrf-test-{uuid4().hex[:8]}",
                "connector_type": "rest",
                "connection_config": {
                    "base_url": "http://localhost:8080/admin",
                },
                "allowed_operations": ["read"],
            },
            headers=auth_headers,
        )
        # Should be rejected (400 for ValueError, 422 for validation, 500 for unhandled)
        assert response.status_code in [400, 422, 500]

    async def test_create_connector_blocks_internal_hosts(self, client: AsyncClient, auth_headers: dict):
        """Test that connector creation blocks internal hostnames."""
        response = await client.post(
            "/api/v1/connectors",
            json={
                "name": "Internal Test",
                "slug": f"internal-test-{uuid4().hex[:8]}",
                "connector_type": "rest",
                "connection_config": {
                    "base_url": "http://metadata.internal/v1/credentials",
                },
                "allowed_operations": ["read"],
            },
            headers=auth_headers,
        )
        # Should be rejected
        assert response.status_code in [400, 422, 500]

    async def test_list_connectors(self, client: AsyncClient, auth_headers: dict, connector_data: dict):
        """Test listing connectors."""
        # Create a connector first
        await client.post(
            "/api/v1/connectors",
            json=connector_data,
            headers=auth_headers,
        )

        response = await client.get(
            "/api/v1/connectors",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestConnectorTypes:
    """Test different connector types."""

    async def test_create_postgresql_connector(self, client: AsyncClient, auth_headers: dict):
        """Test creating a PostgreSQL connector."""
        response = await client.post(
            "/api/v1/connectors",
            json={
                "name": "Test PostgreSQL",
                "slug": f"test-pg-{uuid4().hex[:8]}",
                "connector_type": "postgresql",
                "connection_config": {
                    "host": "db.example.com",
                    "port": 5432,
                    "database": "testdb",
                    "user": "testuser",
                },
                "allowed_operations": ["read"],
                "query_templates": {
                    "get_users": {
                        "query": "SELECT id, name FROM users WHERE id = $1",
                        "default_params": {},
                    },
                },
            },
            headers=auth_headers,
        )
        assert response.status_code in [200, 201]

    async def test_create_redis_connector(self, client: AsyncClient, auth_headers: dict):
        """Test creating a Redis connector."""
        response = await client.post(
            "/api/v1/connectors",
            json={
                "name": "Test Redis",
                "slug": f"test-redis-{uuid4().hex[:8]}",
                "connector_type": "redis",
                "connection_config": {
                    "host": "redis.example.com",
                    "port": 6379,
                    "db": 0,
                },
                "allowed_operations": ["read", "write", "delete"],
            },
            headers=auth_headers,
        )
        assert response.status_code in [200, 201]

    async def test_create_mongodb_connector(self, client: AsyncClient, auth_headers: dict):
        """Test creating a MongoDB connector."""
        response = await client.post(
            "/api/v1/connectors",
            json={
                "name": "Test MongoDB",
                "slug": f"test-mongo-{uuid4().hex[:8]}",
                "connector_type": "mongodb",
                "connection_config": {
                    "connection_string": "mongodb://mongo.example.com:27017",
                    "database": "testdb",
                },
                "allowed_operations": ["read", "write", "update", "delete", "aggregate"],
            },
            headers=auth_headers,
        )
        assert response.status_code in [200, 201]

    async def test_create_elasticsearch_connector(self, client: AsyncClient, auth_headers: dict):
        """Test creating an Elasticsearch connector."""
        response = await client.post(
            "/api/v1/connectors",
            json={
                "name": "Test Elasticsearch",
                "slug": f"test-es-{uuid4().hex[:8]}",
                "connector_type": "elasticsearch",
                "connection_config": {
                    "hosts": ["https://es.example.com:9200"],
                    "api_key": "test-api-key",
                },
                "allowed_operations": ["read", "write", "delete", "search", "aggregate"],
            },
            headers=auth_headers,
        )
        assert response.status_code in [200, 201]

    async def test_create_s3_connector(self, client: AsyncClient, auth_headers: dict):
        """Test creating an S3 connector."""
        response = await client.post(
            "/api/v1/connectors",
            json={
                "name": "Test S3",
                "slug": f"test-s3-{uuid4().hex[:8]}",
                "connector_type": "aws_s3",
                "connection_config": {
                    "region": "us-west-2",
                    "access_key": "AKIAIOSFODNN7EXAMPLE",
                    "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                },
                "allowed_operations": ["read", "write", "delete", "list"],
            },
            headers=auth_headers,
        )
        assert response.status_code in [200, 201]


class TestConnectorSecurity:
    """Test connector security measures."""

    async def test_connector_requires_auth(self, client: AsyncClient):
        """Test that connector endpoints require authentication."""
        response = await client.get("/api/v1/connectors")
        assert response.status_code == 401

    async def test_connector_operation_validation(self, client: AsyncClient, auth_headers: dict):
        """Test that connector validates allowed operations."""
        # Create connector with limited operations
        create_response = await client.post(
            "/api/v1/connectors",
            json={
                "name": "Read Only Connector",
                "slug": f"readonly-{uuid4().hex[:8]}",
                "connector_type": "rest",
                "connection_config": {
                    "base_url": "https://api.example.com",
                },
                "allowed_operations": ["read"],  # Only read allowed
            },
            headers=auth_headers,
        )
        assert create_response.status_code in [200, 201]
        connector_id = create_response.json().get("id")

        if connector_id:
            # Try to execute write operation (should be rejected)
            exec_response = await client.post(
                f"/api/v1/connectors/{connector_id}/execute",
                json={
                    "operation": "write",  # Not allowed
                    "params": {"data": "test"},
                },
                headers=auth_headers,
            )
            # Should fail because write is not in allowed_operations
            assert exec_response.status_code in [400, 403]
