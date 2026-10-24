#!/usr/bin/env python3
"""챗봇 연결 — 웹훅 JSON v1 을 받는 최소 서버(표준 라이브러리만).

이미 챗봇이 있는 회사는 DVG 앱을 새로 만들 필요가 없습니다. 운영사가 «챗봇 연결» 앱에 이 서버의 주소를 넣으면
DVG 가 전화·웹 채팅의 손님 말을 이 주소로 보내고, 여기서 돌려준 답을 말합니다(docs/chatbot-bridge.md).

    CHATBOT_WEBHOOK_SECRET=…  python3 webhook_bot.py        # 127.0.0.1:19998/hook

환경변수
    CHATBOT_WEBHOOK_SECRET  본문 서명 비밀(운영사와 같은 값) — 비우면 서명을 확인하지 않습니다(개발용)
    CHATBOT_WEBHOOK_KEY     Bearer 키(운영사가 넣은 키) — 비우면 확인하지 않습니다
    CHATBOT_HOST · CHATBOT_PORT · CHATBOT_PATH

`answer()` 를 여러분의 챗봇 호출로 바꾸면 됩니다. 나머지(서명·형식·말투)는 그대로 두십시오.
"""

import hashlib
import hmac
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SECRET = os.environ.get("CHATBOT_WEBHOOK_SECRET", "")
KEY = os.environ.get("CHATBOT_WEBHOOK_KEY", "")
HOST = os.environ.get("CHATBOT_HOST", "127.0.0.1")
PORT = int(os.environ.get("CHATBOT_PORT", "19998"))
PATH = os.environ.get("CHATBOT_PATH", "/hook")
MAX_BODY = 256 * 1024


def signature_ok(secret: str, raw: bytes, header: str) -> bool:
    """X-DVG-Signature = hex(HMAC-SHA256(비밀, 본문 바이트)). 본문을 파싱하기 **전** 바이트로 계산한다."""
    want = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, header or "")


def answer(event: dict) -> dict:
    """여기를 여러분의 챗봇 호출로 바꾸십시오.

    event["history"] 에 최근 대화(방금 손님 말 포함)가 있으므로 상태를 저장하지 않아도 됩니다.
    전화(channel=phone)면 짧게 · 물음은 끝에 한 번 · 예시는 낱말마다 마침표로 답하십시오.
    """
    text = event.get("text", "")
    chat = event.get("channel") == "chat"
    # 앞 답에서 choices 를 줬으면 DVG 가 손님 말을 그중 하나로 맞춰 choice 로 보낸다 — 같은 질문을 다시 하지 않는다.
    if event.get("choice"):
        return {"reply": f"{event['choice']}로 알겠습니다. 더 궁금하신 점이 있을까요?"}
    if "주차" in text:
        reply = "건물 지하 2층에 주차하실 수 있어요. 두 시간은 무료예요. 더 궁금하신 점이 있을까요?"
        out = {"reply": reply}
        if chat:
            out["link"] = {"label": "오시는 길", "url": "https://example.com/map"}
        return out
    if "예약" in text:
        return {"reply": "예약 변경은 담당자가 도와드릴게요.", "action": "transfer", "note": "예약 변경 문의"}
    if any(w in text for w in ("고마", "감사", "끊을게", "됐어요")):
        return {"reply": "감사합니다. 좋은 하루 보내세요.", "action": "hangup"}
    if "요일" in text:
        return {"reply": "월요일. 수요일. 금요일. 어느 날이 좋으세요?", "choices": ["월요일", "수요일", "금요일"]}
    return {"reply": "말씀 잘 들었어요. 조금 더 자세히 말씀해 주시겠어요?"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 🔒 손님 말을 로그에 남기지 않는다 — 기본 접근 로그도 끈다
        pass

    def _send(self, status: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        if self.path != PATH:
            self._send(404, {"error": "not_found"})
            return
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BODY:
            self._send(413, {"error": "bad_size"})
            return
        raw = self.rfile.read(n)
        if SECRET and not signature_ok(SECRET, raw, self.headers.get("X-DVG-Signature", "")):
            self._send(401, {"error": "bad_signature"})
            return
        if KEY and not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + KEY):
            self._send(401, {"error": "bad_key"})
            return
        try:
            event = json.loads(raw)
        except ValueError:
            self._send(400, {"error": "bad_json"})
            return
        kind = event.get("event")
        if kind == "start":
            # 비워 두면 운영사가 정한 인사를 씁니다. 회사 인사를 쓰려면 reply 를 채우십시오.
            self._send(200, {})
        elif kind == "message":
            self._send(200, answer(event))
        elif kind == "end":
            # 대화가 끝났다는 알림(응답은 쓰이지 않습니다). 상태를 지우는 자리입니다.
            print(f"끝 conversation={event.get('conversationId')} reason={event.get('reason')}", flush=True)
            self._send(200, {})
        else:
            self._send(400, {"error": "unknown_event"})


def serve(host: str = HOST, port: int = PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


if __name__ == "__main__":
    if not SECRET:
        print("⚠️  CHATBOT_WEBHOOK_SECRET 이 비어 있어 서명을 확인하지 않습니다(개발용)", file=sys.stderr)
    srv = serve()
    print(f"챗봇 웹훅 http://{HOST}:{PORT}{PATH}", flush=True)
    srv.serve_forever()
