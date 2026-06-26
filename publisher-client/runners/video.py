"""Video generation runners — each engine is a separate @register'd class.

The client machine claims ``platform = "video:<engine>"`` jobs. Each runner:
  1. Reads the prompt + params from job.content / job.extra
  2. Generates the video (ComfyUI / API / browser)
  3. Uploads the mp4 to the center via POST /api/publish/video-upload
  4. Returns {success, remote_url: "/uploads/video/.../xxx.mp4"}

Engine contract (all must implement):
  - job.content = video prompt (str)
  - job.extra.reference_urls = list of image URLs (for image-to-video)
  - job.extra.duration / resolution = generation params
  - return: {"success": True, "remote_url": "<center URL>", "message": "..."}
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

from runners import BaseRunner, register


class VideoGenerationError(Exception):
    """Video generation failed."""


@register("video:comfyui")
class ComfyUIVideoRunner(BaseRunner):
    """Generate video via local ComfyUI HTTP API.

    Flow: submit workflow (/prompt) → poll /history → download output →
    upload to center → return URL.

    Requires config [comfyui] section:
      server_url = "http://localhost:8188"
      output_dir = "/path/to/comfyui/output"
    """

    def publish(self, job: dict[str, Any]) -> dict[str, Any]:
        prompt = job.get("content", "")
        extra = job.get("extra") or {}
        reference_urls = extra.get("reference_urls") or []
        duration = extra.get("duration") or 5

        comfyui_cfg = self.cfg.get("comfyui") or {}
        server = comfyui_cfg.get("server_url", "http://localhost:8188")

        print(f"🎬 ComfyUI 视频生成: prompt={prompt[:60]}...")
        print(f"   参考图: {len(reference_urls)} 张, 时长: {duration}s")

        try:
            # 1. Submit workflow to ComfyUI
            workflow = self._build_workflow(prompt, reference_urls, duration)
            prompt_id = self._comfyui_submit(server, workflow)
            print(f"   ComfyUI 提交成功: prompt_id={prompt_id[:8]}...")

            # 2. Poll for completion
            video_path = self._comfyui_wait(server, prompt_id, timeout=1200)
            print(f"   视频生成完成: {video_path}")

            # 3. Upload to center
            video_url = self._upload_to_center(video_path)
            print(f"   已上传: {video_url}")

            return {
                "success": True,
                "remote_url": video_url,
                "message": f"ComfyUI 视频生成成功",
            }
        except Exception as e:
            raise VideoGenerationError(f"ComfyUI 生成失败: {e}") from e

    def _build_workflow(self, prompt: str, reference_urls: list, duration: int) -> dict:
        """Build a minimal ComfyUI workflow JSON.

        Override this with your actual workflow template. This is a placeholder
        that demonstrates the contract — replace with your real ComfyUI API
        format (node graph with CLIPTextEncode, VAEDecode, SaveVideo, etc.).
        """
        comfyui_cfg = self.cfg.get("comfyui") or {}
        wf_file = comfyui_cfg.get("text_to_video_workflow")
        if wf_file and Path(wf_file).exists():
            wf = json.loads(Path(wf_file).read_text())
        else:
            # Minimal placeholder — you MUST replace with a real workflow
            wf = {"3": {"class_type": "KSampler", "inputs": {"seed": 0}}}

        # Inject prompt into the workflow (adjust node id for your template)
        for node in wf.values():
            if isinstance(node, dict) and "positive" in str(node.get("inputs", {})):
                node["inputs"]["positive"] = prompt
        return wf

    def _comfyui_submit(self, server: str, workflow: dict) -> str:
        """POST /prompt to ComfyUI, return prompt_id."""
        data = json.dumps({"prompt": workflow}).encode("utf-8")
        req = urllib.request.Request(
            f"{server}/prompt", data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        return result.get("prompt_id", "")

    def _comfyui_wait(self, server: str, prompt_id: str, timeout: int = 1200) -> str:
        """Poll /history until the job completes, return output file path."""
        deadline = time.time() + timeout
        comfyui_cfg = self.cfg.get("comfyui") or {}
        output_dir = Path(comfyui_cfg.get("output_dir", "/tmp/comfyui_output"))

        while time.time() < deadline:
            try:
                req = urllib.request.Request(f"{server}/history/{prompt_id}")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    history = json.loads(resp.read())

                outputs = (history.get(prompt_id, {}) or {}).get("outputs", {})
                if outputs:
                    # Find the video file in outputs
                    for node_id, node_out in outputs.items():
                        videos = (node_out.get("videos") or node_out.get("gifs") or [])
                        for v in videos:
                            fname = v.get("filename")
                            subfolder = v.get("subfolder", "")
                            path = output_dir / subfolder / fname if fname else None
                            if path and path.exists():
                                return str(path)
            except Exception:
                pass
            time.sleep(5)

        raise VideoGenerationError(f"ComfyUI 超时 ({timeout}s)")

    def _upload_to_center(self, video_path: str) -> str:
        """Upload video file to center's /api/publish/video-upload, return URL."""
        center_cfg = self.cfg.get("center") or {}
        base = center_cfg.get("url", "http://localhost:3001").rstrip("/")
        token = center_cfg.get("token", "")

        with open(video_path, "rb") as f:
            file_data = f.read()

        # Build multipart form
        boundary = "----FormBoundary7MA4YWxkTrZu0gW"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{Path(video_path).name}"\r\n'
            f"Content-Type: video/mp4\r\n\r\n"
        ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

        req = urllib.request.Request(
            f"{base}/api/publish/video-upload",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Authorization": f"Bearer {token}",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())

        url = result.get("url", "")
        if not url:
            raise VideoGenerationError(f"上传失败: {result}")
        # Make URL absolute if relative
        if url.startswith("/"):
            url = f"{base}{url}"
        return url


@register("video:kling")
class KlingVideoRunner(BaseRunner):
    """Generate video via Kling (可灵) API.

    Placeholder — implement when you have Kling API credentials.
    The contract is the same: read prompt from job.content, call Kling API,
    download result, upload to center, return URL.
    """

    def publish(self, job: dict[str, Any]) -> dict[str, Any]:
        raise VideoGenerationError(
            "Kling API runner 尚未实现。请在 runners/video.py 中配置 Kling API 凭证后实现。"
        )


@register("video:jimeng")
class JimengVideoRunner(BaseRunner):
    """Generate video via 即梦 (Jimeng/Dreamina) API.

    Placeholder — implement when you have Jimeng API credentials.
    """

    def publish(self, job: dict[str, Any]) -> dict[str, Any]:
        raise VideoGenerationError(
            "即梦 API runner 尚未实现。请在 runners/video.py 中配置即梦 API 凭证后实现。"
        )


# ===========================================================================
# Image generation runners (same architecture, shorter jobs)
# ===========================================================================

class ImageGenerationError(Exception):
    """Image generation failed."""


@register("image:comfyui")
class ComfyUIImageRunner(BaseRunner):
    """Generate image via local ComfyUI HTTP API.

    Reuses the same ComfyUI infra as video: submit workflow → poll /history →
    download output → upload to center → return URL.
    """

    def publish(self, job: dict[str, Any]) -> dict[str, Any]:
        prompt = job.get("content", "")
        extra = job.get("extra") or {}
        reference_urls = extra.get("reference_urls") or []
        resolution = extra.get("resolution") or "1024x1024"

        comfyui_cfg = self.cfg.get("comfyui") or {}
        server = comfyui_cfg.get("server_url", "http://localhost:8188")

        print(f"🖼️ ComfyUI 图片生成: prompt={prompt[:60]}...")
        print(f"   参考图: {len(reference_urls)} 张, 分辨率: {resolution}")

        try:
            workflow = self._build_image_workflow(prompt, reference_urls, resolution)
            prompt_id = self._comfyui_submit(server, workflow)
            print(f"   ComfyUI 提交成功: prompt_id={prompt_id[:8]}...")

            image_path = self._comfyui_wait_image(server, prompt_id, timeout=600)
            print(f"   图片生成完成: {image_path}")

            image_url = self._upload_to_center(image_path)
            print(f"   已上传: {image_url}")

            return {"success": True, "remote_url": image_url, "message": "ComfyUI 图片生成成功"}
        except Exception as e:
            raise ImageGenerationError(f"ComfyUI 图片生成失败: {e}") from e

    def _build_image_workflow(self, prompt: str, reference_urls: list, resolution: str) -> dict:
        comfyui_cfg = self.cfg.get("comfyui") or {}
        wf_file = comfyui_cfg.get("text_to_image_workflow")
        if wf_file and Path(wf_file).exists():
            wf = json.loads(Path(wf_file).read_text())
        else:
            wf = {"3": {"class_type": "KSampler", "inputs": {"seed": 0}}}
        for node in wf.values():
            if isinstance(node, dict) and "positive" in str(node.get("inputs", {})):
                node["inputs"]["positive"] = prompt
        return wf

    def _comfyui_submit(self, server: str, workflow: dict) -> str:
        data = json.dumps({"prompt": workflow}).encode("utf-8")
        req = urllib.request.Request(f"{server}/prompt", data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read()).get("prompt_id", "")

    def _comfyui_wait_image(self, server: str, prompt_id: str, timeout: int = 600) -> str:
        deadline = time.time() + timeout
        comfyui_cfg = self.cfg.get("comfyui") or {}
        output_dir = Path(comfyui_cfg.get("output_dir", "/tmp/comfyui_output"))
        while time.time() < deadline:
            try:
                req = urllib.request.Request(f"{server}/history/{prompt_id}")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    history = json.loads(resp.read())
                outputs = (history.get(prompt_id, {}) or {}).get("outputs", {})
                if outputs:
                    for _nid, node_out in outputs.items():
                        images = node_out.get("images") or []
                        for img in images:
                            fname = img.get("filename")
                            subfolder = img.get("subfolder", "")
                            path = output_dir / subfolder / fname if fname else None
                            if path and path.exists():
                                return str(path)
            except Exception:
                pass
            time.sleep(3)
        raise ImageGenerationError(f"ComfyUI 图片超时 ({timeout}s)")

    def _upload_to_center(self, image_path: str) -> str:
        center_cfg = self.cfg.get("center") or {}
        base = center_cfg.get("url", "http://localhost:3001").rstrip("/")
        token = center_cfg.get("token", "")
        with open(image_path, "rb") as f:
            file_data = f.read()
        boundary = "----FormBoundary7MA4YWxkTrZu0gW"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{Path(image_path).name}"\r\n'
            f"Content-Type: image/png\r\n\r\n"
        ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            f"{base}/api/publish/video-upload",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
        url = result.get("url", "")
        if not url:
            raise ImageGenerationError(f"上传失败: {result}")
        return f"{base}{url}" if url.startswith("/") else url
