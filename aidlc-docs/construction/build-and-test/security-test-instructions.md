# Security Test Instructions

## 의존성 취약점
```bash
uv run --python 3.14 --with pip-audit==2.10.1 pip-audit -r tests/requirements.txt
```
CI가 푸시마다 같은 명령을 돌린다. 결과 (2026-10-13): **No known vulnerabilities found.**

## 비밀값
- 키가 코드나 문서에 없는지: `.env`의 값을 `git ls-files -co --exclude-standard`로 나온 모든 파일에서 검색하고 `git log -p`에서도 검색한다. 결과: 없음. (생성 중 `tests/test_common.py`에 실제 키가 들어간 것을 이 검색으로 찾아 커밋 전에 고쳤다.)
- 로그에 키가 새지 않는지: 실제 실행 로그(`data/logs/*.jsonl`)에서 검색. 결과: 없음. 단위 테스트(`test_common.py`)가 마스킹을 직접 검증한다.

## 입력 검증과 안전
- 명령줄 인자(칸 ID, 해상도, 좌표)와 외부 응답 검증은 `test_parse.py`가 확인한다(잘못된 요소는 버리고 건수를 센다, Overpass가 아닌 응답은 오류).
- SQL은 매개변수 바인딩만 쓴다. 테이블과 열 이름은 코드 안의 상수만 쓰고, 실패하면 롤백되는 것을 `test_db.py`가 확인한다.
- HTTPS만 허용하고(`http://`는 오류), JSON만 읽는다(`test_common.py`).
- CI 설정: 액션은 커밋 SHA로, `uv`와 `pip-audit`는 버전으로 고정됐는지 `test_versions.py`가 확인한다.

## 해당 없음
인증·인가, 웹 보안 헤더, 침투 시험은 해당 없다(로컬 단일 사용자 도구).
