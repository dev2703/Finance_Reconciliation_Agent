from pathlib import Path


def test_render_python_version_is_compatible_with_neatlogs() -> None:
    assert Path(".python-version").read_text(encoding="utf-8").strip() == "3.13"


def test_runtime_dependencies_include_neatlogs() -> None:
    requirements = Path("requirements-runtime.txt").read_text(encoding="utf-8").splitlines()

    assert any(line.startswith("neatlogs") for line in requirements)
