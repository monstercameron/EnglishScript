function createRedSaveCache(valid) {
  const cacheName = 'englishscript-red-manual-save-v2';
  const prefix = new URL('.englishscript-red-saves/v2/', new URL('.', location.href)).href;
  const lockName = `${cacheName}:${prefix}`;
  let writes = Promise.resolve();
  async function keysFor(cache) {
    return (await cache.keys()).filter(key => key.url.startsWith(prefix)).sort((a, b) => b.url.localeCompare(a.url));
  }
  async function read() {
    try {
      const cache = await caches.open(cacheName);
      for (const key of await keysFor(cache)) {
        try {
          const response = await cache.match(key);
          const saved = await response.json();
          if (valid(saved)) return saved;
        } catch { }
      }
    } catch { }
    return null;
  }
  async function prune(cache, newest) {
    for (const key of (await keysFor(cache)).slice(2)) if (key.url !== newest) await cache.delete(key);
  }
  function write(saved) {
    const snapshot = JSON.stringify(saved);
    writes = writes.catch(() => {}).then(async () => {
      const locks = globalThis.navigator?.locks;
      const store = async () => {
        const cache = await caches.open(cacheName);
        const keys = await keysFor(cache);
        const last = keys.length ? Number(keys[0].url.slice(prefix.length).split('-')[0]) : 0;
        const sequence = Math.max(Date.now() * 1000, last + 1);
        const unique = globalThis.crypto?.randomUUID?.() || `${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
        const url = `${prefix}${String(sequence).padStart(16, '0')}-${unique}`;
        await cache.put(url, new Response(snapshot, { headers: { 'Content-Type': 'application/json' } }));
        await prune(cache, url);
        return true;
      };
      return locks ? await locks.request(lockName, store) : await store();
    }).catch(() => false);
    return writes;
  }
  return { read, write };
}
