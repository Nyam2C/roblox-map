# U1 데이터 기반 — NFR Design Plan

대상: C7 `db.py`, C1 `cells.py`, C2 `register.py`, 공용 `src/geo.py`. 실행 환경은 사용자 Mac의 로컬 스크립트와 SQLite다.
이 단계는 NFR 요구를 패턴과 논리 컴포넌트로 바꾼다. 그리고 Resiliency 확장 규칙이 **사용자가 직접 정하게 한 결정**(변경 관리, CI/CD, 롤백, 배포 방식, 복원력 테스트, 사고 대응, 백업)을 여기서 묻는다. 내가 대신 정하지 않는다.

각 질문의 `[Answer]:` 뒤에 알파벳을 적어 줘. 맞는 보기가 없으면 X를 고르고 설명을 적는다.

## 계획 (체크리스트)

- [x] U1 NFR Requirements 읽기, Resiliency 결정 항목 확인
- [x] 아래 질문 9개에 답 받기 (사용자가 채팅으로 답했고 이 파일에 그대로 옮겨 적음)
- [x] 답변 분석: 모순 없음. 모호한 부분 3건(콘솔 로그 형식, 백업 시점과 방법, CI 세부)은 질문 대신 기본값 D-N5~D-N7로 메웠다(아래 문서 참고)
- [x] `construction/u1-data-foundation/nfr-design/nfr-design-patterns.md` 생성
- [x] `construction/u1-data-foundation/nfr-design/logical-components.md` 생성
- [x] 확장 규칙 준수 요약 작성 (Security, Resiliency, PBT)

## 범주 검토 (규칙상 모든 범주를 평가)

| 범주 | 적용 여부 | 이유 |
|---|---|---|
| 복원 패턴 (재시도, 장애 복구) | 질문 1~7 | 재시도 규칙은 이미 정했다(BR-7.3). Resiliency 규칙이 요구하는 결정을 묻는다 |
| 확장 패턴 | 해당 없음 | 심원고 3칸, 칸 단위 독립 처리. 큐, 캐시, 분산이 필요 없다 |
| 성능 패턴 | 해당 없음 | 쌍별 겹침 비교와 페이지 넘기기로 충분하다(NFR-P3). 최적화 목표 없음 |
| 보안 패턴 | 이미 정함 | 키 환경변수, 매개변수 바인딩, 응답 검증, 최상위 오류 처리(NFR-SEC1~7). 로그 형식만 질문 8에서 정한다 |
| 논리 컴포넌트 | 질문 8, 9 + 기본값 | 큐, 캐시, 회로 차단기는 필요 없다. 공용 도우미 모듈과 설정 위치를 정한다 |

## 설계 기본값 (질문은 안 하지만 틀리면 말해 줘)

| # | 내용 | 이유 |
|---|---|---|
| D-N1 | 설계 패턴: 경계에서 검증(입력과 외부 응답), 실패하면 멈춤(fail closed), 칸 단위 전부 성공해야 저장(트랜잭션), 재실행해도 같은 결과(멱등한 교체), 고정 간격 재시도(10초, 30초, 60초), 로그에서 비밀값 가리기 | NFR 요구와 Business Rules를 패턴 이름으로 묶는 것 |
| D-N2 | 공용 도우미 모듈 `src/common.py` 하나를 둔다. 로깅 설정과 비밀값 가리기, 환경변수 읽기(앞뒤 공백 제거), 재시도가 있는 HTTP GET(`urllib`)을 담는다. C1, C2, 이후 U3도 쓴다 | `cells.py`와 `register.py`가 같은 재시도와 로깅을 쓰는데 컴포넌트끼리 직접 호출하지 않기 위해서. 순수 계산은 `geo.py`, 입출력 도우미는 `common.py`로 나눈다 |
| D-N3 | 큐, 캐시, 회로 차단기, 별도 서비스는 만들지 않는다 | 필요 없다(규모, 단일 사용자) |
| D-N4 | 실행 기록(`collection_runs`)과 로그 파일의 칸 ID가 같은 상관 키 역할을 한다. 요청 ID는 만들지 않는다 | SECURITY-03의 상관 ID를 로컬 도구 수준으로 충족 |

## Question 1 — 변경 관리 (RESILIENCY-03)
이 도구와 맵의 변경을 어떻게 관리할까?

A) 지금 하는 방식을 변경 관리로 본다: 변경은 Git 커밋(단위별)과 AI-DLC 문서 승인으로 기록하고, 큰 변경 전에는 `.rbxl` 복사본을 만든다

B) 가벼운 절차를 제안받는다: 변경 기록(무엇을 왜 바꿨나), 승인, 롤백 메모를 남기는 형식

C) 개인 도구라 정식 변경 관리를 면제한다. 면제 사유를 문서에 적는다

X) Other (please describe after [Answer]: tag below)

참고: A가 지금 이미 하고 있는 방식이다. 별도 절차는 추가하지 않는다.

[Answer]: A

## Question 2 — CI/CD (RESILIENCY-04)
테스트와 점검을 어떻게 자동으로 돌릴까?

A) 파이프라인 없이 로컬에서 수동으로 돌린다. 테스트(`pytest`)와 `pip-audit`는 문서화된 명령으로 실행한다

B) GitHub Actions를 제안받는다: 푸시할 때마다 `pytest`(Hypothesis 시드 출력)와 `pip-audit`를 실행한다

X) Other (please describe after [Answer]: tag below)

참고: 저장소가 GitHub에 있어서 B가 가능하다. PBT 확장(PBT-08)은 속성 기반 테스트를 CI에 넣거나, 넣지 않으면 정당한 사유를 문서에 남기라고 요구한다. A를 고르면 그 사유를 문서에 적는다(로컬 단일 사용자 도구).

[Answer]: B

## Question 3 — 롤백 방식 (RESILIENCY-04)
스크립트나 데이터를 잘못 바꿨을 때 어떻게 되돌릴까?

A) 코드는 Git에서 이전 커밋으로 되돌리고, 데이터는 DB 파일을 지우고 S1(수집과 조립)을 다시 돌린 뒤 `overrides`를 불러온다

B) A에 더해, 큰 작업 전에 `data/map.db`를 자동으로 복사해 둔다(`data/backups/`, git 제외). 필요하면 그 복사본으로 되돌린다

X) Other (please describe after [Answer]: tag below)

참고: 이 유닛의 데이터는 원천에서 다시 받을 수 있어서 A로 충분하다. 값을 잃을 수 있는 건 U4의 `overrides`와 U3의 사진인데, 이 둘은 U4, U3의 설계에서 다룬다.

[Answer]: A

## Question 4 — 배포 방식 (RESILIENCY-04)
이 도구는 서버에 배포하지 않고 로컬에서 실행한다. 변경을 반영하는 방식을 어떻게 볼까?

A) 직접(in-place): 코드를 고친 뒤 로컬에서 바로 실행한다. 별도의 배포 단계가 없다

X) Other (please describe after [Answer]: tag below)

참고: 규칙상 사용자가 명시적으로 선택해야 해서 물었다. 배포할 환경이 없으니 이 보기뿐이다.

[Answer]: A

## Question 5 — 백업 (RESILIENCY-12)
DB 파일의 백업은 어떻게 할까?

A) 별도 백업을 하지 않는다. U1 데이터는 원천에서 재생성할 수 있고, 재생성 안 되는 `overrides`는 텍스트로 내보내 git에 올린다(설계 Q8=B)

B) 큰 작업 전에 DB 파일을 날짜별로 복사한다(`data/backups/`, git 제외). 최근 몇 개만 남긴다

X) Other (please describe after [Answer]: tag below)

참고: Backup & Restore, RTO/RPO 수 시간 목표에 A로도 맞는다. 백업 검증(RESILIENCY-12)은 "새 DB로 S1을 돌리고 `overrides`를 불러와 같은 결과가 나오는지 확인"하는 수동 절차로 정하는 게 기본이다.

[Answer]: B

## Question 6 — 복원력 테스트 (RESILIENCY-14)
복구 절차를 어떻게 검증할까?

A) 복구 시나리오(DB를 지우고 S1 재실행, `overrides` 복구)를 문서에 적고, 마일스톤(U4 완료 때)에 한 번 실제로 해 본다

B) 시나리오만 문서에 적어 두고 실행은 Operations 단계로 미룬다

X) Other (please describe after [Answer]: tag below)

참고: 복구 시나리오는 이 프로젝트에서 실제로 해 보기 쉽다(DB 파일을 지우고 다시 돌리면 된다). 규칙은 시나리오 문서화를 요구한다.

[Answer]: A

## Question 7 — 사고 대응 (RESILIENCY-15)
실행이 실패했을 때(API 오류, 차단, 데이터 이상) 어떻게 대응하고 기록할까?

A) 별도 절차 없이 콘솔과 로그, `collection_runs`를 보고 그때그때 처리한다

B) 가벼운 사고 기록을 남긴다: 원인, 조치, 재발 방지를 `aidlc-docs/` 안의 한 파일에 한 줄씩 추가한다

X) Other (please describe after [Answer]: tag below)

참고: A는 지금까지의 방식이다. B는 같은 문제를 반복하지 않게 해 주고 비용이 작다(파일 하나).

[Answer]: A

## Question 8 — 로그 형식
로그 한 줄의 형식을 어떻게 할까? (내용은 시각, 수준, 칸 ID, 메시지이고 비밀값은 가린다.)

A) 사람이 읽는 한 줄 텍스트(`2026-10-13 12:00:00 INFO [칸ID] 메시지`)

B) JSON 한 줄(기계가 읽고 검색하기 쉽다)

X) Other (please describe after [Answer]: tag below)

참고: 로컬에서 사람이 읽을 일이 많으면 A, 로그를 스크립트로 분석할 계획이 있으면 B다. 규칙(SECURITY-03)은 구조화된 로그를 요구하는데, A도 필드가 고정된 형식이면 충족한다고 본다.

[Answer]: B

## Question 9 — 설정값 위치
겹침 기준(0.5), 버퍼(150 m), 호출 간격, 페이지 크기 같은 조정값을 어디에 둘까?

A) 각 스크립트 상단의 상수로 둔다

B) 루트의 설정 파일 하나(`config.toml`)로 모은다

X) Other (please describe after [Answer]: tag below)

참고: 값이 몇 개 안 되고 바꿀 일이 드물면 A가 단순하다. 여러 스크립트가 같은 값(버퍼 등)을 써서 어긋날 위험이 있으면 B가 낫다. 비밀값은 어느 쪽이든 `.env`에만 둔다.

[Answer]: B

---

## 답변 분석 후 추가한 기본값 (질문은 안 하지만 틀리면 말해 줘)

| # | 내용 | 이유 |
|---|---|---|
| D-N5 | 로그 파일(`data/logs/<스크립트>-<날짜>.jsonl`)은 JSON 한 줄이다(Q8=B). 콘솔에는 같은 내용을 사람이 읽는 한 줄 요약으로 출력한다 | Q8 답은 형식 하나만 정했는데, NFR-U1(콘솔에서 진행 상황이 한눈에 보일 것)과 JSON 콘솔 출력이 부딪힌다 |
| D-N6 | 백업(Q5=B)은 DB를 바꾸는 실행(칸 재수집) 직전에 자동으로 한다. `sqlite3`의 백업 기능으로 `data/backups/map-<날짜시각>.db`에 복사하고 최근 5개만 남긴다 | "큰 작업 전"이 모호했다. 파일 복사는 쓰는 중에 깨질 수 있어 백업 기능을 쓴다 |
| D-N7 | CI(Q2=B)는 GitHub Actions로 푸시와 PR마다 `pytest`(Hypothesis 시드를 실행 번호로 고정해 로그에 남김)와 `pip-audit`를 돌린다. 인증키가 필요 없도록 테스트는 저장해 둔 응답 샘플만 쓴다. 쓰는 액션과 `uv` 버전은 고정한다(고정 방법은 코드 생성에서 확인) | Q2 답에 세부가 없었다. 공급망 규칙(SECURITY-10)과 PBT-08을 CI에서 충족하려는 것 |
| D-N8 | 설정 파일(Q9=B) `config.toml`은 표준 `tomllib`으로 읽는다. Python 3.11 이상이 필요하다. 비밀값은 넣지 않고 git에 올린다 | 별도 라이브러리 없이 읽으려는 것 |

