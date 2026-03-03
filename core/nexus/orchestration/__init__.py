"""Orchestration - Coordinate multiple agents on complex tasks."""

from nexus.orchestration.models import (
    OrchestrationWorkflow,
    OrchestrationStep,
    OrchestrationExecution,
    OrchestrationStepExecution,
)
from nexus.orchestration.service import OrchestrationService
from nexus.orchestration.routes import router

# Backward compatibility aliases
Workflow = OrchestrationWorkflow
WorkflowStep = OrchestrationStep
WorkflowExecution = OrchestrationExecution

__all__ = [
    "OrchestrationWorkflow",
    "OrchestrationStep",
    "OrchestrationExecution",
    "OrchestrationStepExecution",
    "OrchestrationService",
    "router",
    # Aliases
    "Workflow",
    "WorkflowStep",
    "WorkflowExecution",
]
