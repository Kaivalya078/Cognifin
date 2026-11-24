"""Crash-safe file writes for the index registry."""

import json
import os

TMP_PREFIX = ".finsight_tmp_"


def atomic_write_json(path: str, obj: dict) -> None:
    """Write JSON via tmp file → fsync → rename, so a crash never leaves a
    half-written registry behind."""
    tmp_path = os.path.join(os.path.dirname(path), TMP_PREFIX + os.path.basename(path))
    with open(tmp_path, "wb") as f:
        f.write(json.dumps(obj, indent=2).encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)
