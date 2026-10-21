# /// script
# requires-python = ">=3.11"
# dependencies = ["websockets>=12"]
# ///
# Browser bootstrap adapted from h0me5k1n/eon-next-prepay (MIT).
# See THIRD_PARTY_NOTICES.md.
"""Create an E.ON Next API key using a temporary, user-controlled browser session.

The helper opens Chrome/Chromium with a throwaway profile. The user signs in on
E.ON's own website, including any CAPTCHA or verification step. The helper reads
an Auth0 ID token from that page, closes the browser, and uses the token only to
ask E.ON's Kraken API to create the durable ``sk_live_...`` key.

No E.ON password or Auth0 token is printed or saved. The temporary browser
profile is deleted. By default, the resulting API key is copied to the local
clipboard; pass ``--print`` to write it to the terminal instead.

E.ON permits only one live API key per account. If one already exists, this
helper requires the user to type ``REGENERATE`` before replacing it because the
old key will immediately stop working in every application that uses it.
"""

from __future__ import annotations

import argparse
import asyncio
import http.client
import json
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any

import websockets
from websockets.exceptions import WebSocketException

LOGIN_URL = "https://www.eonnext.com/dashboard/login"
GRAPHQL_HOST = "api.eonnext-kraken.energy"
GRAPHQL_PATH = "/v1/graphql/"
LOGIN_TIMEOUT = 600
BROWSER_NAMES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "brave-browser",
    "brave",
    "microsoft-edge",
    "chrome",
    "chrome.exe",
    "msedge",
    "msedge.exe",
)
BROWSER_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)
READ_ID_TOKEN_JS = """(() => {
  for (const key of Object.keys(localStorage)) {
    if (!key.startsWith('@@auth0spajs@@')) continue;
    try {
      const cached = JSON.parse(localStorage.getItem(key));
      const body = cached?.body;
      const token = cached?.id_token || cached?.decodedToken?.raw ||
                    body?.id_token || body?.decodedToken?.raw;
      if (typeof token === 'string' && token.length > 0) return token;
    } catch (error) {}
  }
  return null;
})()"""
LIVE_SECRET_KEY_QUERY = """query GetLiveSecretKey {
  viewer {
    liveSecretKey
  }
}"""
REGENERATE_SECRET_KEY_MUTATION = """mutation RegenerateSecretKey {
  regenerateSecretKey {
    key
  }
}"""


class HelperError(Exception):
    """An expected, safely displayable helper failure."""


def find_browser(explicit: str | None) -> str:
    """Find a Chromium-family browser executable."""
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.is_file():
            return str(candidate)
        if resolved := shutil.which(explicit):
            return resolved
        raise HelperError(f"Browser executable not found: {explicit}")

    for name in BROWSER_NAMES:
        if path := shutil.which(name):
            return path
    for name in BROWSER_PATHS:
        if Path(name).is_file():
            return name

    raise HelperError("No Chromium-based browser was found. Pass its path with --browser.")


def free_local_port() -> int:
    """Reserve an available loopback port number for Chrome DevTools."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _devtools_json(port: int, path: str) -> Any:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        if response.status != 200:
            return None
        return json.load(response)
    except (OSError, ValueError, http.client.HTTPException):
        return None
    finally:
        connection.close()


def eon_page_targets(port: int) -> list[dict[str, Any]]:
    """Return inspectable E.ON web pages from the temporary browser."""
    targets = _devtools_json(port, "/json")
    if not isinstance(targets, list):
        return []

    pages: list[dict[str, Any]] = []
    for target in targets:
        if not isinstance(target, dict) or target.get("type") != "page":
            continue
        url = target.get("url")
        websocket_url = target.get("webSocketDebuggerUrl")
        if not isinstance(url, str) or not isinstance(websocket_url, str):
            continue
        if urllib.parse.urlparse(url).hostname != "www.eonnext.com":
            continue
        pages.append(target)
    return pages


async def read_id_token(websocket_url: str) -> str | None:
    """Read the Auth0 ID token from one E.ON page over local Chrome DevTools."""
    async with websockets.connect(websocket_url, max_size=None) as websocket:
        await websocket.send(
            json.dumps(
                {
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": READ_ID_TOKEN_JS,
                        "returnByValue": True,
                    },
                }
            )
        )
        while True:
            raw_message = await websocket.recv()
            try:
                message = json.loads(raw_message)
            except (TypeError, ValueError):
                continue
            if not isinstance(message, dict) or message.get("id") != 1:
                continue
            result = message.get("result")
            runtime_result = result.get("result") if isinstance(result, dict) else None
            value = runtime_result.get("value") if isinstance(runtime_result, dict) else None
            return value if isinstance(value, str) and value else None


async def close_browser(websocket_url: str) -> None:
    """Ask Chrome to close the complete temporary browser instance."""
    async with websockets.connect(websocket_url, max_size=None) as websocket:
        await websocket.send(json.dumps({"id": 1, "method": "Browser.close"}))


def _wait_for_id_token(process: subprocess.Popen[bytes], port: int, timeout: int) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise HelperError("The browser was closed before sign-in finished.")

        for page in eon_page_targets(port):
            try:
                token = asyncio.run(read_id_token(page["webSocketDebuggerUrl"]))
            except (OSError, ValueError, WebSocketException):
                continue
            if token:
                return token
        time.sleep(1)

    raise HelperError("Timed out waiting for E.ON sign-in to finish.")


def _remove_profile(profile: Path) -> None:
    for _ in range(5):
        try:
            shutil.rmtree(profile)
        except FileNotFoundError:
            return
        except OSError:
            pass
        if not profile.exists():
            return
        time.sleep(0.5)
    print(
        f"WARNING: delete the temporary browser profile manually: {profile}",
        file=sys.stderr,
    )


def _stop_browser(process: subprocess.Popen[bytes], port: int, profile: Path) -> None:
    version = _devtools_json(port, "/json/version")
    websocket_url = version.get("webSocketDebuggerUrl") if isinstance(version, dict) else None
    if isinstance(websocket_url, str):
        try:
            asyncio.run(close_browser(websocket_url))
        except (OSError, ValueError, WebSocketException):
            pass

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    finally:
        _remove_profile(profile)


def acquire_id_token(browser: str, timeout: int) -> str:
    """Open an isolated browser, wait for login, and return an in-memory ID token."""
    port = free_local_port()
    profile = Path(tempfile.mkdtemp(prefix="eon-next-api-key-"))
    try:
        process = subprocess.Popen(
            [
                browser,
                f"--user-data-dir={profile}",
                f"--remote-debugging-port={port}",
                "--remote-debugging-address=127.0.0.1",
                "--remote-allow-origins=http://127.0.0.1",
                "--no-first-run",
                "--no-default-browser-check",
                LOGIN_URL,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as err:
        _remove_profile(profile)
        raise HelperError(f"Could not start the browser: {err}") from err

    print("Sign in to E.ON Next in the browser window that just opened.")
    print(
        "Complete any CAPTCHA or verification-code prompt; the helper will continue automatically."
    )
    try:
        return _wait_for_id_token(process, port, timeout)
    finally:
        _stop_browser(process, port, profile)


def graphql(id_token: str, query: str) -> dict[str, Any]:
    """Run a fixed Kraken GraphQL operation with the temporary browser token."""
    body = json.dumps({"query": query, "variables": {}}).encode()
    # nosemgrep: python.lang.security.audit.httpsconnection-detected.httpsconnection-detected
    connection = http.client.HTTPSConnection(
        GRAPHQL_HOST,
        timeout=30,
        context=ssl.create_default_context(),
    )
    try:
        connection.request(
            "POST",
            GRAPHQL_PATH,
            body=body,
            headers={
                "Authorization": f"Bearer {id_token}",
                "Content-Type": "application/json",
                "User-Agent": "homeassistant-eon-next-api-key-helper",
            },
        )
        response = connection.getresponse()
        if response.status != 200:
            raise HelperError(f"E.ON rejected the request with HTTP {response.status}.")
        payload = json.load(response)
    except HelperError:
        raise
    except (OSError, ValueError, http.client.HTTPException) as err:
        raise HelperError(f"Could not contact E.ON: {err}") from err
    finally:
        connection.close()

    if not isinstance(payload, dict):
        raise HelperError("E.ON returned an unexpected response.")
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        details: list[str] = []
        for error in errors:
            if not isinstance(error, dict):
                continue
            extensions = error.get("extensions")
            if not isinstance(extensions, dict):
                continue
            for field in ("code", "errorCode"):
                code = extensions.get(field)
                if isinstance(code, str) and code not in details:
                    details.append(code)
        suffix = f" ({'; '.join(details)})" if details else ""
        raise HelperError(f"E.ON returned a GraphQL error{suffix}.")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise HelperError("E.ON's response did not contain data.")
    return data


def create_api_key(id_token: str) -> str | None:
    """Create the account key, requiring explicit consent before replacement."""
    data = graphql(id_token, LIVE_SECRET_KEY_QUERY)
    viewer = data.get("viewer")
    if not isinstance(viewer, dict) or "liveSecretKey" not in viewer:
        raise HelperError("E.ON did not report whether an API key already exists.")
    existing_key = viewer["liveSecretKey"]

    if existing_key is None:
        print("No existing API key was found; creating one now.")
    elif isinstance(existing_key, str) and existing_key:
        print()
        print("WARNING: This E.ON account already has a live API key.")
        print("E.ON only allows one key. Replacing it will immediately disconnect every")
        print("other app or integration that still uses the current key.")
        print("If you have the original sk_live_... value, reuse it instead of replacing it.")
        try:
            confirmation = input("Type REGENERATE to invalidate it and create a new key: ").strip()
        except EOFError:
            confirmation = ""
        if confirmation != "REGENERATE":
            print("Cancelled. The existing API key was not changed.")
            return None
    else:
        raise HelperError("E.ON returned an unexpected API-key status.")

    data = graphql(id_token, REGENERATE_SECRET_KEY_MUTATION)
    result = data.get("regenerateSecretKey")
    api_key = result.get("key") if isinstance(result, dict) else None
    if not isinstance(api_key, str) or not api_key.startswith("sk_live_"):
        raise HelperError("E.ON did not return the new API key.")
    return api_key


def copy_to_clipboard(value: str) -> bool:
    """Copy a secret through standard input so it is not exposed in process arguments."""
    commands = (
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "-ib"],
        ["pbcopy"],
        ["clip"],
        ["clip.exe"],
    )
    for command in commands:
        if not shutil.which(command[0]):
            continue
        try:
            subprocess.run(
                command,
                input=value.encode(),
                check=True,
                timeout=5,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an E.ON Next API key using a temporary browser session."
    )
    parser.add_argument("--browser", help="path to a Chromium-based browser executable")
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_key",
        help="print the API key instead of copying it to the clipboard",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=LOGIN_TIMEOUT,
        help=f"seconds allowed for browser sign-in (default: {LOGIN_TIMEOUT})",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.timeout <= 0:
        raise HelperError("--timeout must be greater than zero.")

    browser = find_browser(args.browser)
    # Keep the browser credential only for the key-creation call.
    api_key = create_api_key(acquire_id_token(browser, args.timeout))
    if api_key is None:
        return 1

    print()
    if not args.print_key and copy_to_clipboard(api_key):
        print(f"API key copied to the clipboard ({api_key[:8]}…{api_key[-4:]}).")
    else:
        if not args.print_key:
            print("No supported clipboard command was found; printing the key instead.")
        print(api_key)
    print("Paste it into the E.ON Next integration, then clear your clipboard.")
    print("The full key cannot be retrieved from E.ON again, so keep it in a password manager.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit("Cancelled.") from None
    except HelperError as err:
        raise SystemExit(f"Error: {err}") from None
