"""로컬 DVG 흉내 — 앱 키를 받기 **전에** 내 컴퓨터에서 앱의 대화 흐름을 돌려 본다.

DVG 처럼 서명 헤더를 붙여 앱에 WebSocket 으로 연결하고, 발신자의 말은 여러분이 적은 글로 대신합니다.
앱이 계약(docs/voice-relay-v1.md)의 **형식**을 지키는지 — 메시지 하나에 지시 하나 · 10초 안 응답 · 글자 수 ·
선택지 규칙 · 끝맺음 — 를 그 자리에서 알려 줍니다.

⚠️ 이것은 흉내입니다. 진짜 DVG 와 다른 점(그래서 마지막 확인은 반드시 운영사 DVG 의 `simulate` 로 합니다):
- 주소 풀이(`expect:"address"`)를 하지 않습니다 — 기본은 `address.status:"unavailable"`(«주소 풀이를 못 쓰는 설치»)입니다.
  DVG 가 줄 답을 **직접 적어** 시험할 수 있습니다(아래 «발화 파일»).
- 생년월일(`expect:"birth"`)·전화번호(`expect:"phone"`) 풀이를 하지 않습니다(필요하면 역시 직접 적습니다).
- 선택지는 **글자가 그대로 들어 있을 때만** 고릅니다(초성 추정 없음 — 초성 추정 결과도 직접 적을 수 있습니다).
- 문자(`sms`)는 보내지 않고 `sent` 로만 답합니다.
- 말투 점검은 간이판입니다(쉼표로 이은 나열만 봅니다). 정식 점검은 `simulate` 의 `toneWarning` 입니다.

실행(앱을 먼저 띄운 뒤 다른 창에서):
    pip install -r examples/python/requirements.txt
    DVG_SIGNING_SECRET=test-secret python3 tools/local_dvg.py "강남역" "" "서초동" "착불" "네"

발화를 파일로 줄 수도 있습니다(JSON 배열):
    DVG_SIGNING_SECRET=test-secret python3 tools/local_dvg.py --file my_call.json

발화 파일의 항목은 문자열이거나, **DVG 가 그 발화에 붙일 답을 적은 객체**입니다(계약 §3-2 의 `prompt` 필드):
    ["송파구 신천동",
     {"text": "신천동이요", "address": {"status": "ambiguous", "candidates": [...], "question": "신천동이 여러 곳입니다. 서울. 경기. 배달지는 어느 쪽인가요?"}},
     {"text": "서울이요", "address": {"status": "resolved", "sido": "서울특별시", "gugun": "송파구", "dong": "신천동", "line": "서울 송파구 신천동", "verified": true}},
     {"text": "참불", "choice": "착불", "choiceSource": "initial", "confirm": true}]
⚠️ 적은 값은 흉내가 아니라 **여러분이 정한 답**입니다 — 진짜 DVG 가 그렇게 답하는지는 `simulate` 로 확인하십시오.

주소를 **못 알아들은 경우**를 시험하려면 DVG 가 「주소로 읽지 못함」 이라고 답하게 적습니다([예](calls/address-unknown.json)) —
적지 않으면 «풀이를 쓸 수 없는 설치» 로 답하므로, 그때 원문을 받는 앱은 「어 그게」 도 배달지로 받습니다.

`--chat`(웹 채팅) · `--off-duty`(근무 시간 밖) · `--setup '{…}'`(setup 에 덧붙일 필드)로 setup 을 바꿀 수 있습니다.

`--live` 를 주면 «시험 통화»(`setup.simulated`) 표시 없이 보냅니다 — 앱이 **실제로 주문을 등록**하는 경로까지 돕니다.
🔴 앱의 업무 API 주소를 **개발용(가짜) 서버**로 바꿔 놓고만 쓰십시오. 운영 API 에 붙어 있으면 진짜 주문이 생깁니다.

빈 문자열("")은 «무응답» 입니다. 발화를 다 쓰고 앱이 또 물으면 «발신자가 끊음» 으로 끝납니다.
종료 코드: 0 = 위반·말투 경고 없이 끝남 · 1 = 위반 또는 말투 경고가 있었다(또는 `--expect` 와 다른 결말) · 2 = 연결 실패.
`--expect completed` 처럼 기대 결말을 주면 결말까지 확인합니다 — 엉뚱한 곳에서 사람에게 넘어가도 위반이 아니므로 결말을 함께 보십시오.
"""
import argparse
import asyncio
import hashlib
import hmac
import json
import os
import re
import sys
import time
import urllib.parse

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

REPLY_TIMEOUT = 10        # 계약 §3-1 — DVG 메시지 뒤 10초 안에 지시
MAX_DIRECTIVES = 60       # 계약 §4 — 지시 60회
MAX_ERRORS = 3            # 계약 §3-2 — error 3번 넘으면 사람에게
TEXT_MAX = 500
SMS_MAX_BYTES = 80        # 계약 §3-3 — 문자 80바이트(EUC-KR 기준 한글 약 40자)
SMS_PER_CALL = 4

# 쉼표로 이은 짧은 나열(「강원, 경남, 경북」·「선불인지, 착불인지」) — 전화에서 한 덩어리로 들린다.
_RUN_TOGETHER = re.compile(r"[가-힣A-Za-z0-9]{1,8}(?:인지)?\s*,\s*[가-힣A-Za-z0-9]{1,8}(?:인지)?\s*,")
_INJI_COMMA = re.compile(r"인지\s*,")


def sign(secret, app_id, call_id, ts):
    msg = f"{app_id}\n{call_id}\n{ts}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def tone_warning(text, choices=None):
    if not text:
        return ""
    if _INJI_COMMA.search(text) or _RUN_TOGETHER.search(text):
        return "예시를 쉼표로 이었다 — 낱말마다 마침표로 끊으십시오(「선불. 착불. 어느 쪽인가요?」)"
    for a in choices or []:
        for b in choices or []:
            if a != b and re.search(re.escape(a) + r"\s*,\s*" + re.escape(b), text):
                return "선택지를 쉼표로 이었다 — 낱말마다 마침표로 끊으십시오"
    return ""


# 계약 §3-15 의 예 그대로 — 근무 시간 밖
OFF_DUTY_STAFF = {
    "onDuty": False, "nextOpen": "2026-10-08T09:00:00+09:00", "nextOpenText": "내일 오전 9시", "callback": True,
    "handoffNotice": "지금은 상담 시간이 아니어서 담당자가 바로 받지 못할 수 있어요. 받지 못하면 남겨 주신 내용을 담당자에게 전해 드리고, 내일 오전 9시 이후에 연락드릴게요.",
}

# 발화 파일 객체에 적을 수 있는 키 — 계약 §3-2 의 prompt 필드
CHOICE_KEYS = {"choice", "choiceIndex", "choiceSource", "confirm", "choiceAmbiguous"}
SCRIPT_KEYS = {"text", "address", "birth", "image", "lowConfidence", "spokeDuringPlayback", "heardVoice"} | CHOICE_KEYS
ADDRESS_STATUS = {"resolved", "ambiguous", "partial", "unknown", "unavailable"}


def load_utterances(items):
    """발화 목록 검사 — 틀린 키(오타)는 조용히 무시하지 않고 멈춘다(무시하면 시험이 엉뚱한 것을 시험한다)."""
    if not isinstance(items, list):
        raise SystemExit("발화는 배열이어야 합니다")
    for i, u in enumerate(items, 1):
        if isinstance(u, str):
            continue
        if not isinstance(u, dict) or not isinstance(u.get("text", ""), str):
            raise SystemExit(f"발화 {i}: 문자열이거나 {{\"text\": …}} 객체여야 합니다")
        bad = set(u) - SCRIPT_KEYS
        if bad:
            raise SystemExit(f"발화 {i}: 모르는 키 {sorted(bad)} — 쓸 수 있는 키: {sorted(SCRIPT_KEYS)}")
        a = u.get("address")
        if a is not None and (not isinstance(a, dict) or a.get("status") not in ADDRESS_STATUS):
            raise SystemExit(f"발화 {i}: address.status 는 {sorted(ADDRESS_STATUS)} 중 하나")
    return items


def pick_choice(text, choices):
    hits = [i for i, c in enumerate(choices) if c in text]
    if len(hits) == 1:
        return {"choice": choices[hits[0]], "choiceIndex": hits[0], "choiceSource": "exact"}
    if len(hits) > 1:
        return {"choiceAmbiguous": True}
    return {}


def clean_link(link):
    """계약 §3-20 의 링크 규칙: 이름 1~20자 · https 주소 500자 이하 · 공백·따옴표·꺾쇠 없음. 아니면 None."""
    if not isinstance(link, dict):
        return None
    label = " ".join(str(link.get("label") or "").split())
    url = str(link.get("url") or "").strip()
    if not (1 <= len(label) <= 20) or not url or len(url) > 500 or re.search(r"[\s\"'<>]", url):
        return None
    u = urllib.parse.urlsplit(url)
    if u.scheme.lower() != "https" or not u.hostname or "@" in u.netloc:
        return None
    return {"label": label, "url": url}


class Session:
    def __init__(self, utterances, direction):
        self.utter = [u if isinstance(u, dict) else {"text": u} for u in utterances]
        self.turn = 0
        self.directives = 0
        self.errors = 0
        self.sms = 0
        self.violations = []
        self.tone = 0
        self.narrowing = ""  # 직전 prompt 에 실은 DVG 의 좁히는 질문(address.question)
        self.direction = direction
        self.chat = False  # setup.channel == "chat" 이면 run() 이 켠다(say.link 를 버튼으로 흉내)

    def out(self, who, text):
        print(f"{who} {text}", flush=True)

    def violate(self, why):
        self.violations.append(why)
        self.out("  ❌", why)

    def warn(self, why):
        self.tone += 1
        self.out("  ⚠️", why)

    def next_turn(self, msg):
        self.turn += 1
        msg["turn"] = self.turn
        return json.dumps(msg, ensure_ascii=False)

    def check_text(self, m, required):
        t = m.get("text")
        if t is None or t == "":
            if required:
                return "text_required"
            return ""
        if not isinstance(t, str):
            return "text_required"
        if len(t) > TEXT_MAX:
            return "text_too_long"
        return ""

    def answer(self, m):
        """앱 지시 하나 → (DVG 가 보낼 메시지, 끝 결말 또는 None)."""
        kind = m.get("type")
        if kind == "say":
            code = self.check_text(m, required=True)
            if code:
                return {"type": "error", "code": code, "message": code}, None
            self.out("🤖 AI(안내)", m["text"])
            w = tone_warning(m["text"])
            if w:
                self.warn(w)
            if m.get("link") is not None:
                # 계약 §3-20 — 틀린 링크는 DVG 도 오류 없이 링크만 버리고 말은 그대로 한다.
                link = clean_link(m.get("link"))
                if link is None:
                    self.out("  ℹ️", "say.link 를 버렸습니다(https 주소 · 이름 1~20자가 아님) — 말은 그대로 갑니다")
                elif self.chat:
                    self.out("  🔗", f"[{link['label']}] {link['url']}")
                else:
                    self.out("  🔗", f"(전화에서는 보이지 않습니다) [{link['label']}] {link['url']}")
            return {"type": "said"}, None
        if kind == "ask":
            code = self.check_text(m, required=False)
            if code:
                return {"type": "error", "code": code, "message": code}, None
            choices = m.get("choices")
            expect = m.get("expect")
            if choices is not None:
                ok = (isinstance(choices, list) and 2 <= len(choices) <= 6
                      and all(isinstance(c, str) and 1 <= len(c) <= 20 for c in choices)
                      and len(set(choices)) == len(choices))
                if not ok:
                    return {"type": "error", "code": "bad_choices", "message": "choices 는 2~6개 · 각 1~20자 · 중복 없음"}, None
            if expect is not None:
                if expect not in ("address", "phone", "birth"):
                    return {"type": "error", "code": "bad_expect", "message": "expect 는 address·phone·birth"}, None
                if choices and expect != "birth":
                    return {"type": "error", "code": "bad_expect", "message": "choices 와 expect 는 함께 쓸 수 없다"}, None
            keyterms = m.get("keyterms")
            if keyterms is not None:
                # 계약 §3-19 — 최대 10개 · 각 2~20자 · 중복 없음(앞뒤 공백은 떼고 센다). 힌트 적용 자체는 흉내 내지 않는다.
                kts = [k.strip() for k in keyterms if isinstance(k, str)] if isinstance(keyterms, list) else None
                ok = (kts is not None and len(kts) == len(keyterms) and len(kts) <= 10
                      and all(2 <= len(k) <= 20 for k in kts) and len(set(kts)) == len(kts))
                if not ok:
                    return {"type": "error", "code": "bad_keyterms", "message": "keyterms 는 10개까지 · 각 2~20자 · 중복 없음"}, None
            text = m.get("text") or ""
            if self.narrowing and expect == "address" and text != self.narrowing:
                self.violate("DVG 의 좁히는 질문(address.question)을 글자 그대로 묻지 않았다 — 그래야 다음 답을 좁혀 준다(계약 §3-5)")
            self.narrowing = ""
            label = "🤖 AI(질문)" + (f" [선택지 {' / '.join(choices)}]" if choices else "") + (f" [expect {expect}]" if expect else "")
            self.out(label, text or "(말없이 듣기)")
            w = tone_warning(text, choices)
            if w:
                self.warn(w)
            if not self.utter:
                self.out("📞 발신자", "(끊음 — 준비한 발화를 다 썼습니다)")
                return None, "caller_hangup"
            item = self.utter.pop(0)
            said = item.get("text", "")
            scripted = {k: v for k, v in item.items() if k != "text"}
            self.out("🙋 발신자", (said if said else "(무응답)") + ("  [적어 둔 DVG 답: " + ", ".join(sorted(scripted)) + "]" if scripted else ""))
            p = {"type": "prompt", "text": said, "silence": said == "", "lowConfidence": False,
                 "spokeDuringPlayback": False, "heardVoice": said != ""}
            if choices and said and not (CHOICE_KEYS & scripted.keys()):
                p.update(pick_choice(said, choices))
            if "address" in scripted and expect != "address":
                # 진짜 DVG 는 expect:"address" 가 없는 질문에 주소 풀이를 싣지 않는다
                self.violate("이 발화에 주소 답을 적어 두었는데 앱이 expect:\"address\" 없이 물었다 — 주소는 expect:\"address\" 로 물으십시오")
                scripted.pop("address")
            if CHOICE_KEYS & scripted.keys() and not choices:
                self.violate("이 발화에 선택지 답을 적어 두었는데 앱이 choices 없이 물었다")
                for k in CHOICE_KEYS:
                    scripted.pop(k, None)
            if "birth" in scripted and expect != "birth":
                self.violate("이 발화에 생년월일 답을 적어 두었는데 앱이 expect:\"birth\" 없이 물었다")
                scripted.pop("birth")
            if expect == "address" and "address" not in scripted:
                p["address"] = {"status": "unavailable", "reason": "local_dvg"}  # 적어 두지 않았으면 «풀이를 못 쓰는 설치»
            p.update(scripted)
            a = p.get("address")
            if isinstance(a, dict) and a.get("status") == "ambiguous" and a.get("question"):
                self.narrowing = a["question"]
            return p, None
        if kind == "sms":
            t = m.get("text") or ""
            if not t:
                return {"type": "error", "code": "text_required", "message": "text_required"}, None
            self.sms += 1
            try:
                n = len(t.encode("euc-kr", errors="replace"))
            except LookupError:
                n = len(t.encode("utf-8"))
            if n > SMS_MAX_BYTES:
                self.violate(f"문자 {n}바이트 — 80바이트(한글 약 40자) 이하여야 합니다")
            if self.sms > SMS_PER_CALL:
                self.violate(f"문자 {self.sms}통 — 한 통화 {SMS_PER_CALL}통까지입니다")
            self.out("✉️ 문자", t)
            return {"type": "sms_result", "status": "sent"}, None
        if kind == "prepare":
            texts = m.get("texts")
            if (not isinstance(texts, list) or not 1 <= len(texts) <= 8
                    or not all(isinstance(t, str) and 1 <= len(t) <= 200 for t in texts)):
                return {"type": "error", "code": "bad_prepare", "message": "texts 는 1~8문장 · 각 200자 이하"}, None
            return {"type": "prepared", "accepted": 0}, None  # 시험 통화는 합성하지 않는다(계약 §3-13)
        if kind == "transfer":
            if "to" in m or "number" in m:
                self.violate("transfer 에 번호를 넣었다 — 번호는 지정할 수 없습니다(운영사가 정한 번호로만 갑니다)")
            note = m.get("note")
            self.out("🧑‍💼 사람에게 연결", f"메모: {note}" if note else "")
            return None, "transferred"
        if kind == "hangup":
            self.out("👋 끊기", m.get("text") or "")
            return None, "completed"
        return {"type": "error", "code": "unknown_type", "message": f"모르는 type: {kind!r}"}, None


async def run(url, app_id, secret, utterances, direction, settings, expect=None, live=False, caller="01000000000",
              setup_extra=None):
    call_id = f"{int(time.time())}.local"
    ts = str(int(time.time()))
    headers = {
        "X-DVG-App-Id": app_id, "X-DVG-Call-Id": call_id, "X-DVG-Timestamp": ts,
        "X-DVG-Signature": sign(secret, app_id, call_id, ts), "X-DVG-Relay-Version": "1",
    }
    s = Session(utterances, direction)
    s.chat = (setup_extra or {}).get("channel") == "chat"
    try:
        ws = await asyncio.wait_for(connect(url, additional_headers=headers), timeout=6)
    except InvalidStatus as e:
        print(f"연결 거절 — HTTP {e.response.status_code} (서명 비밀이 앱과 같은지 확인하십시오)", file=sys.stderr)
        return 2
    except (OSError, asyncio.TimeoutError) as e:
        print(f"연결 실패 — {url} ({type(e).__name__}) · 앱을 먼저 띄웠는지 확인하십시오", file=sys.stderr)
        return 2

    setup = {"type": "setup", "version": 1, "callId": call_id, "tenantId": "local", "orgId": "local-org",
             "appId": app_id, "did": "07000000000", "noticePlayed": True, "direction": direction}
    if not live:
        setup["simulated"] = True  # 시험 통화 — 앱은 실제 주문을 만들지 않아야 한다
    if caller:
        setup["caller"] = caller
    if settings:
        setup["settings"] = settings
    if setup_extra:
        setup.update(setup_extra)
    reason = None
    async with ws:
        await ws.send(s.next_turn(setup))
        while reason is None:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=REPLY_TIMEOUT)
            except asyncio.TimeoutError:
                s.violate(f"{REPLY_TIMEOUT}초 안에 지시가 오지 않았다 — 실통화에서는 사람에게 넘어갑니다(app_error)")
                reason = "app_error"
                break
            except ConnectionClosed:
                s.violate("앱이 연결을 먼저 닫았다 — 실통화에서는 사람에게 넘어갑니다(app_error)")
                reason = "app_error"
                break
            try:
                m = json.loads(raw)
                if not isinstance(m, dict):
                    raise ValueError("객체가 아님")
            except ValueError:
                s.violate("JSON 이 아닌 메시지를 보냈다 — 실통화에서는 사람에게 넘어갑니다(app_error)")
                reason = "app_error"
                break
            s.directives += 1
            if s.directives > MAX_DIRECTIVES:
                s.violate(f"지시 {MAX_DIRECTIVES}회를 넘었다 — 실통화에서는 사람에게 넘어갑니다(limit)")
                reason = "limit"
                break
            if m.get("unrecognized"):
                s.out("  📚 못 알아들은 대답으로 알림(unrecognized)", " / ".join(str(x) for x in m["unrecognized"]))
            reply, reason = s.answer(m)
            if reply is not None:
                if reply.get("type") == "error":
                    s.errors += 1
                    s.violate(f"지시 오류 {reply['code']} — {reply.get('message', '')}")
                    if s.errors > MAX_ERRORS:
                        reason = "app_error"
                        break
                await ws.send(s.next_turn(reply))
        try:
            await ws.send(s.next_turn({"type": "end", "reason": reason}))
        except ConnectionClosed:
            pass
    print(f"\n결말: {reason} · 지시 {s.directives}회 · 위반 {len(s.violations)}건 · 말투 경고 {s.tone}건", flush=True)
    if s.utter and reason in ("completed", "transferred"):
        print(f"(쓰지 않은 발화 {len(s.utter)}개)", flush=True)
    if expect and reason != expect:
        print(f"❌ 기대한 결말은 {expect} 인데 {reason} 로 끝났다", flush=True)
        return 1
    return 1 if s.violations or s.tone else 0


def main():
    ap = argparse.ArgumentParser(description="로컬 DVG 흉내 — 앱의 대화 흐름 점검")
    ap.add_argument("utterances", nargs="*", help="발신자 발화(순서대로) · 빈 문자열은 무응답")
    ap.add_argument("--file", help="발화 JSON 배열 파일")
    ap.add_argument("--url", default=os.environ.get("DVG_LOCAL_URL", "ws://127.0.0.1:19999/relay"))
    ap.add_argument("--app-id", default=os.environ.get("DVG_APP_ID", "local-app"))
    ap.add_argument("--outbound", action="store_true", help="DVG 가 건 통화(setup.direction=outbound)로 흉내")
    ap.add_argument("--expect", choices=["completed", "transferred", "caller_hangup"],
                    help="기대 결말 — 다르면 종료 코드 1(명세서의 대화 예마다 적어 두면 회귀 시험이 된다)")
    ap.add_argument("--live", action="store_true",
                    help="시험 통화 표시(simulated) 없이 보낸다 — 실제 등록 경로까지 돈다. 🔴 개발용 업무 API 에만")
    ap.add_argument("--caller", default="01000000000", help="setup.caller(발신번호) · 빈 값이면 싣지 않는다(«발신번호 제공 안 함»)")
    ap.add_argument("--chat", action="store_true",
                    help="웹 채팅으로 흉내(setup.channel=chat · 발신번호·걸려 온 번호 없음) — 앱은 주문을 만들지 않고 transfer 해야 한다")
    ap.add_argument("--off-duty", action="store_true",
                    help="상담원 근무 시간 밖으로 흉내(setup.staff · 계약 §3-15 의 예 그대로)")
    ap.add_argument("--setup", help='setup 에 덧붙일 JSON(계약 §3-2 필드 · 예: \'{"staff":{"onDuty":true}}\')')
    ap.add_argument("--settings", help='설치별 설정 JSON(예: \'{"shopName":"꽃마을"}\')')
    a = ap.parse_args()
    secret = os.environ.get("DVG_SIGNING_SECRET") or os.environ.get("DVG_APP_SIGNING_SECRET")
    if not secret:
        raise SystemExit("DVG_SIGNING_SECRET 이 비어 있습니다 — 앱에 넣은 것과 같은 값을 넣으십시오")
    utter = list(a.utterances)
    if a.file:
        with open(a.file, encoding="utf-8") as f:
            utter = json.load(f)
    utter = load_utterances(utter)
    settings = json.loads(a.settings) if a.settings else None
    extra = {}
    caller = a.caller
    if a.chat:
        extra.update({"channel": "chat", "did": ""})
        caller = ""  # 채팅에는 발신번호가 없다(계약 §3-17)
    if a.off_duty:
        extra["staff"] = OFF_DUTY_STAFF
    if a.setup:
        more = json.loads(a.setup)
        if not isinstance(more, dict):
            raise SystemExit("--setup 은 JSON 객체여야 합니다")
        extra.update(more)
    if a.live:
        print("⚠️ --live: 시험 통화 표시 없이 보냅니다 — 앱이 실제로 주문을 등록합니다. 앱이 개발용 업무 API 에 붙어 있는지 확인하십시오.\n", flush=True)
    sys.exit(asyncio.run(run(a.url, a.app_id, secret, utter, "outbound" if a.outbound else "inbound",
                             settings, a.expect, a.live, caller, extra)))


if __name__ == "__main__":
    main()
