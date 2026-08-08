"""Offload large workflow output_payload blobs to file storage.

Workflow runs (especially stock batch analysis) produce multi-MB output_payload
that can't safely live in a MySQL JSON column — it trips the server's
``max_allowed_packet`` (default 4MB) and raises ``2013 Lost connection``.

This module keeps the full payload in the storage backend (local FS / S3) and
stores a small *reference envelope* in the DB:

    {
        "_payload_storage_key": "workflow_reports/runs/<id>/output.json",
        "_payload_storage_url":  "/api/uploads/<key>?sig=...",   # signed, for clients
        "_payload_size": <bytes>,
        "engine_state": {...},          # always inlined (resume needs it, KB级)
        "node_runs":    [...],          # slimmed: only status/name/result-skeleton
    }

The slimmed ``node_runs`` preserves the keys the report panel actually renders
(``report_files`` / ``report_charts`` / ``summary`` / ``message`` / batch
``items`` children) while dropping the heavy raw envelopes/K-line/news payloads
the UI never reads.

Callers go through :func:`maybe_offload` (write) and :func:`hydrate` (read);
``hydrate`` transparently restores the full payload when it was offloaded, so
the rest of the codebase is unchanged.
"""
from __future__ import annotations

import json
from typing import Any

from loguru import logger

# Marker stored in the DB reference envelope when the full payload is offloaded.
_STORAGE_KEY = "_payload_storage_key"
_STORAGE_URL = "_payload_storage_url"
_STORAGE_SIZE = "_payload_size"

# Keys we keep verbatim inside a slimmed node result (front-end report essentials).
# Mirrors what WorkflowReportPanel / workflowReportAssets actually read.
_KEEP_RESULT_KEYS = (
    "report_files", "files", "report_charts", "charts",
    "summary", "interpretation", "message",
    "ok", "error", "status",
    # structured tables / board stats rendered by the panel
    "stocks", "items", "count",
    "top_gainers", "top_losers", "top_inflow", "top_oversold",
    "matched_boards", "board_avg_pct",
    "signals", "envelope",
)


def _byte_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))


def _slim_node_result(result: Any) -> Any:
    """Drop heavy leaves from a single node result, keep report essentials."""
    if not isinstance(result, dict):
        # Non-dict results are usually small (strings/numbers); keep as-is.
        return result
    slimmed: dict[str, Any] = {}
    for k in _KEEP_RESULT_KEYS:
        if k in result:
            slimmed[k] = result[k]
    # Recurse into batch `items[].children[].result` so the panel still renders
    # multi-stock breakdowns without dragging in every K-line.
    items = slimmed.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            children = item.get("children")
            if isinstance(children, dict):
                item["children"] = {
                    nid: _slim_child(child) for nid, child in children.items()
                }
    return slimmed or {"_truncated": True}


def _slim_child(child: Any) -> Any:
    """Slim a batch child node entry ({result: {...}, status, ...})."""
    if not isinstance(child, dict):
        return child
    res = child.get("result")
    if isinstance(res, dict):
        child = {**child, "result": {k: res[k] for k in _KEEP_RESULT_KEYS if k in res} or {"_truncated": True}}
    return child


def _slim_node_runs(node_runs: Any) -> Any:
    if not isinstance(node_runs, list):
        return node_runs
    out = []
    for nr in node_runs:
        if not isinstance(nr, dict):
            out.append(nr)
            continue
        slim = {k: v for k, v in nr.items() if k != "result"}
        if "result" in nr:
            slim["result"] = _slim_node_result(nr["result"])
        out.append(slim)
    return out


def _threshold_bytes() -> int:
    """Adaptive threshold: ~40% of max_allowed_packet, clamped to [0.5MB, 8MB].

    Resolved lazily from the DB session the first time it's needed and cached.
    Falls back to 1.5MB if the lookup fails (keeps INSERT packets well under a
    4MB max_allowed_packet with SQL text + framing overhead).
    """
    cached = getattr(_threshold_bytes, "_cached", None)
    if cached is not None:
        return cached
    threshold = 1_500_000
    try:
        # Local import avoids a hard DB dependency at module import time.
        from sqlalchemy import text as _text
        from app.core.database import engine as _async_engine

        with _async_engine.sync_engine.connect() as conn:
            row = conn.execute(_text("SHOW VARIABLES LIKE 'max_allowed_packet'")).fetchone()
            if row and row[1]:
                map_bytes = int(row[1])
                threshold = max(524_288, min(8_388_608, int(map_bytes * 0.4)))
    except Exception as exc:  # noqa: BLE001 — never block a run on this lookup
        logger.debug("max_allowed_packet lookup failed, using default threshold: {}", exc)
    setattr(_threshold_bytes, "_cached", threshold)
    return threshold


def maybe_offload(payload: Any, run_id: str) -> Any:
    """If ``payload`` is large, store it to file and return a small reference.

    Returns ``payload`` unchanged when it fits the threshold. When it doesn't,
    returns the reference envelope described in the module docstring.
    """
    if not isinstance(payload, dict):
        return payload
    size = _byte_size(payload)
    threshold = _threshold_bytes()
    if size <= threshold:
        return payload

    try:
        from app.services.storage_service import StorageService

        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        stored = StorageService().save_bytes(
            data,
            filename="output.json",
            content_type="application/json",
            prefix=f"workflow_reports/runs/{run_id}",
        )
        logger.info(
            "Offloaded workflow payload for run {} ({}KB → storage key {})",
            run_id, size // 1024, stored.key,
        )
        # Build the in-DB reference: keep engine_state (resume) + slim node_runs
        # (front-end report essentials + signed URL for full data on demand).
        # engine_state.outputs mirrors node_runs (heavy + redundant); drop the
        # mirror — resume reads node_runs from the top-level key, and the
        # control fields (done_nodes/ready_nodes/paused) are all that's needed.
        engine_state = dict(payload.get("engine_state") or {})
        engine_state.pop("outputs", None)
        reference: dict[str, Any] = {
            _STORAGE_KEY: stored.key,
            _STORAGE_URL: stored.url,
            _STORAGE_SIZE: size,
            "engine_state": engine_state,
            "node_runs": _slim_node_runs(payload.get("node_runs")),
            "graph": payload.get("graph"),
        }
        return reference
    except Exception as exc:  # noqa: BLE001 — fall back to slimmed-in-DB rather than crash
        logger.warning("Failed to offload workflow payload ({}); storing slimmed copy", exc)
        _es = dict(payload.get("engine_state") or {})
        _es.pop("outputs", None)
        return {
            "engine_state": _es,
            "node_runs": _slim_node_runs(payload.get("node_runs")),
            "graph": payload.get("graph"),
            "_offload_failed": True,
        }


def hydrate(payload: Any) -> Any:
    """Restore the full payload if ``payload`` is an offload reference.

    Returns ``payload`` unchanged when it's a normal (non-offloaded) payload.
    On storage read failure, returns the reference envelope as-is so callers
    still get engine_state + slim node_runs instead of nothing.
    """
    if not isinstance(payload, dict) or _STORAGE_KEY not in payload:
        return payload
    key = payload.get(_STORAGE_KEY)
    if not key:
        return payload
    try:
        from app.services.storage_service import StorageService

        raw, _ct = StorageService().fetch_bytes(key) or (None, None)
        if raw:
            return json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to hydrate offloaded workflow payload (key={}): {}", key, exc)
    return payload
