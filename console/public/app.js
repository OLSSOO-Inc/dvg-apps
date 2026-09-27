// 위젯 불러오기. 무엇을 보일지는 콘솔 서버의 CONSOLE_WIDGETS 가 정한다(기본: app,usage,simulate).
//
// 위젯 하나 = public/widgets/<이름>.js 파일 하나. 각 파일은 mount(카드, ctx) 를 내보낸다.
// 새 위젯을 만들려면 파일을 하나 더하고 server.mjs 의 ALL_WIDGETS 에 이름을 넣으십시오.

import { h, put } from './lib/dom.js';

async function api(path, opts = {}) {
  const r = await fetch(path, { ...opts, headers: { Accept: 'application/json', ...(opts.headers || {}) } });
  let body = null;
  try { body = await r.json(); } catch { body = null; }
  return { status: r.status, body, retryAfter: r.headers.get('Retry-After') };
}

// 앱 정보는 여러 위젯이 쓴다(사용량 위젯은 월 상한을 알아야 한다) — 한 번만 불러 나눠 쓴다.
let selfPromise = null;
function self() {
  if (!selfPromise) selfPromise = api('/api/self');
  return selfPromise;
}

async function main() {
  const conn = document.getElementById('conn');
  const root = document.getElementById('widgets');
  let cfg;
  try {
    cfg = await (await fetch('/config.json')).json();
  } catch {
    conn.textContent = '콘솔 서버에 연결하지 못했습니다';
    conn.className = 'conn bad';
    return;
  }
  document.getElementById('insecure').hidden = !cfg.dvgInsecure;

  self().then(({ status, body }) => {
    if (status === 200) {
      conn.textContent = `연결됨 · ${cfg.dvg}`;
      conn.className = 'conn ok';
    } else {
      conn.textContent = `DVG 응답 ${status}${body?.code ? ` · ${body.code}` : ''}`;
      conn.className = 'conn bad';
    }
  });

  const ctx = { api, self, config: cfg };
  for (const name of cfg.widgets) {
    const card = h('section', { class: 'card', 'data-widget': name });
    root.append(card);
    try {
      const mod = await import(`./widgets/${name}.js`);
      await mod.mount(card, ctx);
    } catch (e) {
      // 위젯 하나가 깨져도 나머지는 산다.
      put(card, h('h2', {}, name), h('div', { class: 'msg bad' }, `이 위젯을 그리지 못했습니다: ${e.message}`));
      console.error(e);
    }
  }
}

main();
