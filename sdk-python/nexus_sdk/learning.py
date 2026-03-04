"""Learning SDK - Feedback patterns and improvements."""

from __future__ import annotations

from typing import Any

import httpx


class Learning:
    """Synchronous client for learning and feedback."""

    def __init__(self, client: httpx.Client):
        self._client = client

    def record_feedback(
        self,
        action_type: str,
        feedback_type: str,
        action_description: str | None = None,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        error_message: str | None = None,
        context_tags: list[str] | None = None,
        duration_ms: int | None = None,
        confidence_score: float | None = None,
    ) -> dict[str, Any]:
        """
        Record feedback about an action.

        Args:
            action_type: Type of action (e.g., "code_review", "api_call")
            feedback_type: Outcome (success, failure, partial, timeout, error)
            action_description: What was attempted
            input_data: Input that was provided
            output_data: Output that was produced
            error_message: Error message if failed
            context_tags: Tags for categorization
            duration_ms: How long the action took
            confidence_score: Confidence in the result (0.0-1.0)

        Returns:
            Created feedback record
        """
        response = self._client.post(
            "/learning/feedback",
            json={
                "action_type": action_type,
                "feedback_type": feedback_type,
                "action_description": action_description,
                "input_data": input_data or {},
                "output_data": output_data or {},
                "error_message": error_message,
                "context_tags": context_tags or [],
                "duration_ms": duration_ms,
                "confidence_score": confidence_score,
            },
        )
        response.raise_for_status()
        return response.json()

    def get_patterns(
        self,
        action_type: str | None = None,
        min_success_rate: float | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Get learned patterns from feedback analysis.

        Args:
            action_type: Filter by action type
            min_success_rate: Only patterns with this success rate or higher
            limit: Maximum number of patterns

        Returns:
            List of learned patterns
        """
        params: dict[str, Any] = {"limit": limit}
        if action_type:
            params["action_type"] = action_type
        if min_success_rate is not None:
            params["min_success_rate"] = min_success_rate
        response = self._client.get("/learning/patterns", params=params)
        response.raise_for_status()
        return response.json()

    def get_improvements(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Get suggested improvements.

        Args:
            status: Filter by status (suggested, accepted, rejected, implemented)
            limit: Maximum number of improvements

        Returns:
            List of improvement suggestions
        """
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        response = self._client.get("/learning/improvements", params=params)
        response.raise_for_status()
        return response.json()

    def accept_improvement(self, improvement_id: str) -> dict[str, Any]:
        """Accept an improvement suggestion."""
        response = self._client.post(f"/learning/improvements/{improvement_id}/accept")
        response.raise_for_status()
        return response.json()

    def reject_improvement(self, improvement_id: str, reason: str | None = None) -> dict[str, Any]:
        """Reject an improvement suggestion."""
        response = self._client.post(
            f"/learning/improvements/{improvement_id}/reject",
            json={"reason": reason},
        )
        response.raise_for_status()
        return response.json()

    def implement_improvement(
        self,
        improvement_id: str,
        implementation_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Mark an improvement as implemented."""
        response = self._client.post(
            f"/learning/improvements/{improvement_id}/implement",
            json={"implementation_data": implementation_data or {}},
        )
        response.raise_for_status()
        return response.json()


class LearningAsync:
    """Asynchronous client for learning and feedback."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def record_feedback(
        self,
        action_type: str,
        feedback_type: str,
        action_description: str | None = None,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        error_message: str | None = None,
        context_tags: list[str] | None = None,
        duration_ms: int | None = None,
        confidence_score: float | None = None,
    ) -> dict[str, Any]:
        """Record feedback about an action."""
        response = await self._client.post(
            "/learning/feedback",
            json={
                "action_type": action_type,
                "feedback_type": feedback_type,
                "action_description": action_description,
                "input_data": input_data or {},
                "output_data": output_data or {},
                "error_message": error_message,
                "context_tags": context_tags or [],
                "duration_ms": duration_ms,
                "confidence_score": confidence_score,
            },
        )
        response.raise_for_status()
        return response.json()

    async def get_patterns(
        self,
        action_type: str | None = None,
        min_success_rate: float | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get learned patterns from feedback analysis."""
        params: dict[str, Any] = {"limit": limit}
        if action_type:
            params["action_type"] = action_type
        if min_success_rate is not None:
            params["min_success_rate"] = min_success_rate
        response = await self._client.get("/learning/patterns", params=params)
        response.raise_for_status()
        return response.json()

    async def get_improvements(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get suggested improvements."""
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        response = await self._client.get("/learning/improvements", params=params)
        response.raise_for_status()
        return response.json()

    async def accept_improvement(self, improvement_id: str) -> dict[str, Any]:
        """Accept an improvement suggestion."""
        response = await self._client.post(f"/learning/improvements/{improvement_id}/accept")
        response.raise_for_status()
        return response.json()

    async def reject_improvement(self, improvement_id: str, reason: str | None = None) -> dict[str, Any]:
        """Reject an improvement suggestion."""
        response = await self._client.post(
            f"/learning/improvements/{improvement_id}/reject",
            json={"reason": reason},
        )
        response.raise_for_status()
        return response.json()

    async def implement_improvement(
        self,
        improvement_id: str,
        implementation_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Mark an improvement as implemented."""
        response = await self._client.post(
            f"/learning/improvements/{improvement_id}/implement",
            json={"implementation_data": implementation_data or {}},
        )
        response.raise_for_status()
        return response.json()
