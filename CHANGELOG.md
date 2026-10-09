# 계약 변경 이력

필드 추가는 버전을 올리지 않습니다(모르는 필드는 무시). **기존 앱을 깨뜨리는 변경만** 버전을 올립니다.

## 앞의 말 버리기 `ask.discardEarlier` (DVG 1.4.16.384+)

- 필드 추가(버전 불변). `true` 면 질문을 말하기 전에 들린 발신자 말은 그 질문의 대답에서 뺍니다. 질문 도중 끼어든 말은 그대로 대답이 됩니다(계약 §3-7).
- 이전 DVG 는 필드를 무시합니다(앞의 말도 대답에 들어갑니다).

## 생년월일 `ask.expect:"birth"` (DVG 1.4.16.372+)

- 값 추가(버전 불변). `expect:"birth"` 로 물으면 DVG 가 생년월일 받기를 이끕니다 — `prompt.birth.status`(`need`·`confirm`·`done`·`handoff`)를 보고 `question` 을 그대로 다시 묻습니다(계약 §3-16).
- 확인 단계(`confirm`)는 생략할 수 없고, 확인 뒤 `chart` 가 옵니다. `choices`·`listenSeconds` 와 함께 쓸 수 있습니다(다른 `expect` 와 달리 `choices` 와 함께 써도 `bad_expect` 가 아닙니다).
- 이전 DVG 는 `error bad_expect` — `expect` 를 빼고 다시 물으십시오.

## 상담원 근무 시간 `setup.staff` (DVG 1.4.16.362+)

- 필드 추가(버전 불변). `onDuty` · `nextOpen`·`nextOpenText` · `callback` · `handoffNotice`(계약 §3-15). 근무 시간을 모르면 키가 없습니다.
- 근무 시간 밖에 `transfer` 할 때는 그 전 `say` 에 `handoffNotice` 를 붙이십시오.

## 주소 — 빈소 호실 `room` (DVG 1.4.16.349+)

- 필드 추가(버전 불변). 장례식장 답에 호실이 섞이면 `room`(예: `"3호실"`)이 옵니다(계약 §3-5). 장례식장 배송인데 이 값이 없으면 호실을 물으십시오.

## 주소 — 동 뒤 말 정리 `detailClean` · `detailRepaired` · `needsBuilding` · `heardName` (DVG 1.4.16.347+)

- 필드 추가(버전 불변 · `detail` 은 종전대로 들은 그대로). 정리된 상세 주소 `detailClean`, 고친 흔적 `detailRepaired`, 건물 이름이 필요하면 `needsBuilding:true`, 사전에 없는 장소 이름 `heardName`(계약 §3-5).
- 예제 `slot_app.py` 는 `detailClean` 을 쓰고 `needsBuilding` 이면 건물 이름을 한 번 묻습니다.

## 구버전 DVG 대비 안내 (계약 §3-13)

- 문서만. DVG 1.4.16.339 이전은 `expect:"phone"` 과, 선택지·`expect` 와 함께 쓰는 `listenSeconds` 를 거절합니다 — 그 오류를 받으면 옵션을 줄여 같은 질문을 다시 보내십시오.

## 여러 대로 돌리기 — 연결 주소 여러 개 (DVG 1.4.16.342+)

- 계약 변경 없음. 운영사가 앱 등록에 주소를 최대 5개 넣고 고르는 방법(«순서대로» · «한가한 곳 먼저»)을 정합니다. 통화 한 건은 한 인스턴스에 고정됩니다([시작하기 §2-2](docs/getting-started.md#2-2-여러-대로-돌리기dvg-1416342)).

## 업무 API 토큰 중개 `POST /api/v1/apps/self/token` (DVG 1.4.16.341+) · 외부 API 자격증명 안내

- 엔드포인트 추가(버전 불변). 운영사가 토큰 중개를 켠 회사에서는 DVG 가 받은 업무 API 토큰을 앱에 빌려줍니다(계약 §5-3). 쓰려면 운영사에 요청하십시오.
- 문서 [외부 API 자격증명 · 토큰](docs/external-api-credentials.md) 추가.

## 벨 울리는 동안 setup `ringing` (DVG 1.4.16.340+)

- 필드 추가(버전 불변). 걸려 온 통화에서 setup 이 전화를 받기 전에 올 수 있습니다(`ringing:true`). 준비가 끝나면 첫 지시를 보내십시오(계약 §3-14). 이 필드를 모르는 앱도 그대로 동작합니다.

## 응답 속도 — `expect:"phone"` · `prepare` · 일찍 받기 (DVG 1.4.16.339+)

- 필드·지시 추가(버전 불변). 선택지에 맞는 답 · 네/아니요 · 다 말한 전화번호(`expect:"phone"`)가 들리면 DVG 가 일찍 대답을 넘깁니다(계약 §3-13).
- `prepare` — 곧 말할 문장을 미리 준비시킵니다(말하지 않음). `listenSeconds` 를 선택지·`expect:"phone"` 과 함께 쓸 수 있습니다(주소는 불가).
- 기록 조회(§5-2)에 턴별 시간 `timing`.

## 사용량 평균 `averages` (DVG 1.4.16.338+)

- 필드 추가(버전 불변). `/apps/self/usage` 응답에 평균 통화·평균 음성인식(계약 §5). 분모가 0 이면 키가 없습니다.

## 끊기에도 상담원 메모 `hangup.note` (DVG 1.4.16.336+)

- 필드 추가(버전 불변). `hangup` 에도 `note` 를 실을 수 있습니다(계약 §3-12). 규칙은 `transfer.note` 와 같고, 모르는 DVG 는 무시합니다.

## 자기 통화 기록 읽기 `GET /api/v1/apps/self/diag` (DVG 1.4.16.335+)

- 조회 API 추가(버전 불변). 앱 키로 대화 · 결말 · 메모를 읽습니다(계약 §5-2).
- 운영사가 그 회사에 «기록 공유» 를 켠 경우에만 돌려줍니다(기본 꺼짐). 발신번호는 «발신번호 제공» 설정을 따로 따릅니다. 필요하면 운영사에 요청하십시오.

## Java 예제 (계약 변경 없음)

- [examples/java](examples/java/) — 다른 예제와 같은 동작의 Java 17+ 예제. 서명 확인은 시험 벡터로 검사합니다(`mvn test`). 계약 §2 에 Java 서명 확인 예를 더했습니다.

## 상담원 메모 `transfer.note` (DVG 1.4.16.334+) · 주소 `near_venue` (DVG 1.4.16.329+)

- 필드 추가(버전 불변). `transfer.note` 에 상담원에게 전할 메모를 실으면 DVG 통화 기록에 남습니다(계약 §3-12). DVG 가 상담원에게 직접 전하지는 않습니다.
- `address.source` 에 `near_venue` 추가 — 비슷한 장소 이름을 확인하는 질문입니다(`ambiguous` · 후보가 하나일 수 있음). `question` 을 그대로 다시 물으십시오.
- ⚠️ DVG 1.4.16.330 이전에는 후보 하나짜리 확인 질문(`near_dong` 포함)에 「네」가 확정되지 않았습니다.

## 못 알아들은 대답 알리기 `unrecognized` (DVG 1.4.16.319+)

- 필드 추가(버전 불변). 어느 지시에나 `unrecognized: ["…"]` 로 앱이 알아듣지 못한 대답을 알릴 수 있습니다(계약 §3-11). 자동으로 고쳐지지는 않습니다 — 못 알아들은 답만 넣으십시오.

## 예시는 낱말마다 마침표 · 시험의 `toneWarning` (DVG 1.4.16.308+)

- 메시지 모양 불변. 시험(`/simulate`) 응답의 AI 줄에 `toneWarning` 이 붙을 수 있습니다(예시가 붙어 들리는 문장).
- 예시는 쉼표나 「~인지, ~인지」로 잇지 말고 낱말마다 마침표로 끊으십시오(「선불. 착불. 결제는 어느 쪽인가요?」).
- `address.question` 의 문구가 바뀌었습니다 — 지금처럼 글자 그대로 다시 물으면 됩니다.

## 끊긴 뒤 문자 창 (DVG 1.4.16.311+)

- 메시지 모양 불변. `end`(`caller_hangup`) 뒤 30초 동안 `sms` 만 더 받습니다.
- 문자로 보낼 수 없는 글자(이모지 등)는 「?」로 바뀝니다.

## 모은 칸 보여 주기 `slots` (DVG 1.4.16.307+)

- 필드 추가(버전 불변). 어느 지시에나 `slots:[{key,label,value,state}]` 를 실으면 운영사 화면에 칸으로 보입니다(계약 §3-10).
- 상태는 `none`·`partial`·`done`·`blocked`. 상한을 넘으면 잘릴 뿐 지시는 거절되지 않습니다.

## 통화 상대에게 문자 `sms` (DVG 1.4.16.307+)

- 지시 추가(버전 불변). `{"type":"sms","text":…}` → `{"type":"sms_result","status":…}`(계약 §3-9).
- 받는 사람은 그 통화의 상대로 고정입니다. 한 통 80바이트 · 한 통화 4통 · 수신 통화에서만(DVG 가 건 통화는 `unavailable`).
- 실패(`failed`·`unavailable`·`not_mobile` …)는 위반이 아닙니다.
- 구버전 DVG 는 `error unknown_type`(위반으로 셈) — 그 통화에서는 더 보내지 마십시오.

## 말씀이 끝나면 일찍 닫기 `ask.endSilenceSeconds` (DVG 1.4.16.304+)

- 필드 추가(버전 불변). `listenSeconds` 와 함께 `endSilenceSeconds`(2~10)를 실으면 발신자가 말한 뒤 그만큼 조용할 때 일찍 닫습니다(계약 §3-7). 적용되면 `prompt.endSilenceSeconds` 에 같은 값이 돌아옵니다.
- 넣지 않으면 종전대로 창 끝까지 듣습니다. 구버전 DVG 는 무시합니다.

## 설치별 설정 `setup.settings` (DVG 1.4.16.296+)

- 필드 추가(버전 불변). 회사(설치)마다 다른 값을 `setup.settings` 로 받습니다(계약 §3-8).
- 항목(키·이름·기본값)은 앱 등록에 선언하고 값은 운영사가 회사별로 넣습니다 — 운영사에 요청하십시오. 키가 없으면 앱의 기본값을 쓰십시오.
- AI 고지 문구도 앱마다 정할 수 있습니다(운영사가 앱 등록에 · 「AI」 포함 필수 · DVG 가 먼저 재생). 메시지 모양은 그대로입니다.

## 주소: 잘못 들린 동은 «그 구·군 안의 비슷한 동» 으로 묻는다 (DVG 1.4.16.293+)

- 필드 추가(버전 불변). `address.source` 에 `near_dong` 추가 · `status` 는 `ambiguous`.
- ⚠️ 이때 `candidates[].dong` 이 채워지고 후보가 하나일 수 있습니다. 후보가 둘 이상이라고 가정한 앱은 고치십시오 — `question` 을 그대로 다시 물으면 됩니다(`slot_app.py` 는 이미 그렇게 합니다).

## DVG 가 거는 통화 `setup.direction` (DVG 1.4.16.292+)

- 필드 추가(버전 불변). DVG 가 먼저 건 통화는 `setup.direction:"outbound"`, 수신은 `"inbound"` · 키가 없으면 수신입니다.
- `caller` 는 발신 통화에서도 상대 번호입니다(발신번호 제공이 켜진 경우만). 첫인사를 바꾸려는 앱만 보면 됩니다.

## 긴 듣기 `ask.listenSeconds` (DVG 1.4.16.291+)

- 필드 추가(버전 불변). `listenSeconds`(5~90)를 실으면 그 시간 동안 쉼으로 끊지 않고 말을 모아 한 번에 줍니다(계약 §3-7).
- 적용되면 `prompt.listenSeconds` 에 같은 값이 돌아옵니다. 키가 없으면 적용되지 않은 것(구버전 DVG)입니다.
- 범위 밖이거나 허용되지 않는 조합이면 `error bad_listen_seconds`.

## 예제: 연결이 닫히면 통화가 끝난 것으로

- 예제(파이썬·Go·Node)는 `end` 없이 연결이 닫혀도 통화 종료(`closed`)로 처리합니다. 앱도 그렇게 하십시오.
- DVG 1.4.16.275 부터 `end` 뒤에 close(1000) 로 닫습니다(계약 §3-2 `end` 행 — 정상 종료 · 닫힘 = 끝 · 결말 모름).

## Cloud Run 배포 안내 보강

- 퀵 가이드 B2 에 `--min-instances 0` 선택지를 더했습니다(첫 통화가 약간 늦어질 수 있음). 새 판 배포 중 진행 통화의 동작은 확인되지 않았습니다.

## Cloud Run 예제

- `examples/python/Dockerfile` — `PORT` 로 듣고 root 가 아닌 사용자로 돕니다. 퀵 가이드 B2 에 배포 명령.
- 예제 앱이 서명 비밀의 앞뒤 공백·줄바꿈을 버립니다(붙은 줄바꿈 하나로 모든 서명이 어긋날 수 있습니다).

## 실서버 설치 퀵 가이드 (DVG 1.4.16.262+)

- `docs/deploy-quickstart.md` + `deploy/`(nginx relay·콘솔 설정, systemd 유닛 둘, 같은 서버용 `run`).

## 앱 개발사 콘솔 샘플 (DVG 1.4.16.259+)

- `console/` — 앱 정보 · 사용량 · 시뮬레이터 위젯. 앱 키는 작은 서버가 들고 세 경로만 넘깁니다(브라우저에 키 없음 · 리다이렉트 안 따라감).
- 새 API 없이 `/api/v1/apps/self`·`/self/usage`·`/self/simulate` 를 씁니다.

## 그라파나 템플릿 (DVG 1.4.16.271+)

- 대시보드 3개 · 프로메테우스+그라파나 docker compose 예제. 지표는 계약 v1 과 별개이며 지표 이름은 바꾸지 않습니다(새로 더할 뿐입니다).

## v1 (DVG 1.4.16.257+)

- 1.4.16.265 — `ask.expect:"address"`·`ask.label` + `prompt.address`(주소 풀이 · 좁히는 질문 · 좌표는 운영사에 요청) · `error bad_expect` · 사용량 `addressLookups`·`coordLookups`
- 1.4.16.262 — 같은 서버 실행 시 환경변수 `DVG_APP_*`
- 1.4.16.261 — `say.interruptible` · `prompt.heardVoice`
- 1.4.16.260 — `ask.choices` + `prompt.choice`·`choiceIndex`·`choiceSource`·`confirm`·`choiceAmbiguous`
- 1.4.16.259 — `setup.simulated`(전화 없는 시험) · `POST /api/v1/apps/self/simulate`
- 1.4.16.257 — 최초: `setup`·`said`·`prompt`·`error`·`end` / `say`·`ask`·`transfer`·`hangup` · HMAC 서명 연결
