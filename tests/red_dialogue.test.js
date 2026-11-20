const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function game() {
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
  const document = { querySelector: el, querySelectorAll: () => [], addEventListener() {}, hidden: false };
  const messages = [], requests = [], storage = new Map();
  class Worker { postMessage(data) { messages.push(data); } terminate() {} }
  const sandbox = { document, Element, Worker, ResizeObserver: class { observe() {} }, getComputedStyle: () => ({ paddingLeft: '0', paddingRight: '0' }),
    location: { search: '', hostname: 'localhost' }, URLSearchParams, Uint8Array, AbortController,
    localStorage: { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value) },
    createRedSaveCache: () => ({ read: async () => null, write: async () => true }),
    fetch: async (url, options) => { requests.push({ url, options }); return options?.method === 'POST' ? { ok: true, json: async () => ({ reply: 'A full reply from Oak.', perception: 'friendly' }) } : { ok: true, json: async () => ({ available: true, judge: 'jev' }) }; },
    setTimeout: () => 1, clearTimeout() {}, setInterval() {}, confirm: () => true };
  sandbox.window = { addEventListener() {} };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync('docs/red/main.js', 'utf8'), sandbox);
  return { sandbox, el, messages, requests, storage, run: code => vm.runInContext(code, sandbox) };
}

test('conversation opens in dialogue and mirrors full reply once', () => {
  const g = game();
  g.run("ready = true; state = { mode: 'dialogue', talkPhase: 'closed', talkSession: 1 }; updateTalk(); openTalk()");
  assert.equal(g.messages.at(-1).type, 'talk-open');
  g.run("state = { mode: 'dialogue', talkPhase: 'reply', talkSession: 1, talkRequest: 1, talkPage: 'Page one', talkRawReply: 'The complete reply', talkHasMore: true }; updateTalk('waiting')");
  assert.equal(g.el('#talk-reply').textContent, 'The complete reply');
  g.el('#talk-reply').textContent = 'already announced';
  g.run("state.talkPage = 'Page two'; updateTalk('reply')");
  assert.equal(g.el('#talk-reply').textContent, 'already announced');
});

test('live replies include recent bounded conversation and perception', async () => {
  const g = game();
  await new Promise(resolve => setImmediate(resolve));
  g.run("ready = true; busy = false; liveAvailable = true; state = { mode: 'walk', talkPhase: 'waiting', talkSession: 3, talkRequest: 1 }; transcript = [{question:'Earlier?', reply:'Earlier answer.'}]");
  g.el('#live-companion').checked = true;
  await g.run("replyTo({ session: 3, request: 1, person: 'OAK', question: 'Hello', profile: 'Professor', voice: 'Kind', response: 'Local reply' })");
  const request = JSON.parse(g.requests.find(item => item.options?.method === 'POST').options.body);
  assert.equal(JSON.parse(request.context).conversation[0].question, 'Earlier?');
  assert.ok(request.context.length <= 4000);
  assert.match(g.el('#talk-status').textContent, /Jev heard this as friendly/);
  assert.equal(g.messages.at(-1).type, 'talk-reply');
  assert.equal(g.messages.at(-1).response, 'A full reply from Oak.');
});
