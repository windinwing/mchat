"""Skill loader - scan filesystem for SKILL.md files, parse them, and hot-reload."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import settings


class SkillLoader:
    """Scans the skills directory for SKILL.md files and parses them."""

    def __init__(self, skills_dir: str | None = None) -> None:
        self.skills_dir = Path(skills_dir or settings.skills_dir)

    def scan_skills(self) -> list[dict[str, Any]]:
        """Scan for SKILL.md files and parse skill definitions."""
        skills = []

        if not self.skills_dir.exists():
            logger.warning(
                f"Skills directory not found: {self.skills_dir}"
            )
            return skills

        for item in self.skills_dir.iterdir():
            if item.is_dir():
                skill_md = item / "SKILL.md"
                if skill_md.exists():
                    skill_data = self._parse_skill_md(skill_md)
                    if skill_data:
                        skills.append(skill_data)

        logger.info(f"Loaded {len(skills)} skills from {self.skills_dir}")
        return skills

    @staticmethod
    def _locale_block(content: str, locale: str) -> str:
        """Extract a locales.<locale> block from OpenClaw-style SKILL.md."""
        match = re.search(rf"(?m)^\s*{re.escape(locale)}\s*:\s*$", content)
        if not match:
            return ""
        start = match.end()
        nxt = re.search(
            r"(?m)^\s*(?:en|zh|[a-z]{2})\s*:\s*$",
            content[start:],
        )
        end = start + nxt.start() if nxt else len(content)
        return content[start:end]

    @staticmethod
    def _yaml_quoted_field(block: str, field: str) -> str:
        m = re.search(
            rf'(?m)^\s*{re.escape(field)}\s*:\s*["\'](.+?)["\']\s*$',
            block,
        )
        return m.group(1).strip() if m else ""

    @staticmethod
    def _yaml_multiline_field(block: str, field: str) -> str:
        m = re.search(
            rf"(?m)^\s*{re.escape(field)}\s*:\s*\|\s*\n"
            rf"((?:[ \t]+.+(?:\n|$))+)",
            block,
        )
        if not m:
            return ""
        lines = m.group(1).splitlines()
        indents = [
            len(line) - len(line.lstrip())
            for line in lines
            if line.strip()
        ]
        strip = min(indents) if indents else 0
        out: list[str] = []
        for line in lines:
            if not line.strip():
                out.append("")
            elif len(line) >= strip:
                out.append(line[strip:])
            else:
                out.append(line.lstrip())
        return "\n".join(out).strip()

    def _parse_openclaw_skill_md(
        self, content: str, skill_data: dict[str, Any]
    ) -> None:
        """OpenClaw / xiaoyi patentskill SKILL.md (locales.zh, no --- frontmatter)."""
        i18n: dict[str, dict[str, str]] = {}
        prompt_body = ""
        for locale in ("zh", "en"):
            block = self._locale_block(content, locale)
            if not block:
                continue
            title = self._yaml_quoted_field(block, "name") or self._yaml_quoted_field(
                block, "title"
            )
            desc = self._yaml_quoted_field(block, "description")
            long_desc = self._yaml_multiline_field(block, "long_description")
            entry: dict[str, str] = {}
            if title:
                entry["title"] = title
            if desc:
                entry["description"] = desc
            if entry:
                i18n[locale] = entry
            if long_desc and not prompt_body:
                prompt_body = long_desc
            if desc and not skill_data.get("description"):
                skill_data["description"] = desc
        if i18n:
            skill_data["config"]["i18n"] = i18n
        if prompt_body:
            skill_data["config"]["prompt_body"] = prompt_body
            if not skill_data.get("description"):
                zh_desc = (i18n.get("zh") or {}).get("description", "")
                skill_data["description"] = zh_desc or prompt_body[:500]
        if i18n or prompt_body:
            return
        # Fallback: first markdown heading + paragraph
        heading = re.search(r"(?m)^#\s+(.+)$", content)
        if heading and not skill_data.get("description"):
            skill_data["description"] = heading.group(1).strip()
        if len(content.strip()) > 100:
            skill_data["config"]["prompt_body"] = content.strip()[:12000]

    def _parse_skill_md(self, file_path: Path) -> dict[str, Any] | None:
        """Parse a SKILL.md file to extract skill metadata.

        Supports:
        - YAML frontmatter between --- markers (mchat / example-skill)
        - OpenClaw locales.zh / locales.en blocks (patent-search zip)
        """
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")

            skill_data: dict[str, Any] = {
                "name": file_path.parent.name,
                "description": "",
                "type": "tool",
                "config": {},
                "path": str(file_path),
            }
            body = ""

            if not content.lstrip().startswith("---"):
                self._parse_openclaw_skill_md(content, skill_data)

            # Simple frontmatter parser
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = parts[1].strip()
                    body = parts[2].strip()

                    # Parse simple key: value lines
                    for line in frontmatter.split("\n"):
                        line = line.strip()
                        if ":" in line:
                            key, _, value = line.partition(":")
                            key = key.strip().lower()
                            value = value.strip().strip('"').strip("'")

                            if key == "name":
                                skill_data["name"] = value
                            elif key == "description":
                                skill_data["description"] = value
                            elif key == "type":
                                skill_data["type"] = value
                            elif key == "scope":
                                skill_data["config"]["scope"] = value
                            elif key == "requires_admin":
                                skill_data["config"]["requires_admin"] = value.lower() in (
                                    "true",
                                    "1",
                                    "yes",
                                )

                    if body:
                        skill_data["config"]["prompt_body"] = body
                        if not skill_data.get("description"):
                            skill_data["description"] = body[:500]

                    skill_data["config"].update(self._parse_config(frontmatter))

            skill_dir = file_path.parent
            has_script = (skill_dir / "main.py").exists() or (
                skill_dir / "tool.py"
            ).exists()
            skill_type = str(skill_data.get("type", "tool")).lower()
            if skill_type == "tool" and not has_script and body:
                skill_data["type"] = "prompt"
            elif skill_type == "tool" and not has_script:
                skill_data["type"] = "prompt"

            return skill_data
        except Exception as e:
            logger.error(
                f"Failed to parse skill file {file_path}: {e}"
            )
            return None

    def _parse_config(
        self, frontmatter: str
    ) -> dict[str, Any]:
        """Parse additional config from frontmatter."""
        config: dict[str, Any] = {}

        for line in frontmatter.split("\n"):
            line = line.strip()
            if line.startswith("parameters:"):
                params_str = line.split(":", 1)[1].strip()
                if params_str:
                    try:
                        import json

                        config["parameters"] = json.loads(params_str)
                    except json.JSONDecodeError:
                        pass
            elif line.startswith("scope:"):
                config["scope"] = line.split(":", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("requires_admin:"):
                val = line.split(":", 1)[1].strip().lower()
                config["requires_admin"] = val in ("true", "1", "yes")

        return config

    def get_skill_tools(self) -> list[dict[str, Any]]:
        """Get tool definitions for all loaded skills (for tool calling)."""
        tools = []
        for skill in self.scan_skills():
            tool_def = {
                "type": "function",
                "function": {
                    "name": skill.get("name", ""),
                    "description": skill.get("description", ""),
                    "parameters": (skill.get("config") or {}).get(
                        "parameters",
                        {"type": "object", "properties": {}},
                    ),
                },
            }
            tools.append(tool_def)

        return tools
