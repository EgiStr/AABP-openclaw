#!/usr/bin/env python3
"""
LinkedIn Post Publisher
-----------------------
Publishes a post to LinkedIn using the REST API v2 (Posts API).

Usage:
    python linkedin_post.py --text "Post content..." --hashtags "#AI #DataEngineering"
    python linkedin_post.py --text "Test post" --dry-run

Exit codes:
    0 = success
    1 = failure (see stderr for details)
"""

import os
import sys
import json
import argparse
from pathlib import Path

try:
    import requests
    from dotenv import load_dotenv
except ImportError:
    print("❌ Missing dependencies. Install them first:", file=sys.stderr)
    print("   uv sync", file=sys.stderr)
    sys.exit(1)

# ─── Configuration ──────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(ENV_PATH)

ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
PERSON_URN = os.getenv("LINKEDIN_PERSON_URN", "")

POSTS_API_URL = "https://api.linkedin.com/rest/posts"
API_VERSION = "202401"  # LinkedIn API versioning

# ─── Post Builder ───────────────────────────────────────────


def build_post_payload(text: str, hashtags: str = "") -> dict:
    """
    Build the LinkedIn Posts API payload.

    Args:
        text: The post body text.
        hashtags: Space-separated hashtags (e.g., "#AI #Python").

    Returns:
        dict: The API request payload.
    """
    # Append hashtags to the post text
    full_text = text.strip()
    if hashtags:
        full_text += "\n\n" + hashtags.strip()

    # LinkedIn Posts API payload
    payload = {
        "author": PERSON_URN,
        "commentary": full_text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }

    return payload


def validate_config():
    """Ensure required env vars are set."""
    errors = []
    if not ACCESS_TOKEN:
        errors.append("LINKEDIN_ACCESS_TOKEN is not set")
    if not PERSON_URN:
        errors.append("LINKEDIN_PERSON_URN is not set")
    if errors:
        for e in errors:
            print(f"❌ {e}", file=sys.stderr)
        print(f"\nRun linkedin_oauth.py first to set up credentials.", file=sys.stderr)
        sys.exit(1)


def validate_content(text: str):
    """Validate post content constraints."""
    if not text or not text.strip():
        print("❌ Post text cannot be empty.", file=sys.stderr)
        sys.exit(1)

    if len(text) > 3000:
        print(
            f"❌ Post exceeds LinkedIn's 3000 character limit ({len(text)} chars).",
            file=sys.stderr,
        )
        sys.exit(1)


# ─── Publisher ──────────────────────────────────────────────


def publish_post(payload: dict) -> dict:
    """
    Publish a post to LinkedIn via the Posts API.

    Args:
        payload: The API request payload.

    Returns:
        dict: Response with status and details.
    """
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": API_VERSION,
    }

    response = requests.post(
        POSTS_API_URL,
        headers=headers,
        json=payload,
        timeout=30,
    )

    result = {
        "status_code": response.status_code,
        "success": response.status_code == 201,
    }

    if response.status_code == 201:
        # Extract post ID from x-restli-id header
        post_id = response.headers.get("x-restli-id", "")
        if post_id:
            # Build the post URL
            # URN format: urn:li:share:XXXXX or urn:li:ugcPost:XXXXX
            result["post_id"] = post_id
            # Construct the public URL
            result[
                "post_url"
            ] = f"https://www.linkedin.com/feed/update/{post_id}/"
        result["message"] = "Post published successfully!"
    else:
        # Parse error response
        try:
            error_data = response.json()
            result["error"] = error_data.get(
                "message", error_data.get("error", response.text)
            )
        except (json.JSONDecodeError, ValueError):
            result["error"] = response.text

        # Provide actionable error messages
        if response.status_code == 401:
            result[
                "hint"
            ] = "Access token expired. Re-run linkedin_oauth.py to refresh."
        elif response.status_code == 403:
            result[
                "hint"
            ] = "Missing w_member_social scope. Enable 'Share on LinkedIn' in developer portal."
        elif response.status_code == 422:
            result[
                "hint"
            ] = "Invalid post content. Check character limits and formatting."

    return result


# ─── CLI Interface ──────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Publish a post to LinkedIn via the REST API."
    )
    parser.add_argument(
        "--text",
        required=True,
        help="The post body text.",
    )
    parser.add_argument(
        "--hashtags",
        default="",
        help='Space-separated hashtags (e.g., "#AI #Python").',
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the API payload without publishing.",
    )

    args = parser.parse_args()

    # Validate content
    validate_content(args.text)

    # Build payload
    if not args.dry_run:
        validate_config()

    payload = build_post_payload(args.text, args.hashtags)

    if args.dry_run:
        print("═" * 50)
        print("  DRY RUN — LinkedIn Post Payload")
        print("═" * 50)
        # Mask the author URN for display if not set
        display_payload = payload.copy()
        if not PERSON_URN:
            display_payload["author"] = "urn:li:person:<YOUR_URN>"
        print(json.dumps(display_payload, indent=2, ensure_ascii=False))
        print()
        print(f"📊  Character count: {len(payload['commentary'])}/3000")
        print("✅  Dry run complete. No API call was made.")
        sys.exit(0)

    # Publish
    print("📤  Publishing to LinkedIn...")
    result = publish_post(payload)

    if result["success"]:
        print(f"✅  {result['message']}")
        if "post_url" in result:
            print(f"🔗  {result['post_url']}")
        # Output JSON for the agent to parse
        print(json.dumps(result))
        sys.exit(0)
    else:
        print(
            f"❌  Failed to publish (HTTP {result['status_code']})",
            file=sys.stderr,
        )
        print(f"    Error: {result.get('error', 'Unknown')}", file=sys.stderr)
        if "hint" in result:
            print(f"    Hint: {result['hint']}", file=sys.stderr)
        print(json.dumps(result), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
