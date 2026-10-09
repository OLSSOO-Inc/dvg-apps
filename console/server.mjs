// DVG 앱 개발사 콘솔 샘플 — 서버.
//
// 이 서버가 하는 일은 셋뿐입니다.
//   1. 정적 화면(public/)을 준다.
//   2. 화면의 요청 세 가지만 DVG 로 넘긴다 — 앱 정보 · 사용량 · 시뮬레이터.
//   3. 그때 **앱 키를 붙인다**. 앱 키는 이 서버 안에만 있고 브라우저로 나가지 않는다.
//
// 🔴 앱 키를 브라우저 코드에 넣지 마십시오. 화면을 여는 누구나 키를 읽어 가고, 키는 계약으로 받은 유료 접근권입니다.
// 🔴 이 서버는 «아무 주소나 대신 불러 주는» 프록시가 아닙니다 — 넘기는 경로는 아래 ROUTES 세 개로 고정입니다.
//
// 외부 의존성 없음(Node.js 20+ 표준 라이브러리만).

import http from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { timingSafeEqual, createHash } from 'node:crypto';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PUBLIC = path.join(HERE, 'public');

export const ALL_WIDGETS = ['app', 'usage', 'simulate'];

// 넘기는 경로 — 이것 말고는 없다.
export const ROUTES = {
  'GET /api/self': { dvg: '/api/v1/apps/self', timeoutMs: 10_000 },
  'GET /api/usage': { dvg: '/api/v1/apps/self/usage', timeoutMs: 10_000, query: ['month'] },
  // 시뮬레이터는 DVG 가 앱에 실제로 연결해 대화를 끝까지 돌린다(상한 60초 + 연결 6초).
  'POST /api/simulate': { dvg: '/api/v1/apps/self/simulate', timeoutMs: 90_000, body: true },
};

const MONTH_RE = /^\d{4}-(0[1-9]|1[0-2])$/;
const MAX_BODY = 64 * 1024; // DVG 도 64KB 에서 자른다

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
};

// ── 설정 ─────────────────────────────────────────────────────────────

function isLoopbackHost(h) {
  const v = String(h || '').toLowerCase().replace(/^\[|\]$/g, '');
  return v === 'localhost' || v === '::1' || v.startsWith('127.');
}

// loadConfig: 환경변수 → 설정. 문제가 있으면 **시작하지 않고** 이유를 말한다.
export function loadConfig(env = process.env) {
  const errors = [];
  const warnings = [];

  const base = String(env.DVG_BASE_URL || '').trim().replace(/\/+$/, '');
  let baseURL = null;
  if (!base) {
    errors.push('DVG_BASE_URL 이 비었습니다 (예: https://dvg.example.com:8443)');
  } else {
    try {
      baseURL = new URL(base);
      if (baseURL.protocol !== 'https:' && baseURL.protocol !== 'http:') {
        errors.push(`DVG_BASE_URL 은 http(s) 여야 합니다: ${baseURL.protocol}`);
      } else if (baseURL.protocol === 'http:' && !isLoopbackHost(baseURL.hostname)) {
        // 앱 키가 암호화 없이 오간다. 막지는 않되(폐쇄망 시험) 크게 알린다.
        warnings.push('DVG_BASE_URL 이 평문(http)입니다 — 앱 키가 암호화 없이 오갑니다. https 주소를 쓰십시오.');
      }
    } catch {
      errors.push(`DVG_BASE_URL 을 읽지 못했습니다: ${base}`);
    }
  }

  let appKey = '';
  const keyFile = String(env.DVG_APP_KEY_FILE || '').trim();
  if (!keyFile) {
    errors.push('DVG_APP_KEY_FILE 이 비었습니다 — 앱 키(dvga_…) 한 줄만 담은 파일 경로');
  } else {
    try {
      appKey = readFileSync(keyFile, 'utf8').trim();
      if (!appKey) errors.push(`앱 키 파일이 비었습니다: ${keyFile}`);
      else if (!appKey.startsWith('dvga_')) errors.push(`앱 키 파일에 dvga_ 로 시작하는 키가 없습니다: ${keyFile}`);
    } catch (e) {
      errors.push(`앱 키 파일을 읽지 못했습니다: ${keyFile} (${e.code || e.message})`);
    }
  }

  const host = String(env.HOST || '127.0.0.1').trim();
  const port = Number(env.PORT || 8790);
  if (!Number.isInteger(port) || port < 1 || port > 65535) errors.push(`PORT 가 올바르지 않습니다: ${env.PORT}`);

  const password = String(env.CONSOLE_PASSWORD || '');
  // 🔴 밖에서 열리는데 비밀번호가 없으면 시작하지 않는다 — 누구나 사용량을 보고 시뮬레이터 횟수를 쓴다.
  if (!isLoopbackHost(host) && !password) {
    errors.push(`HOST=${host} 는 이 컴퓨터 밖에서 열립니다 — CONSOLE_PASSWORD 를 정하거나 HOST=127.0.0.1 로 두십시오`);
  }

  let widgets = ALL_WIDGETS;
  if (env.CONSOLE_WIDGETS) {
    const asked = String(env.CONSOLE_WIDGETS).split(',').map((s) => s.trim()).filter(Boolean);
    const unknown = asked.filter((w) => !ALL_WIDGETS.includes(w));
    if (unknown.length) errors.push(`CONSOLE_WIDGETS 에 모르는 이름: ${unknown.join(', ')} (가능: ${ALL_WIDGETS.join(', ')})`);
    widgets = asked.filter((w) => ALL_WIDGETS.includes(w));
    if (!widgets.length && !unknown.length) errors.push('CONSOLE_WIDGETS 가 비었습니다');
  }

  return { errors, warnings, baseURL, appKey, host, port, password, widgets };
}

// ── DVG 로 넘기기 ─────────────────────────────────────────────────────

async function readBody(req, limit) {
  const chunks = [];
  let n = 0;
  for await (const c of req) {
    n += c.length;
    if (n > limit) throw Object.assign(new Error('too_large'), { code: 'too_large' });
    chunks.push(c);
  }
  return Buffer.concat(chunks);
}

function sendJSON(res, status, obj, extra = {}) {
  const body = JSON.stringify(obj);
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    ...extra,
  });
  res.end(body);
}

async function forward(cfg, route, req, res, url) {
  const target = new URL(route.dvg, cfg.baseURL);
  for (const q of route.query || []) {
    const v = url.searchParams.get(q);
    if (v == null || v === '') continue;
    if (q === 'month' && !MONTH_RE.test(v)) {
      return sendJSON(res, 400, { code: 'bad_month', error: 'month 는 YYYY-MM' });
    }
    target.searchParams.set(q, v);
  }

  let body;
  if (route.body) {
    try {
      body = await readBody(req, MAX_BODY);
    } catch (e) {
      return sendJSON(res, 413, { code: 'too_large', error: '요청이 64KB 를 넘습니다' });
    }
  }

  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), route.timeoutMs);
  let r;
  try {
    r = await fetch(target, {
      method: req.method,
      headers: {
        Authorization: `Bearer ${cfg.appKey}`,
        Accept: 'application/json',
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      body,
      signal: ctrl.signal,
      redirect: 'error', // 🔴 리다이렉트를 따라가면 앱 키가 다른 곳으로 간다
    });
  } catch (e) {
    clearTimeout(t);
    const timedOut = e.name === 'AbortError';
    // ⚠️ 오류 문구에 키가 들어가지 않는다(키는 헤더에만 있다). 주소는 사용자가 정한 값이라 보여 준다.
    return sendJSON(res, 502, {
      code: timedOut ? 'dvg_timeout' : 'dvg_unreachable',
      error: timedOut ? `DVG 가 ${route.timeoutMs / 1000}초 안에 답하지 않았습니다` : `DVG 에 연결하지 못했습니다 (${e.cause?.code || e.message})`,
      dvg: cfg.baseURL.origin,
    });
  }
  clearTimeout(t);

  const text = await r.text();
  const extra = {};
  const ra = r.headers.get('retry-after');
  if (ra) extra['Retry-After'] = ra;

  // DVG 가 JSON 이 아닌 것을 주면(404 페이지 · 프록시 오류) 그대로 흘리지 않고 사정을 말한다.
  let parsed;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    parsed = undefined;
  }
  if (parsed === undefined) {
    return sendJSON(res, 502, {
      code: 'dvg_not_json',
      error: `DVG 가 JSON 이 아닌 응답을 줬습니다 (HTTP ${r.status})`,
      hint: r.status === 404 ? 'DVG 에서 앱 플랫폼이 꺼져 있거나(운영사에 확인하십시오) DVG 버전이 낮을 수 있습니다' : undefined,
    }, extra);
  }
  if (r.status === 404 && parsed === null) {
    return sendJSON(res, 404, { code: 'not_found', error: 'DVG 가 이 경로를 모릅니다 — 앱 플랫폼이 꺼져 있거나 DVG 버전이 낮습니다' }, extra);
  }
  return sendJSON(res, r.status, parsed, extra);
}

// ── 정적 파일 ─────────────────────────────────────────────────────────

async function serveStatic(res, urlPath) {
  const rel = urlPath === '/' ? 'index.html' : decodeURIComponent(urlPath).replace(/^\/+/, '');
  const file = path.resolve(PUBLIC, rel);
  // 🔴 public/ 밖을 읽지 않는다(../ 로 앱 키 파일을 달라는 요청)
  if (file !== PUBLIC && !file.startsWith(PUBLIC + path.sep)) {
    res.writeHead(404).end();
    return;
  }
  try {
    const st = await stat(file);
    if (!st.isFile()) throw new Error('not file');
    const buf = await readFile(file);
    res.writeHead(200, {
      'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream',
      'Cache-Control': 'no-cache',
    });
    res.end(buf);
  } catch {
    res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }).end('없는 파일');
  }
}

// ── 인증(선택) ────────────────────────────────────────────────────────

function passwordOK(cfg, req) {
  if (!cfg.password) return true;
  const h = req.headers.authorization || '';
  if (!h.startsWith('Basic ')) return false;
  const decoded = Buffer.from(h.slice(6), 'base64').toString('utf8');
  const pass = decoded.slice(decoded.indexOf(':') + 1);
  // 길이가 달라도 같은 시간이 걸리게 해시끼리 비교한다.
  const a = createHash('sha256').update(pass).digest();
  const b = createHash('sha256').update(cfg.password).digest();
  return timingSafeEqual(a, b);
}

// ── 서버 ──────────────────────────────────────────────────────────────

export function createServer(cfg) {
  return http.createServer(async (req, res) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Referrer-Policy', 'no-referrer');
    res.setHeader('Content-Security-Policy', "default-src 'self'; frame-ancestors 'none'");
    if (!passwordOK(cfg, req)) {
      res.writeHead(401, { 'WWW-Authenticate': 'Basic realm="dvg-app-console", charset="UTF-8"' }).end();
      return;
    }
    const url = new URL(req.url, 'http://console.local');
    try {
      if (url.pathname === '/config.json') {
        // ⚠️ 키는 싣지 않는다 — 화면이 알아야 할 것만.
        return sendJSON(res, 200, {
          widgets: cfg.widgets,
          dvg: cfg.baseURL.origin,
          dvgInsecure: cfg.baseURL.protocol === 'http:' && !isLoopbackHost(cfg.baseURL.hostname),
        });
      }
      if (url.pathname.startsWith('/api/')) {
        const route = ROUTES[`${req.method} ${url.pathname}`];
        if (!route) return sendJSON(res, 404, { code: 'not_found', error: '이 콘솔이 넘기는 경로가 아닙니다' });
        return await forward(cfg, route, req, res, url);
      }
      if (req.method !== 'GET' && req.method !== 'HEAD') {
        res.writeHead(405).end();
        return;
      }
      return await serveStatic(res, url.pathname);
    } catch (e) {
      console.error('[console] 처리 실패:', e.message);
      if (!res.headersSent) sendJSON(res, 500, { code: 'console_error', error: '콘솔 서버 오류' });
    }
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const cfg = loadConfig();
  for (const w of cfg.warnings) console.warn('⚠️ ', w);
  if (cfg.errors.length) {
    for (const e of cfg.errors) console.error('❌', e);
    process.exit(1);
  }
  createServer(cfg).listen(cfg.port, cfg.host, () => {
    const shown = cfg.host.includes(':') ? `[${cfg.host}]` : cfg.host;
    console.log(`DVG 앱 콘솔: http://${shown}:${cfg.port}  →  ${cfg.baseURL.origin}  (위젯: ${cfg.widgets.join(', ')})`);
  });
}
