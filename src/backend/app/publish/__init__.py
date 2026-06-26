"""Content auto-publish system — outbound delivery to domestic/intl channels.

This package is a leaf module: it is invoked only through the
``publish-content`` skill and never depends back on workflow engine,
scheduler, or inbound channel adapters. See
``docs/plan/publish-system/ARCHITECTURE.md``.
"""

from app.publish.base import (
    BasePublisher,
    PublishMedia,
    PublishRequest,
    PublishResult,
)
from app.publish.registry import (
    PublisherProvider,
    get_publisher,
    list_publishers,
)
from app.publish.service import dispatch

__all__ = [
    "BasePublisher",
    "PublishMedia",
    "PublishRequest",
    "PublishResult",
    "PublisherProvider",
    "get_publisher",
    "list_publishers",
    "dispatch",
]
