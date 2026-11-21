const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

const autosaveKey = 'englishscript-red-adventure-v2';
const manualKey = 'englishscript-red-manual-save-v2';
const settle = () => new Promise(resolve => setImmediate(resolve));

function game({ saved = {}, quota = Infinity, fetch, cache } = {}) {
  const elements = new Map();
  class Element {
    constructor() { this.hidden = false; this.disabled = false; this.checked = false; this.value = ''; this.textContent = ''; this.dataset = {}; this.listeners = {}; this.style = {}; this.parentElement = this; this.clientWidth = 500; }
    addEventListener(name, fn) { this.listeners[name] = fn; }
    closest() { return null; }
    focus() {}
    setAttribute() {}
    getContext() { return { createImageData: () => ({ data: new Uint8Array(160 * 144 * 4) }), putImageData() {} }; }
  }
  const el = name => { if (!elements.has(name)) elements.set(name, new Element()); return elements.get(name); };
  el('#continue-save').disabled = true;
  const document = { querySelector: el, querySelectorAll: () => [], addEventListener() {}, hidden: false };
  const workers = [];
  const storage = new Map(Object.entries(saved));
  const cached = [];
  class Worker {
    constructor() { this.messages = []; workers.push(this); }
    postMessage(data) { this.messages.push(JSON.parse(JSON.stringify(data))); }
    terminate() { this.terminated = true; }
  }
  const localStorage = {
    getItem: key => storage.has(key) ? storage.get(key) : null,
    setItem(key, value) {
      if (value.length > quota) throw Object.assign(new Error('quota'), { name: 'QuotaExceededError' });
      storage.set(key, value);
    },
  };
  const sandbox = {
    document, Element, Worker, localStorage, URLSearchParams, Uint8Array, AbortController, AbortSignal,
    ResizeObserver: class { observe() {} }, getComputedStyle: () => ({ paddingLeft: '0', paddingRight: '0' }),
    location: { search: '', hostname: 'example.com' },
    createRedSaveCache: () => cache || { read: async () => null, write: async saved => { cached.push(saved); return true; } },
    fetch: fetch || (async () => ({ ok: true, json: async () => ({}) })),
    setTimeout: () => 1, clearTimeout() {}, setInterval() {}, confirm: () => true,
  };
  sandbox.window = { addEventListener() {} };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync('docs/red/main.js', 'utf8'), sandbox);
  const worker = () => workers.at(-1);
  const send = data => worker().onmessage({ data });
  const autosave = () => JSON.parse(storage.get(autosaveKey));
  return { sandbox, el, workers, worker, send, storage, cached, autosave, run: code => vm.runInContext(code, sandbox) };
}

const save = (actions, content) => JSON.stringify({ version: 2, content, actions });

test('autosave and manual SAVE record the content fingerprint of the loaded chapters', async () => {
  const g = game();
  g.send({ type: 'ready', content: 'chapters-1' });
  assert.equal(g.autosave().content, 'chapters-1');
  g.run('manualPending = true');
  g.send({ type: 'ack', action: 'a' });
  await settle();
  assert.deepEqual(g.autosave(), { version: 2, content: 'chapters-1', actions: ['a'] });
  assert.equal(JSON.parse(g.storage.get(manualKey)).content, 'chapters-1');
  assert.equal(g.cached[0].content, 'chapters-1');
  assert.equal(g.el('#continue-save').disabled, false);
});

test('a save is sent to the worker with its fingerprint', () => {
  const g = game({ saved: { [autosaveKey]: save(['a', 'b'], 'chapters-1') } });
  assert.deepEqual(g.worker().messages[0], { type: 'start', history: ['a', 'b'], content: 'chapters-1', offersChoice: true });
});

for (const [name, content, wording] of [['changed', 'chapters-1', /has changed since this save/], ['older', undefined, /older version/]]) {
  test(`a ${name} save offers to continue anyway`, () => {
    const g = game({ saved: { [autosaveKey]: save(['a', 'b'], content) } });
    g.send({ type: 'changed', content: 'chapters-2' });
    assert.equal(g.el('#save-choice').hidden, false);
    assert.match(g.el('#save-choice-text').textContent, wording);
    g.el('#save-keep').listeners.click();
    assert.equal(g.el('#save-choice').hidden, true);
    assert.deepEqual(g.worker().messages.at(-1), { type: 'restore', history: ['a', 'b'] });
    g.send({ type: 'ready', content: 'chapters-2' });
    assert.deepEqual(g.autosave(), { version: 2, content: 'chapters-2', actions: ['a', 'b'] });
  });
}

test('a changed save can be replaced by a fresh start', () => {
  const g = game({ saved: { [autosaveKey]: save(['a', 'b'], 'chapters-1') } });
  g.send({ type: 'changed', content: 'chapters-2' });
  g.el('#save-fresh').listeners.click();
  assert.deepEqual(g.worker().messages.at(-1), { type: 'restore', history: [] });
  g.el('#save-fresh').listeners.click();
  assert.equal(g.worker().messages.filter(message => message.type === 'restore').length, 1);
  g.send({ type: 'ready', content: 'chapters-2' });
  assert.deepEqual(g.autosave(), { version: 2, content: 'chapters-2', actions: [] });
});

test('a failed restore offers a new adventure or the last SAVE instead of reloading', async () => {
  const g = game({ saved: { [autosaveKey]: save(['a'], 'chapters-1'), [manualKey]: JSON.stringify({ version: 2, content: 'chapters-1', savedAt: 1, actions: ['b'] }) } });
  await settle();
  g.send({ type: 'restore-failed', message: 'The program stopped.' });
  const text = g.el('#connection').textContent;
  assert.match(text, /could not be restored/);
  assert.match(text, /New adventure/);
  assert.match(text, /Continue last SAVE/);
  assert.doesNotMatch(text, /reload/i);
  assert.equal(g.worker().terminated, true);
});

test('a damaged autosave is reported instead of silently replaced', () => {
  const g = game({ saved: { [autosaveKey]: '{"version":2,"actions":["a"' } });
  assert.deepEqual(g.worker().messages[0].history, []);
  assert.equal(g.el('#save-warning').hidden, false);
  assert.match(g.el('#save-warning').textContent, /damaged/);
});

test('a full browser storage warns the player and keeps the in-game SAVE working', async () => {
  const g = game({ quota: 60 });
  g.send({ type: 'ready', content: 'chapters-1' });
  for (let i = 0; i < 6; i++) g.send({ type: 'ack', action: 'up' });
  assert.equal(g.el('#save-warning').hidden, false);
  assert.match(g.el('#save-warning').textContent, /SAVE/);
  g.run('manualPending = true');
  g.send({ type: 'ack', action: 'a' });
  await settle();
  assert.equal(g.cached.at(-1).actions.length, 7);
  assert.equal(g.el('#continue-save').disabled, false);
});

test('a SAVE that cannot be stored anywhere is reported', async () => {
  const g = game({ quota: 0, cache: { read: async () => null, write: async () => false } });
  g.send({ type: 'ready', content: 'chapters-1' });
  g.run('manualPending = true');
  g.send({ type: 'ack', action: 'a' });
  await settle();
  assert.match(g.el('#save-warning').textContent, /SAVE could not be stored/);
});

test('the badge recording download gives up with a clear message', async () => {
  const requests = [];
  const g = game({ fetch: async (url, options) => { requests.push(options); throw Object.assign(new Error('timed out'), { name: 'TimeoutError' }); } });
  await assert.rejects(g.run('startShow(generation)'), /replay\.json: it did not arrive within 30 seconds/);
  assert.ok(requests[0].signal);
  assert.equal(requests[0].cache, 'no-cache');
});

test('a damaged local SAVE is not reported while the backup copy is good', async () => {
  const backup = { version: 2, content: 'chapters-1', savedAt: 5, actions: ['b'] };
  const g = game({ saved: { [manualKey]: '{"version":2' }, cache: { read: async () => backup, write: async () => true } });
  await settle();
  assert.equal(g.el('#save-warning').textContent, '');
  assert.equal(g.el('#continue-save').disabled, false);
});

test('a damaged SAVE with no backup copy is reported', async () => {
  const g = game({ saved: { [manualKey]: '{"version":2' }, cache: { read: async () => null, write: async () => true } });
  await settle();
  assert.match(g.el('#save-warning').textContent, /last SAVE in this browser is damaged/);
  assert.equal(g.el('#continue-save').disabled, true);
});
