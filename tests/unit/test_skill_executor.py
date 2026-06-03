import importlib.util
import textwrap
from pathlib import Path

from app.workspace.skill_runner import _dispatch_namespace as _dispatch_namespace_skill
from app.workspace.skill_runner import _filter_kwargs as _filter_kwargs_for_callable


def test_filter_kwargs_for_callable():
    def main(command: str, query: str | None = None, extra: str | None = None):
        return command, query, extra

    filtered = _filter_kwargs_for_callable(
        main,
        {"command": "search", "query": "锂电池", "page": 1, "unknown": "x"},
    )
    assert filtered == {"command": "search", "query": "锂电池"}


def test_dispatch_namespace_skill(tmp_path: Path):
    (tmp_path / "patent_api.py").write_text(
        textwrap.dedent(
            """
            class PatentAPI:
                def search(self, **kwargs):
                    return {"success": True, "total": 1, "patents": []}

                def format_search_result(self, result, detailed=False):
                    return "ok-search"
            """
        ),
        encoding="utf-8",
    )
    (tmp_path / "patent_skill.py").write_text(
        textwrap.dedent(
            """
            class PatentSkill:
                def __init__(self, api):
                    self.api = api
                    self.commands = {"search": self.handle_search}

                def handle_search(self, args):
                    return self.api.format_search_result(
                        self.api.search(query=args.query)
                    )
            """
        ),
        encoding="utf-8",
    )
    main_py = tmp_path / "main.py"
    main_py.write_text(
        textwrap.dedent(
            """
            def main():
                pass
            """
        ),
        encoding="utf-8",
    )

    spec = importlib.util.spec_from_file_location("main_mod", main_py)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = _dispatch_namespace_skill(
        tmp_path,
        module,
        {"command": "search", "query": "锂电池"},
    )
    assert result == "ok-search"
