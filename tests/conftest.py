import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, settings

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# 실패하면 Hypothesis가 최소 반례와 재현용 blob을 출력한다(PBT-08).
# CI는 `pytest --hypothesis-seed=<실행 번호>`로 시드를 고정하고 로그에 남긴다.
settings.register_profile(
    "default",
    deadline=None,
    print_blob=True,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("default")


def one_region(tmp_path, *cells):
    """Config keys for a regions folder under tmp_path whose one region `r` holds these cells (U7 B).
    A cell's files then go to tmp_path/regions/r/cells/<cell>/<kind>.json."""
    folder = tmp_path / "regions" / "r"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "region.toml").write_text(f"cells = {list(cells)!r}\n".replace("'", '"'), encoding="utf-8")
    return {"regions_dir": str(tmp_path / "regions")}


@pytest.fixture(autouse=True)
def _no_repo_regions(tmp_path, monkeypatch):
    """A config built from DEFAULTS never writes into the repository's regions/ (load_config() still reads config.toml's)."""
    import common
    monkeypatch.setitem(common.DEFAULTS, "regions_dir", str(tmp_path / "no-regions"))
