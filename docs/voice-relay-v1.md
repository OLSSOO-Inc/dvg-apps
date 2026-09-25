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
앱  → DVG  say | ask | transfer | hangup     ← DVG 메시지 하나당 지시 하나
DVG → 앱   said | prompt | error
…
DVG → 앱   end
```

🔴 **DVG 가 메시지를 보낸 뒤 10초 안에 다음 지시를 보내야 합니다.** 넘기면 통화는 사람에게 넘어갑니다(`app_error`).

### 3-2. DVG → 앱

| type | 필드 | 뜻 |
|---|---|---|
| `setup` | `version` · `callId` · `tenantId` · `orgId` · `appId` · `did` · `noticePlayed` · `caller`(조건부) · `simulated`(조건부) | 통화 시작. `caller` 는 **운영자가 설치에서 발신번호 제공을 켰을 때만** 있습니다(키 자체가 없으면 «제공하지 않음»). 🔴 **`simulated:true` 는 전화 없는 시험**(gw 1.4.16.259) — 그때는 **실제 주문을 만들지 마십시오**(실통화에서는 키가 없습니다) |
| `said` | — | `say` 재생이 끝났다 |
| `prompt` | `text` · `silence` · `lowConfidence` · `spokeDuringPlayback` · `heardVoice`(gw 1.4.16.261 — 소리는 있었는데 말로 인식되지 않았다 · 무응답과 «말했는데 못 알아들음» 을 가른다) · (선택지를 줬으면) `choice` · `choiceIndex` · `choiceSource` · `confirm` · `choiceAmbiguous` · (`expect:"address"` 였으면) `address` | `ask` 뒤 발신자가 한 말. `silence:true` 면 아무 말도 없었다. 선택지 판정은 §3-4, 주소는 §3-5 |
| `error` | `code` · `message` | 지시가 잘못됐다 — `unknown_type` · `text_required` · `text_too_long` · `bad_choices` · `bad_expect`. **3번 넘으면** 통화가 사람에게 간다 |
| `end` | `reason` | 세션 끝(§4 결말). 이 뒤로는 보내도 소용없습니다 |

### 3-3. 앱 → DVG

| type | 필드 | 동작 |
|---|---|---|
| `say` | `text`(필수 · 500자 이하) · `interruptible`(선택 · gw 1.4.16.261) | 끝까지 말한다(끼어들어도 멈추지 않음) → `said`. `interruptible:true` 면 **발신자가 끼어들 때 멈춘다**(듣지는 않는다 — 이어서 `ask{text:""}` 로 듣는다). ⚠️ 복창·결제 안내처럼 **끝까지 들려야 하는 말에는 쓰지 마십시오** |
| `ask` | `text`(선택 · 500자 이하) · `choices`(선택 · 2~6개 · 각 1~20자 · 중복 없음) · `expect`(선택 · `"address"`) · `label`(선택 · `expect` 와 함께 · 1~10자) | 질문을 말하고(발신자가 끼어들면 멈춤) **발신자 답을 듣는다** → `prompt`. `text` 가 비면 말없이 듣기만 한다. `choices` 가 규칙에 어긋나면 **묻지 않고** `error bad_choices`. `expect` 는 §3-5(`choices` 와 함께 쓰면 `bad_expect`) |
| `transfer` | — | **사람에게 연결**. 🔴 번호는 지정할 수 없습니다 — 그 주문 회사에 운영자가 정한 호전환 번호로 갑니다 |
| `hangup` | `text`(선택 · 마지막 인사) | 인사 후 통화 종료 |

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
| `ambiguous` | 같은 이름이 여러 곳에 있다 — `candidates` · `question` | ⭐ **`question` 을 글자 그대로** 다시 `ask`(`expect:"address"`) 하십시오. 그러면 DVG 가 기억해 둔 후보로 다음 답(「서울이요」)을 좁힙니다. `question` 이 없으면(후보가 너무 많음) 다르게 묻거나 사람에게 |
| `partial` | 일부만 들었다 — `missing`(`sido`·`gugun`·`dong`) | 빠진 칸을 **다른 문장으로** 묻는다(같은 질문 반복 금지) |
| `unknown` | 주소로 읽지 못했다 — `reason` | 다른 문장으로 한 번 더 묻거나 사람에게 |
| `unavailable` | 이 설치에서 주소 풀이를 쓸 수 없다 | `text`(발화 원문)로 처리한다 |

| 필드 | 뜻 |
|---|---|
| `sido` · `gugun` · `dong` | 정식 이름(`서울특별시` · `송파구` · `신천동`). 세종특별자치시는 `gugun` 이 없다 |
| `detail` | 동 뒤에 들은 말(번지·층·호수) — **정규화하지 않은 발화 조각** |
| `name` | 장소·건물 이름으로 찾았을 때 그 이름 |
| `line` | 복창용 한 줄(`서울 송파구 신천동`) |
| `source` | 근거 — `spoken`(발화에 다 있었다) · `dong_index` · `gugun_index` · `venue`(장소 사전) · `building`(건물명 검색) · `narrowed`(좁히는 답) |
| `verified` | 그 조합이 **행정구역 색인에 실재**하는가 |
| `candidates` · `question` | `ambiguous` 일 때 |
| `missing` · `reason` | `partial` · `unknown`/`unavailable` 일 때 |
| `coord` · `coordStatus` | 좌표(아래) |

- 🔴 **DVG 는 여러 곳 중 하나를 고르지 않습니다** — 잘못 고른 주소는 기사가 다른 도시로 가는 값입니다.
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

⚠️ 상한값(60회·10분·10초·500자)은 **아직 실측으로 정한 값이 아닌 출발점**입니다.

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
