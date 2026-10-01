at design.md 
# Adaptive ServiceNow Workflow Bots — Design Document

## 1. Team & Mission

**Team:** Adaptive ServiceNow Workflow Bots
**Mission:** Build adaptive, agent-driven bots that orchestrate ServiceNow ticket creation and lifecycle management for HR-driven workflows (onboarding, offboarding, transfers, access changes) and generalize to similar request patterns.
**Stack:** Python 3.11+ · MCP Gateway (Model Context Protocol) · ServiceNow Table API (REST) · Claude as the planning LLM.

---

## 2. Goals & Non-Goals

### Goals
- Automate ticket creation for **onboarding** and **offboarding** workflows.
- **Adapt** to new but similar ServiceNow request types via prompt + config (no code change required for new templates).
- Route bot tool calls through a single **MCP Gateway** so downstream integrations (ServiceNow, Slack, Jira, etc.) are pluggable.
- Provide a **human-in-the-loop** approval step before ticket submission.
- Be observable: every action logged with request ID, actor, payload diff, and outcome.

### Non-Goals (v1)
- Full ServiceNow CMDB sync or discovery.
- Bidirectional ticket state sync (initial scope is creation + status read).
- Replacing the ServiceNow Flow Designer — we integrate with it, not replace it.
- Multi-tenant ServiceNow instances (single instance per deployment in v1).

---

## 3. High-Level Architecture

```
┌─────────────┐    natural-language request
│   User /    │ ───────────────────────────────┐
│   HRIS Webhook                                │
└─────────────┘                                 │
                                                 ▼
                                ┌─────────────────────────────┐
                                │  Claude Planning Agent      │
                                │  (intent + plan extraction) │
                                └─────────────┬───────────────┘
                                              │ tool calls
                                              ▼
                                ┌─────────────────────────────┐
                                │       MCP Gateway           │
                                │  (auth, rate limit, audit)  │
                                └─────────────┬───────────────┘
                                              │ tool invocations
                          ┌───────────────────┼───────────────────┐
                          ▼                   ▼                   ▼
              ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
              │ ServiceNow MCP   │ │ Approval MCP     │ │ Notification MCP │
              │ Server (REST)    │ │ Server (Slack/   │ │ Server (email,   │
              │                  │ │  Teams, web)     │ │  webhook)        │
              └────────┬─────────┘ └──────────────────┘ └──────────────────┘
                       │
                       ▼
              ┌──────────────────┐
              │   ServiceNow     │
              │  Table API (REST)│
              └──────────────────┘
```

### Component responsibilities

| Component | Responsibility |
|---|---|
| **Planning Agent (Claude)** | Parse free-text/HRIS event → structured intent + plan (list of MCP tool calls). |
| **MCP Gateway** | Single entry point. Handles auth, rate limiting, audit logging, tool routing. |
| **ServiceNow MCP Server** | Wraps ServiceNow Table API. Exposes `create_ticket`, `get_ticket`, `update_ticket`, `list_templates`. |
| **Approval MCP Server** | Posts approval cards to Slack/Teams, awaits human response. |
| **Notification MCP Server** | Sends confirmation emails/webhooks after ticket creation. |
| **Template Registry** | YAML/JSON definitions mapping intents → ServiceNow field schemas. |

---

## 4. MCP Gateway Integration

The MCP Gateway is the central nervous system. The Claude agent **never calls ServiceNow directly**; it only knows about MCP tools.

### Tool surface (exposed to the agent)
- `snow.create_ticket(template, payload)` — create a record from a template
- `snow.get_ticket(sys_id)` — fetch a ticket
- `snow.update_ticket(sys_id, fields)` — update specific fields
- `snow.list_templates()` — discover available ticket templates
- `approval.request(summary, fields)` — request human approval
- `notify.send(channel, message)` — send a notification

### Why MCP Gateway (not direct API calls)
- **Single auth boundary** — ServiceNow OAuth token lives in the gateway, not in every bot process.
- **Auditability** — every tool call is logged with actor, prompt hash, and payload.
- **Composability** — adding Jira/Confluence/Slack is one new MCP server, no agent change.
- **Rate limiting** — gateway enforces ServiceNow's quota across all bot instances.

### Gateway config example
```yaml
mcp_gateway:
  endpoint: https://mcp.internal.acme.com
  auth:
    type: oauth_client_credentials
    client_id_env: MCP_CLIENT_ID
    client_secret_env: MCP_CLIENT_SECRET
  servers:
    - name: servicenow
      transport: http
      endpoint: https://mcp-snow.internal/sse
    - name: approval
      transport: http
      endpoint: https://mcp-approval.internal/sse
    - name: notify
      transport: http
      endpoint: https://mcp-notify.internal/sse
  rate_limit:
    requests_per_minute: 60
    burst: 10
```

---

## 5. ServiceNow API Integration

We use the **Table API** (`/api/now/table/{table}`) over HTTPS with OAuth 2.0.

### Tables we touch in v1
| Table | Purpose |
|---|---|
| `sc_req_item` / `sc_request` | Service catalog requests (preferred for catalog-driven onboarding/offboarding) |
| `incident` | Ad-hoc IT issues surfaced during provisioning |
| `sys_user` | Read-only lookup of employee record |
| `cmn_location` | Read-only lookup of office/site |
| `sn_hr_core_profile` | HR profile (if HR module licensed) |

### Auth flow
1. Bot process requests a token from ServiceNow via OAuth client-credentials.
2. Token cached for `expires_in - 60s`.
3. All requests go through MCP Gateway, which holds the token.

### Error handling
- **4xx** (except 429): retry once after fixing payload; otherwise surface to agent.
- **429**: respect `Retry-After`; gateway enforces backoff.
- **5xx**: exponential backoff up to 3 attempts, then fail-soft and notify.

---

## 6. Workflow Definitions

### 6.1 Onboarding

**Trigger:** HRIS webhook `employee.created` OR a Slack message like *"Onboard Jane Doe starting Mon, E5, SF office, manager: @alice"*.

**Plan (sequence of MCP tool calls):**
1. `snow.list_templates()` → pick `onboarding_standard`
2. `approval.request(summary, draft_fields)` → human approves bundle
3. `snow.create_ticket(template="onboarding_standard", payload={...})` → creates the parent RITM
4. For each subtask (laptop, badge, accounts, parking): `snow.create_ticket(template="onboarding_subtask", payload={..., parent=sys_id})`
5. `notify.send(channel="#hr-ops", message=...)` → confirmation

**Onboarding ticket fields (default):**
```yaml
template: onboarding_standard
fields:
  short_description: "Onboard {employee_name} ({start_date})"
  assignment_group: "IT-Onboarding"
  category: "Onboarding"
  variables:
    employee_name: string (required)
    start_date: date (required, >= today)
    manager: reference sys_user (required)
    location: reference cmn_location
    role: string
    hardware_tier: enum [standard, engineering, executive]
    required_software: list[string]
```

### 6.2 Offboarding

**Trigger:** HRIS webhook `employee.terminated` OR *"Offboard John Smith, last day Fri, transfer knowledge to @bob"*.

**Plan:**
1. `snow.list_templates()` → pick `offboarding_standard`
2. `approval.request(...)` → manager + IT security co-approve
3. `snow.create_ticket(template="offboarding_standard", payload={...})` → parent
4. Subtasks: `revoke_access`, `recover_assets`, `archive_accounts`, `knowledge_transfer`
5. Schedule a follow-up `snow.update_ticket` on `last_day + 1` to verify completion.
6. `notify.send(channel="#it-security", message=...)`

**Offboarding fields:**
```yaml
template: offboarding_standard
fields:
  short_description: "Offboard {employee_name} (last day {last_day})"
  assignment_group: "IT-Offboarding"
  category: "Offboarding"
  variables:
    employee_name: string (required)
    last_day: date (required)
    manager: reference sys_user
    knowledge_transfer_to: reference sys_user
    reason: enum [voluntary, involuntary, retirement, other]
    asset_return_required: boolean
```

### 6.3 Generalization path
Adding a new workflow (e.g. *role transfer*, *contractor onboarding*) is:
1. Author a YAML template in `templates/`.
2. Register it in the Template Registry.
3. Add a short natural-language description the agent uses for routing.

No agent code change required.

---

## 7. Safety & Approval

- **Destructive fields** (anything matching `*_terminated`, `state=closed_incomplete`, `active=false` on `sys_user`) require an `approval.request` call before `snow.update_ticket`.
- **Cost > $X** tickets (configurable) require manager approval.
- All tool calls are **idempotency-keyed** by `(intent_id, step_index)` to prevent double-submission on retry.

---

## 8. Observability

- **Structured logs** (JSON) per tool call: `request_id`, `actor`, `tool`, `args_hash`, `result_summary`, `latency_ms`, `gateway_decision`.
- **Tracing** via OpenTelemetry; gateway emits spans, agent emits spans, correlated by `trace_id`.
- **Metrics** (Prometheus): tool calls/min, error rate by tool, approval wait time, ticket creation latency.

---

## 9. Repository Layout (proposed)

```
.
├── docs/
│   └── design.md                 # this document
├── bots/
│   ├── planning_agent/           # Claude agent + prompt templates
│   ├── orchestrator/             # plan → tool-call execution
│   └── hris_listener/            # webhook receiver
├── mcp_servers/
│   ├── servicenow/               # ServiceNow Table API wrapper
│   ├── approval/                 # Slack/Teams approval
│   └── notify/                   # email/webhook
├── templates/                    # YAML ticket templates
│   ├── onboarding_standard.yaml
│   ├── onboarding_subtask.yaml
│   ├── offboarding_standard.yaml
│   └── ...
├── gateway/
│   ├── config.example.yaml
│   └── policy/                   # approval rules, rate limits
├── tests/
│   ├── unit/
│   ├── integration/              # mocks ServiceNow
│   └── e2e/                      # full agent run
├── deploy/
│   ├── docker/
│   └── k8s/
├── pyproject.toml
└── README.md
```

---

## 10. Milestones

| Milestone | Deliverable | Exit criteria |
|---|---|---|
| **M0 — Foundations** | Repo layout, MCP Gateway config, ServiceNow MCP server stub, one template (onboarding) | Can create one onboarding ticket end-to-end against a dev ServiceNow instance |
| **M1 — Onboarding** | Planning agent, approval flow, notifications | HRIS webhook → approval → ticket → Slack confirmation |
| **M2 — Offboarding** | Offboarding template + dual approval | Same flow with two-step approval |
| **M3 — Generalization** | Template registry, 3+ templates | New template can be added via config only |
| **M4 — Hardening** | Observability, error handling, runbook | SLOs defined; load test passes; on-call runbook reviewed |

---

## 11. Open Questions

1. **Identity provider** — does the bot act on behalf of an integration user, or per-HR-user with delegated auth? (Recommendation: integration user for v1.)
2. **Catalog vs. incident** — confirm the standard ServiceNow practice at the target instance is to use `sc_req_item` for onboarding, not `incident`.
3. **HRIS source of truth** — Workday? BambooHR? Custom? Drives webhook payload schema.
4. **Approval system** — Slack, Teams, ServiceNow's native approval engine, or all of the above?
5. **Region / data residency** — any constraints on where the bot process and gateway run?