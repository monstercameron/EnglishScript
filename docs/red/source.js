(function () {
  const quick = [
    ['Main', 'main.english'], ['World / Maps', 'maps.english'],
    ['Battles', 'battle.english'], ['People', 'people.english'],
    ['Dialogue AI', 'companion_model.english'], ['Sound', 'sound.english']
  ];
  const validPath = path => typeof path === 'string' && /^[a-zA-Z0-9_/-]+\.english$/.test(path) && !path.includes('..');
  const label = path => path.replace(/\.english$/, '').replace(/[_/]+/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  const token = /"(?:[^"\\]|\\.)*"|\b\d+(?:\.\d+)?\b|\b(?:Ask the model|The answer is|For each|work out|in that order|except|has|from|for|at|when|Use|the|chapters|chapter|libraries|library|To|Whenever|If|Otherwise|Let|Set|be|is|are|not|and|or|contains|Stop|Repeat|while|Return|Book|Judge|Ask|about|verdict|reply|means|one of|text|number|perception|choice|Say)\b/gi;

  function highlight(document, source, firstLine = 1) {
    const fragment = document.createDocumentFragment();
    const lines = source.match(/[^\n]*\n|[^\n]+/g) || [''];
    lines.forEach((line, index) => {
      const row = document.createElement('span');
      row.className = 'source-line';
      row.dataset.line = String(index + firstLine);
      let position = 0;
      const table = /^\s*The\s+.+\s+are\s+.+\bin that order:\s*$/i.test(line);
      const tableRow = /^\s*"(?:[^"\\]|\\.)*"(?:\s+from\s+-?\d+(?:\.\d+)?)?\s+has\b/i.test(line);
      const lookup = /\bthe\s+[a-z][a-z ]*\s+for\s+"(?:[^"\\]|\\.)*"\s+at\b/i.test(line);
      const exception = /^\s*Set\s+.+,\s*except:\s*$/i.test(line);
      const alternative = /^\s*Use\s+.+\s+for\s+.+\.\s*$/i.test(line);
      token.lastIndex = 0;
      for (const match of line.matchAll(token)) {
        const word = match[0].toLowerCase();
        if ((word === 'in that order' && !table) || (word === 'has' && !tableRow) ||
            (word === 'from' && !tableRow) || (word === 'except' && !exception) || (word === 'for' && !alternative && !lookup) || (word === 'at' && !lookup) || (word === 'when' && !alternative)) continue;
        row.append(document.createTextNode(line.slice(position, match.index)));
        const part = document.createElement('span');
        part.className = match[0][0] === '"' ? 'source-string' : /^\d/.test(match[0]) ? 'source-number' : 'source-keyword';
        part.textContent = match[0];
        row.append(part);
        position = match.index + match[0].length;
      }
      row.append(document.createTextNode(line.slice(position)));
      fragment.append(row);
    });
    return fragment;
  }

  function createReader(document, fetch, root) {
    const tabs = document.createElement('div');
    tabs.className = 'source-tabs';
    tabs.setAttribute('role', 'tablist');
    tabs.setAttribute('aria-label', 'Featured chapters');
    const pickerLabel = document.createElement('label');
    pickerLabel.className = 'source-picker';
    pickerLabel.textContent = 'All chapters ';
    const picker = document.createElement('select');
    picker.setAttribute('aria-label', 'All chapters');
    pickerLabel.append(picker);
    const caption = document.createElement('h3');
    caption.id = 'source-current';
    const status = document.createElement('p');
    status.className = 'source-status';
    status.setAttribute('role', 'status');
    const retry = document.createElement('button');
    retry.type = 'button';
    retry.className = 'source-retry';
    retry.textContent = 'Try again';
    retry.hidden = true;
    const pages = document.createElement('div');
    pages.className = 'source-pages';
    const previous = document.createElement('button');
    previous.type = 'button';
    previous.textContent = 'Previous lines';
    const range = document.createElement('span');
    range.setAttribute('aria-live', 'polite');
    const next = document.createElement('button');
    next.type = 'button';
    next.textContent = 'Next lines';
    pages.append(previous, range, next);
    pages.hidden = true;
    const view = document.createElement('pre');
    view.className = 'source-view';
    view.tabIndex = 0;
    view.setAttribute('aria-labelledby', 'source-current');
    const code = document.createElement('code');
    view.append(code);
    view.addEventListener('keydown', event => event.stopPropagation());
    root.append(tabs, pickerLabel, caption, status, retry, pages, view);
    let selected = 'main.english';
    let paths = [];
    let request = 0;
    let retryAction;
    let lines = [];
    let page = 0;
    const pageSize = 150;

    function showPage() {
      const start = page * pageSize;
      const end = Math.min(start + pageSize, lines.length);
      code.replaceChildren(highlight(document, lines.slice(start, end).join(''), start + 1));
      range.textContent = 'Lines ' + (start + 1) + '–' + end + ' of ' + lines.length;
      previous.disabled = page === 0;
      next.disabled = end >= lines.length;
      pages.hidden = lines.length <= pageSize;
      view.scrollTop = 0;
      view.scrollLeft = 0;
    }
    previous.addEventListener('click', () => { if (page > 0) { page--; showPage(); } });
    next.addEventListener('click', () => { if ((page + 1) * pageSize < lines.length) { page++; showPage(); } });

    function showError(message, action) {
      status.textContent = message;
      retryAction = action;
      retry.hidden = false;
    }
    retry.addEventListener('click', () => retryAction());
    function updateSelection() {
      picker.value = selected;
      caption.textContent = label(selected) + ' · ' + selected;
      for (const button of tabs.children) {
        const active = button.dataset.path === selected;
        button.setAttribute('aria-selected', String(active));
        button.tabIndex = active ? 0 : -1;
      }
      if (![...tabs.children].some(button => button.dataset.path === selected) && tabs.firstElementChild) tabs.firstElementChild.tabIndex = 0;
    }
    async function select(path) {
      if (!paths.includes(path)) return;
      selected = path;
      const current = ++request;
      updateSelection();
      code.replaceChildren();
      pages.hidden = true;
      view.scrollTop = 0;
      view.scrollLeft = 0;
      status.textContent = 'Loading ' + path + '…';
      retry.hidden = true;
      try {
        const response = await fetch(path);
        if (!response.ok) throw new Error('Request failed');
        const source = await response.text();
        if (current !== request) return;
        lines = source.match(/[^\n]*\n|[^\n]+/g) || [''];
        page = 0;
        showPage();
        status.textContent = '';
      } catch (error) {
        if (current !== request) return;
        showError('Could not load ' + path + '.', () => select(path));
      }
    }
    picker.addEventListener('change', () => select(picker.value));
    tabs.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      const buttons = [...tabs.children];
      const index = buttons.indexOf(document.activeElement);
      if (index < 0) return;
      event.preventDefault();
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
      buttons[next].focus();
      select(buttons[next].dataset.path);
    });
    async function loadManifest() {
      status.textContent = 'Loading chapters…';
      retry.hidden = true;
      try {
        const response = await fetch('chapters.json');
        if (!response.ok) throw new Error('Request failed');
        const manifest = await response.json();
        if (!Array.isArray(manifest) || !manifest.every(validPath) || !manifest.includes('main.english')) throw new Error('Invalid manifest');
        paths = [...new Set([...manifest, 'companion_model.english'])];
        picker.replaceChildren();
        tabs.replaceChildren();
        for (const path of paths) {
          const option = document.createElement('option');
          option.value = path;
          option.textContent = label(path) + ' · ' + path;
          picker.append(option);
        }
        for (const [name, path] of quick) {
          if (!paths.includes(path)) continue;
          const button = document.createElement('button');
          button.type = 'button';
          button.textContent = name;
          button.dataset.path = path;
          button.setAttribute('role', 'tab');
          button.setAttribute('aria-controls', 'source-panel');
          button.addEventListener('click', () => select(path));
          tabs.append(button);
        }
        select(selected);
      } catch (error) {
        showError('Could not load the chapter list.', loadManifest);
      }
    }
    view.id = 'source-panel';
    view.setAttribute('role', 'tabpanel');
    loadManifest();
    return { select, loadManifest };
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { highlight, createReader, validPath };
  if (typeof document !== 'undefined') {
    const root = document.getElementById('source-reader');
    if (root) createReader(document, fetch, root);
  }
}());

