"""ServiceNow MCP server stub.

This file is the skeleton of the MCP server that wraps the ServiceNow
Table API. In M0 we expose the tool *schema* only; the real stdio/SSE
transport wiring will be filled in alongside `mcp>=1.0` in M1.

The bot's planning agent calls these tools via the MCP Gateway, not
directly. Keeping the server as a separate process enforces the gateway
boundary from the design doc.
"""
from __future__ import annotations

from typing import Any

# Tool schemas exposed to the agent. The gateway advertises these.
TOOLS: list[dict[str, Any]] = [
    {
        "name": "snow.list_templates",
        "description": "List available ServiceNow ticket templates.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "snow.create_ticket",
        "description": "Create a ServiceNow record from a template + payload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "e.g. sc_req_item"},
                "fields": {"type": "object"},
            },
            "required": ["table", "fields"],
        },
    },
    {
        "name": "snow.get_ticket",
        "description": "Fetch a ServiceNow record by sys_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table": {"type": "string"},
                "sys_id": {"type": "string"},
            },
            "required": ["table", "sys_id"],
        },
    },
    {
        "name": "snow.update_ticket",
        "description": "Update specific fields on a ServiceNow record.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table": {"type": "string"},
                "sys_id": {"type": "string"},
                "fields": {"type": "object"},
            },
            "required": ["table", "sys_id", "fields"],
        },
    },
    {
        "name": "approval.request",
        "description": "Request human approval before proceeding with a tool call.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "fields": {"type": "object"},
            },
            "required": ["summary"],
        },
    },
    {
        "name": "notify.send",
        "description": "Send a notification to a channel (email, Slack, webhook).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["channel", "message"],
        },
    },
]


def main() -> None:  # pragma: no cover - placeholder
    """Entry point. Real implementation wires the TOOLS list into an MCP server."""
    raise NotImplementedError(
        "MCP server transport wiring lands in M1. "
        "See docs/design.md §4 (MCP Gateway Integration)."
    )


if __name__ == "__main__":  # pragma: no cover
    main()