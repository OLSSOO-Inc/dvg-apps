// 위젯: 사용량 — GET /api/v1/apps/self/usage?month=YYYY-MM
//
// ⭐ 「0」과 「모름」을 섞지 않는다(판단은 lib/format.js 의 usageView 한 곳).
import { h, put } from '../lib/dom.js';
import { usageView, monthUTC, isMonth, fmtInt, fmtPct, fmtSeconds } from '../lib/format.js';

function stat(k, v, lb) {
  return h('div', { class: 'stat' }, h('div', { class: 'v' }, v), h('div', { class: 'k' }, k), lb ? h('div', { class: 'lb' }, lb) : null);
}

function render(view) {
  if (view.state === 'error') return [h('div', { class: 'msg bad' }, view.message)];
  if (view.state === 'unsupported' || view.state === 'none') return [h('div', { class: 'msg info' }, view.message)];

  const out = [];
  if (!view.complete) {
    out.push(h('div', { class: 'msg warn' }, 'DVG 가 이 달 장부의 합계가 맞지 않는다고 알렸습니다 — 아래 수치를 청구 근거로 쓰지 마십시오.'));
  }
  const lb = view.lowerBound ? '최소값' : '';
  out.push(h('div', { class: 'stats' },
    stat('통화', `${fmtInt(view.calls)}통`),
    stat('사람에게 연결', fmtPct(view.toHumanRate)),
    stat('앱과 연결된 시간', fmtSeconds(view.connectedSeconds)),
    stat('앱 지시', `${fmtInt(view.turns)}번`),
    stat('음성인식', fmtSeconds(view.sttSeconds), lb),
    stat('음성합성', `${fmtInt(view.ttsChars)}자`, lb),
    stat('주소 풀이', `${fmtInt(view.addressLookups)}번`),
  ));
  if (view.lowerBound) {
    out.push(h('div', { class: 'msg warn' },
      `수량을 알 수 없던 통화가 ${fmtInt(view.usageUnknownCalls)}통 있습니다 — 음성인식·음성합성 합계는 그만큼 빠진 «최소값»입니다.`));
  }
  if (view.quota) {
    const bar = h('div', { class: `bar${view.quota.rate >= 1 ? ' over' : ''}` }, h('span'));
    bar.firstChild.style.width = `${Math.min(100, view.quota.rate * 100).toFixed(1)}%`;
    out.push(h('div', {},
      h('label', {}, `월 상한 ${fmtInt(view.quota.used)} / ${fmtInt(view.quota.limit)}통 (${fmtPct(view.quota.rate)})${view.quota.enforce ? ' · 넘으면 사람에게 연결' : ''}`),
      bar));
  }
  if (view.outcomes.length) {
    out.push(h('table', {},
      h('thead', {}, h('tr', {}, h('th', {}, '결말'), h('th', {}, ''), h('td', { class: 'n' }, '통화'))),
      h('tbody', {}, view.outcomes.map((o) => h('tr', {},
        h('td', {}, o.label, ' ', h('code', {}, o.code)),
        h('td', {}, o.toHuman ? h('span', { class: 'tag human' }, '사람에게') : ''),
        h('td', { class: 'n' }, fmtInt(o.n)),
      ))),
    ));
  }
  const upd = view.updatedAt ? new Date(view.updatedAt).toLocaleString('ko-KR') : '—';
  out.push(h('p', { class: 'note' },
    `${view.month} (UTC 기준 달) · 설치 회사 ${view.tenants ? `${fmtInt(view.tenants)}개 테넌트` : '—'} · 마지막 기록 ${upd}` +
    (view.gatewayVersion ? ` · DVG ${view.gatewayVersion}` : '') +
    ' · 시뮬레이터 시험은 세지 않습니다'));
  return out;
}

export async function mount(card, ctx) {
  const month = h('input', { type: 'month', value: monthUTC(), 'aria-label': '달' });
  const reload = h('button', { class: 'ghost', type: 'button' }, '새로고침');
  card.append(h('h2', {}, '📊 사용량', h('span', { class: 'tools' }, month, reload)));
  const body = h('div', {}, '불러오는 중…');
  card.append(body);

  async function load() {
    if (!isMonth(month.value)) {
      put(body, h('div', { class: 'msg bad' }, '달을 고르십시오'));
      return;
    }
    reload.disabled = true;
    try {
      const [{ status, body: j }, self] = await Promise.all([
        ctx.api(`/api/usage?month=${encodeURIComponent(month.value)}`),
        ctx.self(),
      ]);
      const app = self.status === 200 ? self.body?.app || {} : {};
      put(body, ...render(usageView(status, j, app)));
    } finally {
      reload.disabled = false;
    }
  }
  month.addEventListener('change', load);
  reload.addEventListener('click', load);
  await load();
}
