// 위젯: 앱 정보 — GET /api/v1/apps/self
import { h, put } from '../lib/dom.js';
import { fmtInt } from '../lib/format.js';

function when(v) {
  if (!v || String(v).startsWith('0001-')) return '—';
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString('ko-KR');
}

export async function mount(card, ctx) {
  card.append(h('h2', {}, '🧩 앱 정보'));
  const body = h('div', {}, '불러오는 중…');
  card.append(body);

  const { status, body: j } = await ctx.self();
  if (status !== 200 || !j?.app) {
    put(body, h('div', { class: 'msg bad' }, j?.error || `앱 정보를 받지 못했습니다 (HTTP ${status})`));
    return;
  }
  const a = j.app;
  const quota = a.monthlyCallQuota > 0
    ? `${fmtInt(a.monthlyCallQuota)}통 / 월 · ${a.quotaEnforce ? '넘으면 사람에게 연결' : '넘어도 계속(기록만)'}`
    : '없음';
  put(body, 
    h('dl', { class: 'kv' },
      h('dt', {}, '이름'), h('dd', {}, a.name || a.id),
      h('dt', {}, '앱 id'), h('dd', {}, h('code', {}, a.id)),
      h('dt', {}, '상태'), h('dd', {}, a.enabled ? '켜짐' : '꺼짐 — 통화가 이 앱으로 오지 않습니다'),
      h('dt', {}, '설치된 회사'), h('dd', {}, `${fmtInt(j.installations)}곳`),
      h('dt', {}, '월 통화 상한'), h('dd', {}, quota),
      h('dt', {}, '연결 주소'), h('dd', {}, h('code', {}, a.relayUrl || '—')),
      h('dt', {}, '주소 좌표'), h('dd', {}, a.coordinates ? '켜짐' : '꺼짐'),
      h('dt', {}, '앱 키'), h('dd', {}, `…${a.keyHint || '????'} · 마지막 교체 ${when(a.keyRotatedAt)}`),
    ),
    j.installations === 0
      ? h('div', { class: 'msg warn' }, '아직 어느 회사에도 설치되지 않았습니다 — 실통화는 오지 않고 시뮬레이터로만 시험할 수 있습니다.')
      : null,
  );
}
