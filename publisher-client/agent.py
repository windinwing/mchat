"""Publisher-client machine — Pull-mode agent.

A standalone process (deployed on a mac mini or dedicated box) that polls the
MChat center for publish jobs, executes them locally via Playwright with a
persistent real-IP browser profile, and posts results back.

Why standalone: browser automation (anti-detection, cookie persistence, human
timing) is heavy and dirty — it must NOT run in the backend process. Running on
a real user machine with a durable profile is what makes "fully simulate human
behavior" viable (a server IP + fresh fingerprint gets banned instantly).

The client only calls OUT to the center (no listening port), so it works behind
NAT. Configure via config.toml.

Usage:
    python agent.py                # run with config.toml
    python agent.py --once         # claim & run one job then exit (testing)
    python agent.py --dry-run      # claim but don't actually publish (testing)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore

import urllib.request


def load_config(path: str = "config.toml") -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        print(f"❌ 配置文件不存在: {path}", file=sys.stderr)
        print("   请复制 config.example.toml 为 config.toml 并填写", file=sys.stderr)
        sys.exit(1)
    with p.open("rb") as f:
        return tomllib.load(f)


def api(cfg: dict, method: str, path: str, body: dict | None = None) -> dict:
    """Call the MChat center API (sync urllib, no extra deps)."""
    base = cfg["center"]["url"].rstrip("/")
    token = cfg["center"].get("token", "")
    url = f"{base}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}", "_body": e.read().decode("utf-8", "replace")[:200]}
    except Exception as e:
        return {"_error": str(e)}


def claim_job(cfg: dict, platform: str) -> dict | None:
    """Ask the center for one pending job for this platform."""
    client_id = cfg["client"]["id"]
    res = api(cfg, "POST", "/api/publish/jobs/claim", {"platform": platform, "client_id": client_id})
    if res.get("_error"):
        print(f"  claim 错误: {res['_error']}")
        return None
    if not res.get("job_id"):
        return None
    return res.get("job")


def submit_result(cfg: dict, job_id: str, success: bool, message: str = "", **extra) -> None:
    body = {
        "status": "done" if success else "failed",
        "result": {"success": success, "message": message, **extra} if success else None,
        "error": None if success else message,
    }
    api(cfg, "POST", f"/api/publish/jobs/{job_id}/result", body)


def execute_job(cfg: dict, job: dict, dry_run: bool = False) -> None:
    """Dispatch a job to the right runner (Playwright) for its platform."""
    platform = job.get("platform", "")
    job_id = job.get("job_id", "")
    print(f"\n▶ 执行任务 {job_id[:8]} platform={platform}")
    print(f"  标题: {job.get('title','')}")
    print(f"  内容: {(job.get('content') or '')[:80]}...")

    if dry_run:
        print("  [dry-run] 跳过实际发布")
        submit_result(cfg, job_id, success=True, message="dry-run ok")
        return

    try:
        from runners import get_runner  # type: ignore
    except ImportError:
        submit_result(cfg, job_id, success=False, message="runners 模块加载失败")
        print("  ❌ runners 模块加载失败")
        return

    runner = get_runner(platform, cfg)
    if runner is None:
        submit_result(cfg, job_id, success=False, message=f"不支持的 platform: {platform}")
        print(f"  ❌ 不支持 platform={platform}")
        return

    try:
        result = runner.publish(job)
        submit_result(cfg, job_id, success=result.get("success", True),
                       message=str(result.get("message", "")),
                       remote_id=result.get("remote_id"),
                       remote_url=result.get("remote_url"))
        print(f"  ✅ {result.get('message', '完成')}")
    except Exception as e:
        # Human-in-the-loop errors get a distinct code so the center can surface
        # "needs operator action" rather than a generic failure.
        msg = str(e)
        error_code = "error"
        ename = type(e).__name__
        if "NeedsLogin" in ename or "登录" in msg:
            error_code = "needs_login"
        elif "Captcha" in ename or "验证" in msg or "风控" in msg:
            error_code = "captcha"
            print("  ⏸️  遇到风控验证，已暂停回传 — 请人工介入后重试")
        body = {"success": False, "message": msg, "error_code": error_code}
        api(cfg, "POST", f"/api/publish/jobs/{job_id}/result",
            {"status": "failed", "result": None, "error": msg})
        print(f"  ❌ [{error_code}] {msg}")


def trigger_workflow(cfg: dict, workflow_id: str, payload: dict) -> None:
    """Fire a workflow run-once on the center (one-shot)."""
    res = api(cfg, "POST", f"/api/workflows/{workflow_id}/run-once", payload)
    if res.get("_error"):
        print(f"❌ 触发失败: {res['_error']}")
    else:
        print(f"✅ 已触发 workflow {workflow_id[:8]} run={res.get('id','')[:8]}")


def run_scheduler_loop(cfg: dict, schedules: list[dict]) -> None:
    """Loop that fires configured workflow schedules on a fixed cadence.

    Each entry: {workflow_id, payload, every_minutes}. This keeps scheduling
    on the client side (zero backend change, self-contained). For real cron
    precision start the backend worker instead; this is a lightweight fallback
    that coexists with the polling loop.
    """
    import time

    state = {  # workflow_id -> next_run_ts
        s["workflow_id"]: 0.0 for s in schedules
    }
    print(f"⏰ 定时触发器启动: {len(schedules)} 个工作流")
    for s in schedules:
        print(f"   {s['workflow_id'][:8]}... 每 {s.get('every_minutes',60)} 分钟, payload keys={list(s.get('payload',{}).keys())}")
    while True:
        now = time.time()
        for s in schedules:
            wid = s["workflow_id"]
            every = int(s.get("every_minutes", 60)) * 60
            if now >= state.get(wid, 0):
                print(f"\n▶ 定时触发 {wid[:8]}...")
                trigger_workflow(cfg, wid, s.get("payload") or {})
                state[wid] = now + every
        time.sleep(60)


def main() -> None:
    parser = argparse.ArgumentParser(description="MChat publisher-client (Pull mode)")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--once", action="store_true", help="run one job then exit")
    parser.add_argument("--dry-run", action="store_true", help="claim but skip actual publish")
    parser.add_argument(
        "--trigger",
        nargs=2,
        metavar=("WORKFLOW_ID", "PAYLOAD_JSON"),
        help="one-shot: trigger a workflow run-once with a JSON payload, then exit",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="run the workflow scheduler loop (see config [schedule]) instead of polling",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)

    # One-shot workflow trigger.
    if args.trigger:
        wid, payload_json = args.trigger
        import json

        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError as e:
            print(f"❌ payload JSON 无效: {e}")
            return
        trigger_workflow(cfg, wid, payload)
        return

    # Scheduled workflow trigger loop.
    if args.schedule:
        schedules = cfg.get("schedule") or []
        if not schedules:
            print("❌ config 里没有 [schedule] 配置")
            return
        run_scheduler_loop(cfg, schedules)
        return

    platforms = cfg.get("platforms", ["xiaohongshu"])
    interval = int(cfg.get("poll", {}).get("interval_seconds", 15))

    print(f"🤖 publisher-client 启动: id={cfg['client']['id']} platforms={platforms}")
    print(f"   中心: {cfg['center']['url']}  轮询间隔: {interval}s")

    while True:
        got_any = False
        for platform in platforms:
            job = claim_job(cfg, platform)
            if job is not None:
                got_any = True
                execute_job(cfg, job, dry_run=args.dry_run)
                if args.once:
                    return
        if args.once:
            print("(无待处理任务)")
            return
        if not got_any:
            print(f"  … 空闲，{interval}s 后再查", end="\r")
        time.sleep(interval)


if __name__ == "__main__":
    main()
