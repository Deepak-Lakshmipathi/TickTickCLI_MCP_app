"""
TickTick OAuth 2.0 Authentication
Handles the full OAuth flow, token storage, and refresh.
"""

import json
import os
import sys
import time
import webbrowser
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import httpx

AUTH_URL = "https://ticktick.com/oauth/authorize"
TOKEN_URL = "https://ticktick.com/oauth/token"
DEFAULT_REDIRECT_URI = "http://localhost:8765/callback"
SCOPES = "tasks:read tasks:write"

CONFIG_DIR = Path.home() / ".config" / "ticktick-cli"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> dict:
    """Load config from disk."""
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def save_config(config: dict):
    """Save config to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
    # Restrict permissions to owner only
    CONFIG_FILE.chmod(0o600)


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Tiny HTTP handler that captures the OAuth callback code."""

    auth_code = None

    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)

        if "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authorization successful!</h2>"
                b"<p>You can close this tab and return to the terminal.</p>"
                b"</body></html>"
            )
        else:
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            error = params.get("error", ["unknown"])[0]
            self.wfile.write(f"<html><body><h2>Error: {error}</h2></body></html>".encode())

    def log_message(self, format, *args):
        # Suppress default logging
        pass


def do_oauth_flow(client_id: str, client_secret: str, redirect_uri: str = DEFAULT_REDIRECT_URI) -> dict:
    """
    Run the full OAuth authorization code flow.
    Opens a browser, catches the callback, exchanges for tokens.
    Returns the token response dict.
    """
    # Parse port from redirect URI
    parsed = urllib.parse.urlparse(redirect_uri)
    port = parsed.port or 8765

    # Build authorization URL
    auth_params = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "state": "ticktick_cli",
    })
    auth_url = f"{AUTH_URL}?{auth_params}"

    print(f"\nOpening browser for authorization...")
    print(f"If it doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    # Start local server to catch the callback
    server = HTTPServer(("localhost", port), OAuthCallbackHandler)
    server.timeout = 120  # 2 minute timeout

    print(f"Waiting for callback on port {port}...")
    while OAuthCallbackHandler.auth_code is None:
        server.handle_request()

    auth_code = OAuthCallbackHandler.auth_code
    OAuthCallbackHandler.auth_code = None  # Reset
    server.server_close()

    print("Got authorization code, exchanging for tokens...")

    # Exchange code for tokens
    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    response.raise_for_status()
    token_data = response.json()

    return token_data


def setup(client_id: str, client_secret: str, redirect_uri: str = DEFAULT_REDIRECT_URI):
    """
    Full setup: run OAuth flow and save everything to config.
    """
    token_data = do_oauth_flow(client_id, client_secret, redirect_uri)

    config = {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token"),
        "token_type": token_data.get("token_type", "bearer"),
        "expires_at": time.time() + token_data.get("expires_in", 3600),
    }

    save_config(config)
    print(f"\nSetup complete! Config saved to {CONFIG_FILE}")
    return config


def refresh_access_token(config: dict) -> dict:
    """Refresh the access token using the refresh token."""
    if not config.get("refresh_token"):
        raise RuntimeError("No refresh token found. Run 'ticktick setup' again.")

    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": config["refresh_token"],
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    response.raise_for_status()
    token_data = response.json()

    config["access_token"] = token_data.get("access_token", config["access_token"])
    if "refresh_token" in token_data:
        config["refresh_token"] = token_data["refresh_token"]
    config["expires_at"] = time.time() + token_data.get("expires_in", 3600)

    save_config(config)
    return config


def get_valid_token() -> str:
    """
    Returns a valid access token, refreshing if necessary.
    This is the main entry point other modules should use.
    """
    config = load_config()

    if not config.get("access_token"):
        print("Not authenticated. Run: ticktick setup <client_id> <client_secret>")
        sys.exit(1)

    # Refresh if token expires within 5 minutes
    if config.get("expires_at", 0) < time.time() + 300:
        try:
            config = refresh_access_token(config)
        except Exception as e:
            print(f"Token refresh failed: {e}")
            print("Run: ticktick setup <client_id> <client_secret>")
            sys.exit(1)

    return config["access_token"]
