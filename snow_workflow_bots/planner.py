"""Build a plan from a free-text or HRIS-style intent + payload.

The plan is a sequence of MCP tool calls. The orchestrator executes them
in order. This is the *agent* step in the design doc — the actual LLM call
is a future swap-in; for M0 we use a deterministic builder keyed on intent.
"""
from __future__ import annotations

from .models import Intent, Plan, ToolCall
from .templates import TemplateRegistry


def build_plan(
    intent: Intent,
    template_name: str,
    payload: dict,
    *,
    registry: TemplateRegistry,
    request_id: str = "demo",
) -> Plan:
    tpl = registry.get(template_name)
    missing = registry.validate_payload(tpl, payload)
    if missing:
        raise ValueError(f"Template {template_name} missing fields: {missing}")

    short = payload.get("short_description") or tpl.description.format(**payload)
    parent_sys_id = "{snow_sys_id}"  # filled in at orchestrator time

    steps: list[ToolCall] = [
        ToolCall(name="approval.request", args={"summary": short, "fields": payload}),
        ToolCall(
            name="snow.create_ticket",
            args={"table": tpl.table, "fields": {"short_description": short, **payload}},
        ),
    ]

    if tpl.subtask_template:
        for sub in payload.get("subtasks", []):
            steps.append(
                ToolCall(
                    name="snow.create_ticket",
                    args={
                        "table": tpl.table,
                        "fields": {
                            "short_description": sub["short_description"],
                            "parent": parent_sys_id,
                            **sub,
                        },
                    },
                )
            )

    steps.append(
        ToolCall(
            name="notify.send",
            args={"channel": "#hr-ops", "message": f"Created {template_name}: {short}"},
        )
    )

    return Plan(
        intent=intent,
        template=template_name,
        steps=steps,
        summary=f"{intent.value} → {template_name} ({len(steps)} steps)",
    )