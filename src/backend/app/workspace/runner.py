"""Phase 2 placeholder: isolated runner service (not implemented).

Phase 1 keeps the main backend as control plane and uses per-user sidecar
containers only for skill execution inside tenant volumes.

Phase 2 (future): if we need stronger code editing, long-running tasks, or
strict disk quotas, introduce a separate ``mchat-runner`` service that:
  - accepts signed run requests from the control plane
  - never hosts auth, webhooks, workflows, or DB access
  - enforces quotas inside the runner process layer

Do not grow sidecar containers into full application stacks.
"""

from __future__ import annotations

# Intentionally empty — API surface will be defined when Phase 2 starts.
