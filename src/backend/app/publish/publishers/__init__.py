"""Built-in API-class publishers.

Each publisher is a stateless ``BasePublisher`` instance. Register new channels
by appending to the list returned by :func:`build_builtin_publishers` — no
other code (skill surface, workflow engine) needs to change.
"""

from __future__ import annotations

from app.publish.base import BasePublisher
from app.publish.publishers.discord import DiscordPublisher
from app.publish.publishers.dingtalk import DingTalkPublisher
from app.publish.publishers.facebook import FacebookPublisher
from app.publish.publishers.feishu import FeishuPublisher
from app.publish.publishers.image_client import ImageClientPublisher
from app.publish.publishers.linkedin import LinkedInPublisher
from app.publish.publishers.playwright_client import PlaywrightClientPublisher
from app.publish.publishers.slack import SlackPublisher
from app.publish.publishers.telegram_channel import TelegramChannelPublisher
from app.publish.publishers.twitter_x import TwitterXPublisher
from app.publish.publishers.video_client import VideoClientPublisher
from app.publish.publishers.wechat_mp import WechatMpPublisher
from app.publish.publishers.wecom import WeComPublisher


def build_builtin_publishers() -> list[BasePublisher]:
    """Instantiate every built-in publisher (fresh list each call).

    Add new channels here only — the skill surface, registry, and workflow
    engine never change when a publisher is added.
    """
    return [
        # Domestic API channels
        FeishuPublisher(),
        DingTalkPublisher(),
        WeComPublisher(),
        WechatMpPublisher(),
        # Overseas API channels
        SlackPublisher(),
        DiscordPublisher(),
        TelegramChannelPublisher(),
        TwitterXPublisher(),
        FacebookPublisher(),
        LinkedInPublisher(),
        # Client-machine channels (Xiaohongshu/Douyin/Weibo via Playwright)
        PlaywrightClientPublisher(),
        # Video generation (ComfyUI / API on client machine)
        VideoClientPublisher(),
        # Image generation (ComfyUI / SD / API on client machine)
        ImageClientPublisher(),
    ]
