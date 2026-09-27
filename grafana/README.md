# 📈 그라파나 템플릿 — DVG 지표 보기

DVG 1.4.16.271 부터 게이트웨이가 **프로메테우스 지표**(`GET /api/v1/metrics`)를 냅니다. 이 폴더는 그것을 그라파나로 보는
**가져오기만 하면 되는 대시보드 3개**와 **한 대로 시작하는 실행 예제**입니다.

| 대시보드 | 보여 주는 것 |
|---|---|
| [DVG · 주문 접수](dashboards/dvg-order-intake.json) | 🎯 **재오더 무인화율** · 재오더인데 사람에게 넘어간 통화 · 결말·고객 종류 추이 · 발신번호 조회 시간(p50·p95) · 미완성 오더 결과 · 회사별 |
| [DVG · 외부 앱](dashboards/dvg-apps.json) | 앱 통화 · 사람에게 넘어간 비율 · 진행 중 · 주소 확정률 · 결말 추이 · 주소 판정 상태 · 음성인식(분)·음성합성(글자) · 평균 턴·연결 시간 |
| [DVG · 개요](dashboards/dvg-overview.json) | 게이트웨이 버전 · 가동 시간 · 지금 다루는 세션 |

## 규칙 — 무엇이 나오고 무엇이 안 나오나

- 🔒 **수치만 나옵니다.** 대화·발신번호·주소는 지표 어디에도 없습니다(그런 값은 DVG 대시보드 🧾 기록에서만 봅니다).
- 🔑 **지표 전용 토큰**(`dvgm_…`)으로만 읽힙니다. DVG 로그인 토큰으로는 읽히지 않습니다.
- 🏢 **테넌트 토큰은 그 테넌트의 수치만** 보입니다. 고객사는 DVG 대시보드에 자기 계정으로 들어가 자기 토큰을 만듭니다.
- 💰 **수량만** 나옵니다(금액 없음).
- ⚠️ 카운터는 DVG 를 다시 시작하면 0 에서 다시 셉니다 — 대시보드는 전부 `increase()`·`rate()` 로 그립니다.

## 빠르게 시작하기 (docker compose)

1. DVG 운영자가 `GW_METRICS_ENABLED=true` 로 지표 출구를 켭니다.
2. DVG 대시보드 **⚙ Dynamic Voice Settings → 📈 지표 (그라파나)** 에서 토큰을 만듭니다(**한 번만** 보입니다).
3. 토큰을 파일에 둡니다 — 설정 파일(`prometheus.yml`)에 직접 적지 않습니다.

   ```bash
   mkdir -p secrets && printf '%s' 'dvgm_여기에_토큰' > secrets/dvg-token && chmod 600 secrets/dvg-token
   ```

4. [prometheus/prometheus.yml](prometheus/prometheus.yml) 의 `targets` 를 DVG 주소(예: `dvg.example.com:8443`)로 바꿉니다.
5. 그라파나 관리자 비밀번호를 정해 실행합니다(기본값이 없습니다 — 비우면 실행이 멈춥니다).

   ```bash
   GRAFANA_ADMIN_PASSWORD='정할_비밀번호' docker compose up -d
   ```

6. `http://localhost:3000` → **DVG** 폴더. 포트는 이 컴퓨터(127.0.0.1)에만 열립니다.

## 이미 그라파나가 있다면

- 프로메테우스에 [prometheus.yml](prometheus/prometheus.yml) 의 `dvg` 작업을 더합니다.
- 그라파나에 데이터 소스를 **uid `dvg-prometheus`** 로 추가하고(대시보드가 이 uid 를 가리킵니다) `dashboards/*.json` 을 가져옵니다.

## 지표 목록

| 지표 | 라벨 | 뜻 |
|---|---|---|
| `dvg_order_calls_total` | tenant·org·outcome·customer | 주문 접수 통화(outcome = collected·escalated·hangup · customer = returning·new·unknown·none) |
| `dvg_order_caller_lookup_seconds` | tenant·org | 발신번호 조회 시간 히스토그램 |
| `dvg_order_drafts_total` | tenant·org·state | 미완성 오더 예약 접수 결과(created·rejected·unknown) |
| `dvg_app_calls_total` | tenant·org·app·outcome | 외부 앱 통화 결말 |
| `dvg_app_address_judgments_total` | tenant·org·app·status | 주소 풀이 판정 상태 |
| `dvg_app_turns_total` · `dvg_app_connected_seconds_total` | tenant·org·app | 앱 지시 수 · 연결 시간 |
| `dvg_app_stt_seconds_total` · `dvg_app_tts_chars_total` | tenant·org·app | 음성인식 초 · 음성합성 글자 |
| `dvg_app_usage_unknown_calls_total` | tenant·org·app | 수량을 모른 통화 — 0 이 아니면 위 두 합계는 최소값 |
| `dvg_app_live_calls` | tenant·org·app | 진행 중 앱 통화 |
| `dvg_gateway_sessions` | tenant | DVG 가 다루는 세션(PBX 의 모든 통화가 아니다) |
| `dvg_order_org_info` | tenant·org·name·status | 회사 id → 이름 |
| `dvg_build_info` · `dvg_process_start_time_seconds` | version | 빌드 · 시작 시각 |

회사 이름으로 보려면 `* on (org) group_left(name) dvg_order_org_info` 를 붙입니다.

## 검증

- [check/check_dashboards.py](check/check_dashboards.py) — 정적 검사(쿼리가 쓰는 지표가 **실제 DVG 출력**에 있는지 등). 로컬에서 `python3 grafana/check/check_dashboards.py`.
- CI 는 실제 프로메테우스·그라파나 컨테이너를 띄워 [가짜 DVG](check/fake_exporter.py)(DVG 지표 코드로 생성한 [실제 출력](testdata/sample-metrics.txt))를 긁게 하고,
  **모든 패널 쿼리가 오류 없이 도는지**와 대시보드 3개가 등록되는지 확인합니다.
- ⚠️ 운영 DVG 에 붙여 본 것은 아닙니다 — 표본은 실제 코드의 출력이지만 값은 시험용입니다.
