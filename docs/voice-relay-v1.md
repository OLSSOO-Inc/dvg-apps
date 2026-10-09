# DVG 관리형 음성 레이어 v1 — 앱 개발사용 계약

> 대상: DVG 위에서 **음성 자동 주문** 같은 대화 서비스를 만드는 개발사. **DVG 1.4.16.257 이상**.
> ⭐ 처음이면 [시작하기](getting-started.md)부터(예제 앱 · 같은 서버 배포 · 시험).

## 1. 무엇을 해 주나

DVG 가 **전화·음성인식(STT)·음성합성(TTS)** 을 맡고, 앱은 **텍스트로만** 대화를 이끕니다.

| DVG 가 한다 | 앱이 한다 |
|---|---|
| 전화 받기 · 링백 · 사람 연결 | 무엇을 물을지 정하기 |
| STT(한국어 전화 음성 도메인 힌트 포함) · TTS | 답을 해석하고 업무 시스템(예: 주문·배송 관리 API)에 조회·등록 |
| 끼어들기·무음 판정 | 대화를 끝낼지·사람에게 넘길지 판단 |
| **AI 고지**(법적 의무 — 앱이 끌 수 없음) | — |
| 사용량 계량(청구 근거) | — |

## 2. 연결

통화가 오면 **DVG 가 앱에 WebSocket 으로 연결합니다**(앱이 서버). 주소는 운영사가 앱 등록 때 넣은 `relayUrl`(`ws://` 또는 `wss://`)입니다.

⚠️ **연결은 벨이 울리는 동안(응답 전) 시도합니다.** 6초 안에 붙지 못하면 발신자는 **사람에게** 연결됩니다.

### 2-1. DVG 가 건 연결인지 확인하기(필수)

| 헤더 | 값 |
|---|---|
| `X-DVG-App-Id` | 앱 id |
| `X-DVG-Call-Id` | 통화 id |
| `X-DVG-Timestamp` | 유닉스 초 |
| `X-DVG-Signature` | `hex(HMAC-SHA256(signingSecret, appId + "\n" + callId + "\n" + timestamp))` |
| `X-DVG-Relay-Version` | `1` |

- `signingSecret` 은 앱 등록·키 회전 때 운영사가 **한 번만** 전달합니다(앱 키와 **다른 값**).
- 🔴 **타임스탬프가 ±300초를 벗어나면 거절하십시오**(재생 공격 방지).
- 검증 예(Python — 아래 시험 벡터로 확인했습니다):

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

- 검증 예(Java 17+ — 같은 시험 벡터로 확인했습니다 · 전체는 [examples/java](../examples/java/)):

```java
static boolean verifyDvg(Function<String, String> header, String secret, long nowSeconds) throws Exception {
    String appId = header.apply("X-DVG-App-Id"), callId = header.apply("X-DVG-Call-Id");
    String ts = header.apply("X-DVG-Timestamp"), sig = header.apply("X-DVG-Signature");
    if (appId == null || callId == null || sig == null || ts == null || !ts.matches("[0-9]+")) return false;
    if (Math.abs(nowSeconds - Long.parseLong(ts)) > 300) return false;
    Mac mac = Mac.getInstance("HmacSHA256");
    mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
    String want = HexFormat.of().formatHex(mac.doFinal((appId + "\n" + callId + "\n" + ts).getBytes(StandardCharsets.UTF_8)));
    return MessageDigest.isEqual(want.getBytes(StandardCharsets.US_ASCII), sig.getBytes(StandardCharsets.US_ASCII));
}
```

#### 시험 벡터(구현이 맞는지 확인)

| 입력 | 값 |
|---|---|
| `signingSecret` | `test-signing-secret` |
| `X-DVG-App-Id` | `demo-order-app` |
| `X-DVG-Call-Id` | `1790000000.42` |
| `X-DVG-Timestamp` | `1790000000` |
| **기대 `X-DVG-Signature`** | `8f5176f9494aea0ff84847a5d2a80fdac8b90de4d44633d841d4cff3b1133f9a` |

같은 값이 나오지 않으면 구분자(`\n`)·인코딩(UTF-8)·16진 소문자를 확인하십시오. 이 저장소의 CI 가 예제 네 가지(Python·Node.js·Go·Java)로 이 벡터를 검사합니다([conformance/](../conformance/)).

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
| `setup` | `version` · `callId` · `tenantId` · `orgId` · `appId` · `did` · `noticePlayed` · `direction` · `caller`(조건부) · `simulated`(조건부) · `settings`(조건부) · `ringing`(조건부 · DVG 1.4.16.340 이상 · §3-14) · `staff`(조건부 · DVG 1.4.16.362 이상 · §3-15) | 통화 시작. `direction` 은 `"inbound"`(상대가 걸어왔다) 또는 `"outbound"`(DVG 가 걸었다 · DVG 1.4.16.292 이상) — **없으면 수신**(구버전 DVG). `caller` 는 **운영사가 설치에서 발신번호 제공을 켰을 때만** 있고, 발신 통화에서도 **상대 번호**입니다(키 자체가 없으면 «제공하지 않음»). 🔴 **`simulated:true` 는 전화 없는 시험**(DVG 1.4.16.259 이상) — 그때는 **실제 주문을 만들지 마십시오**(실통화에서는 키가 없습니다) |
| `said` | — | `say` 재생이 끝났다 |
| `prompt` | `text` · `silence` · `lowConfidence` · `spokeDuringPlayback` · `heardVoice`(DVG 1.4.16.261 이상 — 소리는 있었는데 말로 인식되지 않았다 · 무응답과 «말했는데 못 알아들음» 을 가른다) · (선택지를 줬으면) `choice` · `choiceIndex` · `choiceSource` · `confirm` · `choiceAmbiguous` · (`expect:"address"` 였으면) `address` · (`expect:"birth"` 였으면 · DVG 1.4.16.372 이상) `birth` · (긴 듣기를 **적용했으면**) `listenSeconds` · (일찍 닫기를 **적용했으면**) `endSilenceSeconds` | `ask` 뒤 발신자가 한 말. `silence:true` 면 아무 말도 없었다. 선택지 판정은 §3-4, 주소는 §3-5, 생년월일은 §3-16 |
| `sms_result` | `status` · `code`(선택) | `sms` 결과(DVG 1.4.16.307 이상 · §3-9). 🔴 **실패여도 오류가 아닙니다**(위반 횟수에 세지 않습니다) |
| `error` | `code` · `message` | 지시가 잘못됐다 — `unknown_type` · `text_required` · `text_too_long` · `bad_choices` · `bad_expect` · `bad_listen_seconds` · `bad_end_silence_seconds`. **3번 넘으면** 통화가 사람에게 간다 |
| `end` | `reason` | 세션 끝(§4 결말). 이 뒤로는 보내도 소용없습니다. DVG 는 `end` 뒤에 **WebSocket close(1000)** 로 연결을 닫습니다(DVG 1.4.16.275 이상). ⚠️ **`end` 없이 연결이 닫혀도 통화는 끝난 것입니다** — 앞에 프록시(Cloud Run 등)가 있으면 `end` 가 오기 전에 닫힐 수 있고, DVG 1.4.16.274 이하는 close 프레임 없이 끊습니다. 그때 결말은 **모른다**로 두십시오(예제 앱은 `reason:"closed"`) |

### 3-3. 앱 → DVG

| type | 필드 | 동작 |
|---|---|---|
| `say` | `text`(필수 · 500자 이하) · `interruptible`(선택 · DVG 1.4.16.261 이상) | 끝까지 말한다(끼어들어도 멈추지 않음) → `said`. `interruptible:true` 면 **발신자가 끼어들 때 멈춘다**(듣지는 않는다 — 이어서 `ask{text:""}` 로 듣는다). ⚠️ 복창·결제 안내처럼 **끝까지 들려야 하는 말에는 쓰지 마십시오** |
| `ask` | `text`(선택 · 500자 이하) · `choices`(선택 · 2~6개 · 각 1~20자 · 중복 없음) · `expect`(선택 · `"address"` · `"phone"`(DVG 1.4.16.339 이상 · §3-13) · `"birth"`(DVG 1.4.16.372 이상 · §3-16)) · `label`(선택 · `expect` 와 함께 · 1~10자) · `listenSeconds`(선택 · 5~90 · §3-7) · `endSilenceSeconds`(선택 · 2~10 · `listenSeconds` 와 함께만 · §3-7) · `discardEarlier`(선택 · `true` · DVG 1.4.16.384 이상 · §3-7) | 질문을 말하고(발신자가 끼어들면 멈춤) **발신자 답을 듣는다** → `prompt`. `text` 가 비면 말없이 듣기만 한다. `choices` 가 규칙에 어긋나면 **묻지 않고** `error bad_choices`. `expect` 는 §3-5(`choices` 와 함께 쓰면 `bad_expect` — 단 `"birth"` 는 함께 쓴다 · §3-16) |
| `sms` | `text`(필수 · **80바이트** 이하 — 한글 약 40자) | **통화 상대에게 문자 한 통**(DVG 1.4.16.307 이상 · §3-9) → `sms_result`. 🔴 받는 사람은 지정할 수 없습니다 |
| `transfer` | `note`(선택 · 1,000자 이하 · DVG 1.4.16.334 이상 · §3-12) | **사람에게 연결**. 🔴 번호는 지정할 수 없습니다 — 그 주문 회사에 운영사가 정한 호전환 번호로 갑니다. `note` 는 상담원에게 전달할 메모(DVG 기록에 남는다) |
| `hangup` | `text`(선택 · 마지막 인사) · `note`(선택 · DVG 1.4.16.336 이상 · §3-12) | 인사 후 통화 종료 |
| `prepare` | `texts`(필수 · 1~8개 · 각 200자 이하 · DVG 1.4.16.339 이상 · §3-13) | 곧 말할 문장을 **미리 합성**해 둔다(말하지 않는다) → `prepared{accepted}` |
| (어느 지시에나) | `unrecognized`(선택 · 문자열 배열 · DVG 1.4.16.319 이상 · §3-11) | 앱이 알아듣지 못한 대답 — 운영사가 볼 수 있는 학습 기록에 쌓인다(지시 실행에는 영향 없음) |

⭐ **모든 지시에 `slots`(선택 · DVG 1.4.16.307 이상)를 실을 수 있습니다** — §3-10. 운영사 화면에 «지금까지 모은 칸» 을 보여 주는 용도이고 동작은 바뀌지 않습니다.

### 3-4. 선택지(`ask.choices`) — DVG 1.4.16.260 이상

답이 몇 개로 정해진 질문(결제 «선불/착불», 확인 «네/아니요» 등)은 `choices` 를 함께 보내면 DVG 가 답을 **그중 하나로 읽어** `prompt.choice` 에 싣습니다. `text` 는 그대로 있습니다(발화 원문).

| `choiceSource` | 뜻 | 앱이 할 일 |
|---|---|---|
| `exact` | 발화에 선택지 낱말이 들어 있었다(「착불이요」) | 그대로 쓴다 |
| `initial` + `confirm:true` | 짧게 뭉개진 답을 **첫 음절 초성**으로 추정했다(「참불」 → 착불) | 🔴 **반드시 복창해 확인받는다**(「결제 착불. 맞으면 「네」.」) |
| (`choice` 없음) + `choiceAmbiguous:true` | 선택지 둘 이상이 들어 있었다(「선불 아니고 착불」) | **다시 묻는다**(DVG 는 짐작으로 고르지 않는다) |
| (`choice` 없음) | 못 골랐다 | 다시 묻거나 사람에게 |

- 🔴 **초성 추정은 좁게 걸립니다** — 선택지들이 **같은 꼬리 초성**을 가질 때만(예: 선**불**/착**불**). 「네/아니요」 처럼 꼬리가 다르면 초성 추정은 **하지 않고** 정확 일치만 봅니다.
- ⚠️ 한 글자 선택지(「네」)는 **낱말 앞머리**에서만 인정합니다(「서초동네」 가 «네» 가 되지 않게).
- ⚠️ **음성인식 힌트는 질문마다 바꿀 수 없습니다**(연결을 맺을 때 정해진다). 앱이 물을 선택지는 운영사에 요청해 **앱 등록의 «음성인식 힌트 낱말»** 에 넣으십시오.

### 3-5. 주소(`ask.expect:"address"`) — DVG 1.4.16.265 이상

주소를 묻는 `ask` 에 `"expect":"address"` 를 실으면 DVG 가 발신자의 답을 **시·도 / 구·군 / 동**으로 풀어 `prompt.address` 에 싣습니다.
행정구역·장소(장례식장 등)·건물명 풀이와 **좁히는 질문**까지 DVG 가 맡습니다 — 앱은 행정구역 사전을 만들 필요가 없습니다.
`label` 은 좁히는 질문에서 이 칸을 부를 이름입니다(「배달지」·「받는 곳」 — 기본 「주소」).

| `address.status` | 뜻 | 앱이 할 일 |
|---|---|---|
| `resolved` | 3단이 정해졌다 | 복창해 확인받고 쓴다. 🔴 `verified:false` 면 **반드시** 복창(행정구역 색인에 없는 이름 — 행정동·리일 수도, 오인식일 수도) |
| `ambiguous` | 같은 이름이 여러 곳에 있다 — `candidates` · `question` | ⭐ **`question` 을 글자 그대로** 다시 `ask`(`expect:"address"`) 하십시오. 그러면 DVG 가 기억해 둔 후보로 다음 답(「서울이요」)을 좁힙니다. `question` 이 없으면(후보가 너무 많음) 다르게 묻거나 사람에게. ⚠️ `source:"near_dong"`(DVG 1.4.16.293 이상)이면 **말한 구·군에 그 동이 없어** 그 구·군 안의 비슷한 동을 묻는 것이고, 후보는 **동**(`candidates[].dong`)이며 **하나일 수도** 있다(확인 질문). 할 일은 같다 — `question` 을 그대로 다시 묻는다. `source:"near_venue"`(DVG 1.4.16.329 이상)는 **비슷한 장례식장 이름**을 묻는 확인 질문이다(후보 하나) — 「네」를 들으면 그 장소로 확정되고(`name` 에 등재명), 「아니요」면 확정되지 않는다 |
| `partial` | 일부만 들었다 — `missing`(`sido`·`gugun`·`dong`) | 빠진 칸을 **다른 문장으로** 묻는다(같은 질문 반복 금지) |
| `unknown` | 주소로 읽지 못했다 — `reason` | 다른 문장으로 한 번 더 묻거나 사람에게 |
| `unavailable` | 이 설치에서 주소 풀이를 쓸 수 없다 | `text`(발화 원문)로 처리한다 |

| 필드 | 뜻 |
|---|---|
| `sido` · `gugun` · `dong` | 정식 이름(`서울특별시` · `송파구` · `신천동`). 세종특별자치시는 `gugun` 이 없다 |
| `detail` | 동 뒤에 들은 말(번지·층·호수) — **정규화하지 않은 발화 조각** |
| `name` | 장소·건물 이름으로 찾았을 때 그 이름 |
| `detailClean` · `detailRepaired` | `detail` 을 정리한 값(군말·끝말 떼기 · 「백이동 802 호」→「102동 802호」 · 「800 이호」→「802호」)과 **호수를 고쳤는가**. `detailRepaired:true` 면 고친 값을 읽어 확인받으십시오(DVG 1.4.16.347 이상) |
| `needsBuilding` | `resolved` 인데 나머지가 **동·호·층 숫자뿐**이고 건물 이름(`name`)도 없다 — 단지 이름을 물으십시오(아래). `resolved` 일 때만 실린다 — 키가 없으면 «판정 안 함»(구버전 DVG 포함 · DVG 1.4.16.347 이상) |
| `heardName` | 장소·건물 검색에 없는 장소의 이름을 **들은 말에서** 떼어 낸 것(시·도/구·군/동·끝말을 뗐다 · `name` 이 비었을 때만). ⚠️ **장소 이름을 물은 질문에서만** 쓰십시오(「장례식장 이름」 등) · 장소 이름 같지 않거나 번지·호수가 있는 답이면 싣지 않는다(DVG 1.4.16.347 이상) |
| `room` | 들은 말 안의 **빈소 호실**(「3호실」·「특실」·「5빈소」 · 숫자 말은 숫자로). 장례식장 배송이면 이 값이 없을 때 호실을 물으십시오 — 같은 장례식장에 빈소가 여럿입니다. ⚠️ 집 주소의 「802호」 는 빈소가 아니라 싣지 않는다(DVG 1.4.16.349 이상) |
| `line` | 복창용 한 줄(`서울 송파구 신천동`) |
| `source` | 근거 — `spoken`(발화에 다 있었다) · `dong_index` · `gugun_index` · `venue`(장소 사전) · `building`(건물명 검색) · `narrowed`(좁히는 답) · `near_dong`(말한 구·군에 없는 동 — 비슷한 동을 묻는다) · `near_venue`(비슷한 장례식장 이름 — 확인 질문 · DVG 1.4.16.329 이상) |
| `verified` | 그 조합이 **행정구역 색인에 실재**하는가 |
| `candidates` · `question` | `ambiguous` 일 때 |
| `missing` · `reason` | `partial` · `unknown`/`unavailable` 일 때 |
| `coord` · `coordStatus` | 좌표(아래) |

- 🔴 **DVG 는 여러 곳 중 하나를 고르지 않습니다** — 후보가 여럿이면 `ambiguous` 로 돌려줍니다.
- ⭐ **잘못 들린 동**(DVG 1.4.16.293 이상) — 말한 구·군에 없는 동이면 DVG 가 그 구·군 안의 비슷한 동을 묻는 `question` 을 줍니다
  (`source:"near_dong"` · 예: 「고양시 덕양구에서 상동동을 찾지 못했습니다. 삼송동. 향동동. 배달지는 어느 쪽인가요?」). 발신자가
  구·군을 따로 답한 경우도 앞 질문의 동과 합쳐 같은 질문을 줍니다. 「아니요」라고 답하면 같은 목록을 다시 주지 않습니다 — 그때 앱은 다른 문장으로 묻습니다.
- ⚠️ **좁히기는 바로 그 질문에만** 걸립니다 — 앱이 다른 문장으로 물으면(다음 칸 등) 새 주소로 읽습니다. 무음 뒤에 같은 질문을 다시 해도 후보는 남아 있습니다.
- ⚠️ 한 답에 두 곳(「강남에서 서초로」)이면 `unknown` + `reason:"multiple_places"` — 칸마다 따로 물으십시오.
- 🏢 **단지 이름이 없는 주소**(DVG 1.4.16.347 이상) — 「향동동 102동 802호」처럼 동·호수만 있으면 `needsBuilding:true` 입니다. 한 동네에 아파트
  단지가 여럿이면 이 주소로는 배달할 곳을 정할 수 없습니다 — 「아파트나 건물 이름을 말씀해 주시겠어요?」처럼 **한 번** 묻고, 모르면 사람에게
  넘기십시오. ⚠️ 숫자만 있는 「향동동 802」는 번지일 수 있어 `false` 입니다. DVG 는 단지 이름이 그 동에 실제로 있는지 확인하지 않습니다.

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
              "question":"신천동이 여러 곳입니다. 경기. 경북. 대구. 서울. 울산. 배달지는 어느 쪽인가요?"}}
← {"type":"ask","text":"신천동이 여러 곳입니다. 경기. 경북. 대구. 서울. 울산. 배달지는 어느 쪽인가요?","expect":"address","label":"배달지"}
→ {"type":"prompt","text":"서울이요","silence":false,"lowConfidence":false,"spokeDuringPlayback":false,"heardVoice":true,
   "address":{"status":"resolved","sido":"서울특별시","gugun":"송파구","dong":"신천동","line":"서울 송파구 신천동","source":"narrowed","verified":true}}
← {"type":"ask","text":"꽃다발. 꽃바구니. 화환. 어느 쪽으로 보내 드릴까요?","choices":["꽃다발","꽃바구니","화환"]}
→ {"type":"prompt","text":"꽃바구니로 할게요","silence":false,"lowConfidence":false,"spokeDuringPlayback":false,"heardVoice":true,"choice":"꽃바구니","choiceIndex":1,"choiceSource":"exact"}
← {"type":"ask","text":"배달지 서울 송파구 신천동. 상품 꽃바구니. 맞으면 「네」. 틀리면 「아니요」.","choices":["네","아니요"]}
→ {"type":"prompt","text":"네","silence":false,"lowConfidence":false,"spokeDuringPlayback":false,"heardVoice":true,"choice":"네","choiceIndex":0,"choiceSource":"exact"}
← {"type":"hangup","text":"주문이 접수되었습니다. 감사합니다."}
→ {"type":"end","reason":"completed"}
```

⭐ 이 대화는 [예제 슬롯 엔진](../examples/python/slot_app.py)의 [꽃 배달 시나리오](../examples/python/scenarios/flower.json)를 전화 없는 시험(§5-1)으로
돌려 받은 메시지입니다(줄을 나누고 `turn` 을 뺐습니다). ⚠️ `setup` 은 실통화 모양으로 적었습니다 —
전화 없는 시험에서는 `simulated:true` 가 붙고 `tenantId`·`orgId`·`did` 가 비어 있을 수 있습니다.

### 3-7. 긴 듣기(`ask.listenSeconds`) — DVG 1.4.16.291 이상

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
- `expect:"address"` 와 함께 쓸 수 없습니다(`bad_listen_seconds`). 범위 밖도 같은 오류입니다. ⏱ `choices`·`expect:"phone"` 과는 함께 씁니다(DVG 1.4.16.339 이상 · 그 전에는 오류) — 정해진 답이 들리면 창·쉼을 기다리지 않습니다(§3-13).
- ⚠️ 창이 길수록 통화 시간(=음성인식 비용)이 늘어납니다. 꼭 필요한 질문에만 쓰십시오.
- 🧪 시험(§5-1)은 글자 시험이라 시간이 흐르지 않습니다 — 발화 하나가 그 창 전체에 한 말로 취급됩니다.

#### 말씀이 끝나면 일찍 닫기(`endSilenceSeconds`) — DVG 1.4.16.304 이상

`listenSeconds` 만 실으면 DVG 는 발신자가 말을 일찍 마쳐도 **창이 끝날 때까지** 기다립니다. 「요즘 가 보고 싶은 곳이
있으세요?」처럼 **충분히 기다려 주되 말이 끝나면 바로 받아야 하는** 대화 질문에는 `endSilenceSeconds` 를 함께 실으십시오 —
발신자가 **한 마디라도 한 뒤** 그 시간만큼 조용하면 창보다 일찍 닫고 답을 줍니다.

```json
{"type":"ask","text":"요즘 가 보고 싶은 곳이 있으세요?","listenSeconds":20,"endSilenceSeconds":3}
```

- **2~10초** · `listenSeconds` 보다 짧아야 하고 `listenSeconds` 없이 쓸 수 없습니다(`bad_end_silence_seconds`).
- ⚠️ **아무 말도 없으면 일찍 닫지 않습니다** — 생각하시는 중일 수 있어서입니다. 무응답은 창이 끝날 때 `silence:true` 입니다.
- ⚠️ 너무 짧으면 숨 고르는 사이에 잘립니다. 「1분 동안 이름 말하기」처럼 **끝까지 모아야 하는 과제에는 넣지 마십시오.**
- ⭐ 적용했으면 `prompt.endSilenceSeconds` 에 같은 값이 돌아옵니다. 키가 없으면 적용되지 않은 것이고(구버전 DVG) 창 끝까지 기다린 것입니다.

#### 앞의 말 버리기(`discardEarlier`) — DVG 1.4.16.384 이상

DVG 는 기본으로 **앞의 `say` 를 듣는 동안 발신자가 한 말도 살려** 다음 `ask` 의 답 맨 앞에 붙입니다(주소를 나눠 말하는 발신자의 말을
잃지 않으려고). 긴 안내·풀이를 들으며 한 혼잣말(「아 그렇구나」)이 **다음 물음의 대답**이 되면 곤란한 물음(예: 풀이 뒤 「상담사와 연결해 드릴까요?」)에는
`discardEarlier` 를 실으십시오.

```json
{"type":"ask","text":"상담사와 연결해 드릴까요?","choices":["네","아니요"],"discardEarlier":true}
```

- 질문을 말하기 **전에** 그때까지 들린 말을 버립니다. 질문 직전 말이 늦게 인식돼 도착하는 것도 질문 시작 뒤 약 1초까지 버립니다.
- ⭐ 질문을 **말하는 중에** 끼어든 말은 살립니다 — 그것이 이 물음의 대답입니다.
- ⚠️ 이어서 말하는 것이 정상인 물음(주소를 나눠 말하기 · 앞 답의 연속)에는 쓰지 마십시오.
- 모르는 DVG(1.4.16.383 이하)는 이 필드를 무시합니다(종전대로 살린다 · 오류 없음). 버렸는지는 `prompt` 에 싣지 않습니다.

### 3-8. 설치별 설정(`setup.settings`) — DVG 1.4.16.296 이상

같은 앱이라도 **회사(설치)마다** 다른 값이 필요할 때가 있습니다(예: 안부 전화가 첫마디에 밝힐 **기관 이름**).
앱은 **항목**을 정하고, 운영사가 회사마다 **값**을 넣습니다.

- **항목은 앱 등록 때 운영사에 알려 주십시오** — 키 · 이름 · 기본값(예: `callerName` · 「기관 이름」 · 「○○구 보건소」).
  운영사가 앱 등록에 그대로 넣습니다(키는 영문으로 시작하는 영문·숫자·`_` 32자 이하 · 10개까지).
- 통화마다 `setup.settings` 에 **실효값**이 옵니다 — 그 회사에 넣은 값, 없으면 기본값:

```json
{"type":"setup","version":1,"callId":"1790779616.2118","orgId":"…","appId":"…","direction":"outbound","settings":{"callerName":"○○구 보건소"}}
```

- ⭐ **키가 없으면 «정하지 않음»** 입니다(값도 기본값도 없음 · 또는 이 기능이 없는 DVG 버전) — 앱이 자기 기본값을 쓰십시오.
- 🔴 **비밀을 넣는 자리가 아닙니다** — 값은 운영사 화면과 이 메시지에 그대로 보입니다. 키·토큰은 앱의 환경변수로 받으십시오.
- 값은 앞뒤 공백이 지워지고 줄바꿈이 없습니다(DVG 가 거절합니다). 길이는 항목마다 정한 한도 이하입니다(기본 60자).
- 🧪 시험(§5-1)도 같은 값을 싣습니다 — 시험 요청의 `orgId`(+선택 `tenantId`)에 맞는 설치가 하나면 그 값, 아니면 기본값입니다.

**AI 고지 문구도 앱마다 정할 수 있습니다**(DVG 1.4.16.296 이상) — 원하는 문구를 운영사에 요청하면 앱 등록에 넣습니다(예: 「AI가 드리는 안부 전화입니다」).
DVG 가 여전히 **앱보다 먼저** 재생하고(`setup.noticePlayed`), 앱은 끌 수 없습니다. 「AI」 또는 「인공지능」이 들어간 문구만 받습니다.
⚠️ 앱의 첫 문장은 고지 **바로 뒤에** 들립니다 — 고지와 같은 말을 되풀이하지 않게 지으십시오.

### 3-9. 통화 상대에게 문자(`sms`) — DVG 1.4.16.307 이상

주문 내용 요약처럼 **방금 통화한 사람에게** 문자를 보낼 때 씁니다.

```json
{"type":"sms","text":"[○○꽃집] 주문접수 12345\n근조 3단 60,000원"}
```
```json
{"type":"sms_result","turn":12,"status":"sent"}
```

- 🔴 **받는 사람은 그 통화의 상대로 고정**입니다 — 앱은 번호를 넣을 수 없습니다.
  발신번호 제공(`caller`)이 꺼져 있어도 보낼 수 있습니다 — 번호는 앱에 가지 않고 DVG 가 보냅니다.
- 🔴 **DVG 가 건 통화(`setup.direction:"outbound"`)에서는 쓸 수 없습니다**(`unavailable`).
- 한 통은 **80바이트**(EUC-KR · 한글 약 40자 · 장문 문자 없음)입니다. 길면 **나눠서** 여러 번 보내십시오. **한 통화 4통까지**입니다.
- 보내는 번호는 운영사가 그 회사에 정한 **문자 발신 번호**입니다. 회신하면 그 번호로 갑니다.
- 📨 **발신자가 끊은 뒤에도 30초 동안은 `sms` 를 받습니다**(DVG 1.4.16.311 이상) — `end` 의 `reason` 이 `caller_hangup` 이면 연결을 바로 닫지 않고
  `sms` 만 더 받아 `sms_result` 로 답합니다. 「네」 하고 바로 끊은 고객에게도 **이미 만든 주문의 접수 문자**를 보낼 수 있습니다.
  받는 사람·한 통화 4통 상한은 그대로이고, `sms` 가 아닌 지시를 보내거나 연결을 닫으면 바로 끝납니다(시험 통화에는 이 창이 없습니다).
  ⚠️ 그 뒤에는 말(`say`·`ask`)을 할 수 없습니다 — 끊긴 통화입니다.
- 이모지처럼 문자로 보낼 수 없는 글자는 DVG 가 「?」로 바꿔 보냅니다(DVG 1.4.16.311 이상).

| `status` | 뜻 | 앱이 할 일 |
|---|---|---|
| `sent` | DVG 가 내보냈다(⚠️ **배달 확인은 아닙니다**) | 「문자로 보내 드렸어요」까지만 말한다 |
| `failed` | 보내려 했는데 실패(`code`: `too_long` = 80바이트 초과 → 나눠서 다시 · `send_failed`) | 문자를 보냈다고 말하지 않는다 |
| `unavailable` | 이 회사에서 문자를 쓸 수 없다(발신 번호 미설정 등) | 말로 안내한다 |
| `not_mobile` | 상대가 휴대폰이 아니다(유선·표시제한) | 말로 안내한다 |
| `rate_limited` | 그 회사의 분당 문자 상한 | 말로 안내한다 |
| `limit` | 이 통화의 문자 수 상한(4통) | 더 보내지 않는다 |
| `simulated` | 시험(§5-1) — **보내지 않았다** | 실통화처럼 이어 간다 |

⚠️ **구버전 DVG**(1.4.16.306 이하)는 `sms` 를 모르고 `error unknown_type` 을 줍니다 — 이것은 위반 횟수에 셉니다.
한 번 받았으면 그 통화에서는 더 보내지 마십시오.

### 3-10. 모은 칸 보여 주기(`slots`) — DVG 1.4.16.307 이상

운영사가 실시간 화면에서 **이 통화가 무엇을 얼마나 받았는지** 보게 하려면, 지시에 지금까지의 칸 목록을 함께 싣습니다.

```json
{"type":"ask","text":"보내는 분 리본 글은 어떻게 적을까요?","slots":[
  {"key":"kind","label":"분류","value":"근조 화환","state":"done"},
  {"key":"addr","label":"배달지","value":"부산 사하구 ○○장례식장","state":"done"},
  {"key":"sender","label":"보내는 분","state":"none"}]}
```

- **DVG 는 판단하지 않습니다** — 무엇이 필수이고 언제 찼는지는 앱이 압니다. 마지막에 받은 목록이 그 통화의 현재 상태입니다(바뀔 때만 실으면 됩니다).
- `state` 는 `none`(아직) · `partial`(들었는데 확인 전) · `done`(확정) · `blocked`(여기서 사람에게 넘김). 모르는 값은 `none` 으로 봅니다.
- 상한: 12칸 · `key` 32자 · `label` 12자 · `value` 60자(넘으면 자릅니다 · **지시는 거절하지 않습니다**). `key` 가 비거나 겹치면 그 칸은 버립니다.
- 🔒 `value` 에는 이름·주소가 들어갑니다 — 운영사가 «값 담기» 를 꺼 두면 화면·기록에 **상태만** 보입니다.
- 통화가 끝나면 마지막 목록이 통화 기록(§5-2)에 남습니다. 구버전 DVG 는 이 필드를 무시합니다(통화는 그대로).

### 3-11. 못 알아들은 대답 알리기(`unrecognized`) — DVG 1.4.16.319 이상

앱이 발신자의 대답을 **알아듣지 못했을 때** 그 대답을 DVG 에 알리면, 앱·회사별 학습 기록에 낱말 빈도로 쌓여 운영사가 볼 수 있습니다.
운영사·개발사는 그것을 보고 앱 사전에 낱말을 더합니다 — **자동으로 고쳐지지는 않습니다.**

- **어느 지시에나** 실을 수 있습니다(`say`·`ask`·`transfer`·`hangup`·`sms`). 보통은 못 알아들은 직후의 다음 지시에 싣습니다:

```json
{"type":"ask","text":"제가 잘 못 들었어요. 화환. 화분. 꽃바구니. 꽃다발. 하나만 말씀해 주세요.","unrecognized":["화한"]}
```

- 🔴 **못 알아들은 그 대답만** 넣으십시오 — 알아들은 답·「아니요」처럼 뜻이 분명한 답을 넣으면 «무엇이 안 잡히나» 가 흐려집니다.
- 지시당 10개 · 각 40자(넘으면 자릅니다) · 통화당 50개까지 쌓입니다. 형식이 틀려도 지시는 그대로 실행됩니다(조용히 버림).
- 🔒 발화 원문을 보관하는 자리가 아닙니다 — **낱말 빈도**만 남고, 번호로 보이는 조각은 낱말 없이 건수만 셉니다.
  🧪 시험(§5-1)은 쌓지 않습니다.
- 모르는 DVG 버전은 이 필드를 무시합니다(통화는 그대로).

### 3-12. 상담원에게 전달할 메모(`transfer.note` · `hangup.note`) — DVG 1.4.16.334 이상 · 끊기는 1.4.16.336 이상

사람에게 넘길 때 **무엇을 들었고 왜 넘기는지**를 `note` 에 적으면 DVG 가 그 통화 기록(§5-2)에 «상담원에게 전달한 내용» 으로 남깁니다.

```json
{"type":"transfer","note":"[AI 접수 - 상담원 확인 요망]\n넘긴 자리: 배달지\n분류: 근조 화환\n배달지: 한중프레임 장례식장 (확인 필요)"}
```

- ⚠️ DVG 가 상담원에게 **직접 전하지는 않습니다** — 상담원은 앱이 자기 주문 시스템(CRM)에 적은 메모를 봅니다. 같은 글을
  여기에도 보내 두면 통화 기록에서 대조할 수 있습니다.
- 1,000자 이하(넘으면 자릅니다) · 줄바꿈은 그대로 · 제어 문자는 뗍니다. 빈 값이면 없는 것과 같습니다.
- 🔒 이름·주소가 들어갈 수 있어 **칸 값과 같은 보관 설정**을 따릅니다 — 운영사가 «값 담기» 를 끈 설치에서는 글은 남지 않고
  «메모가 있었다» 는 사실만 남습니다. 🧪 시험(§5-1)은 기록하지 않습니다.
- 모르는 DVG 버전은 이 필드를 무시합니다(넘기기는 그대로).

**접수를 마치고 끊는 통화**에도 같은 `note` 를 실을 수 있습니다(DVG 1.4.16.336 이상). 규칙은 위와 같고, DVG 는 마지막 말보다 **먼저** 기록합니다
(그 말을 하는 중에 발신자가 끊어도 남습니다).

```json
{"type":"hangup","text":"주문이 접수되었습니다. 감사합니다.","note":"[AI 접수 완료 · 주문번호 1234]\n분류: 화분\n메모: 리본 글 확인 필요"}
```

- 모르는 DVG 버전(1.4.16.335 이하)은 이 필드를 무시합니다(끊기는 그대로).

### 3-13. 응답 속도 — 정해진 답이면 일찍 받기 · 미리 합성(`prepare`) — DVG 1.4.16.339 이상

발신자가 말을 멈춘 뒤 DVG 는 **말이 끝났는지 잠시 기다립니다**(긴 듣기는 `endSilenceSeconds`). 아래 답이 들리면 그 기다림을 줄여 **더 빨리** 받습니다
(설치에 따라 꺼져 있을 수 있습니다). 「네… 아니 잠깐만요」처럼 바로 고치는 말을 놓치지 않을 만큼은 기다립니다.

- `choices` 에 **정확히** 맞는 답(초성으로만 맞은 추정은 기다립니다)
- 선택지가 「네/아니요」인 질문의 긍정·부정(「어 맞아」·「응」·「아니」 포함)
- `expect:"phone"` — **다 말한 한국 전화번호**(국번·자릿수가 맞을 때만). 판정만 하고 번호를 따로 싣지는 않습니다(`prompt.text` 에서 읽으십시오)

그 뒤에 발신자가 이어 말한 것은 다음 질문의 답으로 넘어갑니다.

**미리 합성** — 곧 말할 문장(대개 첫 질문 뒤에 나올 문장)을 미리 보내 두면 그 문장을 말할 때 합성을 기다리지 않습니다.

```json
→ {"type":"prepare","texts":["화분은 포인세티아 5만4천원으로 준비할게요.","근조 화환은 근조 오브제 5만9천원으로 준비할게요."]}
← {"type":"prepared","accepted":2}
```

- 1~8문장 · 각 200자 이하(어기면 `error bad_prepare`) · **통화당 12문장**까지 받아들입니다(넘은 것·같은 문장은 `accepted` 에서 빠집니다).
- 🧪 시험 통화는 합성하지 않습니다(`accepted:0`). 이미 준비된 문장은 다시 합성하지 않습니다. 구버전 DVG 는 `error unknown_type` 입니다(통화는 계속됩니다).

🔙 **구버전 DVG 에 붙을 수 있으면 대비하십시오** — 1.4.16.339 이전 DVG 는 `expect:"phone"` 을 `error bad_expect`, 긴 듣기를 선택지·expect 와 함께 쓰면
`error bad_listen_seconds` 로 **거절합니다**(그 지시는 실행되지 않습니다 — 아무 말도 하지 않았습니다). 그 오류를 받으면 그 통화 동안 `expect:"phone"` 을 빼고(번호는 `text` 에서
읽기) 긴 듣기를 선택지·expect 와 함께 쓰지 않는 모양으로 **같은 질문을 다시** 보내십시오. `prepare` 의 `unknown_type` 을 받으면 그 통화에서는 더 보내지 마십시오.
⚠️ 거절도 위반 횟수에 들어갑니다(통화당 3번 넘으면 사람에게) — 거절마다 다시 시도하지 말고 한 번 판정해 유지하십시오. 대비 없이 구버전 DVG 에 올리면 **모든 통화가 첫 질문에서 사람에게** 갈 수 있습니다 — 앱을 올리기 전에 운영사에 DVG 버전을 확인하십시오.

⏱ 통화마다 **턴별 시간**(AI 가 말한 시간 · 끝났는지 기다린 시간 · 들은 뒤 다음 말까지)이 기록되고, §5-2 기록 조회의 `timing`·`summary.timing` 으로 봅니다.

### 3-14. 벨 울리는 동안 받는 setup(`ringing`) — DVG 1.4.16.340 이상

가입자 조회처럼 **첫 말 전에 시간이 걸리는 일**을 벨 소리 뒤에 숨기기 위해, DVG 는 걸려 온 통화에서 전화를 받기 **전에** setup 을 보냅니다.

```
DVG → 앱   setup {"ringing":true, "caller":"010…"(설치가 허용했을 때만), …}   ← 아직 받지 않았다(발신자는 벨을 듣는다)
           (앱은 여기서 가입자 조회 등을 한다)
앱  → DVG  prepare {…}        ← 받지 않고 처리 → prepared (선택)
앱  → DVG  say | ask …        ← 첫 지시 = «준비됐다»
           DVG 가 전화를 받고 → AI 고지 → 이 지시를 실행
```

- **준비되면 첫 지시를 보내십시오.** 그 지시가 오거나 **벨 상한**(설치마다 다름 · 몇 초)이 지나면 DVG 가 받습니다. 상한이 지나도 앱의 조회는 계속되고,
  고지가 끝난 뒤 첫 지시를 실행합니다(그때부터 평소처럼 10초 안에 보내면 됩니다).
- 벨 동안 온 `prepare` 는 받기 전에 처리합니다(합성도 벨 뒤로 숨는다).
- `noticePlayed` 는 이때 **«앱의 첫 말보다 먼저 말한다»** 는 뜻입니다(아직 받지 않았으므로). 할 일은 같습니다 — 스스로 고지하지 마십시오.
- 이 모드를 모르는 앱도 그대로 동작합니다 — setup 을 받자마자 첫 지시를 보내면 DVG 가 곧바로 받습니다(벨이 길어지지 않습니다).
- `ringing` 이 없으면 이미 받은 통화입니다(구버전 DVG · 🧪 시험 · DVG 가 건 통화).

### 3-15. 상담원 근무 시간(`setup.staff`) — DVG 1.4.16.362 이상

근무 시간이 아닌데 「담당자에게 연결해 드릴게요」만 들으면 발신자는 **곧 연락이 오는 줄** 압니다. 그래서 DVG 는 그 회사의 상담원 근무 시간을
setup 에 실어 줍니다. 근무 시간은 운영사가 회사마다 정합니다.

```json
"staff": {
  "onDuty": false,
  "nextOpen": "2026-10-08T09:00:00+09:00",
  "nextOpenText": "내일 오전 9시",
  "callback": true,
  "handoffNotice": "지금은 상담 시간이 아니어서 담당자가 바로 받지 못할 수 있어요. 받지 못하면 남겨 주신 내용을 담당자에게 전해 드리고, 내일 오전 9시 이후에 연락드릴게요."
}
```

| 필드 | 뜻 |
|---|---|
| `onDuty` | 지금 상담원 근무 시간인가 |
| `nextOpen` | 근무 시간 밖일 때 **다음 근무 시작**(RFC3339 · 그 회사 시간대). 일주일 안에 없으면 키가 없다 |
| `nextOpenText` | 그 시각을 말로 — 「오늘 오후 2시」·「내일 오전 9시 30분」·「모레 오전 9시」·「월요일 오전 9시」. 근무 시작 시각을 그대로 읽는다 · 일주일 넘으면 키가 없다 |
| `callback` | 그 회사에 **상담원 미연결 알림**(문자·앱)이 켜져 있다 — 사람에게 넘겼는데 아무도 받지 않으면 상담원이 접수 내용을 받는다 |
| `handoffNotice` | 근무 시간 밖에 넘길 때 **덧붙일 문장**(해요체). `callback` 이 false 면 「연락드릴게요」 대신 「상담은 내일 오전 9시부터예요.」 · 근무 중이면 키가 없다 |

- **근무 시간을 모르면 `staff` 키가 없습니다** — 종전처럼 말하면 됩니다(짐작해서 «상담 시간이 아니다» 라고 말하지 마십시오).
- 근무 시간 밖에 `transfer` 할 때는 그 앞의 `say` 에 **`handoffNotice` 를 덧붙이십시오**:

```json
{"type":"say","text":"축하 화환은 담당자에게 연결해 드릴게요. 지금은 상담 시간이 아니어서 담당자가 바로 받지 못할 수 있어요. 받지 못하면 남겨 주신 내용을 담당자에게 전해 드리고, 내일 오전 9시 이후에 연락드릴게요."}
{"type":"transfer","note":"…"}
```

- 🔴 **`callback` 이 false 면 「연락드릴게요」를 약속하지 마십시오** — 아무도 내용을 받지 못합니다. `handoffNotice` 는 이미 그에 맞춰져 있습니다.
- 문장을 직접 만들어도 됩니다. 그때도 예시·시각은 마침표로 끊고 물음으로 끝내지 마십시오(넘기는 말이다).
- DVG 는 대신 말하지 않습니다(앱의 대본입니다) · 연결(라우팅)은 근무 시간과 무관하게 그대로입니다 · 공휴일은 구분하지 않습니다.
- 🧪 시험 통화에도 실통화와 같은 값이 옵니다.

### 3-16. 생년월일(`ask.expect:"birth"`) — DVG 1.4.16.372 이상

(`→` DVG→앱 · `←` 앱→DVG — §3-6 과 같다) 생년월일을 묻는 `ask` 에 `"expect":"birth"` 를 실으면 **DVG 가 답을 알아듣고 받기 대화를 이끕니다**(주소의 §3-5 와 같은 자리).
앱은 `prompt.birth.question` 을 **그대로** 다시 물으면 됩니다(`choices` 가 있으면 함께). 한 번에 다 말하든(「1975년 3월 9일 남자야」) 나눠 말하든
빠진 칸만 묻고, 모호하면(두 자리 연도의 세기 · 오전/오후 · 윤달 등) 짐작하지 않고 묻습니다.

```json
← {"type":"ask","text":"생년월일과 태어난 시간, 성별을 말씀해 주세요.","expect":"birth","listenSeconds":15,"endSilenceSeconds":2}
→ {"type":"prompt","text":"1975년 3월 9일 남자야",
   "birth":{"status":"need","question":"양력. 음력. 어느 쪽인가요?","choices":["양력","음력"],"asking":"calendar",
            "heard":{"year":1975,"month":3,"day":9,"gender":"male"}}}
← {"type":"ask","text":"양력. 음력. 어느 쪽인가요?","expect":"birth","choices":["양력","음력"]}
```

| `birth.status` | 앱이 할 일 |
|---|---|
| `need` | `question` 을 `expect:"birth"`(+ `choices`)로 다시 묻는다 |
| `confirm` | `question` 은 **다시 읽기**(「…맞으신가요?」)다 — 그대로 묻는다. 🔴 생략할 수 없다(확인 전에는 원국을 주지 않는다) |
| `done` | 확인이 끝났다 — `chart` 에 원국이 있다 |
| `handoff` | 받지 못했다 — 사람에게 넘긴다(`transfer`). `error` 에 사유 코드(`collect` · `compute:no_leap_month` 등) · `question` 에 넘기며 할 말이 있을 수 있다 |

- `heard`: 지금까지 들은 칸 — `year` · `month` · `day` · `calendar`(`solar`/`lunar`) · `leap` · `hour` · `minute` · `hourBranch`(「축」처럼 시진으로만 말함) ·
  `hourUnknown` · `gender`(`male`/`female`) · `approx`(「쯤」). 아직 모르는 칸은 키가 없습니다.
- `chart`(`done` 일 때만): `year`·`month`·`day`·`hour`(기둥 · `hangul`「계축」·`hanja`「癸丑」 · 시간 모름이면 `hour` 없음) · `hourKnown` · `dayMaster`(「신금」) ·
  `elements`(목·화·토·금·수 개수) · `tenGods`(자리별 십성) · `strongTenGods` · `commander`(사령) · `season` · `luck`(대운수 · 순행 · 지금 대운 `current` ·
  10개 `pillars` · 성별 모름이면 없음) · `solarDate` · `lunar` · `summary`(상담사용 한 줄).
- 원국 계산은 DVG 가 합니다. 해석 문장은 주지 않습니다 — 앱이 원국으로 만듭니다.
- 무음에도 `birth` 가 옵니다(무음도 한 차례 — 다음 `question` 은 말을 바꾼 물음). `done`·`handoff` 뒤 다시 `expect:"birth"` 로 물으면 **새 사람**으로 시작합니다.
- `choices`·`listenSeconds` 와 함께 쓸 수 있습니다 · `label` 은 쓸 수 없습니다(`bad_expect`).
- 🔒 `heard`·`chart` 는 개인정보입니다 — 앱 쪽 저장·로그에 주의하십시오. 대화를 DVG 기록에 남기지 않으려면 운영사에 앱 등록의 «대화를 남기지 않습니다» 를 요청하십시오.
- ⚠️ 1.4.16.371 이하 DVG 는 `expect:"birth"` 를 `bad_expect` 로 거절합니다 — 그때는 `expect` 를 빼고 같은 질문을 다시 보내고 답(`text`)을 직접 읽으십시오.

## 4. 결말과 상한

| 결말(`end.reason`) | 뜻 | 발신자에게 |
|---|---|---|
| `completed` | 앱이 `hangup` | 통화 종료 |
| `transferred` | 앱이 `transfer` | 사람 연결 |
| `caller_hangup` | 발신자가 먼저 끊음 | — |
| `app_error` | 응답 시간 초과·끊김·잘못된 JSON·위반 초과 | 사람 연결 |
| `limit` | 지시 60회 또는 10분 초과 | 사람 연결 |
| `voice_failed` | DVG 쪽 음성 처리 실패(앱 탓 아님) | 사람 연결 |
| `notice_transfer` | AI 고지를 못 틀었고 설치 정책이 «사람에게» | 사람 연결(앱 연결 안 함) |

앱 연결 전에 끝나는 결말(앱은 받지 못함): `app_unavailable`(연결 실패) · `quota`(월 상한 초과 — 운영사가 상한을 둔 경우).

⚠️ 상한값(60회·10분·10초·500자·문자 4통)은 이후 버전에서 조정될 수 있습니다.

## 5. 사용량 확인(앱 키)

```
GET /api/v1/apps/self          Authorization: Bearer dvga_{appId}.{…}
GET /api/v1/apps/self/usage?month=YYYY-MM
```

- 수량만 셉니다: 통화 수 · 결말별 · 테넌트별 · 연결 초 · 지시 수 · TTS 글자(캐시 적중 제외) · STT 초 · 주소 풀이(`addressLookups`) · 좌표 조회(`coordLookups`). **금액은 없습니다.**
- `usageUnknownCalls > 0` 이면 그 달의 TTS·STT 합계는 **하한**입니다. 월 경계는 **UTC** 입니다.
- ⏱ `averages`(DVG 1.4.16.338 이상) — `connectedSeconds`·`connectedCalls`(평균 통화 · 앱에 연결된 통화가 분모) · `sttSeconds`·`sttCalls`
  (평균 음성인식 · 수량을 아는 통화가 분모). 분모가 0 이면 그 키가 없습니다(「모름」 — 0초가 아닙니다).
  음성인식 시간은 **통화 시간에 거의 비례**합니다 — 대본을 짧게 하는 것이 곧 원가 절감입니다.

## 5-1. 전화 없이 시험하기

`POST /api/v1/apps/self/simulate`(앱 키) · body `{"utterances":[…], "caller"?: "…"}` — 실통화와 같은 흐름을 등록된 relay 주소로 돌리고 대화를 글자로 돌려줍니다. 자세한 사용법은 [시작하기 §4](getting-started.md).

## 5-2. 자기 통화 기록 읽기 — DVG 1.4.16.335 이상

```
GET /api/v1/apps/self/diag?days=7&limit=50&orgId=…     Authorization: Bearer dvga_{appId}.{…}
```

DVG 가 남긴 **통화 기록**(대화 전문 · 결말 · 사람에게 넘긴 사유 · 앱이 `transfer.note`·`hangup.note` 로 보낸 메모)을 앱 키로 읽습니다.
`days` 1~92(기본 7) · `limit` 1~500(기본 50 · 최신순) · `orgId` 는 한 회사만.

🔴 **돌려주는 것은 운영사가 설치에서 «기록 공유» 를 켠 회사의 통화뿐입니다**(기본 꺼짐 — 개인정보의 제3자 제공이라 필요하면 운영사에 요청하십시오).
켠 곳이 없으면 `sharedInstallations: 0` · `calls: []` · `note` 로 답합니다 — «통화가 없다» 와 «공유받지 않았다» 를 가르십시오.

```json
{ "supported": true, "appId": "my-app", "days": 7, "sharedInstallations": 1,
  "summary": { "calls": 12, … }, "returned": 12, "truncated": false, "excludedCalls": 3,
  "keep": { "values": true, "caller": true, "dialog": true }, "retentionDays": 90,
  "calls": [ { "at": "…", "orgId": "…", "linkedId": "…", "outcome": "transferred", "toHuman": true,
               "dialog": [ { "from": "ai", "text": "…" }, { "from": "caller", "text": "…" } ],
               "handoffNote": "…", "caller": "010…" } ] }
```

- 🔒 `caller`(발신번호)는 그 설치의 **«발신번호 제공»** 이 켜져 있을 때만 실립니다 — 기록 공유와 **별개**입니다.
- 🔒 담지 않도록 설정된 항목(대화 · 칸 값 · 발신번호)은 기록에 **애초에 없습니다** — `keep` 이 그 상태입니다.
  `handoffNoteWithheld: true` 는 «메모가 있었지만 담지 않음» 입니다(「메모 없음」과 다릅니다).
- `dialog[].text` 가 빈 줄은 `note` 가 그 자리를 말합니다(`silent` · `during_playback` · `low_confidence`).
- 📏 `excludedCalls` 는 기간 안에 있었지만 공유받지 않은 회사의 통화 **수**입니다(내용은 주지 않습니다). `truncated` 는 `limit` 에 잘렸는가입니다.
- `supported: false` = 그 DVG 에 기록 저장이 꺼져 있다 · **502** = 기록을 읽지 못했다(0건이 아닙니다).
- 🧪 시험 통화는 기록되지 않습니다. 보존기간은 `retentionDays` 입니다.


## 5-3. 업무 API 토큰 중개 — DVG 1.4.16.341 이상

```
POST /api/v1/apps/self/token     Authorization: Bearer dvga_{appId}.{…}
{"tenantId":"…","orgId":"…","stale"?:"<만료 응답을 받은 토큰>"}
```

운영사가 그 회사 설치에서 **토큰 중개**를 켰을 때만 동작합니다(지원하는 업무 API 와 provider 값은 운영사가 알려 줍니다). DVG 가 그 회사의 자격증명으로 토큰을 **혼자** 받아 빌려주므로
앱을 여러 대로 돌려도 토큰이 서로를 끊지 않습니다. 비밀 키는 오지 않습니다. `stale` 은 DVG 가 지금 쥔 토큰과 같을 때만 새로 받습니다.
응답·오류·예제는 [외부 API 자격증명 · 토큰 §5](external-api-credentials.md#5-dvg-토큰-중개--post-apiv1appsselftoken-dvg-1416341).

## 5-4. 앱 설정 고치기 — DVG 1.4.16.393 이상

```
GET /api/v1/apps/self       Authorization: Bearer dvga_{appId}.{…}     (지금 설정 · relayHosts 포함)
PUT /api/v1/apps/self       Authorization: Bearer dvga_{appId}.{…}     Content-Type: application/json
```

앱 키로 자기 앱 설정을 고칩니다. **보낸 칸만** 바뀌고, 응답은 바뀐 뒤의 `app` 입니다.

| 칸 | 뜻 |
|---|---|
| `name` | 앱 이름(1~60자) |
| `relayUrl` · `relayUrls` | DVG 가 연결할 주소(`ws://`·`wss://` · 목록은 1~5개 · 첫 주소 = `relayUrl`) — 🔐 **허용 호스트 안에서만** |
| `relayStrategy` | 주소가 여럿일 때 `failover`(순서대로) · `least_busy`(한가한 곳 먼저) |
| `keyterms` | 음성인식 힌트 낱말(2~20자 · 60개까지) |
| `settings` | 설치별 설정 **항목**(통째로 교체 · [§3-8](#3-8-설치별-설정setupsettings--dvg-1416296-이상)) — 값은 운영사가 회사마다 넣습니다 |
| `noticeText` | AI 고지 문구(「AI」 또는 「인공지능」 포함 · 60자 이하 · `""` = 운영사 기본 문구) |
| `simExample` | 시험 예시(한 줄 = 한 발화 · 빈 줄 = 무응답) |

```bash
curl -sS -X PUT -H "Authorization: Bearer $DVG_APP_KEY" -H 'Content-Type: application/json' \
  -d '{"relayUrl":"wss://app.example.com/dvg-relay/v2","keyterms":["화환","화분"]}' \
  "https://<DVG 주소>/api/v1/apps/self"
```

- 🔐 **relay 주소는 운영사가 정한 허용 호스트(`relayHosts`) 안에서만** 바뀝니다. 경로·포트는 자유입니다.
  허용 호스트가 비어 있으면 **403 `relay_hosts_not_set`**, 밖이면 **403 `relay_host_not_allowed`**(응답에 `relayHosts`) — 운영사에 호스트 등록을 요청하십시오.
- 위 표에 없는 칸(켜기·끄기 · 월 상한 · 허용 호스트 등)을 보내면 **400 `field_not_allowed`** 입니다(응답 `allowed` 에 고칠 수 있는 칸). 조용히 무시하지 않습니다.
- 바꿀 칸이 없으면 **400 `nothing_to_change`** · 값이 규칙에 맞지 않으면 **400 `invalid`**(무엇이 틀렸는지 `error` 에).
- 🔑 **키 재발급은 앱 키로 할 수 없습니다** — 키가 샌 것 같으면 운영사에 재발급을 요청하십시오(재발급하면 서명 비밀도 바뀝니다).
- relay 주소를 바꾸면 **다음 통화부터** 새 주소로 갑니다(진행 중인 통화는 그대로). 바꾼 뒤 `simulate`(§5-1)로 확인하십시오.
- 이전 DVG 는 **405** 를 돌려줍니다 — 그때는 운영사에 요청하십시오.

## 6. v1 에 없는 것

- 질문마다 음성인식 힌트 바꾸기 — 앱 등록 단위 낱말만 된다(§3-4)
- 앱이 호전환 번호 지정 — 통화료 사기 위험으로 **막아 두었습니다**
- 원시 오디오
- 운영사 화면 안에 넣는 앱 전용 화면
