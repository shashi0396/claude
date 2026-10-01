"""Core data models for plans, intents, and tool calls."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Intent(str, Enum):
    ONBOARD = "onboard"
    OFFBOARD = "offboard"
    UNKNOWN = "unknown"


class ToolCall(BaseModel):
    """A single tool invocation the orchestrator will execute."""

    name: str  # e.g. "snow.create_ticket"
    args: dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    """An ordered list of tool calls produced by the planning agent."""

    intent: Intent
    template: str
    steps: list[ToolCall]
    summary: str