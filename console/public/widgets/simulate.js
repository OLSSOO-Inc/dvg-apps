// 위젯: 시뮬레이터 — POST /api/v1/apps/self/simulate
//
// DVG 가 **등록된 앱 주소에 실제로 연결해** 실통화와 같은 순서로 대화를 돌리고, 소리 대신 글자로 돌려준다.
// 🔴 앱은 이때 setup.simulated=true 를 받는다 — 그때는 실제 주문을 만들면 안 된다.
// ⚠️ 음성이 아니다 — 음성인식 오인식·무음 판정·끼어들기는 재현되지 않는다.
import { h, put } from '../lib/dom.js';
import { parseUtterances, transcriptItems, simErrorText, outcomeLabel, OUTCOMES, SILENCE_MARK, SIM_MAX_UTTERANCES, SIM_MAX_CHARS } from '../lib/format.js';

const EXAMPLE = ['강남구 역삼동 테헤란로 123', '마포구 서교동이요', '착불이요', '네 맞아요'].join('\n');

function bubble(it) {
  return h('div', { class: `bubble ${it.who} ${it.kind || ''}` },
    h('div', { class: 'who' }, it.who === 'caller' ? '발신자' : 'DVG', it.kindLabel ? ` · ${it.kindLabel}` : ''),
    h('div', { class: 't' }, it.text),
    it.notes.map((n) => h('div', { class: 'n' }, n)),
  );
}

export async function mount(card, ctx) {
  card.classList.add('wide');
  card.append(h('h2', {}, '🧪 시뮬레이터 — 전화 없이 앱 시험'));

  const utter = h('textarea', { spellcheck: 'false', 'aria-label': '발신자 발화' });
  utter.value = EXAMPLE;
  const caller = h('input', { type: 'text', inputmode: 'numeric', placeholder: '01012345678', 'aria-label': '발신번호' });
  const did = h('input', { type: 'text', inputmode: 'numeric', placeholder: '07012345678', 'aria-label': '받은 번호' });
  const org = h('input', { type: 'text', placeholder: '(선택)', 'aria-label': '주문 회사 id' });
  const run = h('button', { type: 'submit', class: 'primary' }, '시험 실행');
  const problems = h('div');
  const result = h('div', {}, h('p', { class: 'note' }, '왼쪽에 발신자가 할 말을 적고 «시험 실행»을 누르십시오.'));

  function check() {
    const { utterances, errors } = parseUtterances(utter.value);
    put(problems, ...errors.map((e) => h('div', { class: 'msg bad' }, e)));
    run.disabled = errors.length > 0;
    return { utterances, errors };
  }
  utter.addEventListener('input', check);

  const form = h('form', {},
    h('label', {}, `발신자가 할 말 — 한 줄에 한 마디 · 최대 ${SIM_MAX_UTTERANCES}줄 · 한 줄 ${SIM_MAX_CHARS}자 · «${SILENCE_MARK}» 줄은 아무 말도 안 함`),
    utter,
    h('div', { class: 'row' },
      h('div', {}, h('label', {}, '발신번호'), caller),
      h('div', {}, h('label', {}, '받은 번호(DID)'), did),
      h('div', {}, h('label', {}, '주문 회사 id'), org),
    ),
    problems,
    h('p', { class: 'note' }, '발화를 다 쓰면 발신자가 끊은 것으로 처리됩니다 · 앱당 분당 20회 · 사용량에 세지 않습니다'),
    run,
  );
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const { utterances, errors } = check();
    if (errors.length) return;
    run.disabled = true;
    run.textContent = '앱과 대화 중…';
    put(result, h('p', { class: 'note' }, 'DVG 가 앱에 연결해 대화를 돌리는 중입니다(최대 1분).'));
    try {
      const { status, body, retryAfter } = await ctx.api('/api/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ utterances, caller: caller.value, did: did.value, orgId: org.value.trim() }),
      });
      if (status !== 200 || !body?.simulated) {
        put(result, h('div', { class: 'msg bad' }, simErrorText(status, body, retryAfter)));
        return;
      }
      const human = OUTCOMES[body.outcome]?.toHuman;
      const items = transcriptItems(body.transcript);
      put(result, 
        h('div', { class: 'outcome' },
          h('span', { class: `big${human ? ' human' : ''}` }, outcomeLabel(body.outcome)),
          h('span', { class: 'code' }, body.outcome),
          body.turns != null ? h('span', { class: 'code' }, `지시 ${body.turns}번`) : null,
          body.elapsedMs != null ? h('span', { class: 'code' }, `${(body.elapsedMs / 1000).toFixed(1)}초`) : null,
        ),
        body.realCall ? h('div', { class: `msg ${human ? 'warn' : 'info'}` }, body.realCall) : null,
        body.detail ? h('div', { class: 'msg bad' }, body.detail) : null,
        items.length ? h('div', { class: 'chat' }, items.map(bubble)) : h('p', { class: 'note' }, '대화 기록이 없습니다.'),
        body.note ? h('p', { class: 'note' }, body.note) : null,
      );
    } finally {
      run.disabled = false;
      run.textContent = '시험 실행';
      check();
    }
  });

  card.append(h('div', { class: 'sim' }, form, h('div', {}, result)));
  check();
}
