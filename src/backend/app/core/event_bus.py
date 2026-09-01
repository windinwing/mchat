"""Simple async event bus for publish/subscribe patterns."""

import asyncio
from collections import defaultdict
from typing import Any, Callable, Coroutine

from loguru import logger

EventHandler = Callable[..., Coroutine[Any, Any, None]]


class EventBus:
    """Async event bus supporting publish/subscribe pattern."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event: str, handler: EventHandler) -> None:
        """Subscribe a handler to an event."""
        self._subscribers[event].append(handler)
        logger.debug(f"Handler subscribed to event '{event}'")

    def unsubscribe(self, event: str, handler: EventHandler) -> None:
        """Unsubscribe a handler from an event."""
        if event in self._subscribers:
            self._subscribers[event] = [
                h for h in self._subscribers[event] if h is not handler
            ]

    def has_subscribers(self, event: str) -> bool:
        """Return True if at least one handler is subscribed to the event."""
        return bool(self._subscribers.get(event))

    async def publish(self, event: str, **data: Any) -> None:
        """Publish an event, calling all subscribed handlers concurrently."""
        handlers = self._subscribers.get(event, [])
        if not handlers:
            logger.debug(f"Event '{event}' published with no subscribers")
            return

        logger.debug(f"Publishing event '{event}' to {len(handlers)} handlers")
        results = await asyncio.gather(
            *[handler(**data) for handler in handlers],
            return_exceptions=True,
        )
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    f"Handler for event '{event}' failed: {result}"
                )

    def clear(self) -> None:
        """Remove all subscribers."""
        self._subscribers.clear()


# Singleton instance
event_bus = EventBus()
