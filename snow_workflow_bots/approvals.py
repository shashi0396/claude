"""Lightweight approval and notification abstractions.

In M0 these are auto-approvers / print-to-stdout, so the demo runs offline.
Real implementations (Slack/Teams, SMTP) slot into the same interface later.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ApprovalRequest:
    summary: str
    fields: dict[str, Any]


class AutoApprover:
    """Approves every request; logs the payload."""

    def __init__(self) -> None:
        self.approved: list[ApprovalRequest] = []

    def request(self, req: ApprovalRequest) -> bool:
        self.approved.append(req)
        return True


class StdoutNotifier:
    """Prints every notification; in real life this is Slack/email."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send(self, channel: str, message: str) -> dict[str, Any]:
        record = {"channel": channel, "message": message}
        self.sent.append(record)
        print(f"[notify → {channel}] {message}")
        return record