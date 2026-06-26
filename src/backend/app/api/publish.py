"""Publisher-client machine API — Pull-mode job protocol.

Remote Playwright clients (running on a mac mini / dedicated box) poll these
endpoints to claim publish jobs for platforms with no official API
(Xiaohongshu, Douyin, …), execute them, and post results back.

The client never opens a listening port — it only calls out to the center, so
no NAT traversal is needed. See ``docs/plan/publish-system/ARCHITECTURE.md`` §3.

Auth: clients identify with a ``client_id``; a shared token can be enforced
later via settings (``publisher_client_token``). For MVP the endpoints are
admin-gated.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field

from app.middleware.auth import Permission, get_current_user
from app.models.user import User
from app.publish.client import (
    claim_job,
    complete_job,
    get_job_status,
)
from app.publish.client.protocol import job_from_dict

router = APIRouter()


class ClaimRequest(BaseModel):
    platform: str = Field(..., description="Target platform: xiaohongshu / douyin / …")
    client_id: str = Field(..., description="Identifier of the claiming client machine")


class ResultRequest(BaseModel):
    status: str = Field("done", description="done | failed")
    result: dict | None = Field(default=None, description="PublishResult fields")
    error: str | None = None


@router.post("/jobs/claim")
async def claim(
    body: ClaimRequest,
    current_user: User = Depends(get_current_user),
):
    """Lease the oldest pending job for ``platform`` to ``client_id``.

    Returns the job (with content/media) or ``{"job_id": null}`` when idle.
    """
    _ = current_user
    job = await claim_job(body.platform, body.client_id)
    if job is None:
        return {"job_id": None}
    return {"job_id": job.job_id, "job": job.to_dict()}


@router.post("/jobs/{job_id}/result")
async def submit_result(
    job_id: str,
    body: ResultRequest,
    current_user: User = Depends(get_current_user),
):
    """Post the outcome of a claimed job back from the client."""
    _ = current_user
    error = body.error if body.status == "failed" else None
    job = await complete_job(job_id, result=body.result, error=error)
    if job is None:
        return {"ok": False, "error": "job not found"}
    return {"ok": True, "job_id": job.job_id, "status": job.status}


@router.get("/jobs/{job_id}")
async def job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """Query a job's current state (used by the publisher while polling)."""
    _ = current_user
    job = await get_job_status(job_id)
    if job is None:
        return {"job_id": job_id, "status": "unknown"}
    return job.to_dict()


@router.get("/health")
async def client_health(current_user: User = Depends(get_current_user)):
    """Liveness probe for the publisher-client subsystem."""
    _ = current_user
    return {"ok": True, "subsystem": "publisher-client"}


@router.post("/video-upload")
async def upload_generated_video(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Client machine uploads a generated video file.

    The client generates the video locally (ComfyUI/API), then POSTs the mp4
    here. We store it and return a downloadable URL. The client puts this URL
    into the job result's ``remote_url`` when calling /jobs/{id}/result.
    """
    import uuid

    from app.services.storage_service import storage_service

    data = await file.read()
    ext = ".mp4"
    if file.filename and "." in file.filename:
        ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    key = f"video/{current_user.id}/{uuid.uuid4()}{ext}"
    await storage_service.save_bytes(key, data, media_type="video/mp4")
    return {"ok": True, "url": f"/uploads/{key}", "size": len(data)}
