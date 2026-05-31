"""MChat SMS notification skill — thin wrapper over NotificationService."""

from __future__ import annotations

from typing import Any


def run(
    command: str = "ping",
    phone: str | None = None,
    provider: str | None = None,
    content: str | None = None,
    workflow_name: str | None = None,
    event: str | None = None,
    run_id: str | None = None,
    message: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    from app.services.notification_service import NotificationService

    if not phone or not str(phone).strip():
        return {"ok": False, "message": "缺少 phone 参数"}

    cmd = (command or "ping").strip().lower()
    svc = NotificationService(db=None)

    if cmd == "ping":
        return svc.send_sms(
            phone=str(phone),
            source="skill",
            provider=provider,
            content="MChat notify ping",
        )
    if cmd == "send":
        body = (content or message or "").strip()
        if not body:
            return {"ok": False, "message": "command=send 需要 content"}
        return svc.send_sms(
            phone=str(phone),
            source="skill",
            provider=provider,
            content=body[:500],
        )
    if cmd == "workflow_alert":
        return svc.send_sms(
            phone=str(phone),
            source="skill",
            provider=provider,
            template="workflow_alert",
            template_params={
                "workflow_name": workflow_name or "Workflow",
                "event": event or "alert",
                "run_id": run_id or "",
                "message": message or "",
            },
        )
    return {"ok": False, "message": f"未知 command: {command}"}
