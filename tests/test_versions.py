"""Dependency pins: scripts and tests use the same exact versions, and CI is pinned (N-8, SECURITY-10)."""
from __future__ import annotations

import ast
import os
import re
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([0-9][A-Za-z0-9_.+!-]*)$")


def _inline_meta(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"(?ms)^# /// script\n(.*?)^# ///$", text)
    assert m, f"{path.name} has no inline script metadata"
    body = "\n".join(line[2:] if line.startswith("# ") else line[1:] for line in m.group(1).splitlines())
    return tomllib.loads(body)


def _inline_deps(path: Path) -> list[str]:
    return _inline_meta(path)["dependencies"]


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
    assert {p.name for p in SCRIPTS} >= {"cells.py", "register.py", "capture.py", "build_luau.py", "estimate.py", "overrides.py", "details.py"}


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
    assert "capture.py --selftest" in text and "uv export --script src/capture.py" in text  # U3 checks (N-U3-9, N-U3-10)
    assert text.count("pip-audit -r") == 2  # test requirements and capture.py's set


# --- U3: capture.py's lean install of streetlevel (Q1=A, Q2=A) ---------------------------------------------

CAPTURE = ROOT / "src" / "capture.py"
HEAVY = {"torch", "pyequilib", "pyexiv2", "pytest", "pytest-asyncio", "cython", "pycryptodome", "pyfrpc"}


def _name(pin: str) -> str:
    return PIN.match(pin).group(1).lower().replace("_", "-")


def test_capture_pins_every_package_and_leaves_out_the_heavy_ones():
    meta = _inline_meta(CAPTURE)
    deps = meta["dependencies"]
    assert all(PIN.match(d) for d in deps), "every capture.py dependency must be pinned with =="
    assert {"streetlevel", "h3", "numpy", "pillow"} <= {_name(d) for d in deps}
    assert not HEAVY & {_name(d) for d in deps}
    assert set(meta["tool"]["uv"]["exclude-dependencies"]) == HEAVY
    assert meta["requires-python"] == ">=3.13"  # numpy 2.5.4 needs 3.12+, and 3.12 pulls an unpinned typing-extensions


def test_capture_pins_cover_the_whole_resolved_set():
    """CI exports the resolved set (`uv export --script`); a package that is not pinned would show up here."""
    resolved_file = os.environ.get("CAPTURE_RESOLVED")
    if not resolved_file:
        pytest.skip("CAPTURE_RESOLVED is set only in CI (needs `uv export --script src/capture.py`)")
    resolved = {_name(m.group(0)): m.group(0).split("==")[1] for line in Path(resolved_file).read_text().splitlines()
                if (m := re.match(r"^[A-Za-z0-9_.-]+==[^\s;]+", line))}
    pinned = {_name(d): d.split("==")[1] for d in _inline_deps(CAPTURE)}
    assert resolved == pinned


# --- U2: the Studio module never runs received text as code (SEC2) ---------------------------------------------

def test_builder_luau_has_no_way_to_run_text_as_code_or_reach_the_network():
    source = (ROOT / "studio" / "ServerStorage" / "MapBuilder.luau").read_text(encoding="utf-8")
    code = re.sub(r"(?s)--\[\[.*?\]\]", "", source)  # the header comment names what is not used
    code = re.sub(r"--[^\n]*", "", code)
    for forbidden in ("loadstring", "HttpService", "RequestAsync", "GetAsync", "PostAsync", "getfenv", "setfenv"):
        assert forbidden not in code, forbidden
    assert code.count(":Destroy()") == 1 and "old:Destroy()" in code  # the only thing it ever destroys is the old Auto/<cell id>


# --- U4: estimate.py stays light, overrides.py needs nothing from outside (N-U4-1) --------------------------------

def _imports(path: Path) -> set[str]:
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.add(node.module.split(".")[0])
    return out


LOCAL = {p.stem for p in (ROOT / "src").glob("*.py")}


def test_estimate_pins_only_pillow_h3_and_shapely_and_does_not_pull_in_numpy_through_projection():
    meta = _inline_meta(ROOT / "src" / "estimate.py")
    assert {_name(d) for d in meta["dependencies"]} == {"pillow", "h3", "shapely"} and all(PIN.match(d) for d in meta["dependencies"])
    assert "projection" not in _imports(ROOT / "src" / "estimate.py") | _imports(ROOT / "src" / "review.py")


def test_overrides_runs_on_the_standard_library_and_our_own_modules_alone():
    assert _inline_meta(ROOT / "src" / "overrides.py")["dependencies"] == []
    for name in ("overrides", "db", "common", "judgement"):  # everything overrides.py imports, transitively
        outside = _imports(ROOT / "src" / f"{name}.py") - set(sys.stdlib_module_names) - LOCAL
        assert not outside, f"{name}.py imports {sorted(outside)}"


# --- U5: details.py needs nothing from outside, details_rules.py is standard library only (U5-NFR-SEC6) ------------------

def test_details_runs_on_the_standard_library_and_our_own_modules_alone():
    assert _inline_meta(ROOT / "src" / "details.py")["dependencies"] == []
    for name in ("details", "db", "common", "judgement", "details_rules"):
        outside = _imports(ROOT / "src" / f"{name}.py") - set(sys.stdlib_module_names) - LOCAL
        assert not outside, f"{name}.py imports {sorted(outside)}"
    assert _imports(ROOT / "src" / "details_rules.py") <= set(sys.stdlib_module_names) | {"__future__"}
