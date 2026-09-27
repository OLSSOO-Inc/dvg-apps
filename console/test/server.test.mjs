// 콘솔 서버 시험 — 가짜 DVG 를 띄워 실제 HTTP 로 확인한다.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { loadConfig, createServer } from '../server.mjs';

const KEY = 'dvga_test0000.' + 'a'.repeat(64);
const seen = [];
let fake;
let consoleSrv;
let base;
let keyFile;

function listen(srv) {
  return new Promise((r) => srv.listen(0, '127.0.0.1', () => r(srv.address().port)));
}

before(async () => {
  fake = http.createServer((req, res) => {
    let body = '';
    req.on('data', (c) => (body += c));
    req.on('end', () => {
      seen.push({ method: req.method, url: req.url, auth: req.headers.authorization, body });
      const send = (s, o, h = {}) => { res.writeHead(s, { 'Content-Type': 'application/json', ...h }); res.end(JSON.stringify(o)); };
      if (req.url === '/api/v1/apps/self') return send(200, { app: { id: 'demo', name: '데모', keyHint: 'aaaa' }, installations: 1 });
      if (req.url.startsWith('/api/v1/apps/self/usage')) return send(200, { supported: true, found: false, month: '2026-09' });
      if (req.url === '/api/v1/apps/self/simulate') {
        if (JSON.parse(body).utterances[0] === 'rate') return send(429, { code: 'rate_limited' }, { 'Retry-After': '42' });
        return send(200, { simulated: true, outcome: 'completed', transcript: [] });
      }
      if (req.url === '/redirect-me') { res.writeHead(302, { Location: 'http://evil.invalid/' }); return res.end(); }
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('404 page not found\n');
    });
  });
  const fp = await listen(fake);
  const dir = mkdtempSync(path.join(tmpdir(), 'dvg-console-'));
  keyFile = path.join(dir, 'key');
  writeFileSync(keyFile, KEY + '\n');
  const cfg = loadConfig({ DVG_BASE_URL: `http://127.0.0.1:${fp}`, DVG_APP_KEY_FILE: keyFile });
  assert.deepEqual(cfg.errors, []);
  consoleSrv = createServer(cfg);
  base = `http://127.0.0.1:${await listen(consoleSrv)}`;
});

after(() => { fake.close(); consoleSrv.close(); });

async function get(p, opts) {
  const r = await fetch(base + p, opts);
  return { status: r.status, text: await r.text(), headers: r.headers };
}

test('앱 키를 붙여 DVG 로 넘기고, 응답에는 키가 없다', async () => {
  seen.length = 0;
  const r = await get('/api/self');
  assert.equal(r.status, 200);
  assert.equal(seen[0].auth, `Bearer ${KEY}`);
  assert.ok(!r.text.includes(KEY));
  assert.ok(!r.text.includes('a'.repeat(64)));
});

test('config.json 에 키가 없다', async () => {
  const r = await get('/config.json');
  assert.equal(r.status, 200);
  assert.ok(!r.text.includes(KEY));
  assert.deepEqual(JSON.parse(r.text).widgets, ['app', 'usage', 'simulate']);
});

test('넘기는 경로는 셋뿐 — 나머지는 DVG 에 가지 않는다', async () => {
  seen.length = 0;
  for (const p of ['/api/v1/apps', '/api/apps', '/api/self/../v1/apps', '/api/metrics', '/api/redirect-me']) {
    assert.equal((await get(p)).status, 404, p);
  }
  assert.equal((await get('/api/self', { method: 'DELETE' })).status, 404);
  assert.equal(seen.length, 0);
});

test('month 형식이 틀리면 DVG 에 보내지 않는다', async () => {
  seen.length = 0;
  assert.equal((await get('/api/usage?month=2026-13')).status, 400);
  assert.equal((await get('/api/usage?month=../../x')).status, 400);
  assert.equal(seen.length, 0);
  assert.equal((await get('/api/usage?month=2026-09')).status, 200);
  assert.equal(seen[0].url, '/api/v1/apps/self/usage?month=2026-09');
});

test('시뮬레이터: 본문을 그대로 넘기고 Retry-After 를 전한다', async () => {
  seen.length = 0;
  const ok = await get('/api/simulate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ utterances: ['안녕'] }) });
  assert.equal(ok.status, 200);
  assert.deepEqual(JSON.parse(seen[0].body), { utterances: ['안녕'] });
  const rl = await get('/api/simulate', { method: 'POST', body: JSON.stringify({ utterances: ['rate'] }) });
  assert.equal(rl.status, 429);
  assert.equal(rl.headers.get('retry-after'), '42');
});

test('64KB 를 넘는 본문은 DVG 에 보내지 않는다', async () => {
  seen.length = 0;
  const r = await get('/api/simulate', { method: 'POST', body: 'x'.repeat(70 * 1024) });
  assert.equal(r.status, 413);
  assert.equal(seen.length, 0);
});

test('정적 파일은 public/ 밖을 주지 않는다', async () => {
  assert.equal((await get('/')).status, 200);
  assert.equal((await get('/lib/format.js')).status, 200);
  for (const p of ['/../server.mjs', '/%2e%2e/server.mjs', '/..%2fserver.mjs', `/${encodeURIComponent(keyFile)}`]) {
    const r = await get(p);
    assert.equal(r.status, 404, p);
    assert.ok(!r.text.includes(KEY), p);
  }
});

test('보안 헤더', async () => {
  const r = await get('/');
  assert.match(r.headers.get('content-security-policy'), /default-src 'self'/);
  assert.equal(r.headers.get('x-content-type-options'), 'nosniff');
});

test('DVG 가 꺼져 있으면 502 로 사정을 말한다(키 없이)', async () => {
  const cfg = loadConfig({ DVG_BASE_URL: 'http://127.0.0.1:1', DVG_APP_KEY_FILE: keyFile });
  const srv = createServer(cfg);
  const p = await listen(srv);
  const r = await fetch(`http://127.0.0.1:${p}/api/self`);
  const t = await r.text();
  srv.close();
  assert.equal(r.status, 502);
  assert.equal(JSON.parse(t).code, 'dvg_unreachable');
  assert.ok(!t.includes(KEY));
});

test('설정: 밖에서 열리는데 비밀번호가 없으면 시작하지 않는다', () => {
  const c = loadConfig({ DVG_BASE_URL: 'https://dvg.example.com', DVG_APP_KEY_FILE: keyFile, HOST: '0.0.0.0' });
  assert.ok(c.errors.some((e) => e.includes('CONSOLE_PASSWORD')));
  const ok = loadConfig({ DVG_BASE_URL: 'https://dvg.example.com', DVG_APP_KEY_FILE: keyFile, HOST: '0.0.0.0', CONSOLE_PASSWORD: 'x' });
  assert.deepEqual(ok.errors, []);
});

test('설정: 평문 DVG 주소는 경고 · 키 파일 오류는 시작 거부', () => {
  assert.equal(loadConfig({ DVG_BASE_URL: 'http://dvg.example.com', DVG_APP_KEY_FILE: keyFile }).warnings.length, 1);
  assert.equal(loadConfig({ DVG_BASE_URL: 'http://127.0.0.1:8080', DVG_APP_KEY_FILE: keyFile }).warnings.length, 0);
  assert.ok(loadConfig({ DVG_BASE_URL: 'https://x', DVG_APP_KEY_FILE: '/no/such' }).errors.length);
  const bad = path.join(path.dirname(keyFile), 'bad');
  writeFileSync(bad, 'Authorization: Bearer dvga_x\n');
  assert.ok(loadConfig({ DVG_BASE_URL: 'https://x', DVG_APP_KEY_FILE: bad }).errors.some((e) => e.includes('dvga_')));
});

test('설정: 위젯 고르기', () => {
  const c = loadConfig({ DVG_BASE_URL: 'https://x', DVG_APP_KEY_FILE: keyFile, CONSOLE_WIDGETS: 'usage' });
  assert.deepEqual(c.widgets, ['usage']);
  assert.ok(loadConfig({ DVG_BASE_URL: 'https://x', DVG_APP_KEY_FILE: keyFile, CONSOLE_WIDGETS: 'usage,chart' }).errors.length);
});

test('비밀번호를 정하면 401', async () => {
  const cfg = loadConfig({ DVG_BASE_URL: base, DVG_APP_KEY_FILE: keyFile, CONSOLE_PASSWORD: 'pw' });
  const srv = createServer(cfg);
  const p = await listen(srv);
  const no = await fetch(`http://127.0.0.1:${p}/`);
  const yes = await fetch(`http://127.0.0.1:${p}/`, { headers: { Authorization: 'Basic ' + Buffer.from('u:pw').toString('base64') } });
  const wrong = await fetch(`http://127.0.0.1:${p}/`, { headers: { Authorization: 'Basic ' + Buffer.from('u:pwx').toString('base64') } });
  srv.close();
  assert.equal(no.status, 401);
  assert.equal(yes.status, 200);
  assert.equal(wrong.status, 401);
});

test('DVG 가 리다이렉트하면 따라가지 않는다(앱 키가 다른 곳으로 가지 않게)', async () => {
  const hits = [];
  const elsewhere = http.createServer((req, res) => { hits.push(req.headers.authorization || ''); res.end('{}'); });
  const ep = await listen(elsewhere);
  const redirector = http.createServer((req, res) => { res.writeHead(302, { Location: `http://127.0.0.1:${ep}/steal` }); res.end(); });
  const rp = await listen(redirector);
  const srv = createServer(loadConfig({ DVG_BASE_URL: `http://127.0.0.1:${rp}`, DVG_APP_KEY_FILE: keyFile }));
  const p = await listen(srv);
  const r = await fetch(`http://127.0.0.1:${p}/api/self`);
  const t = await r.text();
  srv.close(); redirector.close(); elsewhere.close();
  assert.equal(r.status, 502);
  assert.ok(!t.includes(KEY));
  assert.equal(hits.length, 0);
});
