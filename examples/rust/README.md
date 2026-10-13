# Rust 로 DVG 음성 앱 만들기

[`src/main.rs`](src/main.rs) 는 다른 예제(Python · Node.js · Go · Java)와 **같은 일**을 합니다 —
출발지·도착지·결제를 묻고, 복창하고, 등록하고, 끝냅니다. 못 알아들으면 **질문을 바꿔 한 번 더** 묻고, 그래도 안 되면 사람에게 넘깁니다.
계약 전부는 [관리형 음성 레이어 계약 v1](../../docs/voice-relay-v1.md) 에 있습니다.

## 준비

- 최신 stable Rust(`rustup` 으로 설치) — 이 예제는 `cargo` 만 있으면 됩니다.
- 운영사에게 받은 **서명 비밀**(`DVG_SIGNING_SECRET`).

## 실행

```bash
cd examples/rust && DVG_SIGNING_SECRET=… cargo run
```

기본으로 `ws://127.0.0.1:19999/relay` 에서 기다립니다. 주소는 `APP_HOST` · `APP_PORT` · `APP_PATH` 로 바꿉니다.
같은 서버(사이드카)로 돌리면 DVG 가 넣어 주는 `DVG_APP_*` 환경변수를 먼저 읽습니다.

## 쓰는 크레이트

| 크레이트 | 하는 일 |
|---|---|
| `tokio` · `tokio-tungstenite` · `futures-util` | WebSocket 서버 — DVG 의 연결을 **받는** 쪽입니다 |
| `hmac` · `sha2` · `hex` | 서명 확인(HMAC-SHA256) |
| `serde` · `serde_json` | JSON 메시지 |

## 서명 확인 — 업그레이드 **전에** 거른다

DVG 는 연결할 때 `X-DVG-App-Id` · `X-DVG-Call-Id` · `X-DVG-Timestamp` · `X-DVG-Signature` 헤더를 붙입니다.
`tokio_tungstenite::accept_hdr_async_with_config` 의 콜백에서 이 헤더를 확인하고, 틀리면 **401 로 거절해 WebSocket 을 열지 않습니다.**

```rust
pub fn verify_dvg(h: &HeaderMap, secret: &str, now: i64) -> bool {
    // … 헤더 넷이 다 있고, 타임스탬프가 숫자이고 ±300초 안이며, 서명이 64자 16진 소문자일 때만 …
    let mut mac = Hmac::<Sha256>::new_from_slice(secret.as_bytes()).unwrap();
    mac.update(format!("{app_id}\n{call_id}\n{ts}").as_bytes());
    mac.verify_slice(&hex::decode(sig).unwrap()).is_ok() // 상수 시간 비교
}
```

구현이 맞는지는 [시험 벡터](../../conformance/vector.json)로 확인합니다 — `cargo test` 가 그 파일을 읽어
**받아들이기 · 틀린 서명·비밀·대문자 서명·300초 초과 거절**을 확인합니다.

```bash
cd examples/rust && cargo test
```

## 대화 규칙 — 이 예제가 지키는 것

- **한 통화 = 한 연결 = 한 태스크.** DVG 는 엄격한 요청·응답이라 읽기와 쓰기가 번갈아 일어납니다 — 연결을 나눠 쓰지 마십시오.
- **첫 메시지는 항상 `setup`** 입니다. `setup.simulated` 가 `true` 면 **시험 통화**라 실제 주문을 만들지 않습니다.
- **같은 문장을 되풀이하지 않습니다** — 다시 물을 때는 질문을 바꿉니다.
- **예시·복창은 마침표로 끊습니다**(「선불. 착불. 결제는 어느 쪽인가요?」) — 쉼표로 이으면 전화에서 한 덩어리로 들립니다.
- **사람에게 넘길 번호는 앱이 정하지 않습니다** — `{"type":"transfer"}` 만 보내면 DVG 가 회사에 등록된 번호로 넘깁니다.
- **`end` 를 받거나 연결이 닫히면 통화가 끝난 것**이고 오류가 아닙니다(앞에 프록시가 있으면 `end` 없이 닫힐 수 있습니다).
- 모르는 필드는 무시합니다(`serde` 기본 동작) — 필드는 계약 버전을 올리지 않고 늘어날 수 있습니다.

실제 주문 등록은 `register_order()` 자리에 여러분의 업무 API 호출을 넣으면 됩니다.

## 사이드카(같은 서버)로 돌리기

릴리스 바이너리 하나를 만들어 `run` 이라는 이름으로 운영사에 전달합니다.

```bash
cd examples/rust && cargo build --release
```

결과물은 `target/release/order-app` 입니다. DVG 서버와 **같은 CPU·운영체제**(대개 Linux x86_64)로 빌드하십시오.
다른 기계에서 빌드한다면 정적 링크(`x86_64-unknown-linux-musl`)가 가장 탈이 적습니다:

```bash
rustup target add x86_64-unknown-linux-musl && cargo build --release --target x86_64-unknown-linux-musl
```

앱은 제한된 환경에서 돕니다 — 쓸 수 있는 곳은 `DVG_APP_DATA_DIR` 와 `/tmp` 뿐입니다([실서버 설치](../../docs/deploy-quickstart.md)).

## 다른 서버로 돌리기

`APP_HOST=127.0.0.1` 로 두고 앞에 nginx(`wss`)를 두는 구성은 다른 언어와 같습니다 — [실서버 설치 B](../../docs/deploy-quickstart.md#b-다른-서버--nginx--systemd).
