// DVG 외부 앱 최소 예제 (Node.js) — 음성 주문 접수 · 관리형 음성 레이어 v1.
//
// DVG 가 전화·음성인식·음성합성을 맡고, 이 앱은 **텍스트로만** 대화를 이끈다.
// 계약: ../../docs/voice-relay-v1.md
//
// 실행:
//   npm install
//   DVG_SIGNING_SECRET=... node order_app.mjs      # 기본 127.0.0.1:19999, 경로 /relay
//
// DVG 사이드카(같은 서버에서 DVG 가 띄움)로 돌리면 DVG_APP_* 가 자동으로 들어온다.
// ⚠️ 예제다 — 실제 주문 등록은 registerOrder() 자리에 넣는다(업무 시스템 API 는 앱이 직접 부른다).

import crypto from 'node:crypto';
import http from 'node:http';
import { pathToFileURL } from 'node:url';
import { WebSocketServer } from 'ws';

const env = (...names) => names.map((n) => process.env[n]).find((v) => v) || '';
const SIGNING_SECRET = env('DVG_APP_SIGNING_SECRET', 'DVG_SIGNING_SECRET');
const HOST = env('DVG_APP_HOST', 'APP_HOST') || '127.0.0.1';
const PORT = Number(env('DVG_APP_PORT', 'APP_PORT') || 19999);
const PATH = env('DVG_APP_PATH', 'APP_PATH') || '/relay';
const MAX_SKEW = 300; // 초 — 이보다 오래된(또는 미래의) 연결은 거절한다(재생 방지)

// DVG 가 건 연결인가 — 서명·타임스탬프 확인.
export function verifyDvg(headers, secret, now = Math.floor(Date.now() / 1000)) {
  const appId = headers['x-dvg-app-id'] || '';
  const callId = headers['x-dvg-call-id'] || '';
  const ts = headers['x-dvg-timestamp'] || '';
  const sig = headers['x-dvg-signature'] || '';
  if (!(secret && appId && callId && /^\d+$/.test(ts) && sig)) return false;
  if (Math.abs(now - Number(ts)) > MAX_SKEW) return false;
  const want = crypto.createHmac('sha256', secret).update(`${appId}\n${callId}\n${ts}`).digest('hex');
  const a = Buffer.from(want), b = Buffer.from(sig);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

class CallEnded extends Error {}

// 한 통화의 메시지를 차례대로 받는다(DVG 는 엄격한 요청·응답 — 메시지 하나당 지시 하나).
function session(ws) {
  const queue = [];
  const waiters = [];
  let closed = false;
  ws.on('message', (data) => {
    const msg = JSON.parse(data.toString());
    const w = waiters.shift();
    w ? w(msg) : queue.push(msg);
  });
  ws.on('close', () => { closed = true; while (waiters.length) waiters.shift()({ type: 'end', reason: 'closed' }); });
  const recv = async () => {
    const msg = queue.length ? queue.shift() : closed ? { type: 'end', reason: 'closed' } : await new Promise((r) => waiters.push(r));
    if (msg.type === 'end') throw new CallEnded(msg.reason || '');
    return msg;
  };
  const send = (m) => ws.send(JSON.stringify(m));
  return {
    recv,
    async say(text) { send({ type: 'say', text }); await recv(); },
    // 질문하고 답을 받는다. choices 를 주면 DVG 가 답을 그중 하나로 읽어 준다(초성 판정 포함).
    async ask(text, choices) {
      send(choices ? { type: 'ask', text, choices } : { type: 'ask', text });
      const m = await recv();
      if (m.type !== 'prompt' || m.silence) return '';
      return choices ? (m.choice || '') : (m.text || '').trim();
    },
    async end(type, text) { send(text ? { type, text } : { type }); await recv(); },
  };
}

function registerOrder(order, setup) {
  if (setup.simulated) {
    // 🔴 시험 통화(대시보드 🧪) — 실제 주문을 만들지 않는다.
    console.log('시험 통화 — 주문 등록 건너뜀:', JSON.stringify(order));
    return true;
  }
  console.log('주문 등록(예제):', JSON.stringify({ org: setup.orgId, ...order }));
  return true;
}

async function handle(ws) {
  const s = session(ws);
  try {
    const setup = await s.recv(); // 첫 메시지는 항상 setup
    console.log('통화 시작', setup.callId, setup.caller ? '발신번호 제공' : '발신번호 없음');
    const order = {};
    // (칸, 첫 질문, 다시 물을 때의 질문) — 🔴 같은 문장을 되풀이하지 않는다. 다시 물을 때는 질문을 바꾼다.
    for (const [key, question, again, choices] of [
      ['origin', '어디에서 보내시나요?', '제가 잘 못 들었습니다. 물건을 가지러 갈 곳을 말씀해 주세요.'],
      ['destination', '어디로 보내시나요?', '제가 잘 못 들었습니다. 물건을 받으실 곳을 말씀해 주세요.'],
      ['pay', '결제는 선불인가요 착불인가요?', '제가 잘 못 들었습니다. 선불이면 「선불」. 착불이면 「착불」.', ['선불', '착불']],
    ]) {
      let answer = await s.ask(question, choices);
      if (!answer) answer = await s.ask(again, choices);
      if (!answer) return s.end('transfer'); // 번호는 DVG 가 정한다(앱이 지정할 수 없다)
      order[key] = answer;
    }
    // 복창 — 나열은 마침표로 끊는다(쉼표로 이으면 전화에서 한 덩어리로 들린다).
    const ok = await s.ask(`출발 ${order.origin}. 도착 ${order.destination}. 결제 ${order.pay}. 맞으면 「네」라고 말씀해 주세요.`);
    if (!/^(네|예|맞)/.test(ok)) return s.end('transfer');
    await (registerOrder(order, setup) ? s.end('hangup', '접수되었습니다. 감사합니다.') : s.end('transfer'));
  } catch (e) {
    if (e instanceof CallEnded) console.log('통화 끝:', e.message);
    else { console.error('앱 오류:', e); ws.close(); }
  }
}

function main() {
if (!SIGNING_SECRET) {
  console.error('DVG_SIGNING_SECRET 이 비어 있습니다 — 앱 등록 때 받은 서명 비밀을 넣으세요');
  process.exit(1);
}
const wss = new WebSocketServer({ noServer: true, maxPayload: 1 << 20 });
const server = http.createServer((_, res) => { res.writeHead(404).end('not found\n'); });
// WebSocket 업그레이드 전에 거른다 — 경로가 다르거나 서명이 틀리면 연결 자체를 받지 않는다.
server.on('upgrade', (req, socket, head) => {
  const path = (req.url || '').split('?')[0];
  if (path !== PATH) { socket.end('HTTP/1.1 404 Not Found\r\n\r\n'); return; }
  if (!verifyDvg(req.headers, SIGNING_SECRET)) { socket.end('HTTP/1.1 401 Unauthorized\r\n\r\n'); return; }
  wss.handleUpgrade(req, socket, head, (ws) => handle(ws));
});
server.listen(PORT, HOST, () => console.log(`listening ws://${HOST}:${PORT}${PATH}`));
}

// 직접 실행할 때만 서버를 연다(시험이 verifyDvg 만 가져다 쓸 수 있게).
if (import.meta.url === pathToFileURL(process.argv[1] || '').href) main();
