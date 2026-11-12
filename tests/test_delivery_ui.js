'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const appPath = process.argv[2];
const source = fs.readFileSync(appPath, 'utf8');
const start = source.indexOf('function delivery(){');
const end = source.indexOf('\nfunction busy(){', start);
assert(start >= 0 && end > start, 'delivery() test anchor missing');
const deliverySource = source.slice(start, end);

function makeContext(blockers) {
  const buttons = blockers.map(item => ({ dataset: { blockerFile: String(item.file_index) } }));
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, { id, innerHTML: '', textContent: '', value: '', checked: false, onclick: null });
    return elements.get(id);
  };
  const ctx = {
    state: {
      status: 'REVIEW',
      blockers,
      soft_confirmations: ['RULE_ONLY_DETECTION'],
      files: [
        { index: 0, name: 'synthetic-a.txt', seen: true },
        { index: 1, name: '<img src=x onerror=alert(1)>.docx', seen: true },
        { index: 2, name: 'synthetic-c.xlsx', seen: true },
      ],
      task: { task: 'SYNTHETIC', reviewed: false },
      workspace: '/tmp/synthetic-workspace',
    },
    step: 'delivery',
    fileIndex: 0,
    dirty: new Set(),
    document: {
      querySelector: selector => selector === '#export' && blockers.length ? null : element(selector),
      querySelectorAll: selector => selector === '[data-blocker-file]' ? buttons : [],
    },
    $(selector) { return ctx.document.querySelector(selector); },
    esc: value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch])),
    heading: () => '',
    go(next) { ctx.step = next; },
    notify(message) { ctx.lastNotice = message; },
    apiCalls: [],
    async api(path, data) { ctx.apiCalls.push({ path, data }); return { ok: true }; },
    async refresh() { ctx.refreshCount = (ctx.refreshCount || 0) + 1; },
  };
  for (const id of ['#content', '#returnFirstBlocker', '#returnReview', '#restore', '#openRestored', '#restoreIndex', '#edited', '#restoreResult', '#unlock', '#workspace', '#unlockPassword', '#identity', '#visual', '#legal', '#export']) element(id);
  element('#identity').checked = true;
  element('#visual').checked = true;
  element('#legal').checked = true;
  if (blockers.length) elements.set('#export', null);
  vm.createContext(ctx);
  vm.runInContext(`${deliverySource}\ndelivery();`, ctx, { timeout: 1000 });
  return { ctx, buttons, elements };
}

(async () => {
  const malicious = '<script>alert(1)</script> & details';
  const rows = [
    { file_index: 1, file_name: '<img src=x onerror=alert(1)>.docx', code: 'UNKNOWN<&>', message: malicious },
    { file_index: 2, file_name: 'synthetic-c.xlsx', code: 'SENSITIVE_FORMULA_BLOCKED', message: '公式需要本机核查。' },
  ];
  const { ctx, buttons } = makeContext(rows);
  const html = ctx.document.querySelector('#content').innerHTML;
  assert.match(html, /发现 2 项尚未解决的结构性阻断/);
  assert.match(html, /UNKNOWN&lt;&amp;&gt;/);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt; &amp; details/);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;\.docx/);
  assert.doesNotMatch(html, /<script>alert\(1\)<\/script>/);
  assert.doesNotMatch(html, /<img src=x onerror=alert\(1\)>/);
  assert.match(html, /人工确认勾选只用于软性人工复核，不能覆盖或解除结构性阻断/);
  assert.match(html, /id="returnFirstBlocker"/);
  assert.doesNotMatch(html, /id="export"/);
  assert.equal(buttons.length, 2);
  buttons[1].onclick();
  assert.equal(ctx.fileIndex, 2, 'per-item action must select that material');
  assert.equal(ctx.step, 'review', 'per-item action must enter local review');
  assert.equal(ctx.apiCalls.length, 0, 'navigation must not issue export');

  const primary = makeContext(rows);
  primary.elements.get('#returnFirstBlocker').onclick();
  assert.equal(primary.ctx.fileIndex, 1, 'main action must select the first blocked material');
  assert.equal(primary.ctx.step, 'review');
  assert.equal(primary.ctx.apiCalls.length, 0);

  const clear = makeContext([]);
  const clearHtml = clear.ctx.document.querySelector('#content').innerHTML;
  assert.match(clearHtml, /id="export"/);
  assert.doesNotMatch(clearHtml, /id="returnFirstBlocker"/);
  await clear.elements.get('#export').onclick();
  assert.equal(clear.ctx.apiCalls.length, 1, 'normal export path remains available without blockers');
  assert.equal(clear.ctx.apiCalls[0].path, '/export');
  assert.equal(JSON.stringify(clear.ctx.apiCalls[0].data.confirmations), JSON.stringify(['RULE_ONLY_DETECTION']));

  process.stdout.write('PASS: delivery blocker list, HTML escaping, per-file navigation, primary return action, and clear-state export path\n');
})().catch(error => { console.error(error.stack || String(error)); process.exitCode = 1; });
