const assert = require('node:assert/strict');
const { createReader, highlight, validPath } = require('../docs/red/source.js');

class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.attributes = {}; this.listeners = {}; this.hidden = false; this._text = ''; }
  set textContent(value) { this._text = value; this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this._text = ''; this.children = []; this.append(...nodes); }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  get firstElementChild() { return this.children[0]; }
  focus() { document.activeElement = this; }
}
const document = {
  createElement: tag => new Element(tag),
  createDocumentFragment: () => new Element('fragment'),
  createTextNode: text => { const node = new Element('text'); node.textContent = text; return node; }
};
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const tick = () => new Promise(resolve => setImmediate(resolve));
const response = value => ({ ok: true, json: async () => value, text: async () => value });

(async () => {
  const source = 'Use the maps chapter.\r\n  Say "<script>" and 42.\n';
  const rendered = highlight(document, source);
  assert.equal(rendered.textContent, source);
  assert.equal(rendered.children[0].dataset.line, '1');
  assert.equal(rendered.children[1].dataset.line, '2');
  assert.ok(rendered.children[1].children.some(node => node.className === 'source-string' && node.textContent === '"<script>"'));
  assert.ok(!validPath('../secret.english'));
  const model = highlight(document, 'Judge about verdict reply means text number perception Ask the model');
  for (const word of ['Judge', 'about', 'verdict', 'reply', 'means', 'text', 'number', 'perception', 'Ask the model']) {
    assert.ok(model.children[0].children.some(node => node.className === 'source-keyword' && node.textContent === word), word);
  }

  const syntax = highlight(document, 'The base stats are health and speed, in that order:\n  "Nidoran" has 46 and 50.\nSet score to 10, except:\n  Use 99 for 10 when score is 0.\nSay "for when except has in that order".\nSay when.\n');
  for (const [line, words] of [[0, ['in that order']], [1, ['has']], [2, ['except']], [3, ['for', 'when']]]) {
    for (const word of words) assert.ok(syntax.children[line].children.some(node => node.className === 'source-keyword' && node.textContent === word), word);
  }
  assert.ok(syntax.children[4].children.some(node => node.className === 'source-string' && node.textContent.includes('for when except')));
  assert.ok(!syntax.children[5].children.some(node => node.className === 'source-keyword' && node.textContent === 'when'));

  const expandedSource = 'Use the battle, party and sound chapters.\nUse the page and vulkan libraries.\n  "Oak" from 16 has:\n    Voice is "from chapters has".\nSay from.\nLet the result be the evolutions for "Oak" at 16.\n';
  const expanded = highlight(document, expandedSource);
  assert.equal(expanded.textContent, expandedSource);
  for (const [line, words] of [[0, ['chapters']], [1, ['libraries']], [2, ['from', 'has']], [3, ['is']], [5, ['for', 'at']]]) {
    for (const word of words) assert.ok(expanded.children[line].children.some(node => node.className === 'source-keyword' && node.textContent === word), word);
  }
  assert.ok(expanded.children[3].children.some(node => node.className === 'source-string' && node.textContent === '"from chapters has"'));
  assert.ok(!expanded.children[4].children.some(node => node.className === 'source-keyword' && node.textContent === 'from'));

  const choicesSource = 'ChOoSe the answer by the species:\n  For "A", "B" or "C", use "Choose by one of".\n  Otherwise, use "other".\nIf the species is not one of "A", "B":\n  Say "not one of".\nA mood is one of sleepy or happy.\nSay by.\n';
  const choices = highlight(document, choicesSource);
  assert.equal(choices.textContent, choicesSource);
  for (const [line, words] of [[0, ['ChOoSe', 'by']], [1, ['For', 'or', 'use']],
    [2, ['Otherwise', 'use']], [3, ['is', 'not', 'one of']], [5, ['is', 'one of']]]) {
    for (const word of words) assert.ok(choices.children[line].children.some(node => node.className === 'source-keyword' && node.textContent === word), word);
  }
  assert.ok(choices.children[1].children.some(node => node.className === 'source-string' && node.textContent === '"Choose by one of"'));
  assert.ok(choices.children[4].children.some(node => node.className === 'source-string' && node.textContent === '"not one of"'));
  assert.ok(!choices.children[6].children.some(node => node.className === 'source-keyword' && node.textContent === 'by'));

  const pending = {};
  const calls = [];
  const fetch = path => {
    calls.push(path);
    if (path === 'chapters.json') return Promise.resolve(response(['main.english', 'maps.english', 'battle.english', 'conversation.english']));
    pending[path] = deferred();
    return pending[path].promise;
  };
  const root = new Element('section');
  const reader = createReader(document, fetch, root);
  await tick();
  assert.deepEqual(calls, ['chapters.json', 'main.english']);
  const [tabs, pickerLabel, caption, status, retry, pages, view] = root.children;
  assert.equal(tabs.children.find(button => button.textContent === 'Dialogue AI').dataset.path, 'companion_model.english');
  assert.equal(pickerLabel.children[0].children.length, 5);
  assert.ok(pickerLabel.children[0].children.some(option => option.value === 'companion_model.english'));
  reader.select('maps.english');
  pending['maps.english'].resolve(response('Map "<b>"\n'));
  await tick();
  pending['main.english'].resolve(response('stale'));
  await tick();
  assert.equal(view.textContent, 'Map "<b>"\n');
  assert.match(caption.textContent, /maps\.english/);
  assert.equal(tabs.children[1].attributes['aria-selected'], 'true');
  reader.select('battle.english');
  pending['battle.english'].resolve({ ok: false });
  await tick();
  assert.equal(retry.hidden, false);
  assert.match(status.textContent, /battle\.english/);
  retry.listeners.click();
  pending['battle.english'].resolve(response('Ready.'));
  await tick();
  assert.equal(view.textContent, 'Ready.');
  assert.equal(retry.hidden, true);
  tabs.children[0].focus();
  tabs.listeners.keydown({ key: 'ArrowRight', preventDefault() {} });
  assert.equal(document.activeElement, tabs.children[1]);
  assert.equal(calls.at(-1), 'maps.english');
  const longSource = Array.from({length: 301}, (_, index) => `line ${index + 1}\n`).join('');
  pending['maps.english'].resolve(response(longSource));
  await tick();
  assert.equal(pages.hidden, false);
  assert.equal(pages.children[1].textContent, 'Lines 1–150 of 301');
  let combined = view.textContent;
  pages.children[2].listeners.click();
  assert.equal(pages.children[1].textContent, 'Lines 151–300 of 301');
  combined += view.textContent;
  pages.children[2].listeners.click();
  assert.equal(pages.children[1].textContent, 'Lines 301–301 of 301');
  combined += view.textContent;
  assert.equal(combined, longSource);
  assert.equal(pages.children[2].disabled, true);
  pages.children[0].listeners.click();
  assert.equal(pages.children[1].textContent, 'Lines 151–300 of 301');
  console.log('source reader checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
