from __future__ import annotations

import uuid

ASSET_NAMESPACE = uuid.UUID("64a5c413-e50a-4c6d-983a-809c457dca41")


def asset_uuid(sha256: str) -> str:
    """Return the provisional deterministic asset UUID for content."""
    return str(uuid.uuid5(ASSET_NAMESPACE, sha256.lower()))


def atlas_uri(asset_id: str) -> str:
    return f"atlas://asset/{asset_id}"

