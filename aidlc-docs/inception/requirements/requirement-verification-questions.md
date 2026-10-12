# Requirements 확인 질문 — roblox-map

> **의도 요약**: 실제 동네를 Roblox 롤플레이/타운 맵으로 만든다. 구역은 H3 칸으로 나누고, 칸 하나씩 OSM 데이터로 뼈대를 만든 뒤 외관을 다듬는 과정을 반복한다. 구현은 Roblox Studio MCP로 한다.
> **분석**: 신규 프로젝트(기존 코드는 50줄 프로토타입), 요청이 아직 열려 있음(Vague→Incomplete), 범위 Multiple Components, 복잡도 Moderate. 깊이는 **Standard**.
>
> **답변 방법**: `[Answer]:` 뒤에 보기 문자를 적어 주세요. 맞는 보기가 없으면 마지막 `X`를 고르고 직접 적어 주세요. 일부 질문은 문자 뒤에 보충 내용을 같은 줄에 적도록 안내했어요. 끝나면 "완료"라고 알려 주세요.

---

## 파트 A — 진행 방식과 범위

## Question 1
기존 `cells.py`(50줄)를 분석하는 **리버스 엔지니어링 단계**를 어떻게 할까요? 규칙상 기존 코드가 있으면 이 단계가 기본으로 실행되지만, 코드가 작고 동작은 `CLAUDE.md`에 이미 기록돼 있습니다.

A) 건너뜀. 요구사항 문서의 "기존 자산" 항목에 한 단락으로만 기록 (권장)

B) 최소 분량으로 문서 1개만 작성

C) 규칙대로 전체 산출물(아키텍처, 컴포넌트, 의존성 등)을 작성

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 2
이 맵의 **최종 용도**는 무엇인가요?

A) 개인 취미와 포트폴리오. 비공개이거나 친구끼리만 사용

B) Roblox에 무료 경험으로 공개 발행

C) 공개 발행 + Robux 수익화

D) 아직 모름. 먼저 비공개로 만들고 나중에 결정

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 3
**만들 동네**가 정해졌나요?

A) 정했다. 이 문자 뒤에 같은 줄로 장소명이나 위경도 4점을 적어 주세요

B) 후보는 있지만 아직 못 정했다. 후보를 같은 줄에 적어 주세요

C) 정하지 못했다. 고르는 기준을 제안해 주세요

X) Other (please describe after [Answer]: tag below)

[Answer]: A 일단은 부천 심원고등학교

## Question 4
**1차 목표 규모**는 어디까지인가요? (H3 해상도 9 기준 칸 하나는 변 약 170m)

A) 칸 1개. 먼저 한 칸을 Studio에서 걸어 다닐 수 있게 만든 뒤 확장 (권장)

B) 칸 3~7개. 블록 몇 개 정도

C) 동네 전체(수십 칸)를 처음부터 목표로 함

D) 미정. 칸 1개로 시험해 보고 결정

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 5
**건물 충실도**는 어디까지 목표인가요? (아래 단계는 위에서 아래로 누적됩니다)

A) 외곽선을 위로 올린 박스와 색상만. 실루엣 위주

B) A + 지붕 형태, 층 구분, 창문과 문 패턴

C) B + 간판 텍스트, 대표 건물 수작업 제작

D) C + 일부 건물 내부 입장 가능

X) Other (please describe after [Answer]: tag below)

[Answer]: C + 텍스처까지 현실감 있게

## Question 6
**스케일**은 어떻게 할까요? (Roblox에서 1m는 약 3.6 stud입니다. 실제 크기로 만들면 걷는 시간이 현실과 같아집니다)

A) 실제 크기 1:1

B) 축소. 이동이 쾌적하도록 거리를 줄임 (비율은 설계 단계에서 결정)

C) 구역별로 다르게. 도로 폭과 건물은 키우고 거리는 압축

D) 미정. 칸 1개를 1:1로 만들어 보고 결정

X) Other (please describe after [Answer]: tag below)

[Answer]: D

## Question 7
**지형과 도로 등 건물 외의 요소**는 1차에 어디까지 넣나요? (아래 단계는 누적됩니다)

A) 건물만. 바닥은 평평하게

B) A + 도로와 인도(OSM 도로 데이터)

C) B + 나무, 가로등, 벤치, 횡단보도 같은 가로 시설

D) C + 실제 고저차와 하천, 공원 녹지

X) Other (please describe after [Answer]: tag below)

[Answer]: C

## Question 8
**롤플레이 기능**은 1차(v1)에서 어디까지인가요?

A) 맵만. 걸어 다니며 구경

B) A + 문 열기, 집과 가게 소유, 스폰 위치

C) B + 직업, 돈, 차량 등 본격 롤플레이

D) 맵을 완성한 뒤 별도 단계에서 결정

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## 파트 B — 데이터, 실제 장소, 법적·정책 이슈

## Question 9
**실제 상호와 간판**은 어떻게 표현하나요? (상표와 Roblox 정책 이슈가 있을 수 있습니다)

A) 실제 상호와 간판을 그대로 사용

B) 모두 가상의 이름으로 바꿔서 사용

C) 대표 랜드마크만 실제 이름, 나머지는 가상 이름

D) 간판 텍스트 없이 만든다

X) Other (please describe after [Answer]: tag below)

[Answer]: B

## Question 10
실제 사람이 사는 **주거 건물**은 어떻게 다루나요?

A) 다른 건물과 똑같이 외형을 재현

B) 주거 건물은 일반화한 외형(템플릿이나 무작위)으로 대체

C) 외형은 재현하되 번지 같은 식별 정보와 세부 디테일은 제외

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 11
**네이버 거리뷰**를 어떻게 활용하나요? 네이버지도 약관이 자동 수집을 막고 있을 가능성이 있고, 저는 아직 약관을 확인하지 않았습니다. 이미지를 텍스처로 복사하는 용도는 제외합니다.

A) 제가 브라우저로 필요한 건물만 직접 열어 외관(색, 지붕, 층수)을 참고. 대량 수집은 하지 않음

B) 사용자가 직접 캡처하거나 사진을 제공하고, 저는 그 사진만 참고 (권장)

C) 거리뷰는 쓰지 않고 OSM 데이터와 공개 사진만 사용

D) 약관을 먼저 확인한 뒤 결정

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 12
OSM에 **높이 정보가 없는 건물**(지금 테스트 기준 약 80%)은 어떻게 처리하나요?

A) 고정 기본 높이를 사용 (예: 3층, 약 9m)

B) 건물 용도와 면적으로 추정 (소형 단독은 2층, 상업은 4층 등 규칙 기반)

C) 국토부 V-World 같은 공공 데이터로 먼저 보완하고, 남는 건물에 B를 적용

D) 거리뷰나 사진으로 건물마다 수작업 확인 (소규모 구역에만 해당)

X) Other (please describe after [Answer]: tag below)

[Answer]: 거리뷰에서 자동차랑 거리 비율 봐서 높이 계산 ( 다른것들도 )

---

## 파트 C — 품질, 성능, 운영 방식

## Question 13
**대상 기기**는 무엇인가요? (모바일 포함이면 파트 수와 스트리밍 제한이 훨씬 엄격해집니다)

A) PC 위주

B) PC와 모바일 모두. 저사양 폰에서도 끊기지 않게

C) 모바일 중심

D) 미정

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 14
**위치 정확도**는 어느 정도여야 하나요? (OSM 데이터 자체의 오차가 있습니다)

A) 대략적으로 맞으면 됨. 건물 수와 배치가 비슷한 정도

B) 건물 외곽선이 실제와 눈에 띄게 어긋나지 않게 (수 m 이내)

C) 정밀하게. 1m 내외

X) Other (please describe after [Answer]: tag below)

[Answer]: B

## Question 15
자동 생성한 건물을 **수작업으로 다듬은 뒤 재생성**하면 충돌이 생깁니다. 정책을 정해 주세요.

A) 자동 생성 레이어와 수작업 레이어를 분리. 재생성해도 수작업은 보존 (권장)

B) 생성은 1회성. 이후에는 Studio 수동 편집 결과가 원본

C) 칸 전체를 재생성 가능하게 두고, 수작업은 버려도 됨

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## 파트 D — 확장 규칙 선택 (AI-DLC 필수 질문)

## Question 16
**보안 확장 규칙**을 이 프로젝트에 적용할까요?

A) 예. 모든 SECURITY 규칙을 필수 제약으로 적용 (프로덕션급 애플리케이션에 권장)

B) 아니오. 모든 SECURITY 규칙을 건너뜀 (PoC, 프로토타입, 실험 프로젝트에 적합)

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 17
**복원력(Resiliency) 기본 규칙**을 적용할까요? AWS Well-Architected의 신뢰성 원칙에서 가져온 설계 시점의 권고 사항이며, 적용해도 프로덕션 준비 완료를 보장하지는 않습니다.

A) 예. 지침으로 적용 (비즈니스 핵심 워크로드에 권장)

B) 아니오. 건너뜀 (PoC, 프로토타입, 실험 프로젝트에 적합)

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 18
**속성 기반 테스트(PBT) 규칙**을 적용할까요?

A) 예. 모든 PBT 규칙을 필수 제약으로 적용 (비즈니스 로직, 데이터 변환, 직렬화, 상태 있는 컴포넌트가 있는 프로젝트에 권장)

B) 부분 적용. 순수 함수와 직렬화 왕복 테스트에만 적용 (알고리즘 복잡도가 낮은 프로젝트에 적합)

C) 아니오. 모두 건너뜀 (단순 CRUD, UI 전용, 로직이 거의 없는 얇은 통합 계층에 적합)

X) Other (please describe after [Answer]: tag below)

[Answer]: A
