"""Swarm WebSocket handler for real-time coordination."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.swarm.models import MemberStatus
from nexus.swarm.service import SwarmService

logger = logging.getLogger(__name__)


class SwarmConnectionManager:
    """Manage WebSocket connections for swarm coordination."""

    def __init__(self):
        # swarm_id -> {member_id -> WebSocket}
        self.active_connections: dict[UUID, dict[UUID, WebSocket]] = {}
        self._heartbeat_tasks: dict[UUID, asyncio.Task] = {}

    async def connect(
        self,
        websocket: WebSocket,
        swarm_id: UUID,
        member_id: UUID,
    ) -> None:
        """Connect a member to the swarm."""
        await websocket.accept()

        if swarm_id not in self.active_connections:
            self.active_connections[swarm_id] = {}

        self.active_connections[swarm_id][member_id] = websocket

        # Notify other members
        await self.broadcast(
            swarm_id,
            {
                "type": "member_joined",
                "member_id": str(member_id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            exclude=member_id,
        )

    def disconnect(self, swarm_id: UUID, member_id: UUID) -> None:
        """Disconnect a member from the swarm."""
        if swarm_id in self.active_connections:
            self.active_connections[swarm_id].pop(member_id, None)
            if not self.active_connections[swarm_id]:
                del self.active_connections[swarm_id]

    async def broadcast(
        self,
        swarm_id: UUID,
        message: dict[str, Any],
        exclude: UUID | None = None,
    ) -> None:
        """Broadcast a message to all members of a swarm."""
        if swarm_id not in self.active_connections:
            return

        disconnected = []
        for member_id, websocket in self.active_connections[swarm_id].items():
            if member_id == exclude:
                continue
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(member_id)

        # Clean up disconnected
        for member_id in disconnected:
            self.disconnect(swarm_id, member_id)

    async def send_to_member(
        self,
        swarm_id: UUID,
        member_id: UUID,
        message: dict[str, Any],
    ) -> bool:
        """Send a message to a specific member."""
        if swarm_id not in self.active_connections:
            return False

        websocket = self.active_connections[swarm_id].get(member_id)
        if not websocket:
            return False

        try:
            await websocket.send_json(message)
            return True
        except Exception:
            self.disconnect(swarm_id, member_id)
            return False

    def get_connected_count(self, swarm_id: UUID) -> int:
        """Get the number of connected members."""
        return len(self.active_connections.get(swarm_id, {}))


# Global connection manager
swarm_manager = SwarmConnectionManager()


async def handle_swarm_websocket(
    websocket: WebSocket,
    swarm_id: UUID,
    member_id: UUID,
    db: AsyncSession,
) -> None:
    """Handle WebSocket connection for swarm coordination."""
    service = SwarmService(db)

    # Verify member
    member = await service.get_member(member_id)
    if not member or member.swarm_id != swarm_id:
        await websocket.close(code=4003, reason="Not a member of this swarm")
        return

    # Connect
    await swarm_manager.connect(websocket, swarm_id, member_id)

    # Start heartbeat task
    heartbeat_task = asyncio.create_task(
        _heartbeat_loop(service, member_id, swarm_id)
    )

    try:
        # Send initial status
        stats = await service.get_swarm_stats(swarm_id)
        members = await service.list_members(swarm_id)
        await websocket.send_json({
            "type": "swarm_status",
            "member_count": len(members),
            "members": [
                {
                    "id": str(m.id),
                    "agent_id": str(m.agent_id),
                    "role": m.role.value,
                    "status": m.status.value,
                }
                for m in members
            ],
            "pending_tasks": stats.get("pending_tasks", 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Handle messages
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            await _handle_message(
                websocket, service, swarm_id, member_id, message
            )

    except WebSocketDisconnect:
        logger.info(f"Member {member_id} disconnected from swarm {swarm_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        heartbeat_task.cancel()
        swarm_manager.disconnect(swarm_id, member_id)

        # Notify others
        await swarm_manager.broadcast(
            swarm_id,
            {
                "type": "member_left",
                "member_id": str(member_id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )


async def _heartbeat_loop(
    service: SwarmService,
    member_id: UUID,
    swarm_id: UUID,
    interval: int = 30,
) -> None:
    """Send heartbeats periodically."""
    while True:
        try:
            await asyncio.sleep(interval)
            await service.heartbeat(member_id)

            # Check for stale members
            stale = await service.check_stale_members(swarm_id)
            for stale_member in stale:
                await swarm_manager.broadcast(
                    swarm_id,
                    {
                        "type": "member_stale",
                        "member_id": str(stale_member.id),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")


async def _handle_message(
    websocket: WebSocket,
    service: SwarmService,
    swarm_id: UUID,
    member_id: UUID,
    message: dict[str, Any],
) -> None:
    """Handle an incoming WebSocket message."""
    msg_type = message.get("type")

    if msg_type == "heartbeat":
        await service.heartbeat(member_id)
        await websocket.send_json({"type": "heartbeat_ack"})

    elif msg_type == "claim_task":
        task = await service.claim_task(member_id)
        if task:
            await websocket.send_json({
                "type": "task_assigned",
                "task": {
                    "id": str(task.id),
                    "title": task.title,
                    "description": task.description,
                    "task_type": task.task_type,
                    "priority": task.priority,
                    "input_data": task.input_data,
                    "timeout_seconds": task.timeout_seconds,
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            # Notify others
            await swarm_manager.broadcast(
                swarm_id,
                {
                    "type": "task_claimed",
                    "task_id": str(task.id),
                    "member_id": str(member_id),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                exclude=member_id,
            )
        else:
            await websocket.send_json({
                "type": "no_tasks_available",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    elif msg_type == "task_progress":
        task_id = message.get("task_id")
        progress = message.get("progress", 0)
        await swarm_manager.broadcast(
            swarm_id,
            {
                "type": "task_progress",
                "task_id": task_id,
                "member_id": str(member_id),
                "progress": progress,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            exclude=member_id,
        )

    elif msg_type == "task_complete":
        task_id = UUID(message.get("task_id"))
        result_data = message.get("result", {})
        execution_time_ms = message.get("execution_time_ms", 0)

        try:
            result = await service.complete_task(
                task_id=task_id,
                member_id=member_id,
                output_data=result_data,
                success=True,
                execution_time_ms=execution_time_ms,
            )
            await websocket.send_json({
                "type": "task_complete_ack",
                "task_id": str(task_id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            # Notify others
            await swarm_manager.broadcast(
                swarm_id,
                {
                    "type": "task_completed",
                    "task_id": str(task_id),
                    "member_id": str(member_id),
                    "success": True,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                exclude=member_id,
            )

            # Check if all tasks complete
            stats = await service.get_swarm_stats(swarm_id)
            if stats.get("pending_tasks", 0) == 0 and stats.get("in_progress_tasks", 0) == 0:
                results = await service.get_results(swarm_id)
                await swarm_manager.broadcast(
                    swarm_id,
                    {
                        "type": "all_tasks_complete",
                        "total_tasks": stats.get("total_tasks", 0),
                        "completed_tasks": stats.get("completed_tasks", 0),
                        "failed_tasks": stats.get("failed_tasks", 0),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
        except ValueError as e:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    elif msg_type == "task_failed":
        task_id = UUID(message.get("task_id"))
        error = message.get("error", "Unknown error")

        try:
            await service.fail_task(task_id, member_id, error)
            await websocket.send_json({
                "type": "task_fail_ack",
                "task_id": str(task_id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            # Notify others
            await swarm_manager.broadcast(
                swarm_id,
                {
                    "type": "task_failed",
                    "task_id": str(task_id),
                    "member_id": str(member_id),
                    "error": error,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                exclude=member_id,
            )
        except ValueError as e:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    elif msg_type == "get_status":
        stats = await service.get_swarm_stats(swarm_id)
        members = await service.list_members(swarm_id)
        await websocket.send_json({
            "type": "swarm_status",
            "member_count": len(members),
            "members": [
                {
                    "id": str(m.id),
                    "agent_id": str(m.agent_id),
                    "role": m.role.value,
                    "status": m.status.value,
                    "tasks_completed": m.tasks_completed,
                }
                for m in members
            ],
            "pending_tasks": stats.get("pending_tasks", 0),
            "completed_tasks": stats.get("completed_tasks", 0),
            "failed_tasks": stats.get("failed_tasks", 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    else:
        await websocket.send_json({
            "type": "error",
            "message": f"Unknown message type: {msg_type}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
