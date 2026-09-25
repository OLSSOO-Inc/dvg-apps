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

두 예제는 같은 일을 합니다 — 출발지·도착지·결제를 묻고, 복창하고, 등록하고, 끝냅니다. 못 알아들으면 **질문을 바꿔 한 번 더** 묻고, 그래도 안 되면 사람에게 넘깁니다.

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
