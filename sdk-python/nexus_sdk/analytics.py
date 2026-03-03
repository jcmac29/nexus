"""Analytics operations for Nexus SDK."""

from __future__ import annotations

from typing import Any

import httpx


class Analytics:
    """Synchronous analytics operations."""

    def __init__(self, client: httpx.Client):
        self._client = client

    def dashboard(self, days: int = 7) -> dict[str, Any]:
        """
        Get dashboard summary.

        Args:
            days: Number of days to include (1-90)

        Returns:
            Dashboard data with totals and trends
        """
        response = self._client.get(
            "/analytics/dashboard",
            params={"days": days},
        )
        response.raise_for_status()
        return response.json()

    def usage(
        self,
        metric_types: list[str] | None = None,
        granularity: str = "hour",
        days: int = 7,
    ) -> dict[str, Any]:
        """
        Get usage metrics.

        Args:
            metric_types: Filter by metric types (api_request, memory_store, etc.)
            granularity: Time granularity (hour, day)
            days: Number of days

        Returns:
            Usage metrics data
        """
        params: dict[str, Any] = {
            "granularity": granularity,
            "days": days,
        }
        if metric_types:
            params["metric_types"] = metric_types

        response = self._client.get("/analytics/usage", params=params)
        response.raise_for_status()
        return response.json()

    def timeline(
        self,
        metric_type: str = "api_request",
        granularity: str = "hour",
        days: int = 7,
    ) -> list[dict[str, Any]]:
        """
        Get usage timeline data for charts.

        Args:
            metric_type: Type of metric to chart
            granularity: Time granularity
            days: Number of days

        Returns:
            Time series data points
        """
        response = self._client.get(
            "/analytics/usage/timeline",
            params={
                "metric_type": metric_type,
                "granularity": granularity,
                "days": days,
            },
        )
        response.raise_for_status()
        return response.json()["timeline"]

    def endpoints(
        self,
        endpoint: str | None = None,
        days: int = 7,
    ) -> list[dict[str, Any]]:
        """
        Get per-endpoint metrics.

        Args:
            endpoint: Filter by specific endpoint
            days: Number of days

        Returns:
            Endpoint metrics
        """
        params: dict[str, Any] = {"days": days}
        if endpoint:
            params["endpoint"] = endpoint

        response = self._client.get("/analytics/endpoints", params=params)
        response.raise_for_status()
        return response.json()["endpoints"]

    def storage(self, days: int = 30) -> dict[str, Any]:
        """
        Get storage usage.

        Args:
            days: Number of days of history

        Returns:
            Current storage and historical data
        """
        response = self._client.get(
            "/analytics/storage",
            params={"days": days},
        )
        response.raise_for_status()
        return response.json()

    def export(
        self,
        format: str = "json",
        start_date: str | None = None,
        end_date: str | None = None,
        metric_types: list[str] | None = None,
    ) -> Any:
        """
        Export analytics data.

        Args:
            format: Export format (json, csv)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            metric_types: Filter by metric types

        Returns:
            Exported data (dict for JSON, string for CSV)
        """
        params: dict[str, Any] = {"format": format}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if metric_types:
            params["metric_types"] = metric_types

        response = self._client.get("/analytics/export", params=params)
        response.raise_for_status()

        if format == "csv":
            return response.text
        return response.json()


class AnalyticsAsync:
    """Asynchronous analytics operations."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def dashboard(self, days: int = 7) -> dict[str, Any]:
        """Get dashboard summary."""
        response = await self._client.get(
            "/analytics/dashboard",
            params={"days": days},
        )
        response.raise_for_status()
        return response.json()

    async def usage(
        self,
        metric_types: list[str] | None = None,
        granularity: str = "hour",
        days: int = 7,
    ) -> dict[str, Any]:
        """Get usage metrics."""
        params: dict[str, Any] = {
            "granularity": granularity,
            "days": days,
        }
        if metric_types:
            params["metric_types"] = metric_types

        response = await self._client.get("/analytics/usage", params=params)
        response.raise_for_status()
        return response.json()

    async def timeline(
        self,
        metric_type: str = "api_request",
        granularity: str = "hour",
        days: int = 7,
    ) -> list[dict[str, Any]]:
        """Get usage timeline data for charts."""
        response = await self._client.get(
            "/analytics/usage/timeline",
            params={
                "metric_type": metric_type,
                "granularity": granularity,
                "days": days,
            },
        )
        response.raise_for_status()
        return response.json()["timeline"]

    async def endpoints(
        self,
        endpoint: str | None = None,
        days: int = 7,
    ) -> list[dict[str, Any]]:
        """Get per-endpoint metrics."""
        params: dict[str, Any] = {"days": days}
        if endpoint:
            params["endpoint"] = endpoint

        response = await self._client.get("/analytics/endpoints", params=params)
        response.raise_for_status()
        return response.json()["endpoints"]

    async def storage(self, days: int = 30) -> dict[str, Any]:
        """Get storage usage."""
        response = await self._client.get(
            "/analytics/storage",
            params={"days": days},
        )
        response.raise_for_status()
        return response.json()

    async def export(
        self,
        format: str = "json",
        start_date: str | None = None,
        end_date: str | None = None,
        metric_types: list[str] | None = None,
    ) -> Any:
        """Export analytics data."""
        params: dict[str, Any] = {"format": format}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if metric_types:
            params["metric_types"] = metric_types

        response = await self._client.get("/analytics/export", params=params)
        response.raise_for_status()

        if format == "csv":
            return response.text
        return response.json()
