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

  function enabled(value) {
    controls.forEach(control => { control.disabled = !value; });
  }

  async function refresh() {
    if (!local) {
      enabled(false);
      status.textContent = unavailable;
      return;
    }
    try {
      const response = await fetch('/api/companion', { cache: 'no-store' });
      if (!response.ok) throw new Error();
      const data = await response.json();
      if (typeof data.jev !== 'boolean' || typeof data.openai !== 'boolean' || typeof data.sessionKeys !== 'boolean') throw new Error();
      root.querySelector('#jev-key-state').textContent = data.jev ? 'Configured' : 'Missing';
      root.querySelector('#openai-key-state').textContent = data.openai ? 'Configured' : 'Missing';
      enabled(true);
      status.textContent = data.sessionKeys ? 'Session keys are saved.' : 'No session keys saved.';
    } catch (_) {
      enabled(false);
      status.textContent = unavailable;
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
      const response = await fetch('/api/companion/keys', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(keys) });
      if (!response.ok) throw new Error();
      await refresh();
      window.dispatchEvent(new Event('red-companion-settings'));
    } catch (_) {
      enabled(true);
      status.textContent = 'Could not save keys. Check that the local game server is running and try again.';
    }
  });

  forget.addEventListener('click', async () => {
    jev.value = '';
    openai.value = '';
    enabled(false);
    try {
      const response = await fetch('/api/companion/keys', { method: 'DELETE' });
      if (!response.ok) throw new Error();
      await refresh();
      window.dispatchEvent(new Event('red-companion-settings'));
    } catch (_) {
      enabled(true);
      status.textContent = 'Could not forget keys. Check that the local game server is running and try again.';
    }
  });

  enabled(false);
  refresh();
}());
