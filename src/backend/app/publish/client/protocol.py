"""Client-machine job protocol — versioned wire schema.

A ``PublishJob`` is the unit of work handed to a remote client process. It is
plain JSON so the independent ``publisher-client`` program (outside this repo)
can parse it without importing any central-side code. Bump
``PROTOCOL_VERSION`` on any breaking schema change and handle old versions in
``job_from_dict``.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


PROTOCOL_VERSION = 1


class PublishJobStatus:
    """Job lifecycle states (string constants — no enum to keep wire schema plain)."""

    PENDING = "pending"
    CLAIMED = "claimed"
    DONE = "done"
    FAILED = "failed"

    ALL = (PENDING, CLAIMED, DONE, FAILED)
    TERMINAL = (DONE, FAILED)


@dataclass
class PublishJob:
    """A single publish task for a remote Playwright client."""

    job_id: str
    platform: str
    """Target platform key, e.g. ``xiaohongshu`` / ``douyin``."""

    content: str
    title: str | None = None
    media: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    status: str = "pending"
    """``pending`` | ``claimed`` | ``done`` | ``failed``."""

    client_id: str | None = None
    """Which client claimed the job."""

    result: dict[str, Any] | None = None
    """Client-posted result (mirrors ``PublishResult``)."""

    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    protocol_version: int = PROTOCOL_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_job(
    *,
    platform: str,
    content: str,
    title: str | None = None,
    media: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
) -> PublishJob:
    return PublishJob(
        job_id=str(uuid.uuid4()),
        platform=(platform or "").strip().lower(),
        content=content or "",
        title=title,
        media=list(media or []),
        extra=dict(extra or {}),
    )


def job_from_dict(data: dict[str, Any]) -> PublishJob:
    """Reconstruct a job, tolerant of older protocol versions."""
    version = int(data.get("protocol_version") or PROTOCOL_VERSION)
    if version > PROTOCOL_VERSION:
        raise ValueError(f"Unsupported publish job protocol version: {version}")
    return PublishJob(
        job_id=str(data.get("job_id") or uuid.uuid4()),
        platform=str(data.get("platform") or ""),
        content=str(data.get("content") or ""),
        title=data.get("title"),
        media=list(data.get("media") or []),
        extra=dict(data.get("extra") or {}),
        status=str(data.get("status") or "pending"),
        client_id=data.get("client_id"),
        result=data.get("result"),
        error=data.get("error"),
        created_at=float(data.get("created_at") or time.time()),
        updated_at=float(data.get("updated_at") or time.time()),
        protocol_version=version,
    )
