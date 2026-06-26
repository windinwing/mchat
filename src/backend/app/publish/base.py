"""Publish system data contracts.

Mirrors the shape of :mod:`app.channels.base_adapter` but inverted: inbound
adapters *receive* a :class:`ChannelMessage` and reply, publishers *send* a
:class:`PublishRequest` to an external platform. Keeping the same naming
convention lets operators reason about channels/publishers symmetrically.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PublishMedia:
    """A media attachment to ship alongside the text body."""

    type: str
    """Media kind: ``image`` | ``video`` | ``file``."""

    url: str | None = None
    """Remote URL or same-origin ``/uploads`` path (API-class channels)."""

    path: str | None = None
    """Local filesystem path (client-machine / Playwright channels)."""

    caption: str | None = None
    """Optional caption for this specific media item."""


@dataclass
class PublishRequest:
    """Normalized outbound publish payload, channel-agnostic."""

    content: str
    """Primary text body. Required."""

    title: str | None = None
    """Optional title (articles, cards, rich posts)."""

    media: list[PublishMedia] = field(default_factory=list)
    """Ordered media attachments."""

    extra: dict[str, Any] = field(default_factory=dict)
    """Channel-specific extras (tags, topic, at-mentions, …). Opaque to core."""

    request_id: str = ""
    """Correlation id for tracing / client-machine jobs (P2)."""


@dataclass
class PublishResult:
    """Outcome of a single publish attempt."""

    success: bool
    provider: str

    message: str = ""
    remote_id: str | None = None
    """Platform-returned content id, when available."""

    remote_url: str | None = None
    """Public URL of the published content, when available."""

    raw: dict[str, Any] = field(default_factory=dict)
    """Raw provider response for debugging."""

    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "success": self.success,
            "provider": self.provider,
            "message": self.message,
        }
        if self.remote_id:
            data["remote_id"] = self.remote_id
        if self.remote_url:
            data["remote_url"] = self.remote_url
        if self.error_code:
            data["error_code"] = self.error_code
        if self.error_message:
            data["error_message"] = self.error_message
        return data


class BasePublisher(ABC):
    """Abstract outbound publisher.

    Each channel (Feishu, WeChat MP, Slack, …) implements this interface to
    ship a :class:`PublishRequest` to the target platform. The mirror of
    :class:`app.channels.base_adapter.BaseChannelAdapter` for outbound traffic.
    """

    #: Stable provider key, e.g. ``"feishu"``. Used by the registry.
    provider_key: str = ""

    #: Capability tags advertised to callers, e.g. ``("publish:text",)``.
    capabilities: tuple[str, ...] = ("publish:text",)

    @abstractmethod
    async def publish(
        self, config: dict[str, Any], request: PublishRequest
    ) -> PublishResult:
        """Send ``request`` to the platform using channel credentials in ``config``.

        Args:
            config: Channel credentials/options (webhook url, tokens, …).
            request: Normalized payload to publish.
        """
        ...

    async def validate_config(self, config: dict[str, Any]) -> bool:
        """Return True if ``config`` is sufficient for a basic publish."""
        return True
