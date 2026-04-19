from __future__ import annotations

import argparse
import json
import os
import sys
import time
import webbrowser
from dataclasses import dataclass
from email.message import Message
from http.client import HTTPResponse
from pathlib import Path
from typing import Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

AUTH_URL = "https://auth.roblox.com/v2/logout"
LEGACY_UPLOAD_URL = "https://data.roblox.com/Data/Upload.ashx"
AUTHENTICATED_USER_URL = "https://users.roblox.com/v1/users/authenticated"
USER_GAMES_URL_TEMPLATE = "https://games.roblox.com/v2/users/{user_id}/games?accessFilter=2&limit=50&sortOrder=Desc"
UNIVERSE_CONFIG_URL_TEMPLATE = "https://develop.roblox.com/v1/universes/{universe_id}/configuration"
DEFAULT_TIMEOUT_SECONDS = 90
DEFAULT_RETRIES = 2
SUPPORTED_EXTENSIONS = {".rbxl", ".rbxlx"}


class RobloxUploadError(RuntimeError):
    """Raised when an upload step fails."""


@dataclass
class TargetGame:
    universe_id: int
    place_id: int
    name: str


def read_header_case_insensitive(headers: Message, header_name: str) -> Optional[str]:
    for key, value in headers.items():
        if key.lower() == header_name.lower():
            return value
    return None


def read_all_headers_case_insensitive(headers: Message, header_name: str) -> list[str]:
    target = header_name.lower()
    values: list[str] = []
    for key in headers.keys():
        if key.lower() == target:
            found = headers.get_all(key)
            if found:
                values.extend(found)
    return values


def ensure_place_file(file_path: Path) -> None:
    if not file_path.exists() or not file_path.is_file():
        raise RobloxUploadError(f"Place file not found: {file_path}")
    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise RobloxUploadError("Unsupported file extension. Use .rbxl or .rbxlx")


def detect_content_type(file_path: Path) -> str:
    return "application/xml" if file_path.suffix.lower() == ".rbxlx" else "application/octet-stream"


def summarize_http_error(prefix: str, error: HTTPError) -> RobloxUploadError:
    body = error.read().decode("utf-8", errors="replace").strip()
    return RobloxUploadError(f"{prefix} (status={error.code}). Response: {body[:800] if body else '<empty>'}")


def parse_retry_after_seconds(error: HTTPError) -> Optional[float]:
    retry_after = error.headers.get("Retry-After") if error.headers else None
    if not retry_after:
        return None
    try:
        return max(float(retry_after.strip()), 0.0)
    except ValueError:
        return None


def request_with_retries(
    request: Request,
    *,
    timeout_seconds: int,
    retries: int,
    retriable_statuses: Iterable[int] = (429, 500, 502, 503, 504),
) -> HTTPResponse:
    for attempt in range(retries + 1):
        try:
            return urlopen(request, timeout=timeout_seconds)
        except HTTPError as error:
            if error.code not in retriable_statuses or attempt == retries:
                raise
            sleep_time = parse_retry_after_seconds(error)
            time.sleep(sleep_time if sleep_time is not None else min(2**attempt, 8))
        except URLError:
            if attempt == retries:
                raise
            time.sleep(min(2**attempt, 8))
    raise RobloxUploadError("Request failed after retries")


def extract_cookie_value(raw_cookie: str) -> str:
    cookie = raw_cookie.strip()
    if not cookie:
        raise RobloxUploadError("ROBLOSECURITY cookie is empty")
    if cookie.startswith(".ROBLOSECURITY="):
        cookie = cookie.split("=", 1)[1]
    if ";" in cookie:
        cookie = cookie.split(";", 1)[0]
    cookie = cookie.strip()
    if not cookie:
        raise RobloxUploadError("Could not parse ROBLOSECURITY cookie")
    return cookie


def build_cookie_header(cookie_value: str) -> str:
    return f".ROBLOSECURITY={cookie_value}"


def parse_rotated_cookie(set_cookie: str) -> Optional[str]:
    marker = ".ROBLOSECURITY="
    if marker not in set_cookie:
        return None
    value = set_cookie.split(marker, 1)[1].split(";", 1)[0].strip()
    return value or None


def extract_rotated_cookie(headers: Message) -> Optional[str]:
    for value in read_all_headers_case_insensitive(headers, "set-cookie"):
        parsed = parse_rotated_cookie(value)
        if parsed:
            return parsed
    return None


def get_csrf_token(cookie_header: str, timeout_seconds: int, retries: int) -> tuple[str, Optional[str]]:
    request = Request(AUTH_URL, method="POST", headers={"Cookie": cookie_header, "User-Agent": "RobloxUploader/5.0"})
    try:
        with request_with_retries(request, timeout_seconds=timeout_seconds, retries=retries) as response:
            token = read_header_case_insensitive(response.headers, "x-csrf-token")
            rotated = extract_rotated_cookie(response.headers)
    except HTTPError as error:
        token = error.headers.get("x-csrf-token") if error.headers else None
        rotated = extract_rotated_cookie(error.headers) if error.headers else None

    if not token:
        raise RobloxUploadError("CSRF token was not returned. Cookie is invalid or expired.")
    return token, rotated


def get_json(cookie_header: str, csrf_token: str, url: str, timeout_seconds: int, retries: int) -> dict:
    request = Request(
        url,
        method="GET",
        headers={
            "Cookie": cookie_header,
            "x-csrf-token": csrf_token,
            "Accept": "application/json",
            "User-Agent": "RobloxUploader/5.0",
        },
    )
    try:
        with request_with_retries(request, timeout_seconds=timeout_seconds, retries=retries) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except HTTPError as error:
        raise summarize_http_error(f"GET failed: {url}", error) from error
    except json.JSONDecodeError as error:
        raise RobloxUploadError(f"Invalid JSON from {url}: {error}") from error


def patch_json(cookie_header: str, csrf_token: str, url: str, payload: dict, timeout_seconds: int, retries: int) -> dict:
    request = Request(
        url,
        method="PATCH",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Cookie": cookie_header,
            "x-csrf-token": csrf_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "RobloxUploader/5.0",
        },
    )
    try:
        with request_with_retries(request, timeout_seconds=timeout_seconds, retries=retries) as response:
            body = response.read().decode("utf-8", errors="replace").strip()
            return json.loads(body) if body else {}
    except HTTPError as error:
        raise summarize_http_error(f"PATCH failed: {url}", error) from error
    except json.JSONDecodeError as error:
        raise RobloxUploadError(f"Invalid JSON response from {url}: {error}") from error


def resolve_target_game(cookie_header: str, csrf_token: str, timeout_seconds: int, retries: int, place_id: Optional[int]) -> TargetGame:
    me = get_json(cookie_header, csrf_token, AUTHENTICATED_USER_URL, timeout_seconds, retries)
    user_id = me.get("id")
    if not isinstance(user_id, int):
        raise RobloxUploadError("Could not resolve authenticated user from cookie")

    games_url = USER_GAMES_URL_TEMPLATE.format(user_id=user_id)
    games_payload = get_json(cookie_header, csrf_token, games_url, timeout_seconds, retries)
    games = games_payload.get("data")
    if not isinstance(games, list) or not games:
        raise RobloxUploadError("No owned games found for this account")

    parsed: list[TargetGame] = []
    for item in games:
        if not isinstance(item, dict):
            continue
        universe_id = item.get("id")
        root_place = item.get("rootPlace")
        root_place_id = root_place.get("id") if isinstance(root_place, dict) else None
        name = item.get("name") if isinstance(item.get("name"), str) else "Untitled"
        if isinstance(universe_id, int) and isinstance(root_place_id, int):
            parsed.append(TargetGame(universe_id=universe_id, place_id=root_place_id, name=name))

    if not parsed:
        raise RobloxUploadError("Could not parse owned games list")

    if place_id is None:
        return parsed[0]

    for game in parsed:
        if game.place_id == place_id:
            return game

    raise RobloxUploadError("Provided --place-id was not found in your owned games list")


def set_universe_public(cookie_header: str, csrf_token: str, universe_id: int, timeout_seconds: int, retries: int) -> None:
    url = UNIVERSE_CONFIG_URL_TEMPLATE.format(universe_id=universe_id)
    payload = {"isPublic": True}
    patch_json(cookie_header, csrf_token, url, payload, timeout_seconds, retries)


def upload_place_legacy(cookie_header: str, csrf_token: str, place_id: int, file_path: Path, timeout_seconds: int, retries: int) -> tuple[str, Optional[str]]:
    query = urlencode({"assetid": str(place_id), "type": "9", "genreTypeId": "1", "ispublic": "true", "allowComments": "true"})
    target_url = f"{LEGACY_UPLOAD_URL}?{query}"
    request = Request(
        target_url,
        method="POST",
        data=file_path.read_bytes(),
        headers={
            "Cookie": cookie_header,
            "x-csrf-token": csrf_token,
            "Content-Type": detect_content_type(file_path),
            "User-Agent": "RobloxUploader/5.0",
        },
    )

    try:
        with request_with_retries(request, timeout_seconds=timeout_seconds, retries=retries) as response:
            body = response.read().decode("utf-8", errors="replace").strip()
            rotated = extract_rotated_cookie(response.headers)
            return body or "OK", rotated
    except HTTPError as error:
        raise summarize_http_error("Upload failed", error) from error


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Paste cookie -> upload RBXL -> return link -> open browser")
    parser.add_argument("--cookie", type=str, default=None, help="ROBLOSECURITY value (or ROBLOSECURITY env)")
    parser.add_argument("--file", type=Path, default=Path("Place.rbxl"), help="Path to .rbxl/.rbxlx")
    parser.add_argument("--place-id", type=int, default=None, help="Optional place ID. If omitted, latest owned game root place is used")
    parser.add_argument("--public", action="store_true", default=True, help="Try to set universe public after upload")
    parser.add_argument("--no-open", action="store_true", help="Do not open game link in browser")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.timeout <= 0:
        print("Error: --timeout must be > 0", file=sys.stderr)
        return 1
    if args.retries < 0:
        print("Error: --retries must be >= 0", file=sys.stderr)
        return 1

    try:
        ensure_place_file(args.file)

        raw_cookie = args.cookie or os.getenv("ROBLOSECURITY")
        if not raw_cookie:
            print("Error: provide cookie via --cookie or ROBLOSECURITY", file=sys.stderr)
            return 1

        cookie_header = build_cookie_header(extract_cookie_value(raw_cookie))
        csrf_token, rotated_auth_cookie = get_csrf_token(cookie_header, args.timeout, args.retries)
        if rotated_auth_cookie:
            cookie_header = build_cookie_header(rotated_auth_cookie)

        game = resolve_target_game(cookie_header, csrf_token, args.timeout, args.retries, args.place_id)
        print(f"Target game: {game.name} (universe_id={game.universe_id}, place_id={game.place_id})")

        response_text, rotated_upload_cookie = upload_place_legacy(
            cookie_header,
            csrf_token,
            game.place_id,
            args.file,
            args.timeout,
            args.retries,
        )
        print("Upload complete.")
        print(f"Server response: {response_text}")

        if args.public:
            try:
                set_universe_public(cookie_header, csrf_token, game.universe_id, args.timeout, args.retries)
                print("Universe visibility set to public.")
            except RobloxUploadError as error:
                print(f"Warning: could not set public automatically: {error}", file=sys.stderr)

        game_url = f"https://www.roblox.com/games/{game.place_id}/"
        print(f"Game link: {game_url}")

        if not args.no_open:
            webbrowser.open(game_url, new=2)
            print("Opened game link in browser.")

        rotated_cookie = rotated_upload_cookie or rotated_auth_cookie
        if rotated_cookie:
            print("\nUpdated .ROBLOSECURITY (save this new value):")
            print(rotated_cookie)

        print(
            "Note: Roblox deprecated place upload via data.roblox.com on 2024-06-24; "
            "if this flow is blocked on your account, use Open Cloud Place Publishing API.",
            file=sys.stderr,
        )
        return 0
    except URLError as error:
        print(f"Network error: {error}", file=sys.stderr)
        return 1
    except RobloxUploadError as error:
        print(f"Upload error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
