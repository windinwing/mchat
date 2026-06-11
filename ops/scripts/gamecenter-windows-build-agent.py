#!/usr/bin/env python3
"""GameCenter Windows build agent — HTTP API in the logged-in user session.

Why not a classic Windows Service?
  Services run in Session 0. Cocos Creator 2.4.x needs the interactive desktop
  session (build-worker / WebGL). This agent must start at user logon.

Install: ops/scripts/gamecenter-windows-build-agent-setup.ps1

Endpoints:
  GET  /v1/health   — liveness
  GET  /v1/status   — current/last job
  POST /v1/build    — run gamecenter-local-pipeline.sh (JSON body, Bearer token)

Config (first match wins):
  1. GAMECENTER_AGENT_CONFIG env → JSON file path
  2. ops/scripts/gamecenter-windows-agent.json next to this script
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "gamecenter-windows-agent.json"

_state_lock = threading.Lock()
_current_job: dict[str, Any] | None = None
_last_job: dict[str, Any] | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_config() -> dict[str, Any]:
    config_path = os.environ.get("GAMECENTER_AGENT_CONFIG", "").strip()
    if not config_path:
        config_path = str(DEFAULT_CONFIG_PATH)
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Agent config not found: {path}. Copy gamecenter-windows-agent.json.example and edit."
        )
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("Agent config must be a JSON object")
    return data


def _check_token(config: dict[str, Any], header_value: str | None) -> bool:
    expected = str(config.get("token") or "").strip()
    if not expected:
        return True
    if not header_value or not header_value.startswith("Bearer "):
        return False
    return header_value[7:].strip() == expected


def _bash_exe(config: dict[str, Any]) -> str:
    custom = str(config.get("bash_exe") or "").strip()
    if custom:
        return custom
    return r"C:\Program Files\Git\bin\bash.exe"


def _pipeline_script(config: dict[str, Any]) -> str:
    custom = str(config.get("pipeline_script") or "").strip()
    if custom:
        return custom
    mchat_dir = str(config.get("mchat_dir") or r"C:\Users\Administrator\dev\mchat").strip()
    return str(Path(mchat_dir) / "ops" / "scripts" / "gamecenter-local-pipeline.sh")


def _run_pipeline(
    config: dict[str, Any],
    slug: str,
    deploy_host: str,
    force: bool,
    build_id: str,
    *,
    skip_pull: bool = False,
) -> dict[str, Any]:
    global _current_job, _last_job

    pipeline = _pipeline_script(config)
    if not Path(pipeline).is_file():
        raise FileNotFoundError(f"pipeline script missing: {pipeline}")

    bash = _bash_exe(config)
    if not Path(bash).is_file():
        raise FileNotFoundError(f"bash not found: {bash}")

    pipeline_posix = pipeline.replace("\\", "/")
    cmd = f"bash '{pipeline_posix}' '{deploy_host}' '{slug}'"
    if force:
        cmd += " --force"
    if skip_pull:
        cmd += " --skip-pull"
    args = [bash, "--noprofile", "--norc", "-lc", cmd]

    started = _utc_now()
    job = {
        "slug": slug,
        "build_id": build_id or None,
        "deploy_host": deploy_host,
        "force": force,
        "started_at": started,
        "status": "running",
    }
    with _state_lock:
        if _current_job and _current_job.get("status") == "running":
            raise RuntimeError(
                f"build busy: slug={_current_job.get('slug')} started={_current_job.get('started_at')}"
            )
        _current_job = job

    timeout = int(config.get("build_timeout_seconds") or 1800)
    run_kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": max(timeout, 60),
        "cwd": str(Path(pipeline).parent),
    }
    # Cocos 2.4.x build-worker needs a desktop GL context; hidden/SSH subprocesses fail WebGL.
    if os.name == "nt":
        create_console = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x10)
        run_kwargs["creationflags"] = create_console
    try:
        proc = subprocess.run(args, **run_kwargs)
        finished = _utc_now()
        result = {
            **job,
            "status": "built" if proc.returncode == 0 else "failed",
            "returncode": proc.returncode,
            "finished_at": finished,
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
        }
    except subprocess.TimeoutExpired as exc:
        finished = _utc_now()
        result = {
            **job,
            "status": "failed",
            "returncode": -1,
            "finished_at": finished,
            "stdout": (exc.stdout or "") if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "") if isinstance(exc.stderr, str) else "",
            "error": f"timeout after {timeout}s",
        }
    except Exception as exc:
        finished = _utc_now()
        result = {
            **job,
            "status": "failed",
            "returncode": -1,
            "finished_at": finished,
            "stdout": "",
            "stderr": traceback.format_exc(),
            "error": str(exc),
        }
    finally:
        with _state_lock:
            _current_job = None
            _last_job = result
    return result


class AgentHandler(BaseHTTPRequestHandler):
    server_version = "GameCenterBuildAgent/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(
            "[%s] %s - %s\n" % (_utc_now(), self.address_string(), fmt % args)
        )

    @property
    def _config(self) -> dict[str, Any]:
        return self.server.config  # type: ignore[attr-defined]

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _unauthorized(self) -> None:
        self._send_json(401, {"ok": False, "error": "unauthorized"})

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        data = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if not _check_token(self._config, self.headers.get("Authorization")):
            self._unauthorized()
            return
        if path == "/v1/health":
            self._send_json(
                200,
                {
                    "ok": True,
                    "service": "gamecenter-windows-build-agent",
                    "time": _utc_now(),
                },
            )
            return
        if path == "/v1/status":
            with _state_lock:
                payload = {
                    "ok": True,
                    "current": _current_job,
                    "last": _last_job,
                }
            self._send_json(200, payload)
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if not _check_token(self._config, self.headers.get("Authorization")):
            self._unauthorized()
            return
        if path != "/v1/build":
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        try:
            body = self._read_json_body()
            slug = str(body.get("slug") or "").strip()
            if not slug:
                self._send_json(400, {"ok": False, "error": "slug required"})
                return
            deploy_host = str(
                body.get("deploy_host") or self._config.get("deploy_host") or "10.98.8.15"
            ).strip()
            force = bool(body.get("force"))
            skip_pull = bool(body.get("skip_pull"))
            build_id = str(body.get("build_id") or "").strip()
            result = _run_pipeline(
                self._config, slug, deploy_host, force, build_id, skip_pull=skip_pull
            )
            ok = result.get("status") == "built"
            self._send_json(200 if ok else 500, {"ok": ok, **result})
        except RuntimeError as exc:
            self._send_json(409, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"ok": False, "error": str(exc), "trace": traceback.format_exc()})


def main() -> int:
    try:
        config = load_config()
    except Exception as exc:
        print(f"Failed to load config: {exc}", file=sys.stderr)
        return 1

    host = str(config.get("host") or "0.0.0.0").strip()
    port = int(config.get("port") or 19280)
    httpd = ThreadingHTTPServer((host, port), AgentHandler)
    httpd.config = config  # type: ignore[attr-defined]
    print(
        f"GameCenter build agent listening on http://{host}:{port} "
        f"(deploy_host={config.get('deploy_host', '10.98.8.15')})",
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Agent stopping…", flush=True)
        httpd.shutdown()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
