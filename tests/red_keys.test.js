const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../docs/red/keys.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

function setup(hostname, fetch) {
  const elements = {};
  for (const id of ['provider-key-status', 'provider-key-form', 'jev-key', 'openai-key', 'forget-provider-keys', 'jev-key-state', 'openai-key-state', 'submit']) {
    elements[id] = { value: '', textContent: '', disabled: false, listeners: {}, addEventListener(name, callback) { this.listeners[name] = callback; } };
  }
  elements['provider-key-form'].querySelector = () => elements.submit;
  const root = { html: '', set innerHTML(value) { this.html = value; }, querySelector(selector) { return elements[selector.slice(1)]; } };
  const events = [];
  const context = { document: { getElementById: () => root }, location: { hostname, protocol: 'http:' }, fetch, window: { dispatchEvent(event) { events.push(event.type); } }, Event: class { constructor(type) { this.type = type; } } };
  vm.runInNewContext(source, context);
  return { elements, root, events };
}
const ok = data => ({ ok: true, json: async () => data });

(async () => {
  const calls = [];
  let state = { available: true, jev: true, openai: false, sessionKeys: false };
  let fail = false;
  const fetch = async (path, options = {}) => {
    calls.push({ path, options });
    if (fail) return { ok: false };
    if (options.method === 'POST') state = { available: true, jev: true, openai: true, sessionKeys: true };
    if (options.method === 'DELETE') state = { available: true, jev: true, openai: false, sessionKeys: false };
    return ok(state);
  };
  const { elements: e, root, events } = setup('localhost', fetch);
  await tick();
  assert.match(root.html, /<details\b/);
  assert.match(root.html, /<summary>API keys<\/summary>/);
  assert.match(root.html, /id="jev-key"[^>]*type="password"/);
  assert.match(root.html, /id="openai-key"[^>]*type="password"/);
  assert.equal(e['jev-key'].value, '');
  assert.equal(e['openai-key'].value, '');
  assert.equal(e['jev-key-state'].textContent, 'Configured');
  assert.equal(e['openai-key-state'].textContent, 'Missing');
  e['jev-key'].value = '  example-jev  ';
  e['openai-key'].value = '  ';
  await e['provider-key-form'].listeners.submit({ preventDefault() {} });
  assert.deepEqual(JSON.parse(calls.find(call => call.options.method === 'POST').options.body), { jev: 'example-jev' });
  assert.equal(e['jev-key'].value, '');
  assert.equal(e['openai-key'].value, '');
  assert.equal(e['openai-key-state'].textContent, 'Configured');
  assert.deepEqual(events, ['red-companion-settings']);
  assert.doesNotMatch(e['provider-key-status'].textContent, /example-jev/);
  await e['forget-provider-keys'].listeners.click();
  assert.equal(calls.filter(call => call.options.method === 'DELETE').length, 1);
  assert.deepEqual(events, ['red-companion-settings', 'red-companion-settings']);
  assert.equal(e['openai-key-state'].textContent, 'Missing');
  fail = true;
  e['openai-key'].value = 'example-openai';
  await e['provider-key-form'].listeners.submit({ preventDefault() {} });
  assert.equal(e['openai-key'].value, '');
  assert.match(e['provider-key-status'].textContent, /Could not save/);
  assert.doesNotMatch(e['provider-key-status'].textContent, /example-openai/);
  assert.equal(events.length, 2);
  const externalCalls = [];
  const external = setup('example.com', (...args) => { externalCalls.push(args); });
  await tick();
  assert.equal(external.elements['jev-key'].disabled, true);
  assert.match(external.elements['provider-key-status'].textContent, /local game server/);
  assert.equal(externalCalls.length, 0);
  console.log('provider key checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
