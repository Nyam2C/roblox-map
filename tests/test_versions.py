"""Dependency pins: scripts and tests use the same exact versions, and CI is pinned (N-8, SECURITY-10)."""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([0-9][A-Za-z0-9_.+!-]*)$")


def _inline_deps(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"(?ms)^# /// script\n(.*?)^# ///$", text)
    assert m, f"{path.name} has no inline script metadata"
    body = "\n".join(line[2:] if line.startswith("# ") else line[1:] for line in m.group(1).splitlines())
    return tomllib.loads(body)["dependencies"]


def _requirements() -> dict[str, str]:
    pins = {}
    for line in (ROOT / "tests" / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            m = PIN.match(line)
            assert m, f"tests/requirements.txt must pin exactly: {line!r}"
            pins[m.group(1).lower()] = m.group(2)
    return pins


SCRIPTS = sorted(p for p in (ROOT / "src").glob("*.py") if "# /// script" in p.read_text(encoding="utf-8"))


def test_there_are_scripts_with_inline_metadata():
    assert {p.name for p in SCRIPTS} >= {"cells.py", "register.py"}


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_inline_dependencies_are_pinned_and_match_the_test_requirements(script):
    reqs = _requirements()
    for dep in _inline_deps(script):
        m = PIN.match(dep)
        assert m, f"{script.name}: {dep!r} must be pinned with =="
        name, version = m.group(1).lower(), m.group(2)
        if name in reqs:
            assert reqs[name] == version, f"{script.name} pins {name}=={version} but tests use {reqs[name]}"


def test_ci_workflow_is_pinned_and_runs_tests_and_audit():
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    uses = re.findall(r"uses:\s*(\S+)", text)
    assert uses and all(re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", u) for u in uses), "pin actions by commit SHA"
    assert "latest" not in text
    assert re.search(r'version:\s*"[0-9.]+"', text), "pin the uv version"
    assert "--hypothesis-seed=" in text and "pip-audit==" in text and "pytest tests/" in text
