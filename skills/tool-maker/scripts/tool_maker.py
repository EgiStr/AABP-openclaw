#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import textwrap
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TOOL_MAKER_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = Path(__file__).resolve().parent
STAGING_ROOT = TOOL_MAKER_ROOT / "staging"
SKILLS_ROOT = PROJECT_ROOT / "skills"
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(ENV_PATH)


@dataclass
class GenerationResult:
    ok: bool
    request_id: str
    tool_name: str
    attempt: int
    traceback: str
    bundle_file: Path


def _normalize_tool_name(name: str) -> str:
    normalized = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in name.lower())
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized[:64] or "generated-skill"


def _build_fallback_code(payload: Dict[str, Any], traceback_text: str = "") -> str:
    tool_name = payload["tool_name"]
    description = payload.get("description", "Auto generated skill")
    required_inputs = payload.get("required_inputs", ["query"])
    required_literal = ", ".join(repr(x) for x in required_inputs)
    return textwrap.dedent(
        f'''
        from __future__ import annotations

        from typing import Any, Dict

        try:
            from zeroclaw.skills.base import BaseSkill
        except Exception:
            from base_skill_contract import BaseSkill


        class GeneratedSkill(BaseSkill):
            name = "{tool_name}"
            description = "{description}"

            def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
                missing = [k for k in [{required_literal}] if k not in payload]
                if missing:
                    return {{"ok": False, "error": f"missing inputs: {{', '.join(missing)}}"}}

                return {{
                    "ok": True,
                    "skill": self.name,
                    "received": payload,
                    "note": "Template generated. Implement API integration in this method."
                }}

            def healthcheck(self) -> Dict[str, Any]:
                return {{"ok": True, "skill": self.name}}
        '''
    ).strip() + "\n"


def _generate_with_llm(payload: Dict[str, Any], traceback_text: str = "") -> str:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    model = os.getenv("TOOL_MAKER_MODEL", "openai/gpt-4.1-mini")
    if not api_key:
        return _build_fallback_code(payload, traceback_text)

    system_prompt = (
        "You generate a single Python file implementing a skill class that inherits BaseSkill. "
        "Output only code, no markdown. Must include: class GeneratedSkill(BaseSkill), run(payload), healthcheck(). "
        "Import pattern must be: try zeroclaw BaseSkill, then fallback to base_skill_contract BaseSkill."
    )
    user_prompt = {
        "task": "Generate skill code",
        "payload": payload,
        "previous_traceback": traceback_text,
        "constraints": [
            "Return JSON-serializable dict from run",
            "Do not read local files",
            "No infinite loops",
            "Keep implementation concise",
        ],
    }
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
                ],
                "temperature": 0.2,
            },
            timeout=90,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return content.strip() + "\n"
    except Exception:
        return _build_fallback_code(payload, traceback_text)


def _validate_base_skill_contract(code_text: str) -> Tuple[bool, str]:
    try:
        tree = ast.parse(code_text)
    except SyntaxError as exc:
        return False, f"SyntaxError: {exc}"

    class_node = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "GeneratedSkill":
            class_node = node
            break

    if class_node is None:
        return False, "GeneratedSkill class not found"

    base_names = []
    for base in class_node.bases:
        if isinstance(base, ast.Name):
            base_names.append(base.id)
        elif isinstance(base, ast.Attribute):
            base_names.append(base.attr)

    if "BaseSkill" not in base_names:
        return False, "GeneratedSkill must inherit BaseSkill"

    methods = {node.name for node in class_node.body if isinstance(node, ast.FunctionDef)}
    for required in ["run", "healthcheck"]:
        if required not in methods:
            return False, f"Missing required method: {required}"

    return True, "ok"


def _sandbox_check(skill_file: Path, timeout_sec: int = 25) -> Tuple[bool, str]:
    def _local_compile_check() -> Tuple[bool, str]:
        proc = subprocess.run(
            [sys.executable, "-m", "py_compile", str(skill_file)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return False, (proc.stderr or proc.stdout).strip()
        return True, "docker unavailable, py_compile only"

    docker = shutil.which("docker")
    if not docker:
        return _local_compile_check()

    docker_info = subprocess.run([docker, "info"], capture_output=True, text=True)
    if docker_info.returncode != 0:
        return _local_compile_check()

    runner_code = textwrap.dedent(
        """
        import importlib.util
        import json
        import pathlib

        skill_path = pathlib.Path('/workspace/generated_skill.py')
        spec = importlib.util.spec_from_file_location('generated_skill', skill_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        skill = mod.GeneratedSkill()
        hc = skill.healthcheck()
        res = skill.run({'query': 'smoke-test', 'dry_run': True})
        print(json.dumps({'healthcheck': hc, 'result': res}))
        """
    ).strip()

    workspace_dir = skill_file.parent
    runner_path = workspace_dir / "_sandbox_runner.py"
    generated_path = workspace_dir / "generated_skill.py"
    contract_src = SCRIPTS_ROOT / "base_skill_contract.py"
    contract_dst = workspace_dir / "base_skill_contract.py"

    shutil.copyfile(skill_file, generated_path)
    shutil.copyfile(contract_src, contract_dst)
    runner_path.write_text(runner_code, encoding="utf-8")

    cmd = [
        docker,
        "run",
        "--rm",
        "--network",
        "none",
        "--memory",
        "256m",
        "--cpus",
        "1",
        "-v",
        f"{workspace_dir.resolve()}:/workspace",
        "python:3.11-slim",
        "python",
        "/workspace/_sandbox_runner.py",
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        return False, "Sandbox timeout exceeded"
    finally:
        for tmp in [runner_path, generated_path, contract_dst]:
            if tmp.exists():
                tmp.unlink()

    if proc.returncode != 0:
        error_text = (proc.stderr or proc.stdout).strip()
        if "docker api" in error_text.lower() or "dockerdesktoplinuxengine" in error_text.lower():
            return _local_compile_check()
        return False, error_text
    return True, (proc.stdout or "sandbox ok").strip()


def _write_bundle(request_dir: Path, payload: Dict[str, Any], code: str, result: Dict[str, Any]) -> Path:
    bundle = {
        "request_id": request_dir.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
        "result": result,
        "code_preview": "\n".join(code.splitlines()[:80]),
    }
    bundle_file = request_dir / "bundle.json"
    bundle_file.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    return bundle_file


def generate(payload: Dict[str, Any], max_attempts: int = 3) -> GenerationResult:
    tool_name = _normalize_tool_name(payload["tool_name"])
    request_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    request_dir = STAGING_ROOT / request_id
    request_dir.mkdir(parents=True, exist_ok=True)
    payload["tool_name"] = tool_name

    traceback_text = ""
    latest_bundle: Optional[Path] = None

    for attempt in range(1, max_attempts + 1):
        code = _generate_with_llm(payload, traceback_text=traceback_text)
        skill_file = request_dir / f"{tool_name}.py"
        skill_file.write_text(code, encoding="utf-8")

        valid, validation_msg = _validate_base_skill_contract(code)
        if not valid:
            traceback_text = validation_msg
            latest_bundle = _write_bundle(
                request_dir,
                payload,
                code,
                {"ok": False, "attempt": attempt, "traceback": validation_msg},
            )
            continue

        sandbox_ok, sandbox_out = _sandbox_check(skill_file)
        latest_bundle = _write_bundle(
            request_dir,
            payload,
            code,
            {
                "ok": sandbox_ok,
                "attempt": attempt,
                "traceback": "" if sandbox_ok else sandbox_out,
                "sandbox_output": sandbox_out,
            },
        )
        if sandbox_ok:
            return GenerationResult(
                ok=True,
                request_id=request_id,
                tool_name=tool_name,
                attempt=attempt,
                traceback="",
                bundle_file=latest_bundle,
            )

        traceback_text = sandbox_out

    return GenerationResult(
        ok=False,
        request_id=request_id,
        tool_name=tool_name,
        attempt=max_attempts,
        traceback=traceback_text,
        bundle_file=latest_bundle if latest_bundle else request_dir / "bundle.json",
    )


def _send_telegram_approval(chat_id: str, text: str, request_id: str) -> Dict[str, Any]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN is not set"}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    keyboard = {
        "inline_keyboard": [
            [{"text": "Approve & Deploy", "callback_data": f"toolmaker:approve:{request_id}"}],
            [{"text": "View Code", "callback_data": f"toolmaker:view:{request_id}"}],
            [{"text": "Reject", "callback_data": f"toolmaker:reject:{request_id}"}],
        ]
    }
    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": keyboard,
        "parse_mode": "Markdown",
    }
    try:
        resp = requests.post(url, json=payload, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        return {"ok": bool(data.get("ok")), "response": data}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def notify(bundle_file: Path, chat_id: str) -> Dict[str, Any]:
    data = json.loads(bundle_file.read_text(encoding="utf-8"))
    payload = data["payload"]
    result = data["result"]
    request_id = data["request_id"]

    lines = [
        "*Tool-Maker Request*",
        f"Request ID: `{request_id}`",
        f"Tool: `{payload.get('tool_name')}`",
        f"Status Uji: {'✅ PASS' if result.get('ok') else '❌ FAIL'}",
        f"Percobaan: {result.get('attempt')}",
    ]
    api_hints = payload.get("api_key_hints") or []
    if api_hints:
        lines.append(f"API Key Tambahan: {', '.join(api_hints)}")
    if not result.get("ok"):
        lines.append(f"Traceback ringkas: {str(result.get('traceback', ''))[:240]}")
    lines.append("\nPilih aksi:")

    return _send_telegram_approval(chat_id=chat_id, text="\n".join(lines), request_id=request_id)


def _hot_reload() -> Dict[str, Any]:
    commands = [
        ["zeroclaw", "skills", "reload"],
        ["zeroclaw", "daemon", "reload"],
    ]
    for cmd in commands:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if proc.returncode == 0:
                return {"ok": True, "command": " ".join(cmd), "output": (proc.stdout or "").strip()}
        except Exception:
            continue
    return {"ok": False, "error": "Hot-reload command unavailable"}


def _write_generated_skill_md(skill_dir: Path, payload: Dict[str, Any]) -> None:
    content = textwrap.dedent(
        f"""
        ---
        name: {payload['tool_name']}
        description: "{payload.get('description', 'Auto-generated skill')}"
        ---

        # {payload['tool_name']}

        Auto-generated by Tool-Maker.

        ## Required Inputs
        {json.dumps(payload.get('required_inputs', []), ensure_ascii=False)}

        ## Expected Output
        {payload.get('expected_output', 'JSON object')}
        """
    ).strip() + "\n"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def handle_action(request_id: str, action: str) -> Dict[str, Any]:
    request_dir = STAGING_ROOT / request_id
    bundle_file = request_dir / "bundle.json"
    if not bundle_file.exists():
        return {"ok": False, "error": f"bundle not found: {bundle_file}"}

    bundle = json.loads(bundle_file.read_text(encoding="utf-8"))
    payload = bundle["payload"]
    tool_name = payload["tool_name"]
    code_file = request_dir / f"{tool_name}.py"

    if action == "view":
        return {
            "ok": True,
            "request_id": request_id,
            "code_file": str(code_file),
            "code": code_file.read_text(encoding="utf-8") if code_file.exists() else "",
        }

    if action == "reject":
        return {"ok": True, "request_id": request_id, "status": "rejected"}

    if action != "approve":
        return {"ok": False, "error": f"unknown action: {action}"}

    if not code_file.exists():
        return {"ok": False, "error": f"generated code not found: {code_file}"}

    skill_dir = SKILLS_ROOT / tool_name
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    target_py = scripts_dir / f"{tool_name}.py"
    target_contract = scripts_dir / "base_skill_contract.py"
    shutil.copyfile(code_file, target_py)
    shutil.copyfile(SCRIPTS_ROOT / "base_skill_contract.py", target_contract)
    _write_generated_skill_md(skill_dir, payload)

    reload_result = _hot_reload()
    return {
        "ok": True,
        "request_id": request_id,
        "status": "deployed",
        "target": str(target_py),
        "reload": reload_result,
    }


def _load_payload(args: argparse.Namespace) -> Dict[str, Any]:
    if args.payload_file:
        return json.loads(Path(args.payload_file).read_text(encoding="utf-8-sig"))
    if args.payload_json:
        raw = args.payload_json.strip()
        if (raw.startswith("'") and raw.endswith("'")) or (raw.startswith('"') and raw.endswith('"')):
            raw = raw[1:-1]
        return json.loads(raw)
    raise ValueError("Provide --payload-file or --payload-json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tool-Maker orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)

    p_generate = sub.add_parser("generate", help="Generate and sandbox-test a new skill")
    p_generate.add_argument("--payload-file", help="Path to payload JSON file")
    p_generate.add_argument("--payload-json", help="Raw payload JSON string")
    p_generate.add_argument("--max-attempts", type=int, default=3)

    p_notify = sub.add_parser("notify", help="Send Telegram HITL approval request")
    p_notify.add_argument("--bundle-file", required=True)
    p_notify.add_argument("--chat-id", required=True)

    p_action = sub.add_parser("handle-action", help="Handle approve/view/reject")
    p_action.add_argument("--request-id", required=True)
    p_action.add_argument("--action", required=True, choices=["approve", "view", "reject"])

    args = parser.parse_args()
    STAGING_ROOT.mkdir(parents=True, exist_ok=True)

    if args.command == "generate":
        payload = _load_payload(args)
        result = generate(payload=payload, max_attempts=args.max_attempts)
        print(
            json.dumps(
                {
                    "ok": result.ok,
                    "request_id": result.request_id,
                    "tool_name": result.tool_name,
                    "attempt": result.attempt,
                    "traceback": result.traceback,
                    "bundle_file": str(result.bundle_file),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        sys.exit(0 if result.ok else 1)

    if args.command == "notify":
        response = notify(Path(args.bundle_file), chat_id=args.chat_id)
        print(json.dumps(response, indent=2, ensure_ascii=False))
        sys.exit(0 if response.get("ok") else 1)

    if args.command == "handle-action":
        response = handle_action(request_id=args.request_id, action=args.action)
        print(json.dumps(response, indent=2, ensure_ascii=False))
        sys.exit(0 if response.get("ok") else 1)


if __name__ == "__main__":
    main()
