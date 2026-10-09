// 서명 시험 벡터 — Node 예제의 verifyDvg 가 DVG 와 같은 값을 받아들이는가.
import fs from 'node:fs';
import { verifyDvg } from '../examples/node/order_app.mjs';

const v = JSON.parse(fs.readFileSync(new URL('./vector.json', import.meta.url)));
const h = { 'x-dvg-app-id': v.appId, 'x-dvg-call-id': v.callId, 'x-dvg-timestamp': String(v.timestamp), 'x-dvg-signature': v.signature };
const ts = v.timestamp;
const checks = [
  ['벡터를 받아들인다', verifyDvg(h, v.signingSecret, ts), true],
  ['틀린 서명은 거절', verifyDvg({ ...h, 'x-dvg-signature': '0'.repeat(64) }, v.signingSecret, ts), false],
  ['틀린 비밀은 거절', verifyDvg(h, 'other-secret', ts), false],
  ['300초 넘게 지난 연결은 거절', verifyDvg(h, v.signingSecret, ts + 301), false],
  ['300초 이내는 받는다', verifyDvg(h, v.signingSecret, ts + 300), true],
];
let fail = 0;
for (const [name, got, want] of checks) { console.log(got === want ? 'ok  ' : 'FAIL', name); if (got !== want) fail++; }
process.exit(fail ? 1 : 0);
