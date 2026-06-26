"""Publisher-client machine protocol (Pull mode).

The central side never runs a browser. For platforms with no official publish
API (Xiaohongshu, Douyin, WeChat Channels) a dedicated client process polls
this protocol to claim a job, executes it locally via Playwright, and posts the
result back. See ``docs/plan/publish-system/ARCHITECTURE.md`` §3.
"""

from app.publish.client.protocol import (
    PROTOCOL_VERSION,
    PublishJob,
    PublishJobStatus,
    build_job,
    job_from_dict,
)
from app.publish.client.dispatcher import (
    claim_job,
    complete_job,
    enqueue_job,
    get_job_status,
)

__all__ = [
    "PROTOCOL_VERSION",
    "PublishJob",
    "PublishJobStatus",
    "build_job",
    "job_from_dict",
    "claim_job",
    "complete_job",
    "enqueue_job",
    "get_job_status",
]
