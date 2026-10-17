//! DVG 외부 앱 최소 예제 (Rust) — 음성 주문 접수 · 관리형 음성 레이어 v1.
//!
//! DVG 가 전화·음성인식·음성합성을 맡고, 이 앱은 **텍스트로만** 대화를 이끈다.
//! 계약: ../../docs/voice-relay-v1.md
//!
//! 실행:
//!
//! ```text
//! cargo run                                  # DVG_SIGNING_SECRET=... 필요 · 기본 127.0.0.1:19999, 경로 /relay
//! cargo build --release                      # 사이드카용 바이너리 → target/release/order-app
//! ```
//!
//! 같은 서버(사이드카)로 실행되면 DVG_APP_* 가 자동으로 들어온다.
//! ⚠️ 예제다 — 실제 주문 등록은 register_order() 자리에 넣는다(업무 시스템 API 는 앱이 직접 부른다).

use std::collections::BTreeMap;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use futures_util::{SinkExt, StreamExt};
use hmac::{Hmac, Mac};
use serde::{Deserialize, Serialize};
use sha2::Sha256;
use tokio::net::{TcpListener, TcpStream};
use tokio_tungstenite::tungstenite::handshake::server::{ErrorResponse, Request, Response};
use tokio_tungstenite::tungstenite::http::{HeaderMap, StatusCode};
use tokio_tungstenite::tungstenite::protocol::WebSocketConfig;
use tokio_tungstenite::tungstenite::{Error as WsError, Message};
use tokio_tungstenite::WebSocketStream;

/// 이보다 오래된(또는 미래의) 연결은 거절한다(재생 방지 · 초).
const MAX_SKEW: i64 = 300;

fn env(def: &str, names: &[&str]) -> String {
    for n in names {
        if let Ok(v) = std::env::var(n) {
            if !v.is_empty() {
                return v;
            }
        }
    }
    def.to_string()
}

fn now_unix() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

/// DVG 가 건 연결인가 — 서명·타임스탬프 확인.
///
/// 서명 = hex(HMAC-SHA256(서명 비밀, "{앱 id}\n{통화 id}\n{타임스탬프}")) · 16진 소문자.
pub fn verify_dvg(h: &HeaderMap, secret: &str, now: i64) -> bool {
    let get = |k: &str| h.get(k).and_then(|v| v.to_str().ok()).unwrap_or("");
    let (app_id, call_id) = (get("x-dvg-app-id"), get("x-dvg-call-id"));
    let (ts, sig) = (get("x-dvg-timestamp"), get("x-dvg-signature"));
    if secret.is_empty() || app_id.is_empty() || call_id.is_empty() || sig.is_empty() {
        return false;
    }
    if ts.is_empty() || !ts.bytes().all(|b| b.is_ascii_digit()) {
        return false;
    }
    let sec: i64 = match ts.parse() {
        Ok(v) => v,
        Err(_) => return false,
    };
    if sec.to_string() != ts {
        return false; // 「01790000000」처럼 다른 표기는 받지 않는다
    }
    if (now - sec).abs() > MAX_SKEW {
        return false;
    }
    if sig.len() != 64 || !sig.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f')) {
        return false;
    }
    let want = match hex::decode(sig) {
        Ok(v) => v,
        Err(_) => return false,
    };
    let mut mac = match Hmac::<Sha256>::new_from_slice(secret.as_bytes()) {
        Ok(m) => m,
        Err(_) => return false,
    };
    mac.update(format!("{app_id}\n{call_id}\n{ts}").as_bytes());
    mac.verify_slice(&want).is_ok() // 상수 시간 비교
}

/// DVG → 앱 메시지(필요한 필드만 — 모르는 필드는 무시된다).
#[derive(Deserialize, Default, Debug)]
#[serde(default, rename_all = "camelCase")]
struct In {
    #[serde(rename = "type")]
    typ: String,
    text: String,
    silence: bool,
    choice: String,
    reason: String,
    call_id: String,
    org_id: String,
    caller: Option<String>,
    simulated: bool,
    /// "chat" = 웹 채팅(계약 §3-17)
    channel: String,
    /// prompt: expect:"address" 의 결과 — 키가 없으면 None(오래된 DVG)
    address: Option<Address>,
}

/// prompt.address 중 이 예제가 쓰는 필드(계약 §3-5).
#[derive(Deserialize, Default, Debug)]
#[serde(default, rename_all = "camelCase")]
struct Address {
    status: String,
    line: String,
    detail: String,
    detail_clean: String,
    question: String,
}

/// 앱 → DVG 지시.
#[derive(Serialize, Default)]
struct Out {
    #[serde(rename = "type")]
    typ: String,
    #[serde(skip_serializing_if = "String::is_empty")]
    text: String,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    choices: Vec<String>,
    /// ask: "address" 면 DVG 가 주소를 풀어 준다(계약 §3-5)
    #[serde(skip_serializing_if = "String::is_empty")]
    expect: String,
    #[serde(skip_serializing_if = "String::is_empty")]
    label: String,
    /// transfer: 상담원에게 남길 메모
    #[serde(skip_serializing_if = "String::is_empty")]
    note: String,
}

#[derive(Debug)]
enum AppError {
    /// 통화가 끝났다(end 를 받았거나 연결이 닫혔다) — 오류가 아니다.
    Ended,
    Other(String),
}

impl From<WsError> for AppError {
    fn from(e: WsError) -> Self {
        match e {
            WsError::ConnectionClosed | WsError::AlreadyClosed => AppError::Ended,
            other => AppError::Other(other.to_string()),
        }
    }
}

/// 한 통화 — DVG 는 엄격한 요청·응답이라 읽기·쓰기가 한 태스크에서 번갈아 일어난다.
struct Session {
    ws: WebSocketStream<TcpStream>,
}

impl Session {
    async fn recv(&mut self) -> Result<In, AppError> {
        loop {
            let next = tokio::time::timeout(Duration::from_secs(15 * 60), self.ws.next())
                .await
                .map_err(|_| AppError::Other("15분 동안 메시지가 없습니다".into()))?;
            let msg = match next {
                // DVG 는 end 를 보낸 뒤 연결을 닫는다. 앞에 프록시가 있으면 end 가 오기 전에 닫힐 수 있다 —
                // 그래도 통화는 끝났다(결말은 모른다). 오류로 다루지 않는다.
                None | Some(Ok(Message::Close(_))) => {
                    println!("통화 끝: closed");
                    return Err(AppError::Ended);
                }
                Some(Err(e)) => return Err(e.into()),
                Some(Ok(m)) => m,
            };
            if !msg.is_text() {
                continue; // ping·pong 은 라이브러리가 처리한다
            }
            let text = msg.to_text().map_err(|e| AppError::Other(e.to_string()))?;
            let m: In = serde_json::from_str(text).map_err(|e| AppError::Other(e.to_string()))?;
            if m.typ == "end" {
                println!("통화 끝: {}", m.reason);
                return Err(AppError::Ended);
            }
            return Ok(m);
        }
    }

    async fn send(&mut self, typ: &str, text: &str, choices: &[&str]) -> Result<(), AppError> {
        self.send_out(Out {
            typ: typ.to_string(),
            text: text.to_string(),
            choices: choices.iter().map(|c| c.to_string()).collect(),
            ..Out::default()
        })
        .await
    }

    async fn send_out(&mut self, out: Out) -> Result<(), AppError> {
        let body = serde_json::to_string(&out).map_err(|e| AppError::Other(e.to_string()))?;
        self.ws.send(Message::text(body)).await?;
        Ok(())
    }

    /// 질문하고 답을 받는다. choices 를 주면 DVG 가 답을 그중 하나로 읽어 준다(초성 판정 포함).
    async fn ask(&mut self, text: &str, choices: &[&str]) -> Result<String, AppError> {
        self.send("ask", text, choices).await?;
        let m = self.recv().await?;
        if m.typ != "prompt" || m.silence {
            return Ok(String::new());
        }
        if !choices.is_empty() {
            return Ok(m.choice); // 못 골랐으면 빈 값 → 다시 묻는다
        }
        Ok(m.text.trim().to_string())
    }

    /// 주소를 묻는다 — DVG 가 시·도/구·군/동으로 풀어 준다(계약 §3-5). 복창용 한 줄, 못 얻으면 빈 문자열.
    /// resolved → DVG 의 한 줄(line) + 동 뒤의 말(detailClean) · ambiguous → DVG 의 좁히는 질문을 **글자 그대로** 다시 묻는다 ·
    /// unavailable(또는 address 가 없는 오래된 DVG) → 발화 원문(마지막 복창이 확인한다) · 그 밖 → 바꾼 질문으로 한 번 더.
    async fn ask_address(
        &mut self,
        question: &str,
        again: &str,
        label: &str,
    ) -> Result<String, AppError> {
        let mut text = question.to_string();
        // 첫 질문 + 바꾼 질문 + (여러 곳일 때) DVG 의 좁히는 질문
        for _ in 0..3 {
            self.send_out(Out {
                typ: "ask".into(),
                text: text.clone(),
                expect: "address".into(),
                label: label.into(),
                ..Out::default()
            })
            .await?;
            let m = self.recv().await?;
            let heard = if m.silence {
                String::new()
            } else {
                m.text.trim().to_string()
            };
            match &m.address {
                Some(a) if a.status == "resolved" => {
                    let detail = if a.detail_clean.is_empty() {
                        &a.detail
                    } else {
                        &a.detail_clean
                    };
                    return Ok(format!("{} {}", a.line, detail).trim().to_string());
                }
                Some(a) if a.status == "ambiguous" && !a.question.is_empty() => {
                    text = a.question.clone();
                    continue;
                }
                Some(a) if a.status == "unavailable" && !heard.is_empty() => return Ok(heard),
                None if !heard.is_empty() => return Ok(heard),
                _ => {}
            }
            if text == again {
                break; // 바꾼 질문으로도 못 얻었다 — 더 묻지 않는다
            }
            text = again.to_string();
        }
        Ok(String::new())
    }

    async fn end(&mut self, typ: &str, text: &str) -> Result<(), AppError> {
        self.end_note(typ, text, "").await
    }

    async fn end_note(&mut self, typ: &str, text: &str, note: &str) -> Result<(), AppError> {
        self.send_out(Out {
            typ: typ.to_string(),
            text: text.to_string(),
            note: note.to_string(),
            ..Out::default()
        })
        .await?;
        self.recv().await.map(|_| ())
    }
}

fn register_order(order: &BTreeMap<&str, String>, setup: &In) -> bool {
    let body = serde_json::to_string(order).unwrap_or_default();
    if setup.simulated {
        // 🔴 시험 통화(setup.simulated) — 실제 주문을 만들지 않는다.
        println!("시험 통화 — 주문 등록 건너뜀: {body}");
        return true;
    }
    println!("주문 등록(예제): org={} {body}", setup.org_id);
    true
}

async fn handle(ws: WebSocketStream<TcpStream>) -> Result<(), AppError> {
    let mut s = Session { ws };
    let setup = s.recv().await?; // 첫 메시지는 항상 setup
    println!(
        "통화 시작 {} (발신번호 제공={})",
        setup.call_id,
        setup.caller.is_some()
    );
    let mut order: BTreeMap<&str, String> = BTreeMap::new();
    // (칸, 첫 질문, 다시 물을 때의 질문, 선택지, 주소 칸 이름) — 🔴 같은 문장을 되풀이하지 않는다. 다시 물을 때는 질문을 바꾼다.
    let steps: [(&str, &str, &str, &[&str], &str); 3] = [
        (
            "origin",
            "어디에서 보내시나요?",
            "제가 잘 못 들었습니다. 물건을 가지러 갈 곳의 구와 동을 말씀해 주세요.",
            &[],
            "출발지",
        ),
        (
            "destination",
            "어디로 보내시나요?",
            "제가 잘 못 들었습니다. 물건을 받으실 곳의 구와 동을 말씀해 주세요.",
            &[],
            "도착지",
        ),
        (
            "pay",
            "선불. 착불. 결제는 어느 쪽인가요?",
            "제가 잘 못 들었습니다. 선불이면 「선불」. 착불이면 「착불」.",
            &["선불", "착불"],
            "",
        ),
    ];
    for (key, question, again, choices, label) in steps {
        let ans = if label.is_empty() {
            let mut ans = s.ask(question, choices).await?;
            if ans.is_empty() {
                ans = s.ask(again, choices).await?;
            }
            ans
        } else {
            // 주소는 DVG 가 풀어 준다(앱이 파싱하지 않는다)
            s.ask_address(question, again, label).await?
        };
        if ans.is_empty() {
            return s.end("transfer", "").await; // 번호는 DVG 가 정한다(앱이 지정할 수 없다)
        }
        order.insert(key, ans);
    }
    // 복창 — 나열은 마침표로 끊는다(쉼표로 이으면 전화에서 한 덩어리로 들린다).
    let readback = format!(
        "출발 {}. 도착 {}. 결제 {}. 맞으면 「네」라고 말씀해 주세요.",
        order["origin"], order["destination"], order["pay"]
    );
    let ok = s.ask(&readback, &[]).await?;
    if !(ok.starts_with('네') || ok.starts_with('예') || ok.starts_with('맞')) {
        return s.end("transfer", "").await;
    }
    let summary = format!(
        "출발 {}. 도착 {}. 결제 {}.",
        order["origin"], order["destination"], order["pay"]
    );
    if setup.channel == "chat" {
        // 🔴 웹 채팅은 상담·안내용 — 실제 주문을 만들지 않고 모은 내용을 메모로 상담원에게 넘긴다(계약 §3-17).
        return s.end_note("transfer", "", &format!("채팅 문의 — {summary}")).await;
    }
    if register_order(&order, &setup) {
        return s.end("hangup", "접수되었습니다. 감사합니다.").await;
    }
    s.end("transfer", "").await
}

fn reject(code: StatusCode, body: &str) -> ErrorResponse {
    let mut r = ErrorResponse::new(Some(body.to_string()));
    *r.status_mut() = code;
    r
}

// WebSocketConfig 는 non_exhaustive — 필드만 바꾼다 · 콜백의 오류 형식(ErrorResponse)은 라이브러리가 정한다.
#[allow(clippy::field_reassign_with_default, clippy::result_large_err)]
async fn serve(stream: TcpStream, secret: String, path: String) {
    // WebSocket 업그레이드 전에 거른다 — 서명이 틀리면 연결 자체를 받지 않는다.
    let check = move |req: &Request, resp: Response| -> Result<Response, ErrorResponse> {
        if req.uri().path() != path {
            return Err(reject(StatusCode::NOT_FOUND, "not found"));
        }
        if !verify_dvg(req.headers(), &secret, now_unix()) {
            return Err(reject(StatusCode::UNAUTHORIZED, "bad signature"));
        }
        Ok(resp)
    };
    let mut cfg = WebSocketConfig::default();
    cfg.max_message_size = Some(1 << 20);
    let accept = tokio_tungstenite::accept_hdr_async_with_config(stream, check, Some(cfg));
    let ws = match tokio::time::timeout(Duration::from_secs(10), accept).await {
        Ok(Ok(ws)) => ws,
        Ok(Err(e)) => {
            eprintln!("연결 거절: {e}");
            return;
        }
        Err(_) => {
            eprintln!("연결 거절: 핸드셰이크 시간 초과");
            return;
        }
    };
    if let Err(AppError::Other(e)) = handle(ws).await {
        eprintln!("앱 오류: {e}");
    }
}

#[tokio::main]
async fn main() {
    let secret = env("", &["DVG_APP_SIGNING_SECRET", "DVG_SIGNING_SECRET"]);
    let host = env("127.0.0.1", &["DVG_APP_HOST", "APP_HOST"]);
    let port = env("19999", &["DVG_APP_PORT", "APP_PORT"]);
    let path = env("/relay", &["DVG_APP_PATH", "APP_PATH"]);
    if secret.is_empty() {
        eprintln!("DVG_SIGNING_SECRET 이 비어 있습니다 — 앱 등록 때 받은 서명 비밀을 넣으세요");
        std::process::exit(1);
    }
    let addr = if host.contains(':') {
        format!("[{host}]:{port}") // IPv6
    } else {
        format!("{host}:{port}")
    };
    let listener = match TcpListener::bind(&addr).await {
        Ok(l) => l,
        Err(e) => {
            eprintln!("{addr} 에서 기다릴 수 없습니다: {e}");
            std::process::exit(1);
        }
    };
    println!("listening ws://{addr}{path}");
    loop {
        match listener.accept().await {
            Ok((stream, _)) => {
                tokio::spawn(serve(stream, secret.clone(), path.clone()));
            }
            Err(e) => eprintln!("accept 실패: {e}"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio_tungstenite::tungstenite::http::{HeaderName, HeaderValue};

    /// 서명 시험 벡터 — verify_dvg 가 DVG 와 같은 값을 받아들이는가(../../conformance/vector.json).
    #[test]
    fn verify_dvg_conformance_vector() {
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../conformance/vector.json");
        let raw = std::fs::read_to_string(path).expect("conformance/vector.json");
        let v: serde_json::Value = serde_json::from_str(&raw).expect("JSON");
        let s = |k: &str| v[k].as_str().expect(k).to_string();
        let ts = v["timestamp"].as_i64().expect("timestamp");
        let headers = |sig: &str| {
            let mut h = HeaderMap::new();
            for (k, val) in [
                ("x-dvg-app-id", s("appId")),
                ("x-dvg-call-id", s("callId")),
                ("x-dvg-timestamp", ts.to_string()),
                ("x-dvg-signature", sig.to_string()),
            ] {
                h.insert(
                    HeaderName::from_static(k),
                    HeaderValue::from_str(&val).unwrap(),
                );
            }
            h
        };
        let (secret, good) = (s("signingSecret"), headers(&s("signature")));
        let bad = headers(&"0".repeat(64));
        let upper = headers(&s("signature").to_uppercase());
        for (name, got, want) in [
            ("벡터를 받아들인다", verify_dvg(&good, &secret, ts), true),
            ("틀린 서명은 거절", verify_dvg(&bad, &secret, ts), false),
            (
                "틀린 비밀은 거절",
                verify_dvg(&good, "other-secret", ts),
                false,
            ),
            ("대문자 서명은 거절", verify_dvg(&upper, &secret, ts), false),
            (
                "300초 넘게 지난 연결은 거절",
                verify_dvg(&good, &secret, ts + 301),
                false,
            ),
            (
                "300초 이내는 받는다",
                verify_dvg(&good, &secret, ts + 300),
                true,
            ),
        ] {
            assert_eq!(got, want, "{name}");
        }
    }
}
