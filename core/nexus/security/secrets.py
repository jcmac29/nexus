"""Secret management for Nexus."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Optional, Any
from enum import Enum

from nexus.security.encryption import EncryptionService, get_encryption_service


class SecretBackend(str, Enum):
    """Supported secret backends."""
    ENV = "env"
    FILE = "file"
    AWS_SECRETS_MANAGER = "aws_secrets_manager"
    HASHICORP_VAULT = "vault"
    ENCRYPTED_DB = "encrypted_db"


class SecretProvider(ABC):
    """Abstract base class for secret providers."""

    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        """Get a secret value."""
        pass

    @abstractmethod
    async def set(self, key: str, value: str) -> None:
        """Set a secret value."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a secret."""
        pass

    @abstractmethod
    async def list(self) -> list[str]:
        """List all secret keys."""
        pass


class EnvSecretProvider(SecretProvider):
    """Secret provider using environment variables."""

    def __init__(self, prefix: str = "NEXUS_SECRET_"):
        self.prefix = prefix

    async def get(self, key: str) -> Optional[str]:
        return os.environ.get(f"{self.prefix}{key.upper()}")

    async def set(self, key: str, value: str) -> None:
        os.environ[f"{self.prefix}{key.upper()}"] = value

    async def delete(self, key: str) -> None:
        env_key = f"{self.prefix}{key.upper()}"
        if env_key in os.environ:
            del os.environ[env_key]

    async def list(self) -> list[str]:
        return [
            k.replace(self.prefix, "").lower()
            for k in os.environ
            if k.startswith(self.prefix)
        ]


class FileSecretProvider(SecretProvider):
    """Secret provider using encrypted file storage."""

    def __init__(self, path: str = "/etc/nexus/secrets.json"):
        self.path = path
        self._encryption = get_encryption_service()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            with open(self.path) as f:
                encrypted = json.load(f)
                return {k: self._encryption.decrypt(v) for k, v in encrypted.items()}
        return {}

    def _save(self, secrets: dict) -> None:
        encrypted = {k: self._encryption.encrypt(v) for k, v in secrets.items()}
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(encrypted, f)

    async def get(self, key: str) -> Optional[str]:
        secrets = self._load()
        return secrets.get(key)

    async def set(self, key: str, value: str) -> None:
        secrets = self._load()
        secrets[key] = value
        self._save(secrets)

    async def delete(self, key: str) -> None:
        secrets = self._load()
        if key in secrets:
            del secrets[key]
            self._save(secrets)

    async def list(self) -> list[str]:
        return list(self._load().keys())


class AWSSecretsManagerProvider(SecretProvider):
    """Secret provider using AWS Secrets Manager."""

    def __init__(self, prefix: str = "nexus/"):
        self.prefix = prefix
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("secretsmanager")
        return self._client

    async def get(self, key: str) -> Optional[str]:
        import asyncio
        from botocore.exceptions import ClientError

        def _get():
            try:
                response = self._get_client().get_secret_value(
                    SecretId=f"{self.prefix}{key}"
                )
                return response.get("SecretString")
            except ClientError as e:
                if e.response["Error"]["Code"] == "ResourceNotFoundException":
                    return None
                raise

        return await asyncio.get_event_loop().run_in_executor(None, _get)

    async def set(self, key: str, value: str) -> None:
        import asyncio
        from botocore.exceptions import ClientError

        def _set():
            client = self._get_client()
            secret_id = f"{self.prefix}{key}"

            try:
                client.put_secret_value(
                    SecretId=secret_id,
                    SecretString=value,
                )
            except ClientError as e:
                if e.response["Error"]["Code"] == "ResourceNotFoundException":
                    client.create_secret(
                        Name=secret_id,
                        SecretString=value,
                    )
                else:
                    raise

        await asyncio.get_event_loop().run_in_executor(None, _set)

    async def delete(self, key: str) -> None:
        import asyncio

        def _delete():
            self._get_client().delete_secret(
                SecretId=f"{self.prefix}{key}",
                ForceDeleteWithoutRecovery=True,
            )

        await asyncio.get_event_loop().run_in_executor(None, _delete)

    async def list(self) -> list[str]:
        import asyncio

        def _list():
            response = self._get_client().list_secrets(
                Filters=[{"Key": "name", "Values": [self.prefix]}]
            )
            return [
                s["Name"].replace(self.prefix, "")
                for s in response.get("SecretList", [])
            ]

        return await asyncio.get_event_loop().run_in_executor(None, _list)


class VaultSecretProvider(SecretProvider):
    """Secret provider using HashiCorp Vault."""

    def __init__(
        self,
        url: str = "http://localhost:8200",
        token: Optional[str] = None,
        mount_point: str = "secret",
        path_prefix: str = "nexus/",
    ):
        self.url = url
        self.token = token or os.environ.get("VAULT_TOKEN")
        self.mount_point = mount_point
        self.path_prefix = path_prefix
        self._client = None

    def _get_client(self):
        if self._client is None:
            import hvac
            self._client = hvac.Client(url=self.url, token=self.token)
        return self._client

    async def get(self, key: str) -> Optional[str]:
        import asyncio

        def _get():
            client = self._get_client()
            try:
                response = client.secrets.kv.v2.read_secret_version(
                    path=f"{self.path_prefix}{key}",
                    mount_point=self.mount_point,
                )
                return response["data"]["data"].get("value")
            except Exception:
                return None

        return await asyncio.get_event_loop().run_in_executor(None, _get)

    async def set(self, key: str, value: str) -> None:
        import asyncio

        def _set():
            client = self._get_client()
            client.secrets.kv.v2.create_or_update_secret(
                path=f"{self.path_prefix}{key}",
                secret={"value": value},
                mount_point=self.mount_point,
            )

        await asyncio.get_event_loop().run_in_executor(None, _set)

    async def delete(self, key: str) -> None:
        import asyncio

        def _delete():
            client = self._get_client()
            client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=f"{self.path_prefix}{key}",
                mount_point=self.mount_point,
            )

        await asyncio.get_event_loop().run_in_executor(None, _delete)

    async def list(self) -> list[str]:
        import asyncio

        def _list():
            client = self._get_client()
            try:
                response = client.secrets.kv.v2.list_secrets(
                    path=self.path_prefix,
                    mount_point=self.mount_point,
                )
                return response["data"]["keys"]
            except Exception:
                return []

        return await asyncio.get_event_loop().run_in_executor(None, _list)


class SecretManager:
    """Unified secret manager supporting multiple backends."""

    def __init__(self, backend: SecretBackend = SecretBackend.ENV, **kwargs):
        self.backend = backend
        self._provider = self._create_provider(backend, **kwargs)

    def _create_provider(self, backend: SecretBackend, **kwargs) -> SecretProvider:
        if backend == SecretBackend.ENV:
            return EnvSecretProvider(**kwargs)
        elif backend == SecretBackend.FILE:
            return FileSecretProvider(**kwargs)
        elif backend == SecretBackend.AWS_SECRETS_MANAGER:
            return AWSSecretsManagerProvider(**kwargs)
        elif backend == SecretBackend.HASHICORP_VAULT:
            return VaultSecretProvider(**kwargs)
        else:
            raise ValueError(f"Unsupported secret backend: {backend}")

    async def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a secret value."""
        value = await self._provider.get(key)
        return value if value is not None else default

    async def set(self, key: str, value: str) -> None:
        """Set a secret value."""
        await self._provider.set(key, value)

    async def delete(self, key: str) -> None:
        """Delete a secret."""
        await self._provider.delete(key)

    async def list(self) -> list[str]:
        """List all secret keys."""
        return await self._provider.list()

    async def get_json(self, key: str) -> Optional[dict]:
        """Get a secret as JSON."""
        value = await self.get(key)
        if value:
            return json.loads(value)
        return None

    async def set_json(self, key: str, value: dict) -> None:
        """Set a secret as JSON."""
        await self.set(key, json.dumps(value))


# Global secret manager instance
_secret_manager: Optional[SecretManager] = None


def get_secret_manager() -> SecretManager:
    """Get or create the global secret manager."""
    global _secret_manager
    if _secret_manager is None:
        # Determine backend from environment
        backend_name = os.environ.get("NEXUS_SECRET_BACKEND", "env")
        backend = SecretBackend(backend_name)
        _secret_manager = SecretManager(backend)
    return _secret_manager


async def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get a secret using the global secret manager."""
    return await get_secret_manager().get(key, default)


async def set_secret(key: str, value: str) -> None:
    """Set a secret using the global secret manager."""
    await get_secret_manager().set(key, value)
