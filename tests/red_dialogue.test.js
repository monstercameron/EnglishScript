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
    location: { search: '', hostname: 'localhost' }, URLSearchParams, Uint8Array, AbortController, AbortSignal,
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
  g.run("ready = true; busy = false; liveAvailable = true; state = { mode: 'walk', talkPhase: 'waiting', talkSession: 3, talkRequest: 1 }; conversations.set('OAK', [{question:'Earlier?', reply:'Earlier answer.'}])");
  g.el('#live-companion').checked = true;
  await g.run("replyTo({ session: 3, request: 1, person: 'OAK', identity: 'OAK', question: 'Hello', profile: 'Professor', voice: 'Kind', response: 'Local reply' })");
  const request = JSON.parse(g.requests.find(item => item.options?.method === 'POST').options.body);
  assert.equal(JSON.parse(request.context).conversation[0].question, 'Earlier?');
  assert.ok(request.context.length <= 4000);
  assert.match(g.el('#talk-status').textContent, /Jev heard this as friendly/);
  assert.equal(g.messages.at(-1).type, 'talk-reply');
  assert.equal(g.messages.at(-1).response, 'A full reply from Oak.');
});


test('conversation memory follows the character and resets with a new or loaded game', async () => {
  const g = game();
  await new Promise(resolve => setImmediate(resolve));
  g.run("ready = true; busy = false; liveAvailable = true; state = { mode: 'walk', talkPhase: 'waiting', talkSession: 1, talkRequest: 1 }");
  g.el('#live-companion').checked = true;
  await g.run("replyTo({ session: 1, request: 1, person: 'MOM', identity: 'MOM', question: 'Mom question', response: 'Local' })");
  g.run("busy = false; queue = []; talkPending = false; talkAction('close'); busy = false; queue = []; talkPending = false; state = { mode: 'walk', talkPhase: 'waiting', talkSession: 2, talkRequest: 1 }");
  await g.run("replyTo({ session: 2, request: 1, person: 'OAK', identity: 'OAK', question: 'Oak question', response: 'Local' })");
  g.run("busy = false; queue = []; talkPending = false; talkAction('close'); busy = false; queue = []; talkPending = false; state = { mode: 'walk', talkPhase: 'waiting', talkSession: 3, talkRequest: 1 }");
  await g.run("replyTo({ session: 3, request: 1, person: 'MOM', identity: 'MOM', question: 'Back again', response: 'Local' })");
  const contexts = g.requests.filter(item => item.options?.method === 'POST').map(item => JSON.parse(JSON.parse(item.options.body).context));
  assert.equal(contexts[1].conversation.length, 0);
  assert.equal(contexts[2].conversation[0].question, 'Mom question');
  g.run("startGame(false)");
  assert.equal(g.run('conversations.size'), 0);
  g.run("conversations.set('MOM', [{ question: 'old', reply: 'old' }]); startGame(true, { version: 2, actions: ['a'] })");
  assert.equal(g.run('conversations.size'), 0);
});

test('closing or restarting aborts a pending request and discards a late reply', async () => {
  for (const operation of ['close', 'restart']) {
    const g = game();
    await new Promise(resolve => setImmediate(resolve));
    let finish;
    g.sandbox.fetch = (url, options) => new Promise(resolve => { g.requests.push({ url, options }); finish = resolve; });
    g.run("ready = true; busy = false; liveAvailable = true; state = { mode: 'walk', talkPhase: 'waiting', talkSession: 4, talkRequest: 1 }");
    g.el('#live-companion').checked = true;
    const pending = g.run("replyTo({ session: 4, request: 1, person: 'MOM', identity: 'MOM', question: 'Hello', response: 'Local' })");
    const signal = g.requests.at(-1).options.signal;
    if (operation === 'close') g.run("talkAction('close')");
    else g.run('startGame(false)');
    assert.equal(signal.aborted, true);
    finish({ ok: true, json: async () => ({ reply: 'Late reply' }) });
    await pending;
    assert.equal(g.messages.some(message => message.type === 'talk-reply'), false);
    assert.equal(g.run('conversations.size'), 0);
  }
});

test('conversation memory bounds entries and exchange text', async () => {
  const g = game();
  await new Promise(resolve => setImmediate(resolve));
  g.run("ready = true; busy = false; liveAvailable = false; state = { talkPhase: 'waiting', talkSession: 1, talkRequest: 1 }");
  for (let i = 0; i < 35; i++) {
    g.sandbox.name = `PERSON ${i}`;
    await g.run("replyTo({ session: 1, request: 1, person: name, identity: name, question: 'q'.repeat(800), response: 'r'.repeat(800) })");
  }
  assert.equal(g.run('conversations.size'), 32);
  assert.equal(g.run("conversations.get('PERSON 34')[0].question.length"), 500);
  assert.equal(g.run("conversations.get('PERSON 34')[0].reply.length"), 500);
});


test('people with the same displayed name have separate memories, and missing identity has none', async () => {
  const g = game();
  await new Promise(resolve => setImmediate(resolve));
  g.run("ready = true; busy = false; liveAvailable = true; state = { talkPhase: 'waiting', talkSession: 1, talkRequest: 1 }");
  g.el('#live-companion').checked = true;
  await g.run("replyTo({ session: 1, request: 1, person: 'CLERK', identity: 'SHOP 1 CLERK', question: 'First shop', response: 'Local' })");
  await g.run("replyTo({ session: 1, request: 1, person: 'CLERK', identity: 'SHOP 2 CLERK', question: 'Second shop', response: 'Local' })");
  await g.run("replyTo({ session: 1, request: 1, person: 'CLERK', question: 'Unknown shop', response: 'Local' })");
  await g.run("replyTo({ session: 1, request: 1, person: 'CLERK', identity: 'SHOP 1 CLERK', question: 'Back', response: 'Local' })");
  const contexts = g.requests.filter(item => item.options?.method === 'POST').map(item => JSON.parse(JSON.parse(item.options.body).context));
  assert.equal(contexts[1].conversation.length, 0);
  assert.equal(contexts[2].conversation.length, 0);
  assert.equal(contexts[3].conversation[0].question, 'First shop');
  assert.equal(g.run('conversations.size'), 2);
});

test('turning off live replies aborts the request and delivers the local response', async () => {
  const g = game();
  await new Promise(resolve => setImmediate(resolve));
  let finish;
  g.sandbox.fetch = (url, options) => new Promise(resolve => { g.requests.push({ url, options }); finish = resolve; });
  g.run("ready = true; busy = false; liveAvailable = true; state = { talkPhase: 'waiting', talkSession: 1, talkRequest: 1 }");
  g.el('#live-companion').checked = true;
  const pending = g.run("replyTo({ session: 1, request: 1, person: 'MOM', identity: 'MOM', question: 'Hello', response: 'Local answer' })");
  const signal = g.requests.at(-1).options.signal;
  g.el('#live-companion').checked = false;
  g.el('#live-companion').listeners.change();
  assert.equal(signal.aborted, true);
  g.el('#live-companion').checked = true;
  finish({ ok: true, json: async () => ({ reply: 'Late live reply' }) });
  await pending;
  assert.equal(g.messages.at(-1).type, 'talk-reply');
  assert.equal(g.messages.at(-1).response, 'Local answer');
});

test('a long live reply is capped before it reaches the game', async () => {
  const g = game();
  await new Promise(resolve => setImmediate(resolve));
  g.sandbox.fetch = async (url, options) => ({ ok: true, json: async () => ({ reply: 'Oak says hello. '.repeat(400), perception: 'friendly' }) });
  g.run("ready = true; busy = false; liveAvailable = true; state = { talkPhase: 'waiting', talkSession: 1, talkRequest: 1 }");
  g.el('#live-companion').checked = true;
  await g.run("replyTo({ session: 1, request: 1, person: 'OAK', identity: 'OAK', question: 'Hello', response: 'Local' })");
  assert.equal(g.messages.at(-1).type, 'talk-reply');
  assert.equal(g.messages.at(-1).response.length, 2000);
});
