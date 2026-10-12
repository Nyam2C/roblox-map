# Units of Work

이 프로젝트는 배포 단위가 없는 로컬 도구 묶음이다. 유닛은 개발 순서의 한 덩어리이고, 각 유닛이 Construction의 Functional Design, NFR, Code Generation 루프를 한 번씩 돈다.

결정 근거: 유닛 계획 Q1=B(위험부터), Q2=A(도로·가로시설은 U1 수집과 U2 생성), Q3=A(첫 칸), Q4=B(`src/`), User Stories는 건너뜀.

## 진행 순서

```text
U1 데이터 기반 -> U3 거리뷰 캡처 -> U2 Studio 생성기 -> U4 판단·보정 -> U5 디테일 -> 나머지 칸 반복
```

- 첫 칸은 `8930e0af13bffff`(학교 중심이 속한 가장 큰 칸)이다. 유닛마다 이 칸으로 시험하고, U5까지 끝나면 나머지 칸 `8930e0af123ffff`, `8930e0af12bffff`에 같은 흐름(서비스 S1~S5)을 반복한다.
- 순서는 위험 기준이다. U3과 U2는 서로 의존하지 않는다. U3을 먼저 하는 이유는 거리뷰 캡처가 안 되면 일찍 알기 위해서다.

## 유닛 정의

### U1. 데이터 기반
- **컴포넌트**: C7 `db.py`, C1 `cells.py`(DB 전환, 도로·가로시설 수집 추가), C2 `register.py`
- **책임**: SQLite 스키마, OSM 이름·태그와 도로·가로시설 수집, V-World 건물통합정보 수집, V-World 건물에 OSM 이름·태그 붙이기
- **첫 작업**: V-World 건물통합정보를 페이지를 넘겨 받고 OSM 이름·태그를 붙이는 것이 첫 칸에서 되는지 확인한다(시험 호출은 2026-10-13에 성공)
- **완료 기준**: 첫 칸의 건물, 도로, 가로시설, 대장 매칭이 DB에 있고 같은 입력으로 다시 돌려도 같은 결과가 나온다
- **Functional Design 대상(순수 로직)**: `assign_cell`, `assemble`, 층수·높이 필드 정규화
- **전제**: 인증키는 `.env`(`VWORLD_KEY`)

### U3. 거리뷰 캡처
- **컴포넌트**: C3 `capture.py`
- **책임**: 칸별 캡처 지점 계획, 360도 캡처, 사진 저장과 DB 기록, 속도 제한, 차단 시 중단
- **첫 작업**: 거리뷰가 Playwright로 실제로 열리고 지점 사이를 이동하는지, 360도 캡처가 되는지 시험한다
- **완료 기준**: 첫 칸의 지점별 사진이 `captures/8930e0af13bffff/<지점ID>/`에 저장되고 `captures`에 기록된다. 차단되면 우회하지 않고 멈춘다
- **Functional Design 대상**: `plan_points`(지점 배치 규칙), 사진이 없는 건물 판정(D-4)
- **의존**: U1의 `buildings`

### U2. Studio 생성기
- **컴포넌트**: C6 `build_luau.py`, `studio/Builder.luau`
- **책임**: 좌표 → stud 변환, 외곽선 → 박스, 도로·가로시설 생성, `Workspace/Auto/<칸ID>`와 `Manual` 레이어, 기본 스폰 지점(학교 정문 앞 도로)
- **첫 작업**: 첫 칸을 1:1로 만들어 스케일(FR-10)을 확정한다
- **완료 기준**: 첫 칸의 건물 박스와 도로가 Studio에 서고 재생성해도 `Manual`은 그대로이며 스폰 지점에서 걸어 다닐 수 있다
- **Functional Design 대상**: `to_studs`, `outline_to_box`, 덩어리 분할
- **의존**: U1의 `buildings`, `streetscape`

### U4. 판단·보정
- **컴포넌트**: C4 `estimate.py`, C5 `overrides.py`
- **책임**: 층수·높이·외관 판단과 근거 기록, 보정 관리, 보정 내보내기·복구, 사용자와 Claude의 확인 루프(S4)
- **완료 기준**: 첫 칸 건물마다 층수·높이·외관과 근거가 있고, 사용자와 Claude가 Studio에서 같이 보고 현실 스케일에 맞는다고 확인했다. 보정은 `overrides/<칸ID>.json`에 있다
- **Functional Design 대상**: `effective_building`(보정 > 판단 > 대장 > 기본값), `height_from_floors`, 대장과 사진이 어긋날 때의 판정
- **의존**: U1의 `buildings`(V-World 층수·높이 포함), U3의 `captures`, U2(결과를 Studio에서 확인)

### U5. 디테일
- **컴포넌트**: C6 확장
- **책임**: 지붕 형태, 층 구분, 창문·문 패턴, 가상 간판, 재질과 텍스처, 학교 본관 수작업
- **완료 기준**: 첫 칸에서 건물이 사진과 비교해 알아볼 만하고(FR-7 주거 건물 포함) 3칸 규모에서 걸어 다녀도 끊기지 않는 수준까지 간다(NFR-1은 칸을 늘린 뒤 최종 확인)
- **Functional Design 대상**: 지붕·창문 배치 규칙
- **의존**: U2, U4

## 코드 배치 전략 (Q4=B)

```text
roblox-map/
  src/                       Python 스크립트 (uv run src/<이름>.py)
    cells.py  register.py  capture.py  estimate.py  overrides.py  build_luau.py  db.py
  studio/Builder.luau        Studio에 넣는 ModuleScript 소스
  tests/                     속성 기반 테스트와 예시 테스트
  overrides/<칸ID>.json      수동 보정 (git 포함)
  data/map.db                SQLite (git 제외)
  captures/<칸ID>/<지점ID>/  거리뷰 사진 (git 제외)
  .env  .env.example         인증키 (.env는 git 제외)
  aidlc-docs/                AI-DLC 문서
```

- `cells.py`는 `src/`로 옮긴다. 실행 명령이 `uv run src/cells.py ...`로 바뀌므로 U1 코드 생성 때 `CLAUDE.md`의 실행 예시를 같이 고친다.
- 각 스크립트는 PEP 723 인라인 의존성(버전 고정, NFR-7)으로 단독 실행된다. `db.py`는 같은 폴더의 공용 모듈이라 `import db`로 쓴다.
- `studio/`, `tests/`, `overrides/`, `data/`를 루트에 두는 것은 내 기본값이다. 바꾸고 싶으면 알려 달라.
- `.gitignore`에 `data/`를 U1에서 추가한다. `captures/`, `.env`는 이미 있다.

## Construction 루프에서 유닛마다 거치는 단계

| 유닛 | Functional Design | NFR Requirements | NFR Design | Code Generation | Build and Test |
|---|---|---|---|---|---|
| U1 | 실행 | 실행 (PBT 프레임워크, 의존성 고정, 검증 규칙을 여기서 한 번 정함) | 실행 (최소, 처음 한 번) | 실행 | 실행 |
| U3 | 실행 | 이어서 적용 (캡처 속도 수치만 추가) | 건너뜀 (U1에서 정함) | 실행 | 실행 |
| U2 | 실행 | 이어서 적용 (성능 기준) | 건너뜀 | 실행 | 실행 |
| U4 | 실행 | 이어서 적용 | 건너뜀 | 실행 | 실행 |
| U5 | 실행 | 이어서 적용 (3칸 성능) | 건너뜀 | 실행 | 실행 |

Infrastructure Design은 계획대로 건너뛴다. 이 표는 계획이고, 각 유닛에서 필요 없다고 판단되면 그때 줄인다.
