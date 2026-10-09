# DVG Apps — 음성 앱 개발 키트

**DVG(Dynamic VoIP Gateway) 위에서 전화 응대 앱을 만드는 개발사를 위한 공개 저장소**입니다 — 계약서 · 예제 앱 · 적합성 시험.

DVG 가 **전화·음성인식(STT)·음성합성(TTS)·AI 고지·사람 연결**을 맡고, 여러분의 앱은 **텍스트로만** 대화를 이끕니다.

```
발신자 ──전화──▶ DVG ──(WebSocket · JSON 텍스트)──▶ 여러분의 앱 ──▶ 여러분의 업무 시스템 API
                 ▲ 음성인식·합성·고지·사람 연결          ▲ 무엇을 물을지 · 답 해석 · 주문 등록
```

## 누가 무엇을 하나 — 운영사(관리자) · 앱 개발사

앱은 **DVG 운영사와의 계약**으로 붙습니다. 운영사는 DVG 를 운영하고 앱을 등록·설치하며, 개발사는 앱과 자기 서버를 만듭니다.
아래 왼쪽은 **운영사가 설정하는 것**(개발사는 요청만 합니다), 오른쪽은 **개발사가 하는 것**입니다.

| 운영사(DVG 관리자)가 한다 | 앱 개발사가 한다 |
|---|---|
| **앱 키**(`dvga_…`)·**서명 비밀** 발급과 전달(한 번만 보여 줌) · 키 재발급 | **WebSocket 서버** 구현 — DVG 의 연결을 받는 쪽([계약 §2](docs/voice-relay-v1.md)) |
| **허용 호스트** — 여러분의 앱 서버 호스트(최대 5개). 이 안에서만 앱 키로 relay 주소를 바꿀 수 있습니다 | **앱 설정을 앱 키로 직접** — 이름 · relay 주소(허용 호스트 안 · 여러 대면 최대 5개와 분배 방식) · 음성인식 힌트 낱말 · 설정 항목 · AI 고지 문구 · 시험 예시([계약 §5-4](docs/voice-relay-v1.md#5-4-앱-설정-고치기--dvg-1416393-이상)) |
| — | **서명·타임스탬프 검증**([시험 벡터](conformance/vector.json) 통과) · 키·비밀을 환경변수(비밀 저장소)에만 보관 |
| **회사(설치)에 앱 연결** — 그 회사로 오는 전화를 앱이 받게 함 | **대화 대본** — 무엇을 묻고 어떻게 복창할지([대화 규칙](docs/getting-started.md#3-대화-규칙--이것만-지키면-됩니다)) |
| **사람 연결 번호** — `transfer` 가 가는 번호(앱은 지정할 수 없음) · 상담원 근무 시간 | 언제 끝낼지·사람에게 넘길지 판단 · 넘길 때 `note` 작성 |
| **설치별 설정 값**(`setup.settings`) — 개발사가 정한 항목에 회사마다 값을 넣음 | 설정 **항목**(키·이름·기본값) 정의(앱 키로) · 값이 없을 때의 기본 동작 |
| 앱 켜기·끄기 · 월 통화 상한 | AI 고지 문구 · 고지 뒤에 이어질 첫 문장 · 음성인식 힌트 낱말(앱 키로) |
| **좌표 제공**·**발신번호 제공**(`caller`) 켜기 · 문자 발신 번호 | 좌표·발신번호가 **없을 때**의 처리 |
| **기록 공유** 켜기(기본 꺼짐) · «대화를 남기지 않음» 설정 | 자기 통화 기록 읽기(앱 키) · 앱 쪽 로그·저장의 **개인정보 처리** |
| **토큰 중개** 켜기(지원하는 업무 API 와 provider 값은 운영사가 알려 줌) | **업무 시스템 API 연동** — 자격증명 보관·토큰 캐시·중복 주문 방지([외부 API 자격증명](docs/external-api-credentials.md)) |
| **같은 서버(사이드카) 실행** 허용·시작 · 사이드카 환경값(업무 자격증명) 넣기 · 자원 상한 | 실행 파일(`run`) 준비 · `DVG_APP_DATA_DIR` 밖에 쓰지 않기 |
| DVG 서버의 공인 IP 알려 주기 · 지표 토큰 발급 · 월 상한 | **자기 서버 배포** — 도메인·TLS·nginx·systemd 또는 Cloud Run · DVG IP 만 허용([실서버 설치](docs/deploy-quickstart.md)) |
| — | **시험**(전화 없이 `simulate`) · **사용량 확인**(앱 키) |

⭐ **운영사에 요청할 것 목록** — 등록 전에 한 번에 정리해 보내십시오:
앱 서버 **호스트**(허용 호스트로 등록됩니다 — 예 `app.example.com`) · 좌표 제공 필요 여부 · 발신번호 필요 여부 · 기록 공유 필요 여부 ·
토큰 중개 필요 여부 · 같은 서버 실행이면 실행 파일과 필요한 메모리.
relay 주소 · 설치별 설정 항목 · 음성인식 힌트 낱말 · AI 고지 문구는 키를 받은 뒤 **앱 키로 직접** 넣습니다(DVG 1.4.16.393 이상 —
그보다 오래된 DVG 면 이것도 운영사에 요청하십시오).

## 어떤 언어로 만드나 — **아무 언어나**

앱은 DVG 에 **연결을 받는 WebSocket 서버**이고, 주고받는 것은 **JSON 텍스트**뿐입니다.
서명 확인은 HMAC-SHA256 한 줄이라 어느 언어에도 표준 라이브러리로 있습니다.

| 예제 | 실행 |
|---|---|
| [Python](examples/python/order_app.py) | `pip install -r examples/python/requirements.txt` → `DVG_SIGNING_SECRET=… python3 examples/python/order_app.py` |
| [Node.js](examples/node/order_app.mjs) | `cd examples/node && npm install` → `DVG_SIGNING_SECRET=… node order_app.mjs` |
| [Go](examples/go/main.go) | `cd examples/go && DVG_SIGNING_SECRET=… go run .` (Go 1.21+ · 사이드카용은 `go build` 로 바이너리 하나) |
| [Java](examples/java/src/main/java/io/olssoo/dvg/example/OrderApp.java) | `cd examples/java && mvn -q package` → `DVG_SIGNING_SECRET=… java -jar target/order-app.jar` (Java 17+ · 의존성 포함 jar 하나) |

네 예제(Python · Node.js · Go · Java)는 같은 일을 합니다 — 출발지·도착지·결제를 묻고, 복창하고, 등록하고, 끝냅니다. 못 알아들으면 **질문을 바꿔 한 번 더** 묻고, 그래도 안 되면 사람에게 넘깁니다.
모두 기본으로 `ws://127.0.0.1:19999/relay` 에서 기다리고, 같은 서버(사이드카)로 돌리면 DVG 가 넣어 주는 `DVG_APP_*` 환경변수를 읽습니다.
실제 주문 등록은 각 예제의 등록 함수 자리에 여러분의 업무 API 호출을 넣으면 됩니다. Python 예제는 [Dockerfile](examples/python/Dockerfile)(Cloud Run 용)도 있습니다.

### 도메인 예제 — 시나리오 JSON 하나로 바꾼다

[`examples/python/slot_app.py`](examples/python/slot_app.py) 는 **슬롯 엔진**입니다 — 무엇을 묻고 어떻게 복창할지는 시나리오 파일에 있고 대화 규칙은 엔진 한 곳에 있습니다.
`examples/python` 폴더에서 실행합니다.

| 시나리오 | 묻는 것 | 실행 |
|---|---|---|
| [꽃 배달](examples/python/scenarios/flower.json) | 배달지(주소) · 상품(꽃다발/꽃바구니/화환) | `DVG_APP_SCENARIO=scenarios/flower.json python3 slot_app.py` |
| [대리운전](examples/python/scenarios/driver.json) | 출발지 · 목적지(주소) · 변속기(자동/수동) | `DVG_APP_SCENARIO=scenarios/driver.json python3 slot_app.py` |
| [음식 배달](examples/python/scenarios/food.json) | 메뉴(자유) · 배달지(주소) · 결제(카드/현금) | `DVG_APP_SCENARIO=scenarios/food.json python3 slot_app.py` |

⭐ **주소는 앱이 풀지 않습니다** — `ask` 에 `"expect":"address"` 를 실으면 DVG 가 발신자의 답을 시·도/구·군/동으로 풀어 주고, 같은 이름이 여러 곳이면
**좁히는 질문**까지 만들어 줍니다([계약 §3-5](docs/voice-relay-v1.md)). 한 통의 메시지 전부는 [계약 §3-6](docs/voice-relay-v1.md) 에 있습니다.

## 문서

- 📘 [시작하기](docs/getting-started.md) — 등록 받기 · 어디서 돌리나(다른 서버 / DVG 와 같은 서버) · 대화 규칙 · 시험 · 체크리스트
- 🚀 [실서버 설치 퀵 가이드](docs/deploy-quickstart.md) — 같은 서버(사이드카) · 다른 서버(nginx `wss` + systemd) · 서버 없이(Cloud Run 컨테이너) · 콘솔 HTTPS. 설정 파일은 [`deploy/`](deploy/) 에 있습니다
- 📜 [관리형 음성 레이어 계약 v1](docs/voice-relay-v1.md) — 메시지 · 서명 · 결말 · 상한
- 🔑 [외부 API 자격증명 · 토큰](docs/external-api-credentials.md) — 키를 어디에 두나 · 토큰 재사용 · 앱을 여러 대로 돌릴 때 · DVG 토큰 중개
- ✅ [적합성 시험](conformance/) — 서명 시험 벡터(모든 언어가 같은 값을 받아들여야 한다)
- 🖥 [앱 개발사 콘솔 샘플](console/) — 앱 키로 **내 앱의 사용량**을 보고 **전화 없이 시험**하는 웹 화면(위젯 단위 · 앱 키는 서버에만 · DVG 1.4.16.259+)

## 앱을 쓰려면

운영사가 **앱 키**와 **서명 비밀**을 한 번 전달합니다(셀프 가입 없음) — 무엇을 요청할지는 [위 목록](#누가-무엇을-하나--운영사관리자--앱-개발사)에 있습니다.
키를 받은 뒤의 설정은 앱 키로 직접 합니다([계약 §5-4](docs/voice-relay-v1.md#5-4-앱-설정-고치기--dvg-1416393-이상)).
이 저장소는 누구나 볼 수 있지만, 실제 통화에 붙이려면 등록이 필요합니다.

## 버전

계약 버전은 [CHANGELOG](CHANGELOG.md) 에 적습니다. 필드는 **버전을 올리지 않고 늘어날 수 있으니** 모르는 필드는 무시하십시오.
서명 방식처럼 **기존 앱을 깨뜨리는 변경은 계약 버전을 올려서만** 합니다(서명 방식은 공개 [시험 벡터](conformance/vector.json)로 고정돼 있습니다).

## 기여 · 보안

- 기여: [CONTRIBUTING.md](CONTRIBUTING.md)
- 보안 문제는 이슈로 올리지 말고 [SECURITY.md](SECURITY.md) 의 연락처로 알려 주십시오.
