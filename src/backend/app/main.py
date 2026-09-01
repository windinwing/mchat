"""Core ASGI entry point.

The reusable factory lives in :mod:`app.application` so Cloud can compose a
Core application without importing and instantiating this module-level app.
"""

from app.application import _validate_production_security, create_app
from app.core.config import settings

app = create_app()

__all__ = ["app", "create_app", "_validate_production_security"]


def main() -> None:
    """Run the Core application with uvicorn."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
