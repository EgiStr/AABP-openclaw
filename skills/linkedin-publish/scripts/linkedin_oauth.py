#!/usr/bin/env python3
"""
LinkedIn OAuth 2.0 Authorization Flow
--------------------------------------
Handles initial token acquisition for the LinkedIn API.

Usage:
    python linkedin_oauth.py

Flow:
    1. Prints authorization URL → user opens in browser
    2. Starts local callback server at LINKEDIN_REDIRECT_URI
    3. Exchanges auth code for access token
    4. Saves token and Person URN to .env
"""

import os
import sys
import json
import webbrowser
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

try:
    import requests
    from dotenv import load_dotenv, set_key
except ImportError:
    print("❌ Missing dependencies. Install them first:")
    print("   uv sync")
    sys.exit(1)

# ─── Configuration ──────────────────────────────────────────

# Walk up from scripts/ to project root to find .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(ENV_PATH)

CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("LINKEDIN_REDIRECT_URI", "http://localhost:3000/callback")

AUTHORIZE_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
PROFILE_URL = "https://api.linkedin.com/v2/userinfo"

SCOPES = ["openid", "profile", "w_member_social", "email"]

# ─── Callback Handler ──────────────────────────────────────

auth_code_holder = {"code": None}


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handles the OAuth 2.0 redirect callback."""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            auth_code_holder["code"] = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>&#10004; Authorization successful!</h1>"
                b"<p>You can close this window and return to the terminal.</p>"
                b"</body></html>"
            )
        elif "error" in params:
            error = params.get("error_description", params["error"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                f"<html><body><h1>&#10060; Authorization failed</h1>"
                f"<p>{error}</p></body></html>".encode("utf-8")
            )
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress default request logging."""
        pass


# ─── OAuth Flow ─────────────────────────────────────────────

def validate_config():
    """Ensure required env vars are set."""
    missing = []
    if not CLIENT_ID:
        missing.append("LINKEDIN_CLIENT_ID")
    if not CLIENT_SECRET:
        missing.append("LINKEDIN_CLIENT_SECRET")
    if missing:
        print(f"❌ Missing environment variables: {', '.join(missing)}")
        print(f"   Please set them in {ENV_PATH}")
        sys.exit(1)


def get_authorization_url():
    """Build the LinkedIn OAuth authorization URL."""
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "state": "aba_linkedin_oauth",
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def wait_for_callback():
    """Start local HTTP server and wait for OAuth callback."""
    parsed = urllib.parse.urlparse(REDIRECT_URI)
    port = parsed.port or 3000

    server = HTTPServer(("localhost", port), OAuthCallbackHandler)
    print(f"⏳  Waiting for callback on {REDIRECT_URI}...")
    server.handle_request()  # Handle single request then return
    server.server_close()

    return auth_code_holder["code"]


def exchange_code_for_token(auth_code):
    """Exchange authorization code for access token."""
    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    response = requests.post(TOKEN_URL, data=data, timeout=30)

    if response.status_code != 200:
        print(f"❌ Token exchange failed: {response.status_code}")
        print(f"   Response: {response.text}")
        sys.exit(1)

    token_data = response.json()
    access_token = token_data["access_token"]
    expires_in = token_data.get("expires_in", "unknown")

    print(f"✅  Access token acquired (expires in {expires_in}s)")
    return access_token


def fetch_person_urn(access_token):
    """Fetch the authenticated user's LinkedIn Person URN."""
    headers = {
        "Authorization": f"Bearer {access_token}",
    }
    response = requests.get(PROFILE_URL, headers=headers, timeout=15)

    if response.status_code != 200:
        print(f"⚠️  Could not fetch profile: {response.status_code}")
        return None

    data = response.json()
    sub = data.get("sub", "")
    if sub:
        person_urn = f"urn:li:person:{sub}"
        print(f"✅  Person URN: {person_urn}")
        return person_urn

    print("⚠️  Could not extract Person URN from profile response.")
    return None


def save_to_env(access_token, person_urn=None):
    """Save credentials to .env file."""
    set_key(str(ENV_PATH), "LINKEDIN_ACCESS_TOKEN", access_token)
    if person_urn:
        set_key(str(ENV_PATH), "LINKEDIN_PERSON_URN", person_urn)
    print(f"💾  Credentials saved to {ENV_PATH}")


# ─── Main ───────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("  LinkedIn OAuth 2.0 — Autonomous Branding Agent")
    print("=" * 50)
    print()

    validate_config()

    # Step 1: Generate and open auth URL
    auth_url = get_authorization_url()
    print("🔗  Open this URL in your browser to authorize:")
    print(f"    {auth_url}")
    print()

    try:
        webbrowser.open(auth_url)
        print("   (Browser opened automatically)")
    except Exception:
        print("   (Could not open browser automatically — please copy the URL)")

    print()

    # Step 2: Wait for callback
    auth_code = wait_for_callback()
    if not auth_code:
        print("❌ No authorization code received.")
        sys.exit(1)

    print(f"✅  Authorization code received")
    print()

    # Step 3: Exchange for token
    access_token = exchange_code_for_token(auth_code)

    # Step 4: Fetch Person URN
    person_urn = fetch_person_urn(access_token)

    # Step 5: Save to .env
    save_to_env(access_token, person_urn)

    print()
    print("🎉  Setup complete! Your agent can now publish to LinkedIn.")
    print("    Token will need to be refreshed when it expires (typically 60 days).")


if __name__ == "__main__":
    main()
