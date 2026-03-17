#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List


KNOWN_CAPABILITIES = [
    "notebooklm research",
    "linkedin publishing",
    "linkedin oauth",
]


@dataclass
class ToolMakerPayload:
    trigger: str
    requested_at: str
    user_instruction: str
    tool_name: str
    description: str
    required_inputs: List[str]
    expected_output: str
    requires_external_api: bool
    api_key_hints: List[str]


def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9\s-]", "", text).strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:48] or "generated-skill"


def detect_gap(instruction: str) -> bool:
    lowered = instruction.lower()
    if any(cap in lowered for cap in KNOWN_CAPABILITIES):
        return False

    high_signal_keywords = [
        "api",
        "integrasi",
        "fetch",
        "saham",
        "stock",
        "job",
        "lowongan",
        "trend",
        "scrape",
        "github issue",
    ]
    return any(k in lowered for k in high_signal_keywords)


def build_payload(instruction: str) -> ToolMakerPayload:
    lowered = instruction.lower()
    api_hints: List[str] = []
    required_inputs = ["query"]
    expected_output = "JSON object"

    if "saham" in lowered or "stock" in lowered:
        api_hints.append("ALPHA_VANTAGE_API_KEY or FINNHUB_API_KEY")
        required_inputs = ["ticker", "range"]
        expected_output = "OHLC summary, volume trend, and key anomalies in JSON"
    elif "lowongan" in lowered or "job" in lowered:
        api_hints.append("RAPIDAPI_KEY or custom jobs API key")
        required_inputs = ["keywords", "location", "date_range"]
        expected_output = "Top tech stack demand trends and sample vacancies in JSON"

    tool_name = slugify(instruction)
    return ToolMakerPayload(
        trigger="trigger_tool_maker_skill",
        requested_at=datetime.now(timezone.utc).isoformat(),
        user_instruction=instruction,
        tool_name=tool_name,
        description=f"Auto-generated skill for: {instruction}",
        required_inputs=required_inputs,
        expected_output=expected_output,
        requires_external_api=bool(api_hints),
        api_key_hints=api_hints,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect skill gaps and emit Tool-Maker payload.")
    parser.add_argument("--instruction", required=True, help="Original user instruction")
    args = parser.parse_args()

    if not detect_gap(args.instruction):
        print(json.dumps({"triggered": False, "reason": "No skill gap detected"}, ensure_ascii=False))
        return

    payload = build_payload(args.instruction)
    print(json.dumps({"triggered": True, "payload": asdict(payload)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
