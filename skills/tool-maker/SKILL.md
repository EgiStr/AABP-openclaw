---
name: tool-maker
description: "Self-synthesizing skill framework. Detects capability gaps, generates new Python skills in sandbox, and requests HITL approval before deployment."
---

# Tool-Maker Skill (EPIC 5)

Skill ini dipanggil saat ABA menemukan **skill gap** (kapabilitas belum tersedia), lalu:
1. Membuat payload `trigger_tool_maker_skill`
2. Menghasilkan skill Python baru secara dinamis
3. Menjalankan verifikasi di Docker sandbox
4. Melakukan auto-fix maksimal 3 iterasi jika muncul traceback
5. Mengirim notifikasi HITL ke Telegram
6. Deploy + hot-reload setelah approval

## Story 5.1 — Autonomous Skill Gap Detection

Gunakan script:

```bash
python skills/tool-maker/scripts/trigger_tool_maker_skill.py \
  --instruction "ambil tren lowongan tech stack terbaru"
```

Jika terdeteksi gap, output JSON berisi:
- `trigger`: `trigger_tool_maker_skill`
- `tool_name`, `description`, `required_inputs`, `expected_output`
- `requires_external_api`, `api_key_hints`

## Story 5.2 — Sandboxed Code Generation & Execution

Generate + test sandbox:

```bash
python skills/tool-maker/scripts/tool_maker.py generate \
  --payload-file tmp_payload.json
```

Perilaku:
- Kode wajib membentuk class turunan `BaseSkill`
- Validasi struktur class menggunakan AST
- Uji syntax + smoke test di Docker (`python:3.11-slim`)
- Jika traceback, auto-fix hingga 3 percobaan

## Story 5.3 — HITL Registration & Deployment

Kirim approval request:

```bash
python skills/tool-maker/scripts/tool_maker.py notify \
  --bundle-file skills/tool-maker/staging/<request_id>/bundle.json \
  --chat-id <telegram_chat_id>
```

Tombol Telegram yang dikirim:
- `[Approve & Deploy]`
- `[View Code]`
- `[Reject]`

Handle aksi approval:

```bash
python skills/tool-maker/scripts/tool_maker.py handle-action \
  --request-id <request_id> \
  --action approve
```

Saat `approve`:
- Skill dipindahkan ke `/skills/<tool_name>/scripts/`
- `SKILL.md` otomatis dibuat
- Hot-reload dipicu dengan command `zeroclaw skills reload` (fallback `zeroclaw daemon reload`)
