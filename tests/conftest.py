import sys
from pathlib import Path

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
