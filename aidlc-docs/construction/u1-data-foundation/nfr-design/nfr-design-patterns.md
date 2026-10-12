# U1 데이터 기반 — NFR Design Patterns

근거: U1 NFR Requirements, 계획서 답변 Q1~Q9(A B A A B A A B B), 기본값 D-N1~D-N8.

## 1. 설계 패턴

| 패턴 | 적용 위치 | 근거 규칙 |
|---|---|---|
| **경계에서 검증** | 명령줄 인자(해상도, 좌표, 칸 ID), 외부 응답(Overpass, V-World), 설정 파일 값 | BR-7.4, NFR-SEC2 |
| **실패하면 멈춤(fail closed)** | 필수 원천 하나라도 실패하면 그 칸은 저장하지 않는다. 키가 없거나 형식이 틀리면 시작하지 않는다 | BR-7.1, NFR-SEC6 |
| **칸 단위 트랜잭션** | 한 칸의 원천 행 삭제와 삽입이 전부 성공하거나 전부 되돌려진다 | BR-6.1, BR-7.1 |
| **멱등한 교체** | 같은 입력으로 칸을 다시 돌리면 같은 상태가 된다. `overrides`, `estimates`는 건드리지 않는다 | BR-6.1, 6.2, P-8 |
| **고정 간격 재시도** | 429, 502, 504, 시간 초과일 때 10초, 30초, 60초 뒤에 재시도한다. 그 밖의 오류는 재시도하지 않는다. Overpass와 V-World에 같다 | BR-7.3 |
| **호출 간격 두기** | Overpass, V-World 호출 사이에 설정값(`config.toml`)만큼 쉰다 | NFR-P2 |
| **페이지 완전성 확인** | V-World는 `total`만큼 받았는지 확인하고 다르면 오류로 본다 | BR-7.2 |
| **비밀값 가리기** | 로그 필터가 환경변수에서 읽은 키 값을 `<KEY>`로 바꾼다. 요청 URL을 기록할 때 쿼리의 `key`를 가린다. 키는 읽을 때 앞뒤 공백을 지운다 | NFR-SEC1, BR-7.5 |
| **최상위 오류 처리** | 각 스크립트의 `main()`을 공용 실행기로 감싼다. 처리되지 않은 오류는 가린 메시지로 로그에 남기고 트랜잭션을 되돌린 뒤 0이 아닌 코드로 끝낸다. 사용자 인터럽트는 종료 코드 130 | NFR-SEC6 |
| **칸 ID 상관 키** | 모든 로그 줄과 `collection_runs` 행에 칸 ID가 있다. 요청 ID는 만들지 않는다(D-N4) | SECURITY-03 |

## 2. 로그 설계 (Q8=B, D-N5)

- 파일: `data/logs/<스크립트>-<YYYYMMDD>.jsonl`, 한 줄에 JSON 하나(git 제외). 자동 삭제하지 않는다.
- 필드: `ts`(ISO 8601), `level`, `script`, `cell_id`(없으면 `null`), `msg`, 필요하면 `extra`(건수, 소요 시간 등).
- 콘솔: 같은 필드로 `12:00:00 INFO [8930e0af13bffff] V-World 554건 수신` 같은 한 줄 요약을 출력한다.
- 가리는 대상: 인증키 값 전체, URL 쿼리의 `key=` 값. 내부 파일 경로는 오류 메시지에 넣지 않는다(스택 트레이스는 파일 로그에만 남기고 콘솔에는 요약만).

## 3. 설정 설계 (Q9=B, D-N8)

`config.toml`(루트, git 포함, 비밀값 없음). 읽을 때 형식과 범위를 검증한다. 값이 없으면 아래 기본값을 쓴다.

| 키 | 기본값 | 의미 |
|---|---|---|
| `h3_res` | 9 | H3 해상도 |
| `overlap_threshold` | 0.5 | 겹침 판정 기준 (BR-4.2) |
| `buffer_m` | 150 | 수집 버퍼(m) (BR-4.9) |
| `overpass_pause_s` | 1 | Overpass 호출 사이 대기(초) |
| `vworld_pause_s` | 0.5 | V-World 호출 사이 대기(초) |
| `vworld_page_size` | 1000 | V-World 한 번에 받는 건수(최대 1000) |
| `retry_waits_s` | [10, 30, 60] | 재시도 대기 |
| `db_path` | `data/map.db` | DB 파일 |
| `log_dir` | `data/logs` | 로그 폴더 |
| `backup_dir`, `backup_keep` | `data/backups`, 5 | 백업 폴더, 보관 개수 |

## 4. Resiliency 결정 (사용자 선택)

| 규칙 | 선택 | 설계 반영 |
|---|---|---|
| RESILIENCY-03 변경 관리 (Q1=A) | 지금 방식: Git 단위별 커밋과 AI-DLC 문서 승인 | 변경은 커밋 메시지와 승인 기록(`audit.md`)으로 남는다. 큰 Studio 작업 전에는 `.rbxl` 복사본을 만든다 |
| RESILIENCY-04 CI/CD (Q2=B) | GitHub Actions | 푸시와 PR마다 `pytest`와 `pip-audit`를 돌린다(D-N7, 아래 5장) |
| RESILIENCY-04 롤백 (Q3=A) | 코드는 Git 되돌리기, 데이터는 DB 삭제 후 S1 재실행과 `overrides` 불러오기 | 아래 6장 런북 R-1~R-3 |
| RESILIENCY-04 배포 방식 (Q4=A) | 직접(in-place), 별도 배포 단계 없음 | 워크로드 중요도가 낮음~중간(요구사항 워크로드 분류)이라 맞다 |
| RESILIENCY-11 DR 전략 | Backup & Restore (RTO/RPO 수 시간, 요구사항에서 정함) | 아래 6장 |
| RESILIENCY-12 백업 (Q5=B) | 칸 재수집 직전 자동 DB 백업, 최근 5개 보관(D-N6) | `db.backup()`이 한다. 복구 검증은 마일스톤 복구 연습 때 수동으로 한다 |
| RESILIENCY-14 복원력 테스트 (Q6=A) | 시나리오를 문서화하고 U4 완료 때 한 번 실제로 해 본다 | 아래 6장의 연습 계획 |
| RESILIENCY-15 사고 대응 (Q7=A) | 별도 절차 없이 콘솔, 로그, `collection_runs`를 보고 그때그때 처리 | 실패 이유가 `collection_runs.error`와 JSON 로그에 남는다. 원인 추적은 이 둘과 Git 이력으로 한다 |

## 5. CI 설계 (Q2=B, D-N7)

`.github/workflows/ci.yml`을 코드 생성에서 만든다.
- **트리거**: `main`으로의 푸시와 PR.
- **단계**: 저장소 체크아웃 → `uv` 설치 → `uv run --with-requirements tests/requirements.txt pytest tests/` → `pip-audit -r tests/requirements.txt`.
- **PBT 시드(PBT-08)**: Hypothesis 시드를 실행 번호로 고정해 로그에 찍는다. 실패하면 Hypothesis가 최소 반례와 재현 방법을 출력한다.
- **비밀값 없음**: 테스트는 `tests/fixtures/`에 저장해 둔 응답 샘플(Overpass, V-World)만 쓴다. CI에 인증키를 넣지 않는다.
- **고정**: 쓰는 액션과 `uv` 버전은 고정하고 `latest`를 쓰지 않는다(SECURITY-10). 고정 방법(커밋 SHA 또는 버전 태그)은 코드 생성에서 확인한다.
- **감사 범위**: `pip-audit`는 `tests/requirements.txt`를 본다. 스크립트 인라인 의존성과 같은 버전이라는 것을 확인하는 테스트(N-8)가 이 감사가 의미를 갖게 한다.

## 6. 복구 런북 (Backup & Restore, RESILIENCY-11, 13, 14)

| # | 상황 | 절차 | 확인 |
|---|---|---|---|
| R-1 | DB 파일이 사라졌거나 깨졌다 | ① 깨진 파일을 옮겨 둔다 ② 새 DB로 S1(`cells.py` → `register.py`)을 모든 칸에 돌린다 ③ `overrides/<칸ID>.json`을 불러온다 | 칸마다 건물 수가 이전 실행 기록과 같고 `orphans`가 비어 있거나 설명된다 |
| R-2 | 잘못된 코드를 넣었다 | `git revert` 또는 이전 커밋으로 되돌린다. 필요하면 영향받은 칸의 S1을 다시 돌린다 | 테스트 통과, 같은 칸을 다시 돌려 결과가 이전과 같다 |
| R-3 | 보정값을 잃었다 | `overrides/<칸ID>.json`(git에 있다)에서 불러온다 | 불러온 개수가 파일의 항목 수와 같다 |
| R-4 | 재수집으로 데이터가 이상해졌다 | `data/backups/`의 직전 백업을 `data/map.db`로 복사하거나, 원인을 고친 뒤 칸을 다시 수집한다 | 건물 수와 샘플 몇 건을 직전 실행 기록과 비교한다 |
| R-5 | V-World 키가 만료됐거나 서비스가 안 된다 | 키 상태를 확인하고(만료 2027-04-13, 연장 가능) 재시도한다. 그 칸은 저장되지 않았으므로 이전 데이터는 그대로다 | 시험 호출이 `OK`를 돌려준다 |
| R-6 | Overpass가 계속 실패한다 | 시간을 두고 다시 돌린다. 그 칸은 이전 상태로 남는다 | 재시도 후 성공하거나 `collection_runs`에 실패 이유가 남는다 |

- **통신 계획**: 사용자 한 명이라 별도 통신 계획이 필요 없다(RESILIENCY-13의 해당 항목은 N/A).
- **복구 연습(Q6=A)**: U4 완료 시점에 R-1과 R-3을 실제로 한다. DB 파일을 옮겨 두고 새 DB에서 S1을 돌린 뒤 `overrides`를 불러와, 건물 수와 보정 항목 수가 같은지 확인하고 결과를 기록한다.
- **교차 지역 복제**: 해당 없음. 로컬 도구이고 재생성 가능한 데이터다. 재생성이 안 되는 `overrides`는 GitHub에 올라가 로컬 밖에도 사본이 있다.
- **백업 암호화**: 백업은 공개 데이터의 복사본이라 저장 시 암호화는 별도 구성하지 않는다(NFR Requirements의 SECURITY-01 예외와 같은 근거).

## 7. 보안 패턴 요약

| 규칙 | 설계 |
|---|---|
| SECURITY-03 로깅 | JSON 로그에 시각, 수준, 스크립트, 칸 ID, 메시지. 비밀값 필터. 중앙 로그 서비스는 해당 없음(예외 유지) |
| SECURITY-05 입력 검증 | 인자와 응답과 설정을 경계에서 검증, 매개변수 바인딩 |
| SECURITY-09, 15 | 최상위 오류 처리, 가린 메시지, 트랜잭션 롤백 |
| SECURITY-10 공급망 | 정확한 버전 고정, CI에서 `pip-audit` 자동 실행, 불필요한 의존성 없음 |
| SECURITY-12 | 하드코딩된 키 없음, `.env`는 git 제외 |
| SECURITY-13 | JSON만 읽는다. 수정 이력은 `collection_runs`와 로그 |

## 확장 규칙 준수 요약

### Security Baseline
SECURITY-01(저장 시, 예외), SECURITY-03(중앙 로그, 예외)는 NFR Requirements의 문서화된 예외 그대로다. SECURITY-02, 04, 06, 07, 08, 14는 N/A, 나머지는 위 7장대로 준수한다. 차단 항목은 없다.

### Resiliency Baseline

| 규칙 | 상태 | 근거 |
|---|---|---|
| RESILIENCY-01, 02 | 준수 | 워크로드 분류, RTO/RPO 수 시간 |
| RESILIENCY-03 변경 관리 | 준수 | 사용자 선택(Q1=A): Git 단위별 커밋과 AI-DLC 승인 |
| RESILIENCY-04 CI/CD, 롤백, 배포 방식 | 준수 | 사용자 선택(Q2=B, Q3=A, Q4=A) |
| RESILIENCY-05~07 모니터링, 상태 점검 | N/A | 배포된 서비스 없음. 실행 기록과 로그로 갈음 |
| RESILIENCY-08~10 고가용성, 자동 확장, 의존성 격리 | N/A | 단일 사용자 로컬 도구 |
| RESILIENCY-11 DR 전략 | 준수 | Backup & Restore, 런북 R-1~R-6 |
| RESILIENCY-12 백업 | 준수 (예외 1건) | 자동 백업, 보관 5개, 수동 복구 검증. 교차 지역 복제는 N/A(위 사유). 백업 암호화는 SECURITY-01 예외와 같은 근거 |
| RESILIENCY-13 복구 절차 | 준수 | 런북, 복구 후 확인. 통신 계획은 N/A(사용자 한 명) |
| RESILIENCY-14 복원력 테스트 | 준수 | 시나리오 문서화, U4 완료 때 R-1과 R-3 실습 |
| RESILIENCY-15 사고 대응 | **사용자 선택에 따른 예외, 확인 필요** | 사용자가 별도 사고 대응 절차 없이 로그와 실행 기록으로 처리하기로 선택(Q7=A). 규칙의 사후 분석(COE) 항목은 `collection_runs.error`, JSON 로그, Git 이력이 대신한다. 더 엄격하게 하려면 Q7의 B(가벼운 사고 기록 파일)로 바꿀 수 있다 |

### Property-Based Testing
PBT-08의 CI 연동은 GitHub Actions(D-N7)로 충족한다. PBT-07(생성기), PBT-10은 코드 생성과 Build and Test에서 확인한다.
