(function () {
  const root = document.getElementById('provider-keys');
  if (!root) return;

  root.innerHTML = `<details class="provider-keys"><summary>API keys</summary>
    <p>Keys are kept by the local game server for this browser session. Existing keys are never shown.</p>
    <p id="provider-key-status" role="status">Checking local service…</p>
    <form id="provider-key-form" autocomplete="off">
      <label for="jev-key">Jev API key <span id="jev-key-state">Unknown</span></label>
      <input id="jev-key" name="jev" type="password" autocomplete="off" spellcheck="false">
      <label for="openai-key">OpenAI API key <span id="openai-key-state">Unknown</span></label>
      <input id="openai-key" name="openai" type="password" autocomplete="off" spellcheck="false">
      <div class="provider-key-actions"><button type="submit">Save entered keys</button><button id="forget-provider-keys" type="button">Forget session keys</button></div>
    </form>
    <p>Leave a field blank to keep its current key. Forget removes session keys; server-configured keys may remain available.</p>
  </details>`;

  const status = root.querySelector('#provider-key-status');
  const form = root.querySelector('#provider-key-form');
  const jev = root.querySelector('#jev-key');
  const openai = root.querySelector('#openai-key');
  const forget = root.querySelector('#forget-provider-keys');
  const controls = [jev, openai, form.querySelector('button[type="submit"]'), forget];
  const local = ['localhost', '127.0.0.1', '[::1]', '::1'].includes(location.hostname) && ['http:', 'https:'].includes(location.protocol);
  const unavailable = 'API keys are available when this page is opened through the local game server on your computer.';
  const patience = 10;

  function enabled(value) {
    controls.forEach(control => { control.disabled = !value; });
  }

  function deadline() {
    return typeof AbortSignal === 'function' && typeof AbortSignal.timeout === 'function' ? AbortSignal.timeout(patience * 1000) : undefined;
  }

  async function ask(path, options = {}) {
    const response = await fetch(path, { ...options, signal: deadline() });
    if (!response.ok) throw new Error();
    return response;
  }

  function timedOut(error) {
    return error && error.name === 'TimeoutError';
  }

  function problem(action, error) {
    return timedOut(error)
      ? `Could not ${action}: the local game server did not answer within ${patience} seconds. Try again.`
      : `Could not ${action}. Check that the local game server is running and try again.`;
  }

  async function refresh() {
    if (!local) {
      enabled(false);
      status.textContent = unavailable;
      return;
    }
    try {
      const data = await (await ask('/api/companion', { cache: 'no-store' })).json();
      if (typeof data.jev !== 'boolean' || typeof data.openai !== 'boolean' || typeof data.sessionKeys !== 'boolean') throw new Error();
      root.querySelector('#jev-key-state').textContent = data.jev ? 'Configured' : 'Missing';
      root.querySelector('#openai-key-state').textContent = data.openai ? 'Configured' : 'Missing';
      enabled(true);
      status.textContent = data.sessionKeys ? 'Session keys are saved.' : 'No session keys saved.';
    } catch (error) {
      enabled(timedOut(error));
      status.textContent = timedOut(error) ? problem('check the API keys', error) : unavailable;
    }
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const keys = {};
    if (jev.value.trim()) keys.jev = jev.value.trim();
    if (openai.value.trim()) keys.openai = openai.value.trim();
    jev.value = '';
    openai.value = '';
    if (!Object.keys(keys).length) {
      status.textContent = 'Enter a key to save.';
      return;
    }
    enabled(false);
    try {
      await ask('/api/companion/keys', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(keys) });
      await refresh();
      window.dispatchEvent(new Event('red-companion-settings'));
    } catch (error) {
      enabled(true);
      status.textContent = problem('save keys', error);
    }
  });

  forget.addEventListener('click', async () => {
    jev.value = '';
    openai.value = '';
    enabled(false);
    try {
      await ask('/api/companion/keys', { method: 'DELETE' });
      await refresh();
      window.dispatchEvent(new Event('red-companion-settings'));
    } catch (error) {
      enabled(true);
      status.textContent = problem('forget keys', error);
    }
  });

  enabled(false);
  refresh();
}());
