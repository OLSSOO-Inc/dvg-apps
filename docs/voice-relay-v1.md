# DVG 관리형 음성 레이어 v1 — 앱 개발사용 계약

> 대상: DVG 위에서 **음성 자동 주문** 같은 대화 서비스를 만드는 개발사. DVG 게이트웨이 **1.4.16.257+**.
> ⭐ 처음이면 [시작하기](getting-started.md)부터(예제 앱 · 같은 서버 배포 · 시험).

## 1. 무엇을 해 주나

DVG 가 **전화·음성인식(STT)·음성합성(TTS)** 을 맡고, 앱은 **텍스트로만** 대화를 이끕니다.

| DVG 가 한다 | 앱이 한다 |
|---|---|
| 전화 받기 · 링백 · 사람 연결 | 무엇을 물을지 정하기 |
| STT(한국어 전화 음성 도메인 힌트 포함) · TTS | 답을 해석하고 업무 시스템(예: 주문·배송 관리 API)에 조회·등록 |
| 끼어들기·에코 대조·무음 판정 | 대화를 끝낼지·사람에게 넘길지 판단 |
| **AI 고지**(법적 의무 — 앱이 끌 수 없음) | — |
| 사용량 계량(청구 근거) | — |

## 2. 연결

통화가 오면 **DVG 가 앱에 WebSocket 으로 연결합니다**(앱이 서버). 주소는 운영자가 앱 등록 때 넣은 `relayUrl`(`ws://` 또는 `wss://`)입니다.

⚠️ **연결은 벨이 울리는 동안(응답 전) 시도합니다.** 6초 안에 붙지 못하면 발신자는 **사람에게** 연결됩니다.

### 2-1. DVG 가 건 연결인지 확인하기(필수)

| 헤더 | 값 |
|---|---|
| `X-DVG-App-Id` | 앱 id |
| `X-DVG-Call-Id` | 통화 id |
| `X-DVG-Timestamp` | 유닉스 초 |
| `X-DVG-Signature` | `hex(HMAC-SHA256(signingSecret, appId + "\n" + callId + "\n" + timestamp))` |
| `X-DVG-Relay-Version` | `1` |

- `signingSecret` 은 앱 등록·키 회전 때 **한 번만** 전달됩니다(앱 키와 **다른 값**).
- 🔴 **타임스탬프가 ±300초를 벗어나면 거절하십시오**(재생 공격 방지).
- 검증 예(Python — DVG 서명과 같은 값이 나오는 것을 확인했습니다):

```python
import hmac, hashlib, time

def verify_dvg(headers, signing_secret, now=None, skew=300):
    app_id = headers.get("X-DVG-App-Id", "")
    call_id = headers.get("X-DVG-Call-Id", "")
    ts = headers.get("X-DVG-Timestamp", "")
    sig = headers.get("X-DVG-Signature", "")
    if not (app_id and call_id and ts.isdigit() and sig):
        return False
    now = int(time.time()) if now is None else now
    if abs(now - int(ts)) > skew:
        return False
    msg = f"{app_id}\n{call_id}\n{ts}".encode()
    want = hmac.new(signing_secret.encode(), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, sig)
```

#### 시험 벡터(구현이 맞는지 확인)

| 입력 | 값 |
|---|---|
| `signingSecret` | `test-signing-secret` |
| `X-DVG-App-Id` | `demo-order-app` |
| `X-DVG-Call-Id` | `1790000000.42` |
| `X-DVG-Timestamp` | `1790000000` |
| **기대 `X-DVG-Signature`** | `8f5176f9494aea0ff84847a5d2a80fdac8b90de4d44633d841d4cff3b1133f9a` |

같은 값이 나오지 않으면 구분자(`\n`)·인코딩(UTF-8)·16진 소문자를 확인하십시오. 이 저장소의 CI 가 두 예제로 이 벡터를 검사합니다([conformance/](../conformance/)).

## 3. 메시지

모든 메시지는 JSON 텍스트 프레임이고 `type` 과 `turn`(DVG 쪽 차례 번호)을 가집니다. 모르는 필드는 **무시**하십시오(필드는 버전을 올리지 않고 늘어날 수 있습니다).

### 3-1. 흐름 — 엄격한 요청·응답

```
DVG → 앱   setup
앱  → DVG  say | ask | sms | transfer | hangup     ← DVG 메시지 하나당 지시 하나
DVG → 앱   said | prompt | sms_result | error
…
DVG → 앱   end
```

🔴 **DVG 가 메시지를 보낸 뒤 10초 안에 다음 지시를 보내야 합니다.** 넘기면 통화는 사람에게 넘어갑니다(`app_error`).

### 3-2. DVG → 앱

| type | 필드 | 뜻 |
|---|---|---|
| `setup` | `version` · `callId` · `tenantId` · `orgId` · `appId` · `did` · `noticePlayed` · `direction` · `caller`(조건부) · `simulated`(조건부) · `settings`(조건부) | 통화 시작. `direction` 은 `"inbound"`(상대가 걸어왔다) 또는 `"outbound"`(DVG 가 걸었다 · gw 1.4.16.292+) — **없으면 수신**(구버전 DVG). `caller` 는 **운영자가 설치에서 발신번호 제공을 켰을 때만** 있고, 발신 통화에서도 **상대 번호**입니다(키 자체가 없으면 «제공하지 않음»). 🔴 **`simulated:true` 는 전화 없는 시험**(gw 1.4.16.259) — 그때는 **실제 주문을 만들지 마십시오**(실통화에서는 키가 없습니다) |
| `said` | — | `say` 재생이 끝났다 |
| `prompt` | `text` · `silence` · `lowConfidence` · `spokeDuringPlayback` · `heardVoice`(gw 1.4.16.261 — 소리는 있었는데 말로 인식되지 않았다 · 무응답과 «말했는데 못 알아들음» 을 가른다) · (선택지를 줬으면) `choice` · `choiceIndex` · `choiceSource` · `confirm` · `choiceAmbiguous` · (`expect:"address"` 였으면) `address` · (긴 듣기를 **적용했으면**) `listenSeconds` · (일찍 닫기를 **적용했으면**) `endSilenceSeconds` | `ask` 뒤 발신자가 한 말. `silence:true` 면 아무 말도 없었다. 선택지 판정은 §3-4, 주소는 §3-5 |
| `sms_result` | `status` · `code`(선택) | `sms` 결과(gw 1.4.16.307+ · §3-9). 🔴 **실패여도 오류가 아닙니다**(위반 횟수에 세지 않습니다) |
| `error` | `code` · `message` | 지시가 잘못됐다 — `unknown_type` · `text_required` · `text_too_long` · `bad_choices` · `bad_expect` · `bad_listen_seconds` · `bad_end_silence_seconds`. **3번 넘으면** 통화가 사람에게 간다 |
| `end` | `reason` | 세션 끝(§4 결말). 이 뒤로는 보내도 소용없습니다. DVG 는 `end` 뒤에 **WebSocket close(1000)** 로 연결을 닫습니다(DVG 1.4.16.275+). ⚠️ **`end` 없이 연결이 닫혀도 통화는 끝난 것입니다** — 앞에 프록시(Cloud Run 등)가 있으면 `end` 가 오기 전에 닫힐 수 있고, DVG 1.4.16.274 이하는 close 프레임 없이 끊습니다. 그때 결말은 **모른다**로 두십시오(예제 앱은 `reason:"closed"`) |

### 3-3. 앱 → DVG

| type | 필드 | 동작 |
|---|---|---|
| `say` | `text`(필수 · 500자 이하) · `interruptible`(선택 · gw 1.4.16.261) | 끝까지 말한다(끼어들어도 멈추지 않음) → `said`. `interruptible:true` 면 **발신자가 끼어들 때 멈춘다**(듣지는 않는다 — 이어서 `ask{text:""}` 로 듣는다). ⚠️ 복창·결제 안내처럼 **끝까지 들려야 하는 말에는 쓰지 마십시오** |
| `ask` | `text`(선택 · 500자 이하) · `choices`(선택 · 2~6개 · 각 1~20자 · 중복 없음) · `expect`(선택 · `"address"`) · `label`(선택 · `expect` 와 함께 · 1~10자) · `listenSeconds`(선택 · 5~90 · §3-7) · `endSilenceSeconds`(선택 · 2~10 · `listenSeconds` 와 함께만 · §3-7) | 질문을 말하고(발신자가 끼어들면 멈춤) **발신자 답을 듣는다** → `prompt`. `text` 가 비면 말없이 듣기만 한다. `choices` 가 규칙에 어긋나면 **묻지 않고** `error bad_choices`. `expect` 는 §3-5(`choices` 와 함께 쓰면 `bad_expect`) |
| `sms` | `text`(필수 · **80바이트** 이하 — 한글 약 40자) | **통화 상대에게 문자 한 통**(gw 1.4.16.307+ · §3-9) → `sms_result`. 🔴 받는 사람은 지정할 수 없습니다 |
| `transfer` | — | **사람에게 연결**. 🔴 번호는 지정할 수 없습니다 — 그 주문 회사에 운영자가 정한 호전환 번호로 갑니다 |
| `hangup` | `text`(선택 · 마지막 인사) | 인사 후 통화 종료 |

⭐ **모든 지시에 `slots`(선택 · gw 1.4.16.307+)를 실을 수 있습니다** — §3-10. 운영자 화면에 «지금까지 모은 칸» 을 보여 주는 용도이고 동작은 바뀌지 않습니다.

### 3-4. 선택지(`ask.choices`) — gw 1.4.16.260+

답이 몇 개로 정해진 질문(결제 «선불/착불», 확인 «네/아니요» 등)은 `choices` 를 함께 보내면 DVG 가 답을 **그중 하나로 읽어** `prompt.choice` 에 싣습니다. `text` 는 그대로 있습니다(발화 원문).

| `choiceSource` | 뜻 | 앱이 할 일 |
|---|---|---|
| `exact` | 발화에 선택지 낱말이 들어 있었다(「착불이요」) | 그대로 쓴다 |
| `initial` + `confirm:true` | 짧게 뭉개진 답을 **첫 음절 초성**으로 추정했다(「참불」 → 착불) | 🔴 **반드시 복창해 확인받는다**(「결제 착불. 맞으면 「네」.」) |
| (`choice` 없음) + `choiceAmbiguous:true` | 선택지 둘 이상이 들어 있었다(「선불 아니고 착불」) | **다시 묻는다**(DVG 는 짐작으로 고르지 않는다) |
| (`choice` 없음) | 못 골랐다 | 다시 묻거나 사람에게 |

- ⭐ **판정은 DVG 내장 주문 엔진과 같은 함수**입니다(한국어 전화 음성에서 실측된 규칙).
- 🔴 **초성 추정은 좁게 걸립니다** — 선택지들이 **같은 꼬리 초성**을 가질 때만(예: 선**불**/착**불**). 「네/아니요」 처럼 꼬리가 다르면 초성 추정은 **하지 않고** 정확 일치만 봅니다(그렇지 않으면 「나중에요」 가 «네» 가 됩니다).
- ⚠️ 한 글자 선택지(「네」)는 **낱말 앞머리**에서만 인정합니다(「서초동네」 가 «네» 가 되지 않게).
- ⚠️ **음성인식 힌트는 질문마다 바꿀 수 없습니다**(연결을 맺을 때 정해진다). 앱이 물을 선택지는 운영자에게 요청해 **앱 등록의 «음성인식 힌트 낱말»** 에 넣으십시오.

### 3-5. 주소(`ask.expect:"address"`) — gw 1.4.16.265+

주소를 묻는 `ask` 에 `"expect":"address"` 를 실으면 DVG 가 발신자의 답을 **시·도 / 구·군 / 동**으로 풀어 `prompt.address` 에 싣습니다.
행정구역 사전·동 색인·장소 사전(장례식장 등)·건물명 검색과 **좁히는 질문**까지 DVG 가 맡습니다 — 앱은 행정구역 사전을 만들 필요가 없습니다.
`label` 은 좁히는 질문에서 이 칸을 부를 이름입니다(「배달지」·「받는 곳」 — 기본 「주소」).

| `address.status` | 뜻 | 앱이 할 일 |
|---|---|---|
| `resolved` | 3단이 정해졌다 | 복창해 확인받고 쓴다. 🔴 `verified:false` 면 **반드시** 복창(행정구역 색인에 없는 이름 — 행정동·리일 수도, 오인식일 수도) |
| `ambiguous` | 같은 이름이 여러 곳에 있다 — `candidates` · `question` | ⭐ **`question` 을 글자 그대로** 다시 `ask`(`expect:"address"`) 하십시오. 그러면 DVG 가 기억해 둔 후보로 다음 답(「서울이요」)을 좁힙니다. `question` 이 없으면(후보가 너무 많음) 다르게 묻거나 사람에게. ⚠️ `source:"near_dong"`(gw 1.4.16.293+)이면 **말한 구·군에 그 동이 없어** 그 구·군 안의 비슷한 동을 묻는 것이고, 후보는 **동**(`candidates[].dong`)이며 **하나일 수도** 있다(확인 질문 — 「향동동이 맞으면 「맞아요」라고…」). 할 일은 같다 — `question` 을 그대로 다시 묻는다 |
| `partial` | 일부만 들었다 — `missing`(`sido`·`gugun`·`dong`) | 빠진 칸을 **다른 문장으로** 묻는다(같은 질문 반복 금지) |
| `unknown` | 주소로 읽지 못했다 — `reason` | 다른 문장으로 한 번 더 묻거나 사람에게 |
| `unavailable` | 이 설치에서 주소 풀이를 쓸 수 없다 | `text`(발화 원문)로 처리한다 |

| 필드 | 뜻 |
|---|---|
| `sido` · `gugun` · `dong` | 정식 이름(`서울특별시` · `송파구` · `신천동`). 세종특별자치시는 `gugun` 이 없다 |
| `detail` | 동 뒤에 들은 말(번지·층·호수) — **정규화하지 않은 발화 조각** |
| `name` | 장소·건물 이름으로 찾았을 때 그 이름 |
| `line` | 복창용 한 줄(`서울 송파구 신천동`) |
| `source` | 근거 — `spoken`(발화에 다 있었다) · `dong_index` · `gugun_index` · `venue`(장소 사전) · `building`(건물명 검색) · `narrowed`(좁히는 답) · `near_dong`(말한 구·군에 없는 동 — 비슷한 동을 묻는다) |
| `verified` | 그 조합이 **행정구역 색인에 실재**하는가 |
| `candidates` · `question` | `ambiguous` 일 때 |
| `missing` · `reason` | `partial` · `unknown`/`unavailable` 일 때 |
| `coord` · `coordStatus` | 좌표(아래) |

- 🔴 **DVG 는 여러 곳 중 하나를 고르지 않습니다** — 잘못 고른 주소는 기사가 다른 도시로 가는 값입니다.
- ⭐ **잘못 들린 동**(gw 1.4.16.293+) — 「고양시 덕양구 상동동」처럼 말한 구·군에 없는 동이면 DVG 가 「고양시 덕양구에서
  상동동을 찾지 못했습니다. 배달지가 삼송동인지, 향동동인지 말씀해 주세요.」를 준다(`source:"near_dong"`). 발신자가
  구·군을 따로 답한 경우(「상동동이요」 → 좁히는 질문 → 「아니요 경기도 고양시요」)도 앞 질문의 동과 합쳐 같은 질문을 준다.
  「아니요」라고 답하면 같은 목록을 다시 주지 않는다 — 그때 앱은 다른 문장으로 묻는다.
- ⚠️ **좁히기는 바로 그 질문에만** 걸립니다 — 앱이 다른 문장으로 물으면(다음 칸 등) 새 주소로 읽습니다. 무음 뒤에 같은 질문을 다시 해도 후보는 남아 있습니다.
- ⚠️ 한 답에 두 곳(「강남에서 서초로」)이면 `unknown` + `reason:"multiple_places"` — 칸마다 따로 물으십시오.

**좌표(선택)** — 앱마다 자기 좌표 체계(자체 지오코더·배차 시스템)가 있을 수 있어 **기본으로는 좌표를 싣지 않습니다.** DVG 좌표가 필요하면
운영사에 **앱 등록의 「좌표 제공」** 을 요청하십시오. 켜진 앱에는 `resolved` 일 때 `coord:{lon, lat, source}`(WGS84 십진 도)와 `coordStatus`
(`ok` · `ambiguous` · `unknown` · `unavailable`)가 붙습니다. ⚠️ **좌표는 동 단위**(번지 반영 없음)이고 출처(`source`)를 밝힙니다.
못 얻으면 **좌표 없이** 주소만 갑니다 — 좌표를 필수로 쓰는 앱은 `coord` 가 없을 때의 처리를 두십시오.

### 3-6. 대화 예 — 꽃 배달 한 통(JSON 전부)

`→` 는 DVG 가 앱에, `←` 는 앱이 DVG 에 보내는 메시지입니다(`turn` 은 생략).

```json
→ {"type":"setup","version":1,"callId":"1790000000.42","tenantId":"…","orgId":"flower-01","appId":"flower-app","did":"07012345678","noticePlayed":true}
← {"type":"say","text":"꽃 배달 주문을 도와드리겠습니다."}
→ {"type":"said"}
← {"type":"ask","text":"꽃을 어디로 보내 드릴까요?","expect":"address","label":"배달지"}
→ {"type":"prompt","text":"신천동이요","silence":false,"lowConfidence":false,"spokeDuringPlayback":false,"heardVoice":true,
   "address":{"status":"ambiguous","source":"dong_index",
              "candidates":[{"sido":"경기도","gugun":"시흥시"},{"sido":"경상북도","gugun":"경산시"},{"sido":"대구광역시","gugun":"동구"},{"sido":"서울특별시","gugun":"송파구"},{"sido":"울산광역시","gugun":"북구"}],
              "question":"신천동이 여러 곳입니다. 배달지가 경기인지, 경북인지, 대구인지, 서울인지, 울산인지 말씀해 주세요."}}
← {"type":"ask","text":"신천동이 여러 곳입니다. 배달지가 경기인지, 경북인지, 대구인지, 서울인지, 울산인지 말씀해 주세요.","expect":"address","label":"배달지"}
→ {"type":"prompt","text":"서울이요","silence":false,"lowConfidence":false,"spokeDuringPlayback":false,"heardVoice":true,
   "address":{"status":"resolved","sido":"서울특별시","gugun":"송파구","dong":"신천동","line":"서울 송파구 신천동","source":"narrowed","verified":true}}
← {"type":"ask","text":"꽃다발인지, 꽃바구니인지, 화환인지 말씀해 주세요.","choices":["꽃다발","꽃바구니","화환"]}
→ {"type":"prompt","text":"꽃바구니로 할게요","silence":false,"lowConfidence":false,"spokeDuringPlayback":false,"heardVoice":true,"choice":"꽃바구니","choiceIndex":1,"choiceSource":"exact"}
← {"type":"ask","text":"배달지 서울 송파구 신천동. 상품 꽃바구니. 맞으면 「네」. 틀리면 「아니요」.","choices":["네","아니요"]}
→ {"type":"prompt","text":"네","silence":false,"lowConfidence":false,"spokeDuringPlayback":false,"heardVoice":true,"choice":"네","choiceIndex":0,"choiceSource":"exact"}
← {"type":"hangup","text":"주문이 접수되었습니다. 감사합니다."}
→ {"type":"end","reason":"completed"}
```

⭐ 이 대화는 [예제 슬롯 엔진](../examples/python/slot_app.py)의 [꽃 배달 시나리오](../examples/python/scenarios/flower.json)가 **DVG 실제 relay·주소 풀이 코드**와
실제로 주고받은 메시지입니다(발화는 글자로 넣은 시험 · 줄을 나누고 `turn` 을 뺐습니다). ⚠️ `setup` 은 실통화 모양으로 적었습니다 —
전화 없는 시험에서는 `simulated:true` 가 붙고 `tenantId`·`orgId`·`did` 가 비어 있을 수 있습니다.

### 3-7. 긴 듣기(`ask.listenSeconds`) — gw 1.4.16.291+

보통의 `ask` 는 발신자가 말을 멈추고 **잠깐 조용하면** 답이 끝난 것으로 봅니다. 그래서 「생각나는 과일 이름을 말씀해 주세요」처럼
**생각하며 쉬는 것이 정상인 질문**은 첫 낱말 뒤 잠깐 쉬는 순간 답이 잘립니다. 그런 질문에는 `listenSeconds` 를 실으십시오 —
DVG 가 그 시간(**5~90초**) 동안 쉼으로 끊지 않고 말을 모아 **한 번에** `prompt.text` 로 줍니다.

```json
{"type":"ask","text":"30초 동안 생각나는 과일 이름을 말씀해 주세요. 시작하세요.","listenSeconds":30}
```

- 창이 끝나는 순간 말하는 중이면 그 말이 끝날 때까지 잠깐 더 기다립니다(마지막 낱말이 잘리지 않게).
- ⭐ **적용했으면 `prompt.listenSeconds` 에 같은 값이 돌아옵니다.** 키가 없으면 **적용되지 않은 것**입니다(이 기능이 없는 DVG
  버전 등) — 그때 답은 잘렸을 수 있으니 점수를 매기는 앱은 «측정 못 함» 으로 다루십시오.
- 아무 말도 없으면 `silence:true`(소리는 있었는데 인식되지 않았으면 `heardVoice:true`).
- `choices`·`expect` 와 함께 쓸 수 없습니다(`bad_listen_seconds`). 범위 밖도 같은 오류입니다.
- ⚠️ 창이 길수록 통화 시간(=음성인식 비용)이 늘어납니다. 꼭 필요한 질문에만 쓰십시오.
- 🧪 시험(§5-1)은 글자 시험이라 시간이 흐르지 않습니다 — 발화 하나가 그 창 전체에 한 말로 취급됩니다.

#### 말씀이 끝나면 일찍 닫기(`endSilenceSeconds`) — gw 1.4.16.304+

`listenSeconds` 만 실으면 DVG 는 발신자가 말을 일찍 마쳐도 **창이 끝날 때까지** 기다립니다. 「요즘 가 보고 싶은 곳이
있으세요?」처럼 **충분히 기다려 주되 말이 끝나면 바로 받아야 하는** 대화 질문에는 `endSilenceSeconds` 를 함께 실으십시오 —
발신자가 **한 마디라도 한 뒤** 그 시간만큼 조용하면 창보다 일찍 닫고 답을 줍니다.

```json
{"type":"ask","text":"요즘 가 보고 싶은 곳이 있으세요?","listenSeconds":20,"endSilenceSeconds":3}
```

- 실제 전화에서 생긴 일: 발신자는 5초 만에 답을 마쳤는데 20초 창이 끝날 때까지 아무 말이 없어 「듣고 있어? 나 말 끝났다고.」가 나왔습니다.
- **2~10초** · `listenSeconds` 보다 짧아야 하고 `listenSeconds` 없이 쓸 수 없습니다(`bad_end_silence_seconds`).
- ⚠️ **아무 말도 없으면 일찍 닫지 않습니다** — 생각하시는 중일 수 있어서입니다. 무응답은 창이 끝날 때 `silence:true` 입니다.
- ⚠️ 너무 짧으면 숨 고르는 사이에 잘립니다(그것이 긴 듣기를 만든 이유입니다). 「1분 동안 이름 말하기」처럼 **끝까지 모아야 하는
  과제에는 넣지 마십시오.**
- ⭐ 적용했으면 `prompt.endSilenceSeconds` 에 같은 값이 돌아옵니다. 키가 없으면 적용되지 않은 것이고(구버전 DVG) 창 끝까지 기다린 것입니다.

### 3-8. 설치별 설정(`setup.settings`) — gw 1.4.16.296+

같은 앱이라도 **회사(설치)마다** 다른 값이 필요할 때가 있습니다(예: 안부 전화가 첫마디에 밝힐 **기관 이름**).
앱은 **항목**을 정하고, 운영자는 DVG 대시보드에서 회사마다 **값**을 넣습니다.

- **항목은 앱 등록 때 운영자에게 알려 주십시오** — 키 · 이름 · 기본값(예: `callerName` · 「기관 이름」 · 「○○구 보건소」).
  운영자가 앱 등록에 그대로 넣습니다(키는 영문으로 시작하는 영문·숫자·`_` 32자 이하 · 10개까지).
- 통화마다 `setup.settings` 에 **실효값**이 옵니다 — 그 회사에 넣은 값, 없으면 기본값:

```json
{"type":"setup","version":1,"callId":"1790779616.2118","orgId":"…","appId":"…","direction":"outbound","settings":{"callerName":"○○구 보건소"}}
```

- ⭐ **키가 없으면 «정하지 않음»** 입니다(값도 기본값도 없음 · 또는 이 기능이 없는 DVG 버전) — 앱이 자기 기본값을 쓰십시오.
- 🔴 **비밀을 넣는 자리가 아닙니다** — 값은 운영자 화면과 이 메시지에 그대로 보입니다. 키·토큰은 앱의 환경변수로 받으십시오.
- 값은 앞뒤 공백이 지워지고 줄바꿈이 없습니다(DVG 가 거절합니다). 길이는 항목마다 정한 한도 이하입니다(기본 60자).
- 🧪 시험(§5-1)도 같은 값을 싣습니다 — 시험 요청의 `orgId`(+선택 `tenantId`)에 맞는 설치가 하나면 그 값, 아니면 기본값입니다.

**AI 고지 문구도 앱마다 정할 수 있습니다**(gw 1.4.16.296+) — 운영자가 앱 등록에 넣습니다(예: 「AI가 드리는 안부 전화입니다」).
DVG 가 여전히 **앱보다 먼저** 재생하고(`setup.noticePlayed`), 앱은 끌 수 없습니다. 「AI」 또는 「인공지능」이 들어간 문구만 받습니다.
⚠️ 앱의 첫 문장은 고지 **바로 뒤에** 들립니다 — 고지와 같은 말을 되풀이하지 않게 지으십시오.

### 3-9. 통화 상대에게 문자(`sms`) — gw 1.4.16.307+

주문 내용 요약처럼 **방금 통화한 사람에게** 문자를 보낼 때 씁니다.

```json
{"type":"sms","text":"[○○꽃집] 주문접수 12345\n근조 3단 60,000원"}
```
```json
{"type":"sms_result","turn":12,"status":"sent"}
```

- 🔴 **받는 사람은 그 통화의 상대로 고정**입니다 — 앱은 번호를 넣을 수 없습니다(DVG 가 스팸 발송 창구가 되지 않게).
  발신번호 제공(`caller`)이 꺼져 있어도 보낼 수 있습니다 — 번호는 앱에 가지 않고 DVG 가 보냅니다.
- 🔴 **DVG 가 건 통화(`setup.direction:"outbound"`)에서는 쓸 수 없습니다**(`unavailable`) — 그 번호는 앱이 고른 번호라 위 원칙이 깨집니다.
- 한 통은 **80바이트**(EUC-KR · 한글 약 40자 · 장문 문자 없음)입니다. 길면 **나눠서** 여러 번 보내십시오. **한 통화 4통까지**입니다.
- 보내는 번호는 운영자가 그 회사에 정한 **문자 발신 내선**입니다. 회신하면 그 번호로 갑니다.
- 📨 **발신자가 끊은 뒤에도 30초 동안은 `sms` 를 받습니다**(DVG 1.4.16.311+) — `end` 의 `reason` 이 `caller_hangup` 이면 연결을 바로 닫지 않고
  `sms` 만 더 받아 `sms_result` 로 답합니다. 「네」 하고 바로 끊은 고객에게도 **이미 만든 주문의 접수 문자**를 보낼 수 있게 하려는 것입니다.
  받는 사람·한 통화 4통 상한은 그대로이고, `sms` 가 아닌 지시를 보내거나 연결을 닫으면 바로 끝납니다(시험 통화에는 이 창이 없습니다).
  ⚠️ 그 뒤에는 말(`say`·`ask`)을 할 수 없습니다 — 끊긴 통화입니다.
- 이모지처럼 문자로 보낼 수 없는 글자는 DVG 가 「?」로 바꿔 보냅니다(DVG 1.4.16.311+ — 글자 하나 때문에 문자 전체가 거절되지 않게).

| `status` | 뜻 | 앱이 할 일 |
|---|---|---|
| `sent` | DVG 가 내보냈다(⚠️ **배달 확인은 아닙니다**) | 「문자로 보내 드렸어요」까지만 말한다 |
| `failed` | 보내려 했는데 실패(`code`: `too_long` = 80바이트 초과 → 나눠서 다시 · `send_failed`) | 문자를 보냈다고 말하지 않는다 |
| `unavailable` | 이 회사에서 문자를 쓸 수 없다(발신 내선 미설정 등) | 말로 안내한다 |
| `not_mobile` | 상대가 휴대폰이 아니다(유선·표시제한) | 말로 안내한다 |
| `rate_limited` | 그 회사의 분당 문자 상한 | 말로 안내한다 |
| `limit` | 이 통화의 문자 수 상한(4통) | 더 보내지 않는다 |
| `simulated` | 시험(§5-1) — **보내지 않았다** | 실통화처럼 이어 간다 |

⚠️ **구버전 DVG**(1.4.16.306 이하)는 `sms` 를 모르고 `error unknown_type` 을 줍니다 — 이것은 위반 횟수에 셉니다.
한 번 받았으면 그 통화에서는 더 보내지 마십시오.

### 3-10. 모은 칸 보여 주기(`slots`) — gw 1.4.16.307+

운영자가 대시보드 📡 실시간에서 **이 통화가 무엇을 얼마나 받았는지** 보게 하려면, 지시에 지금까지의 칸 목록을 함께 싣습니다.

```json
{"type":"ask","text":"보내는 분 리본 글은 어떻게 적을까요?","slots":[
  {"key":"kind","label":"분류","value":"근조 화환","state":"done"},
  {"key":"addr","label":"배달지","value":"부산 사하구 ○○장례식장","state":"done"},
  {"key":"sender","label":"보내는 분","state":"none"}]}
```

- **DVG 는 판단하지 않습니다** — 무엇이 필수이고 언제 찼는지는 앱이 압니다. 마지막에 받은 목록이 그 통화의 현재 상태입니다(바뀔 때만 실으면 됩니다).
- `state` 는 `none`(아직) · `partial`(들었는데 확인 전) · `done`(확정) · `blocked`(여기서 사람에게 넘김). 모르는 값은 `none` 으로 봅니다.
- 상한: 12칸 · `key` 32자 · `label` 12자 · `value` 60자(넘으면 자릅니다 · **지시는 거절하지 않습니다**). `key` 가 비거나 겹치면 그 칸은 버립니다.
- 🔒 `value` 에는 이름·주소가 들어갑니다 — 운영자가 «값 담기» 를 꺼 두면 화면·기록에 **상태만** 보입니다.
- 통화가 끝나면 마지막 목록이 🧾 기록에 남습니다. 구버전 DVG 는 이 필드를 무시합니다(통화는 그대로).

## 4. 결말과 상한

| 결말(`end.reason`) | 뜻 | 발신자에게 |
|---|---|---|
| `completed` | 앱이 `hangup` | 통화 종료 |
| `transferred` | 앱이 `transfer` | 사람 연결 |
| `caller_hangup` | 발신자가 먼저 끊음 | — |
| `app_error` | 응답 시간 초과·끊김·잘못된 JSON·위반 초과 | 사람 연결 |
| `limit` | 지시 60회 또는 10분 초과 | 사람 연결 |
| `voice_failed` | DVG 쪽 음성 배관 실패(앱 탓 아님) | 사람 연결 |
| `notice_transfer` | AI 고지를 못 틀었고 운영 정책이 «사람에게» | 사람 연결(앱 연결 안 함) |

앱 연결 전에 끝나는 결말(앱은 받지 못함): `app_unavailable`(연결 실패) · `quota`(월 상한 초과 — 운영자가 강제로 둔 경우).

⚠️ 상한값(60회·10분·10초·500자·문자 4통)은 **아직 실측으로 정한 값이 아닌 출발점**입니다.

## 5. 사용량 확인(앱 키)

```
GET /api/v1/apps/self          Authorization: Bearer dvga_{appId}.{…}
GET /api/v1/apps/self/usage?month=YYYY-MM
```

- 수량만 셉니다: 통화 수 · 결말별 · 테넌트별 · 연결 초 · 지시 수 · TTS 글자(캐시 적중 제외) · STT 초 · 주소 풀이(`addressLookups`) · 좌표 조회(`coordLookups`). **금액은 없습니다.**
- `usageUnknownCalls > 0` 이면 그 달의 TTS·STT 합계는 **하한**입니다. 월 경계는 **UTC** 입니다.

## 5-1. 전화 없이 시험하기

`POST /api/v1/apps/self/simulate`(앱 키) · body `{"utterances":[…], "caller"?: "…"}` — 실통화와 같은 흐름을 등록된 relay 주소로 돌리고 대화를 글자로 돌려줍니다. 자세한 사용법은 [시작하기 §4](getting-started.md).

## 6. v1 에 없는 것

- 질문마다 음성인식 힌트 바꾸기 — 앱 등록 단위 낱말만 된다(§3-4)
- 앱이 호전환 번호 지정 — 통화료 사기 위험으로 **막아 두었습니다**
- 원시 오디오 — 필요하면 기존 SDK 경로(`/api/v1/ws/stream`)
- 대시보드 안 앱 화면
