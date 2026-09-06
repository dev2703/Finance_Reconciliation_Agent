from pathlib import Path


def test_runtime_dependencies_include_neatlogs() -> None:
    requirements = Path("requirements-runtime.txt").read_text(encoding="utf-8").splitlines()

    assert any(line.startswith("neatlogs") for line in requirements)
