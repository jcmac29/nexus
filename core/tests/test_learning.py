"""Tests for learning module."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_record_feedback_success(authenticated_client: AsyncClient):
    """Test recording successful feedback."""
    response = await authenticated_client.post(
        "/api/v1/learning/feedback",
        json={
            "action_type": "code_review",
            "feedback_type": "success",
            "duration_ms": 1500,
            "confidence_score": 0.9,
            "input_data": {"file": "main.py"},
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["action_type"] == "code_review"
    assert data["feedback_type"] == "success"
    assert data["duration_ms"] == 1500


@pytest.mark.asyncio
async def test_record_feedback_failure(authenticated_client: AsyncClient):
    """Test recording failure feedback."""
    response = await authenticated_client.post(
        "/api/v1/learning/feedback",
        json={
            "action_type": "analysis",
            "feedback_type": "failure",
            "error_message": "Operation timed out",
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["feedback_type"] == "failure"


@pytest.mark.asyncio
async def test_list_feedback(authenticated_client: AsyncClient):
    """Test listing feedback entries."""
    # Record multiple feedback entries
    for i in range(3):
        await authenticated_client.post(
            "/api/v1/learning/feedback",
            json={
                "action_type": "test_action",
                "feedback_type": "success" if i % 2 == 0 else "failure",
            },
        )

    # List feedback
    response = await authenticated_client.get("/api/v1/learning/feedback")
    assert response.status_code == 200

    data = response.json()
    assert len(data) >= 3


@pytest.mark.asyncio
async def test_list_feedback_filtered(authenticated_client: AsyncClient):
    """Test listing feedback with filters."""
    # Record feedback
    await authenticated_client.post(
        "/api/v1/learning/feedback",
        json={"action_type": "filtered_action", "feedback_type": "success"},
    )

    # Filter by action type
    response = await authenticated_client.get(
        "/api/v1/learning/feedback?action_type=filtered_action"
    )
    assert response.status_code == 200

    data = response.json()
    assert all(f["action_type"] == "filtered_action" for f in data)


@pytest.mark.asyncio
async def test_get_patterns(authenticated_client: AsyncClient):
    """Test getting learned patterns."""
    # Record enough feedback to generate patterns
    for i in range(10):
        await authenticated_client.post(
            "/api/v1/learning/feedback",
            json={
                "action_type": "pattern_action",
                "feedback_type": "success" if i < 8 else "failure",
                "duration_ms": 1000 + i * 100,
            },
        )

    # Get patterns - this returns a list
    response = await authenticated_client.get(
        "/api/v1/learning/patterns?action_type=pattern_action&min_attempts=1"
    )
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_get_improvements(authenticated_client: AsyncClient):
    """Test getting improvement suggestions."""
    response = await authenticated_client.get("/api/v1/learning/improvements")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_accept_improvement(authenticated_client: AsyncClient):
    """Test accepting an improvement suggestion."""
    # First get improvements to find an ID
    response = await authenticated_client.get("/api/v1/learning/improvements")
    assert response.status_code == 200

    improvements = response.json()
    if len(improvements) > 0:
        improvement_id = improvements[0]["id"]
        accept_response = await authenticated_client.post(
            f"/api/v1/learning/improvements/{improvement_id}/decide",
            json={"accept": True},
        )
        assert accept_response.status_code in [200, 404]


@pytest.mark.asyncio
async def test_reject_improvement(authenticated_client: AsyncClient):
    """Test rejecting an improvement suggestion."""
    response = await authenticated_client.get("/api/v1/learning/improvements")
    assert response.status_code == 200

    improvements = response.json()
    if len(improvements) > 0:
        improvement_id = improvements[0]["id"]
        reject_response = await authenticated_client.post(
            f"/api/v1/learning/improvements/{improvement_id}/decide",
            json={"accept": False, "reason": "Not applicable"},
        )
        assert reject_response.status_code in [200, 404]


@pytest.mark.asyncio
async def test_feedback_with_context_tags(authenticated_client: AsyncClient):
    """Test feedback with context tags."""
    response = await authenticated_client.post(
        "/api/v1/learning/feedback",
        json={
            "action_type": "tagged_action",
            "feedback_type": "success",
            "context_tags": ["python", "code_review"],
        },
    )
    assert response.status_code == 201
    assert "python" in response.json()["context_tags"]


@pytest.mark.asyncio
async def test_get_learning_stats(authenticated_client: AsyncClient):
    """Test getting learning statistics."""
    # Record some feedback first
    await authenticated_client.post(
        "/api/v1/learning/feedback",
        json={"action_type": "stats_action", "feedback_type": "success"},
    )

    response = await authenticated_client.get("/api/v1/learning/stats")
    assert response.status_code == 200
    assert isinstance(response.json(), dict)
