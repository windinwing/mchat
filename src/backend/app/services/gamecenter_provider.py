"""GameCenter provider built on the generic rooted project bridge."""

from __future__ import annotations

from app.services.configured_bridge_provider import create_configured_bridge_service
from app.services.devbridge_admin_settings import resolved_gamecenter_settings
from app.services.rooted_project_bridge_service import RootedProjectBridgeService


def create_gamecenter_bridge_service(
    *,
    project_allowlist_override: set[str] | None = None,
) -> RootedProjectBridgeService:
    """Build a bridge service; optional per-group slug allowlist overrides global."""
    return create_configured_bridge_service(
        "gamecenter",
        resolved_gamecenter_settings(),
        project_allowlist_override=project_allowlist_override,
    )


class GamecenterBridgeService(RootedProjectBridgeService):
    """Alias class for type hints and direct construction in tests."""
