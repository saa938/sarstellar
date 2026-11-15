"""Portable checkpoint identities and Linux Volume paths, including from Windows clients."""

from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath

SCHEMA_VERSION = "paired-v1"


def checkpoint_name(site: dict) -> str:
    payload = json.dumps(site, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256((SCHEMA_VERSION + payload).encode()).hexdigest()[:16]
    return f"{site['id']}-{digest}.parquet"


def remote_checkpoint_path(site: dict, data_root: str = "/data") -> str:
    """Serialize a POSIX container path regardless of the client's native path convention."""
    return str(PurePosixPath(data_root) / "scorecard" / SCHEMA_VERSION / checkpoint_name(site))
