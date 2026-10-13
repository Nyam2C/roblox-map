# U5 확장: 간판 이미지 (Functional Design + NFR + Code Generation 계획)

날짜 2026-10-13. 근거: 사용자가 Azure OpenAI 이미지 생성(배포 `gpt-image-2.5-sunburst`)을 제안했고 시험 한 장(한글 "바른치과" 띠간판, 24초)이 글자까지 정확했다. 사용자 결정 "추천대로 진행해": **띠간판(`sg`)과 층별 간판(`sgf`)만 이미지**, 현판(`sn`)·돌출간판(`sp`)·옥상 간판(`sr`)은 글자 유지. U5 BR-14의 "외부 자산 없음"은 간판 이미지에 한해 푼다(audit 2026-10-13).

## 규칙 (BR-10에 SI-1~SI-9로 더한다)

- **SI-1 대상.** `kind == "sign"`이고 꼬리가 `sg`·`sgf`인 항목. 첫 칸 145개(띠 55, 층별 90), 서로 다른 글자 134개.
- **SI-2 열쇠.** `sign_image_key(text, tail, bg, ink, aspect)` = `sha1("v1|" + text + "|" + tail[:2](sg/sgf) + "|" + bg + "|" + ink + "|" + aspect)[:16]`. `aspect` = 가로/세로를 0.5 단위로 반올림한 문자열(예 `7.5`). 같은 열쇠는 한 번만 만들고 한 번만 올린다.
- **SI-3 프롬프트.** 한 틀: 정면 한국식 상가 간판, 판 색(`bg` 이름 → 색 설명), 글자 색, 글자 `"<text>"` 정확히(다른 글자 없음), 업종 아이콘(글자 끝 어휘 → `SIGN_ICONS`: 치과→이빨, 약국→십자, 학원→연필, 내과·의원·한의원→십자/잎, 카페→컵, 분식·김밥→그릇, 치킨→닭, 미용실→가위, 부동산→집, 편의점→바구니, 피아노→건반, 독서실→책, 필라테스→사람, 법무사→저울, 노래연습장→음표, 꽃집→꽃, 피자→피자, 안경→안경, 유치원·어린이집→해, 요양병원·복지관→손, 태권도→발차기 실루엣, 호프→맥주잔, 휴대폰→전화; 없으면 아이콘 없음), 사람·사진·다른 문자 없음, 판이 화면을 가득 채움. 프롬프트에는 열쇠·경로·비밀값이 들어가지 않는다.
- **SI-4 후처리.** 생성(1536×1024) → 판 테두리 밖 여백 자르기(흰 배경 제거, 가장자리 밝기 240 이상을 여백으로) → 간판 비율(`aspect`)로 양옆 또는 위아래를 판 가장자리 평균색으로 채우기 → 가로 1024 px로 줄이기 → `assets/signs/<key>.png`(git 제외). 원본은 `assets/signs/raw/<key>.png`.
- **SI-5 올리기.** Claude가 Studio MCP `upload_image`로 올린다(캐시 폴더를 127.0.0.1에서 서빙, URL은 `http://127.0.0.1:8765/<key>.png`). 결과 `{url: "rbxassetid://N"}`를 `signs.py record --cells <칸> --file map.json`이 `signs/<칸ID>.json`(git 포함)에 `{key: {asset_id, text, tail, bg, ink, aspect, uploaded_at}}`로 적는다. 검수 거부로 빠진 자산은 Studio에서 안 보이므로 B&T 캡처로 확인하고, 빠진 것은 열쇠를 지우고 다시 만든다.
- **SI-6 덩어리.** `build_luau.py`가 `signs/<칸ID>.json`을 읽어 열쇠가 있는 `sg`/`sgf` 항목에 `a=<asset_id>`(정수)를 더한다. 글자 `t`는 그대로 둔다(대체용). manifest `sign_images` = `a`가 붙은 수.
- **SI-7 Builder.** `a`가 있으면 `TextLabel` 대신 `ImageLabel`(`Image = "rbxassetid://" .. a`, `ScaleType = Stretch`, 배경 투명, 크기 1×1). `a`는 `tonumber`로 받아 정수가 아니면 글자로 대체. `verify`의 `labels`는 `TextLabel` + `ImageLabel`.
- **SI-8 비밀값과 비용.** `OPENAI_API_KEY`, `OPENAI_BASE_URL`은 `.env`에서만(`uv run --env-file .env`). 코드·문서·로그·Luau에 쓰지 않는다. 생성은 `signs.py generate --cells <칸> [--limit N] [--workers 4]`로 열쇠가 없는 것만, 실행당 상한(`--limit`, 기본 200). 실패(HTTP 4xx/5xx, 시간 초과)는 3번 재시도 뒤 그 열쇠를 건너뛰고 계속한다. 응답 형식이 이상하면 멈춘다.
- **SI-9 결정성.** 이미지 자체는 비결정적이지만 `signs/<칸ID>.json`이 자산 ID를 고정하므로 같은 입력은 같은 덩어리 파일을 낸다. 복구(R-16)에는 이 파일을 포함한다. 파일이 없으면 글자 간판으로 만들어진다(전부 대체).

## NFR

- 성능: 간판 145장(칸 3개면 약 450장)의 `ImageLabel`은 1024×≤256 px 텍스처라 메모리 약 1 MB/장 이하. B&T에서 걷기 60 FPS를 다시 잰다(미달이면 `MaxDistance`를 150으로).
- 시간·비용: 장당 약 24초, 4개 병렬이면 첫 칸 약 15분. 요금은 배포 요금제에 따른다(사용자 부담).
- 보안: 프롬프트에는 가상 이름만. 업로드는 사용자의 Roblox 계정으로 Studio가 한다. `assets/`는 git 제외.
- 테스트: 열쇠와 비율 묶음의 안정성, 프롬프트에 글자가 그대로 들어가고 비밀값이 없음, 자르기·채우기(합성 이미지), `a` 키는 매핑이 있을 때만, 매핑 없는 칸은 예전과 같은 덩어리, CLI(`plan`, `generate`는 가짜 응답으로, `record` 왕복), Builder 파일에 `rbxassetid://`와 `ImageLabel`, `signs.py`는 pillow만 의존.

## Code Generation 계획

- [x] 1. `details_rules.py`: `SIGN_IMAGE_TAILS`, `SIGN_ICONS`, `aspect_bucket`, `sign_image_key`, `sign_prompt`, `PALETTE_WORDS`(판 색 이름 → 영어 설명).
- [x] 2. `src/signs.py`(의존 pillow): `plan`(칸의 대상 항목 → `data/build/<칸>/signs-plan.json`), `generate`(urllib로 `{base}/images/generations` POST, 후처리, 캐시), `record`(업로드 결과 → `signs/<칸>.json`), `status`, `--selftest`.
- [x] 3. `build_luau.py`: `signs/<칸>.json` 읽기, `item_literal`의 `a`, manifest `sign_images`, `--selftest` 유지.
- [x] 4. `studio/Builder.luau`: `addSignGui`의 `ImageLabel` 경로, `verify`의 `labels`.
- [x] 5. 테스트: `tests/test_signs.py`, `test_details_rules.py`·`test_build_luau.py`·`test_versions.py` 추가.
- [x] 6. 문서: BR-10에 SI-1~9, CLAUDE.md(명령과 결정), `.gitignore`(`assets/`).
- [ ] 7. Build and Test: 첫 칸 생성(10장 먼저 보고 나머지), 올리기, 기록, 덩어리 다시 만들기, Studio 재생성, 캡처, 걷기 FPS, 문서, 커밋.
