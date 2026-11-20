const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');
const stores = new Map();
let denied = false;
const caches = { async open(name) {
  if (denied) throw Error('denied');
  if (!stores.has(name)) stores.set(name, new Map());
  const entries = stores.get(name);
  return {
    async keys() { return [...entries.keys()].map(url => ({ url })); },
    async match(key) { return entries.get(key.url)?.clone(); },
    async put(url, response) { entries.set(url, response); },
    async delete(key) { return entries.delete(key.url); }
  };
} };
let lock = Promise.resolve();
const navigator = { locks: { request(name, run) {
  const next = lock.then(run);
  lock = next.catch(() => {});
  return next;
} } };
const code = fs.readFileSync(require('node:path').join(__dirname, '../docs/red/save-cache.js'), 'utf8');
function instance(path = '/red/') {
  const context = { caches, navigator, location: { href: `https://example.com${path}` }, URL, Response, crypto: webcrypto };
  vm.createContext(context);
  vm.runInContext(code, context);
  return context.createRedSaveCache(saved => saved && saved.version === 2 && Array.isArray(saved.actions));
}
(async () => {
  const first = instance(), second = instance();
  assert.equal(await first.read(), null);
  assert(await first.write({ version: 2, actions: ['a'] }));
  assert.equal((await instance().read()).actions[0], 'a');
  assert.deepEqual(await Promise.all([
    first.write({ version: 2, actions: ['b'] }),
    second.write({ version: 2, actions: ['c'] })
  ]), [true, true]);
  assert.equal((await instance().read()).actions[0], 'c');
  const entries = stores.get('englishscript-red-manual-save-v2');
  assert.equal(entries.size, 2);
  assert([...entries.keys()].every(url => url.startsWith('https://example.com/red/.englishscript-red-saves/v2/')));
  assert.equal(await instance('/other/').read(), null);
  denied = true;
  assert.equal(await first.read(), null);
  assert.equal(await first.write({ version: 2, actions: ['a'] }), false);
  console.log('Red save cache tests passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
