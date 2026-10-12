# Performance Test Instructions

부하 시험은 해당 없다(단일 사용자, 칸 단위 배치 실행). 대신 NFR-P1("칸 하나를 수 분 이내")을 실제 칸으로 잰다.

## 요구
- **칸 하나 수집·조립**: 수 분 이내(U1-NFR-P1).
- **DB 크기**: 3칸 규모에서 문제되지 않을 것.

## 측정 방법
```bash
time uv run --env-file .env src/cells.py --cells <칸ID>
time uv run --env-file .env src/register.py --cells <칸ID>
ls -la data/map.db
```
`collection_runs`의 `started_at`, `finished_at`으로도 볼 수 있다.

## 이번 결과 (2026-10-13, 첫 칸 `8930e0af13bffff`)
| 항목 | 결과 | 요구 | 판정 |
|---|---|---|---|
| `cells.py` (Overpass) | 약 131초 (재시도 대기 100초 포함, 실제 호출은 약 30초) | 수 분 이내 | 통과 |
| `register.py` (V-World, 558건, 1페이지) | 약 4초 | 수 분 이내 | 통과 |
| DB 크기 | 약 412 KB | 문제 없음 | 통과 |
| 테스트 93개 | 약 4초 | - | - |

병목은 Overpass의 504 재시도 대기다. V-World는 한 페이지에 1000건이라 칸 하나에 한 번 호출로 끝난다. 칸이 늘어도 Overpass 호출 간격(`overpass_pause_s`)과 재시도가 시간의 대부분이다.
