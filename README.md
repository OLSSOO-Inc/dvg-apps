# DVG Apps — 음성 앱 개발 키트

**DVG(Dynamic VoIP Gateway) 위에서 전화 응대 앱을 만드는 개발사를 위한 공개 저장소**입니다 — 계약서 · 예제 앱 · 적합성 시험.

DVG 가 **전화·음성인식(STT)·음성합성(TTS)·AI 고지·사람 연결**을 맡고, 여러분의 앱은 **텍스트로만** 대화를 이끕니다.

```
발신자 ──전화──▶ DVG ──(WebSocket · JSON 텍스트)──▶ 여러분의 앱 ──▶ 여러분의 업무 시스템 API
                 ▲ 음성인식·합성·고지·사람 연결          ▲ 무엇을 물을지 · 답 해석 · 주문 등록
```

## 어떤 언어로 만드나 — **아무 언어나**

앱은 DVG 에 **연결을 받는 WebSocket 서버**이고, 주고받는 것은 **JSON 텍스트**뿐입니다. DVG 가 Go 로 만들어졌다고 앱도 Go 일 필요는 없습니다.
서명 확인은 HMAC-SHA256 한 줄이라 어느 언어에도 표준 라이브러리로 있습니다.

| 예제 | 실행 |
|---|---|
| [Python](examples/python/order_app.py) | `pip install -r examples/python/requirements.txt` → `DVG_SIGNING_SECRET=… python3 examples/python/order_app.py` |
| [Node.js](examples/node/order_app.mjs) | `cd examples/node && npm install` → `DVG_SIGNING_SECRET=… node order_app.mjs` |
| [Go](examples/go/main.go) | `cd examples/go && DVG_SIGNING_SECRET=… go run .` (Go 1.21+ · 사이드카용은 `go build` 로 바이너리 하나) |

세 예제는 같은 일을 합니다 — 출발지·도착지·결제를 묻고, 복창하고, 등록하고, 끝냅니다. 못 알아들으면 **질문을 바꿔 한 번 더** 묻고, 그래도 안 되면 사람에게 넘깁니다.

### 도메인 예제 — 시나리오 JSON 하나로 바꾼다

[`examples/python/slot_app.py`](examples/python/slot_app.py) 는 **슬롯 엔진**입니다 — 무엇을 묻고 어떻게 복창할지는 시나리오 파일에 있고 대화 규칙은 엔진 한 곳에 있습니다.

| 시나리오 | 묻는 것 | 실행 |
|---|---|---|
| [꽃 배달](examples/python/scenarios/flower.json) | 배달지(주소) · 상품(꽃다발/꽃바구니/화환) | `DVG_APP_SCENARIO=scenarios/flower.json python3 slot_app.py` |
| [대리운전](examples/python/scenarios/driver.json) | 출발지 · 목적지(주소) · 변속기(자동/수동) | `DVG_APP_SCENARIO=scenarios/driver.json python3 slot_app.py` |
| [음식 배달](examples/python/scenarios/food.json) | 메뉴(자유) · 배달지(주소) · 결제(카드/현금) | `DVG_APP_SCENARIO=scenarios/food.json python3 slot_app.py` |

⭐ **주소는 앱이 풀지 않습니다** — `ask` 에 `"expect":"address"` 를 실으면 DVG 가 발신자의 답을 시·도/구·군/동으로 풀어 주고, 같은 이름이 여러 곳이면
**좁히는 질문**까지 만들어 줍니다([계약 §3-5](docs/voice-relay-v1.md)). 한 통의 메시지 전부는 [계약 §3-6](docs/voice-relay-v1.md) 에 있습니다.

## 문서

- 📘 [시작하기](docs/getting-started.md) — 등록 받기 · 어디서 돌리나(다른 서버 / DVG 와 같은 서버) · 대화 규칙 · 시험 · 체크리스트
- 📜 [관리형 음성 레이어 계약 v1](docs/voice-relay-v1.md) — 메시지 · 서명 · 결말 · 상한
- ✅ [적합성 시험](conformance/) — 서명 시험 벡터(모든 언어가 같은 값을 받아들여야 한다)

## 앱을 쓰려면

앱은 **DVG 운영사와의 계약**으로 붙습니다 — 운영사가 앱을 등록하고 **앱 키**와 **서명 비밀**을 한 번 전달합니다(셀프 가입 없음).
이 저장소는 누구나 볼 수 있지만, 실제 통화에 붙이려면 등록이 필요합니다.

## 버전

계약 버전은 [CHANGELOG](CHANGELOG.md) 에 적습니다. 필드는 **버전을 올리지 않고 늘어날 수 있으니** 모르는 필드는 무시하십시오.
서명 방식처럼 **기존 앱을 깨뜨리는 변경은 계약 버전을 올려서만** 합니다(DVG 쪽 시험이 공개 벡터를 고정합니다).

## 기여 · 보안

- 기여: [CONTRIBUTING.md](CONTRIBUTING.md)
- 보안 문제는 이슈로 올리지 말고 [SECURITY.md](SECURITY.md) 의 연락처로 알려 주십시오.
