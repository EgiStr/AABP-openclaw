---
name: tool-maker
description: "Self-synthesizing skill framework. Detects capability gaps, generates new Python skills in sandbox, and requests HITL approval before deployment."
---

# Tool-Maker Skill (EPIC 5)

This skill is invoked when ABA detects a **skill gap** (missing capability), then:
1. Builds a `trigger_tool_maker_skill` payload
2. Generates a new Python skill dynamically
3. Runs verification in a Docker sandbox
4. Applies auto-fix up to 3 iterations when tracebacks occur
5. Sends HITL notification to Telegram
6. Deploys + hot-reloads after approval

## Token Efficiency Rules
- Use minimal payloads: send only critical inputs (`tool_name`, `description`, `required_inputs`, `expected_output`).
- Summarize tracebacks before returning to the generator (avoid sending full long logs).
- For multiple independent requests, process generate/notify in batched rounds.
- Keep user-facing responses concise-first; show full code only when requested (`View Code`).

## Story 5.1 — Autonomous Skill Gap Detection

Use the script:

```bash
python skills/tool-maker/scripts/trigger_tool_maker_skill.py \
  --instruction "ambil tren lowongan tech stack terbaru"
```

If a gap is detected, JSON output includes:
- `trigger`: `trigger_tool_maker_skill`
- `tool_name`, `description`, `required_inputs`, `expected_output`
- `requires_external_api`, `api_key_hints`

## Story 5.2 — Sandboxed Code Generation & Execution

Generate + test in sandbox:

```bash
python skills/tool-maker/scripts/tool_maker.py generate \
  --payload-file tmp_payload.json
```

Behavior:
- Code must define a class inheriting from `BaseSkill`
- Class structure is validated with AST
- Syntax + smoke tests run in Docker (`python:3.11-slim`)
- On traceback, auto-fix retries up to 3 attempts
- Keep generation output length constrained for token efficiency

## Story 5.3 — HITL Registration & Deployment

Send approval request:

```bash
python skills/tool-maker/scripts/tool_maker.py notify \
  --bundle-file skills/tool-maker/staging/<request_id>/bundle.json \
  --chat-id <telegram_chat_id>
```

Telegram action buttons sent:
- `[Approve & Deploy]`
- `[View Code]`
- `[Reject]`

Handle approval action:

```bash
python skills/tool-maker/scripts/tool_maker.py handle-action \
  --request-id <request_id> \
  --action approve
```

On `approve`:
- Skill is moved to `/skills/<tool_name>/scripts/`
- `SKILL.md` is generated automatically
- Hot-reload is triggered via `zeroclaw skills reload` (fallback: `zeroclaw daemon reload`)
