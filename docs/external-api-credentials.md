# 외부 API 자격증명 · 토큰

앱은 업무 시스템 API(주문 등록·고객 조회 등)를 **직접** 부릅니다 — DVG 는 그 호출을 중계하지 않습니다.
이 문서는 그 API 의 키·토큰을 **어디에 두고, 어떻게 재사용하고, 앱을 여러 대로 돌릴 때 무엇을 조심하는지**를 다룹니다.

## 1. 먼저 판정 — 그 API 의 토큰은 어떤 종류인가

| 종류 | 예 | 여러 대로 돌리면 |
|---|---|---|
| **고정 키** | 요청마다 `X-Api-Key` 를 싣는다 | 문제 없음 — 서버마다 같은 키를 쓰면 된다 |
| **독립 토큰** | 받을 때마다 새 토큰이 생기고 **앞의 것도 계속 산다** | 문제 없음 — 서버마다 각자 받아 캐시한다 |
| 🔴 **하나뿐인 토큰** | **새로 받으면 앞의 토큰이 즉시 죽는다**(자격증명 하나에 토큰 하나) | 서버마다 받으면 **서로를 끊는다** → §4 |

모르면 업무 시스템 제공사에 «같은 자격증명으로 토큰을 두 번 받으면 첫 토큰이 계속 유효한가» 를 물으십시오. 이 한 가지가 설계를 가릅니다.

## 2. 어디에 두나

| 어디서 돌리나 | 두는 곳 |
|---|---|
| 같은 서버(사이드카) | DVG 운영사가 사이드카 **환경값**으로 넣습니다. 앱은 환경변수로 읽습니다. DVG 화면·API 는 값을 다시 보여 주지 않습니다(이름만). ⚠️ 값을 바꾸면 **앱을 다시 시작해야** 반영됩니다(DVG 가 `restartRequired` 로 알린다) |
| 다른 서버 | `/etc/dvg-app/app.env`(0640 · 앱 사용자만 읽기) — [실서버 설치](deploy-quickstart.md) B |
| Cloud Run | Secret Manager 에 넣고 `--set-secrets 이름=비밀:latest` 로 환경변수가 되게 합니다(서명 비밀과 같은 방법 — [실서버 설치](deploy-quickstart.md) B2) |

- 🔴 설치별 설정(`setup.settings`)에는 **넣지 마십시오** — 그 값은 운영자 화면과 메시지에 그대로 보입니다.
- 🔴 키·토큰을 **로그에 남기지 마십시오.** 오류 메시지에 요청 URL 이 통째로 들어가는 라이브러리가 많습니다 — 쿼리에 키가 실리는 API 면 오류를 그대로 찍지 말고 상태 코드만 남기십시오.

## 3. 토큰 재사용 규칙

1. **호출마다 받지 않는다.** 받은 토큰을 기억해 두고 만료(또는 «만료됐다» 응답)까지 씁니다.
2. **동시에 한 번만 받는다.** 통화 여러 건이 동시에 «토큰이 없다» 를 보면 한 건만 받고 나머지는 그 결과를 기다리게 합니다.
3. **재시작 너머로 잇는다.** `DVG_APP_DATA_DIR`(사이드카) 같은 곳에 0600 으로 저장하고 시작할 때 읽습니다. 그렇지 않으면 배포·재시작마다 새로 받습니다.
4. **만료 응답을 받으면 «내가 쓴 토큰이 지금 쥔 토큰과 같을 때만»** 새로 받습니다. 다르면 다른 요청이 이미 바꿔 둔 것이니 그 새 토큰으로 다시 시도만 합니다.

## 4. 앱을 여러 대로 돌릴 때(«하나뿐인 토큰» API)

Cloud Run 자동 확장, 서버 두 대 이중화처럼 **앱 인스턴스가 둘 이상**이면 §3 만으로는 부족합니다 — 인스턴스끼리는 기억을 공유하지 않습니다.
고를 수 있는 방법:

| 방법 | 어떻게 | 고려할 점 |
|---|---|---|
| **A. 인스턴스 하나로 고정** | Cloud Run `--max-instances 1` · 서버는 액티브-스탠바이 | 가장 단순. 대신 그 한 대가 부하를 다 진다 |
| **B. 인스턴스마다 다른 자격증명** | 제공사에 자격증명을 여러 벌 받는다 | 서로 간섭이 0. 자격증명마다 비용이 붙을 수 있다 |
| **C. 공유 저장소** | Redis·DB 에 토큰 하나 + **받을 때만 잠금** + §3-4 비교 | 인스턴스 수와 무관. 그 저장소를 운영해야 한다 |
| **D. DVG 토큰 중개** | DVG 가 토큰을 **혼자** 받아 빌려준다(§5) | DVG 가 그 API 의 발급 방법을 알 때만(지원 목록은 §5) · 운영사가 설치에서 켠다 |

## 5. DVG 토큰 중개 — `POST /api/v1/apps/self/token` (DVG 1.4.16.341+)

DVG 운영사가 그 회사 설치에서 **토큰 중개**를 켜면(지원: `insung`), DVG 가 그 회사의 자격증명으로 토큰을 받아 앱에 빌려줍니다.
**비밀 키는 앱에 오지 않습니다** — 호출에 필요한 토큰과 식별자만 옵니다. 같은 회사의 DVG 내장 기능과도 같은 토큰을 쓰므로 서로 끊지 않습니다.

```
POST /api/v1/apps/self/token         Authorization: Bearer dvga_{appId}.{…}
{"tenantId":"…","orgId":"…"}                       ← setup 의 tenantId·orgId
{"tenantId":"…","orgId":"…","stale":"<토큰>"}       ← 이 토큰이 «만료» 응답을 받았다
```

```json
{ "provider": "insung", "token": "…", "mCode": "…", "ccCode": "…", "userId": "…", "baseUrl": "https://…",
  "ageSeconds": 812, "reissued": false, "replaced": false }
```

- `stale` 이 **DVG 가 지금 쥔 토큰과 같을 때만** 새로 받습니다(`reissued:true`). 다르면 이미 바뀐 것이라 새로 받지 않고 지금 토큰을 줍니다(`replaced:true`).
- 응답을 받은 토큰은 **그대로 캐시**하고, 업무 API 가 만료를 알릴 때만 `stale` 과 함께 다시 부르십시오. 매 호출마다 부를 필요는 없습니다.
- 오류: `403 token_broker_off`(운영사가 켜지 않았다 — 앱이 자기 자격증명으로 받아야 한다) · `404 not_installed` · `409 insung_credentials_missing` ·
  `429 reissue_limited`(막 받은 토큰이 거듭 죽는다 — **같은 자격증명으로 직접 받는 곳이 있다**) · `502 token_issue_failed` · `503 token_cache_local`.
- 🔴 중개를 쓰는 앱은 **같은 자격증명으로 직접 토큰을 받지 마십시오** — 받는 순간 DVG 가 빌려준 토큰이 죽습니다.

예(Python · 표준 라이브러리만 · 스레드 안전):

```python
import json, threading, urllib.request

class BrokeredToken:
    """DVG 토큰 중개 — 회사(tenantId, orgId)마다 토큰 하나를 기억하고, 만료 때만 stale 과 함께 다시 받는다."""

    def __init__(self, api_base, app_key):
        self.api_base, self.app_key = api_base.rstrip("/"), app_key
        self.lock, self.cache = threading.Lock(), {}

    def _ask(self, tenant, org, stale=None):
        body = {"tenantId": tenant, "orgId": org}
        if stale:
            body["stale"] = stale
        req = urllib.request.Request(self.api_base + "/api/v1/apps/self/token", data=json.dumps(body).encode(),
                                     headers={"Authorization": "Bearer " + self.app_key, "Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)

    def get(self, tenant, org):
        with self.lock:  # 같은 인스턴스 안에서는 한 번만 묻는다
            if (tenant, org) not in self.cache:
                self.cache[(tenant, org)] = self._ask(tenant, org)
            return self.cache[(tenant, org)]

    def expired(self, tenant, org, used_token):
        """업무 API 가 «만료» 라고 답했을 때 — 쓴 토큰을 알려 주고 새(또는 이미 바뀐) 토큰을 받는다."""
        with self.lock:
            cur = self.cache.get((tenant, org))
            if cur and cur["token"] != used_token:
                return cur  # 이 인스턴스의 다른 요청이 이미 바꿨다
            self.cache[(tenant, org)] = self._ask(tenant, org, stale=used_token)
            return self.cache[(tenant, org)]
```

사이드카에서는 `DVG_API_BASE` 가 이 API 의 주소입니다. 앱 키는 운영사에게 받은 `dvga_…` 입니다(서명 비밀과 다릅니다).

## 6. 시간과 실패

- **10초 규칙** — DVG 메시지를 받고 10초 안에 지시를 보내야 합니다. 업무 API 시간 제한은 그보다 짧게 잡고, 느릴 수 있으면 먼저 `say` 로 시간을 버십시오.
- **가입자 조회는 벨 울리는 동안** — 걸려 온 통화의 setup 은 전화를 받기 **전에** 옵니다(`ringing:true` · 계약 §3-14). 그때 조회를 시작하고 다 되면 첫 지시를 보내십시오.
- 🔴 **주문 등록은 재시도하지 마십시오**(또는 제공사의 멱등 키를 쓰십시오) — 응답을 못 받은 주문을 다시 보내면 **중복 주문**이 됩니다. 결과를 모르면 «모름» 으로 두고 사람에게 넘기십시오.
- 만료와 «자격증명 틀림» 을 섞지 마십시오 — 틀린 자격증명으로는 몇 번을 다시 받아도 같습니다. 그때는 재시도하지 말고 운영사에 알리십시오.
