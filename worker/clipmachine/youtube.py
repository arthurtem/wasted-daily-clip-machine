"""YouTube Data API client and resumable upload helpers."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from clipmachine import db
from clipmachine.crypto import CryptoError, decrypt

logger = logging.getLogger(__name__)

TOKEN_URI = "https://oauth2.googleapis.com/token"
CHUNK_SIZE = 8 * 1024 * 1024
RETRY_STATUSES = frozenset({500, 502, 503, 504})
MAX_RETRIES = 5


class YouTubeError(RuntimeError):
    """Raised when the YouTube client cannot be built or used."""


class YouTubeNotConnected(YouTubeError):
    """Raised when no YouTube connection exists."""


class InvalidGrantError(YouTubeError):
    """Raised when the stored refresh token is revoked or expired."""


def _invalid_grant(error: Exception) -> bool:
    """Return whether a refresh error means the grant is no longer valid."""
    return "invalid_grant" in str(error)


def get_client(connection: Mapping[str, Any] | None = None) -> Any:
    """Build an authenticated YouTube client from the stored connection."""
    if connection is None:
        connection = db.get_youtube_connection()
    if not connection:
        raise YouTubeNotConnected("YouTube not connected")

    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise YouTubeError(
            "GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET must be set"
        )

    try:
        refresh_token = decrypt(str(connection["refresh_token_enc"]))
    except CryptoError as exc:
        raise YouTubeError(
            "Could not decrypt the stored YouTube token"
        ) from exc
    scopes = str(connection.get("scopes") or "").split()
    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes or None,
    )
    try:
        credentials.refresh(Request())
    except RefreshError as exc:
        if _invalid_grant(exc):
            raise InvalidGrantError("YouTube refresh token is invalid") from exc
        raise YouTubeError(f"YouTube token refresh failed: {exc}") from exc

    return build(
        "youtube", "v3", credentials=credentials, cache_discovery=False
    )


def get_channel_title(client: Any | None = None) -> str:
    """Return the authenticated channel's title."""
    service = client or get_client()
    response = (
        service.channels().list(part="snippet", mine=True).execute()
    )
    items = response.get("items") or []
    if not items:
        raise YouTubeError("YouTube returned no channel")
    return str(items[0]["snippet"]["title"])


def _http_status(error: HttpError) -> int:
    """Return an HTTP status from a googleapiclient error."""
    response = getattr(error, "resp", None)
    return int(getattr(response, "status", 0) or 0)


def is_retryable(error: HttpError) -> bool:
    """Return whether a video upload error is transient."""
    return _http_status(error) in RETRY_STATUSES


def is_stop_error(error: HttpError) -> bool:
    """Return whether an error is a quota or upload-limit stop condition."""
    content = getattr(error, "content", b"")
    if isinstance(content, bytes):
        text = content.decode("utf-8", errors="ignore")
    else:
        text = str(content)
    return "quotaExceeded" in text or "uploadLimitExceeded" in text


def upload_short(
    client: Any,
    path: Path,
    title: str,
    description: str,
    tags: list[str],
    privacy_status: str | None = None,
) -> str:
    """Upload a resumable MP4 to YouTube and return the video id."""
    privacy = (
        privacy_status
        or os.environ.get("YT_PRIVACY_STATUS", "").strip()
        or "public"
    )
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "20",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(
        str(path),
        mimetype="video/mp4",
        chunksize=CHUNK_SIZE,
        resumable=True,
    )
    request = client.videos().insert(
        part="snippet,status", body=body, media_body=media
    )

    response: dict[str, Any] | None = None
    retries = 0
    while response is None:
        try:
            _status, response = request.next_chunk()
        except HttpError as exc:
            if is_retryable(exc) and retries < MAX_RETRIES:
                retries += 1
                delay = min(2**retries, 8)
                logger.warning(
                    "clip %s upload retry %d after HTTP %s",
                    path.parent.name,
                    retries,
                    _http_status(exc),
                )
                time.sleep(delay)
                continue
            raise

    video_id = str(response.get("id") or "")
    if not video_id:
        raise YouTubeError("YouTube upload returned no video id")
    logger.info("clip %s uploaded video_id=%s", path.parent.name, video_id)
    return video_id
