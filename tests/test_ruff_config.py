import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("command", [("format", "--check"), ("check",)])
def test_ruff_skips_bundled_skills_but_checks_project_source(tmp_path: Path, command: tuple):
    root = Path(__file__).resolve().parents[1]
    shutil.copyfile(root / "pyproject.toml", tmp_path / "pyproject.toml")
    bundled = tmp_path / ".claude/skills/neatlogs-py-openai/references"
    bundled.mkdir(parents=True)
    (bundled / "example.py").write_text("invalid python !!!\n", encoding="utf-8")
    (bundled / "example.md").write_text("```python\nx=  1\n```\n", encoding="utf-8")
    project = tmp_path / "services/example.py"
    project.parent.mkdir()
    project.write_text("x = 1\n", encoding="utf-8")

    def run_ruff():
        return subprocess.run(
            [sys.executable, "-m", "ruff", *command, "."],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

    result = run_ruff()
    assert result.returncode == 0, result.stdout + result.stderr

    project.write_text("import os\nx=  1\n", encoding="utf-8")
    result = run_ruff()
    assert result.returncode == 1, result.stdout + result.stderr
    assert "example.py" in result.stdout + result.stderr
    assert ".claude" not in result.stdout + result.stderr
