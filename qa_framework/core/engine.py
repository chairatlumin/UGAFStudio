from __future__ import annotations

import re

SUPPORTED_VERSIONS = {
    "5.7",
    "5.8",
}


def normalize_engine_version(
    version: str | None,
) -> str | None:
    if not version:
        return None

    match = re.search(
        r"5\.(7|8)",
        version,
    )

    if not match:
        return None

    return f"5.{match.group(1)}"


def detect_engine_version(
    engine_association: str | None,
) -> str | None:
    return normalize_engine_version(engine_association)


def is_supported_version(
    version: str | None,
) -> bool:
    return version in SUPPORTED_VERSIONS
