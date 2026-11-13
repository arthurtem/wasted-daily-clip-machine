"""Upload and delete files in Vercel Blob through a small Node helper."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
BLOB_HELPER = SCRIPTS_DIR / "blob.mjs"
NODE_ENV = "NODE_BIN"


class BlobError(RuntimeError):
    """Raised when a Vercel Blob operation fails."""


def _node_binary() -> str:
    """Return the Node binary path from the environment or PATH."""
    return os.environ.get(NODE_ENV, "").strip() or "node"


def _run(*args: str) -> str:
    """Run the Node blob helper and return its last stdout line."""
    try:
        result = subprocess.run(
            [_node_binary(), str(BLOB_HELPER), *args],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise BlobError("node is not installed or not on PATH") from exc
    if result.returncode != 0:
        raise BlobError(
            f"blob helper failed ({result.returncode}): "
            f"{result.stderr[-500:].strip()}"
        )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def put_file(local_path: Path, pathname: str) -> str:
    """Upload a local file to Vercel Blob and return its public URL."""
    path = Path(local_path)
    if not path.is_file():
        raise BlobError(f"cannot upload missing file: {path}")
    url = _run("put", str(path), pathname)
    if not url.startswith("https://"):
        raise BlobError(f"blob helper returned an invalid URL: {url!r}")
    logger.info("blob upload %s -> %s", pathname, url)
    return url


def delete_url(url: str) -> None:
    """Delete a Vercel Blob object by its public URL."""
    _run("delete", url)
    logger.info("blob delete %s", url)


def download_file(url: str, destination: Path) -> Path:
    """Download a public Blob URL to a local path."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    logger.info("downloaded blob %s -> %s", url, destination)
    return destination
