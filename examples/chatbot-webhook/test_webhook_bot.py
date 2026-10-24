#!/usr/bin/env python3
"""webhook_bot.py 시험 — 서명 시험 벡터 · 실제 HTTP 요청 · 응답 모양. 표준 라이브러리만."""

import hashlib
import hmac
import json
import os
import sys
import threading
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["CHATBOT_WEBHOOK_SECRET"] = "whsec"
os.environ["CHATBOT_WEBHOOK_KEY"] = "k1"
import webhook_bot  # noqa: E402

# 🔏 서명 시험 벡터 — DVG 가 같은 비밀·본문에 붙이는 값(docs/chatbot-bridge.md §4-3).
VECTOR_SECRET = "whsec"
VECTOR_BODY = b'{"version":1,"event":"message"}'
VECTOR_SIG = "3d2a77c9bf41b413af1634205fd6ec52615bc8a15d5f0c4c7239082f4da20e79"


def post(url, body, sig=None, key="k1"):
    raw = json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=raw, method="POST", headers={
        "Content-Type": "application/json",
        "X-DVG-Signature": sig if sig is not None else hmac.new(b"whsec", raw, hashlib.sha256).hexdigest(),
        "Authorization": "Bearer " + key,
    })
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def main():
    passed = 0
    assert webhook_bot.signature_ok(VECTOR_SECRET, VECTOR_BODY, VECTOR_SIG), "시험 벡터를 받아들이지 않음"
    assert not webhook_bot.signature_ok("other", VECTOR_BODY, VECTOR_SIG), "틀린 비밀을 받아들임"
    assert not webhook_bot.signature_ok(VECTOR_SECRET, VECTOR_BODY + b" ", VECTOR_SIG), "바뀐 본문을 받아들임"
    passed += 3

    srv = webhook_bot.serve("127.0.0.1", 0)
    url = f"http://127.0.0.1:{srv.server_address[1]}/hook"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = {"version": 1, "conversationId": "c1", "channel": "phone", "history": [], "simulated": True,
            "departments": [], "ts": 1790000000}
    try:
        st, body = post(url, dict(base, event="message", text="주차"), sig="bad")
        assert st == 401, (st, body)
        st, body = post(url, dict(base, event="message", text="주차"), key="wrong")
        assert st == 401, (st, body)
        passed += 2

        st, body = post(url, dict(base, event="start"))
        assert st == 200 and body == {}, (st, body)
        st, body = post(url, dict(base, event="message", text="주차 어디예요?"))
        assert st == 200 and body["reply"].endswith("?") and "link" not in body, body
        st, body = post(url, dict(base, event="message", text="주차", channel="chat"))
        assert body["link"]["url"].startswith("https://"), body
        st, body = post(url, dict(base, event="message", text="예약 바꾸려고요"))
        assert body["action"] == "transfer" and body["note"], body
        st, body = post(url, dict(base, event="message", text="고마워요"))
        assert body["action"] == "hangup", body
        st, body = post(url, dict(base, event="message", text="무슨 요일 돼요"))
        assert len(body["choices"]) == 3, body
        # 고른 답에는 같은 질문을 되풀이하지 않는다.
        st, body = post(url, dict(base, event="message", text="수요일", choice="수요일"))
        assert "choices" not in body and body["reply"].startswith("수요일"), body
        st, body = post(url, dict(base, event="end", reason="hangup"))
        assert st == 200 and body == {}, (st, body)
        passed += 8
    finally:
        srv.shutdown()
    print(f"ok — {passed}개 통과")


if __name__ == "__main__":
    main()
