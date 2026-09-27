import { test } from 'node:test';
import assert from 'node:assert/strict';
import { usageView, parseUtterances, transcriptItems, monthUTC, SIM_MAX_UTTERANCES } from '../public/lib/format.js';

const month = (u, extra = {}) => ({ supported: true, found: true, month: '2026-09', tz: 'UTC', complete: true, usage: u, ...extra });
const base = { calls: 10, byOutcome: { completed: 6, transferred: 3, caller_hangup: 1 }, byTenant: { t1: 10 }, turns: 40,
  connectedSeconds: 600, sttSeconds: 300, ttsChars: 2000, usageUnknownCalls: 0 };

test('기록 없음은 0건이 아니라 «아직 없음»', () => {
  const v = usageView(200, { supported: true, found: false, month: '2026-09', usage: null, complete: true });
  assert.equal(v.state, 'none');
  assert.equal(v.calls, undefined); // 숫자를 만들지 않는다
});

test('장부를 못 읽으면 0이 아니라 오류', () => {
  const v = usageView(502, { code: 'ledger_unreadable' });
  assert.equal(v.state, 'error');
  assert.match(v.message, /모름/);
});

test('장부가 꺼져 있으면 unsupported', () => {
  assert.equal(usageView(200, { supported: false, month: '2026-09' }).state, 'unsupported');
});

test('사람에게 연결 비율', () => {
  const v = usageView(200, month(base));
  assert.equal(v.state, 'ok');
  assert.equal(v.toHumanRate, 0.3);
  assert.equal(v.lowerBound, false);
});

test('모르는 결말이 섞이면 비율을 내지 않는다(분모가 틀린다)', () => {
  const v = usageView(200, month({ ...base, byOutcome: { completed: 6, transferred: 3, brand_new: 1 } }));
  assert.equal(v.toHumanRate, null);
  assert.ok(v.outcomes.find((o) => o.code === 'brand_new')); // 버리지 않고 보인다
});

test('수량을 몰랐던 통화가 있으면 최소값', () => {
  const v = usageView(200, month({ ...base, usageUnknownCalls: 2 }));
  assert.equal(v.lowerBound, true);
  assert.equal(v.usageUnknownCalls, 2);
});

test('정합 판정은 DVG 값을 그대로 쓴다', () => {
  // 합계가 맞아 보여도 DVG 가 false 라고 하면 false.
  assert.equal(usageView(200, month(base, { complete: false })).complete, false);
});

test('월 상한', () => {
  const v = usageView(200, month(base), { monthlyCallQuota: 8, quotaEnforce: true });
  assert.deepEqual(v.quota, { limit: 8, used: 10, rate: 1.25, enforce: true });
  assert.equal(usageView(200, month(base), { monthlyCallQuota: 0 }).quota, null);
});

test('발화: 빈 줄은 무시 · «(무응답)» 은 빈 발화', () => {
  const { utterances, errors } = parseUtterances('  안녕하세요 \n\n(무응답)\n착불\n');
  assert.deepEqual(utterances, ['안녕하세요', '', '착불']);
  assert.deepEqual(errors, []);
});

test('발화 상한은 DVG 와 같다', () => {
  const many = Array.from({ length: SIM_MAX_UTTERANCES + 1 }, (_, i) => `말 ${i}`).join('\n');
  assert.equal(parseUtterances(many).errors.length, 1);
  assert.equal(parseUtterances('가'.repeat(301)).errors.length, 1);
  assert.equal(parseUtterances('가'.repeat(300)).errors.length, 0); // 글자 수로 센다(바이트 아님)
});

test('대화 기록: 선택지·주소 판정 표시', () => {
  const items = transcriptItems([
    { who: 'dvg', kind: 'notice', text: 'AI 상담원입니다' },
    { who: 'dvg', kind: 'ask', text: '결제는요?' },
    { who: 'caller', kind: 'listen', text: '착불', choice: '착불', choiceSource: 'initial', confirm: true },
    { who: 'caller', kind: 'listen', text: '중구', address: { status: 'ambiguous', question: '어느 중구요?' } },
    { who: 'caller', kind: 'silence' },
  ]);
  assert.equal(items[0].kindLabel, 'AI 고지');
  assert.match(items[2].notes[0], /복창/);
  assert.match(items[3].notes[0], /좁히는 질문/);
  assert.equal(items[4].kindLabel, '무응답');
});

test('달은 UTC', () => {
  assert.equal(monthUTC(new Date('2026-09-30T20:00:00-09:00')), '2026-10');
});
