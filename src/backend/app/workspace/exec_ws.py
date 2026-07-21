"""Interactive shell into a managed execution sidecar via WebSocket.

Provides a ttyd-like terminal: a browser xterm.js client talks binary frames
for stdin/stdout and small JSON control frames (resize/ping) over a single
``/ws/exec`` connection. Only global admins may attach, and only into
sidecars labeled ``mchat.workspace=true`` — never arbitrary host containers.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import pty
import shutil
import struct
import subprocess
import termios
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from loguru import logger
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.middleware.auth import has_global_scope
from app.models.user import User

router = APIRouter()


async def _authenticate_ws(token: str | None) -> User | None:
    """Validate a bearer token and return the user, or None."""
    if not token:
        return None
    try:
        from app.core.security import verify_access_token

        payload = verify_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            return None
        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.id == user_id))
            return result.scalar_one_or_none()
    except Exception:
        return None


def _docker_bin() -> str:
    return shutil.which("docker") or "docker"


def _is_managed_sidecar(container: str) -> bool:
    """True only if the container exists, is running, and carries the
    ``mchat.workspace=true`` label. Refuses arbitrary host containers."""
    docker = _docker_bin()
    proc = subprocess.run(
        [
            docker,
            "inspect",
            container,
            "--format",
            "{{.State.Running}}|{{index .Config.Labels \""
            + settings.workspace_container_label
            + "\"}}",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    if proc.returncode != 0:
        return False
    out = (proc.stdout or "").strip()
    running, _, label = out.partition("|")
    return running == "true" and label == "true"


def _container_has_shell(container: str, shell: str) -> bool:
    """True if the shell resolves in the container.

    Uses ``command -v`` (PATH-aware, works for both bare names like ``bash``
    and absolute paths) rather than ``test -x <name>`` — a bare ``test -x
    bash`` fails because ``docker exec`` doesn't resolve PATH for the test
    argument, only ``command -v``/``which`` do.
    """
    proc = subprocess.run(
        [_docker_bin(), "exec", container, "sh", "-c", f"command -v {shell} >/dev/null 2>&1"],
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0


def _set_pty_size_initial(master_fd: int, cols: int, rows: int) -> None:
    """Set the PTY window size BEFORE spawning the exec.

    docker exec reads the slave's winsize at startup, so the initial size is
    adopted by the container. (Runtime ioctl resizes are NOT propagated by
    docker exec — see ``resize_pty`` for the dynamic path.)
    """
    try:
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
    except OSError as exc:
        logger.debug("pty initial size failed: {}", exc)


def resize_pty(master_fd: int, cols: int, rows: int) -> None:
    """Resize the container PTY at runtime.

    ``docker exec -it`` does NOT propagate host-side TIOCSWINSZ changes to the
    container's PTY after start, so we set the size from inside the shell via
    ``stty``. Because the master end is a real tty, ``stty`` succeeds (unlike
    the old piped approach). We wrap it to suppress the echoed command and
    prompt noise on the terminal.
    """
    # Update the host pty too (keeps host/slave consistent for any tooling).
    try:
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    except OSError:
        pass
    # stty on the tty stdin inside the container; semicolons keep it one line.
    # The echo of this command is unavoidable under docker exec's PTY, but it's
    # a single short line — acceptable for an admin debug shell.
    try:
        os.write(master_fd, f" stty rows {rows} cols {cols}\n".encode())
    except OSError as exc:
        logger.debug("pty stty resize failed: {}", exc)


async def _pump_pty_to_ws(master_fd: int, ws: WebSocket) -> None:
    """Forward PTY master output to the websocket as binary frames.

    ``os.read`` on the master fd is blocking, so it runs on a worker thread
    via ``to_thread``; each read yields to the event loop between chunks.
    """
    loop = asyncio.get_event_loop()
    try:
        while True:
            chunk = await loop.run_in_executor(None, lambda: os.read(master_fd, 65536))
            if not chunk:
                break
            await ws.send_bytes(chunk)
    except (OSError, asyncio.CancelledError) as exc:
        logger.debug("exec ws pty pump ended: {}", exc)


@router.websocket("/ws/exec")
async def exec_endpoint(
    websocket: WebSocket,
    token: str | None = Query(None),
    container: str | None = Query(None),
    shell: str | None = Query(None),
    cols: int | None = Query(None),
    rows: int | None = Query(None),
):
    """Open an interactive shell (``docker exec -it``) into a sidecar.

    Protocol:
      - C→S binary frame  → bytes written to the container stdin
      - C→S text frame    → JSON control: {type:resize,cols,rows} | {type:ping}
      - S→C binary frame  → container stdout/stderr bytes
      - S→C text frame    → JSON: {type:exit,code} | {type:error,message} | {type:pong}
    """
    # 1) AuthN — must have a valid token.
    user = await _authenticate_ws(token)
    if user is None:
        await websocket.close(code=1008)  # policy violation
        return

    # 2) AuthZ — only global admins may exec (root shell is powerful).
    async with async_session_factory() as db:
        is_admin = await has_global_scope(user, db)
    if not is_admin:
        logger.warning("exec ws denied (non-admin) for user {}", user.id)
        await websocket.close(code=1008)
        return

    # 3) Validate target: a real running sidecar we manage.
    container_name = (container or "").strip()
    if not container_name:
        await websocket.close(code=1008)
        return
    if not _is_managed_sidecar(container_name):
        logger.warning("exec ws denied (unmanaged container) {}", container_name)
        await websocket.close(code=1008)
        return

    # 4) Pick a shell that actually exists in the image (bash → sh).
    chosen_shell = (shell or "bash").strip() or "bash"
    if not _container_has_shell(container_name, chosen_shell):
        if chosen_shell != "sh" and _container_has_shell(container_name, "sh"):
            chosen_shell = "sh"
        else:
            await websocket.accept()
            await websocket.send_text(
                json.dumps({"type": "error", "message": f"shell not found: {chosen_shell}"})
            )
            await websocket.close(code=1008)
            return

    await websocket.accept()

    # 5) Allocate a host PTY and run `docker exec -it` against it. The PTY
    #    slave is the exec's stdin/stdout/stderr, so the container-side shell
    #    sees a real tty (stty, Ctrl-C, line editing all work). We read/write
    #    the master end. Initial size is set via TIOCSWINSZ before spawn
    #    (docker reads it at start); runtime resize uses `stty` because
    #    docker exec does NOT propagate host ioctl changes after start.
    term_cols = int(cols) if cols and cols > 0 else 80
    term_rows = int(rows) if rows > 0 else 24
    try:
        master_fd, slave_fd = pty.openpty()
    except OSError as exc:
        logger.error("exec ws openpty failed for {}: {}", container_name, exc)
        await websocket.send_text(
            json.dumps({"type": "error", "message": f"failed to allocate pty: {exc}"})
        )
        await websocket.close(code=1011)
        return

    _set_pty_size_initial(master_fd, term_cols, term_rows)

    cmd = [
        _docker_bin(),
        "exec",
        "-i",
        "-t",
        container_name,
        chosen_shell,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            start_new_session=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("exec ws failed to spawn for {}: {}", container_name, exc)
        for fd in (master_fd, slave_fd):
            try:
                os.close(fd)
            except OSError:
                pass
        await websocket.send_text(
            json.dumps({"type": "error", "message": f"failed to start shell: {exc}"})
        )
        await websocket.close(code=1011)
        return
    finally:
        # Parent doesn't need the slave once the child inherited it.
        try:
            os.close(slave_fd)
        except OSError:
            pass

    logger.info("exec ws opened: user={} container={} pid={}", user.id, container_name, proc.pid)

    def _send_resize(c: int, r: int) -> None:
        resize_pty(master_fd, c, r)

    # No initial runtime stty — initial size was set via ioctl before spawn,
    # which docker adopts. (Calling stty here would echo noise at startup.)

    pump = asyncio.create_task(_pump_pty_to_ws(master_fd, websocket))

    try:
        while True:
            msg = await websocket.receive()
            data = msg.get("bytes")
            text = msg.get("text")
            if data:
                # stdin bytes from the terminal → write to PTY master
                try:
                    os.write(master_fd, data)
                except OSError:
                    break
                continue
            if text:
                try:
                    ctrl = json.loads(text)
                except json.JSONDecodeError:
                    continue
                mtype = ctrl.get("type")
                if mtype == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif mtype == "resize":
                    _send_resize(
                        int(ctrl.get("cols", 80) or 80),
                        int(ctrl.get("rows", 24) or 24),
                    )
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.error("exec ws error for {}: {}", container_name, exc)
    finally:
        # Tear down: stop the pump, close the PTY (SIGHUP to the shell), report exit.
        pump.cancel()
        try:
            os.close(master_fd)
        except OSError:
            pass
        try:
            proc.terminate()
        except ProcessLookupError:
            pass
        try:
            code = await asyncio.wait_for(proc.wait(), timeout=3)
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001
            code = -1
        try:
            await websocket.send_text(json.dumps({"type": "exit", "code": code}))
        except Exception:  # noqa: BLE001
            pass
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass
        logger.info("exec ws closed: container={} code={}", container_name, code)
