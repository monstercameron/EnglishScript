// Programs printed in the text of a page: colour them, and let the reader run them.
//
// A program is written in the page as
//
//   <figure class="snippet">
//     <pre class="program" data-expect="ok | refused">...</pre>
//     <pre class="output">...</pre>          (optional: what it says, as printed)
//   </figure>
//
// A page may mark one figure with data-world. Its program is then put in front
// of every figure marked data-with-world, as the reference manual's examples
// all build on the small world described at its start.

import { play, show, failed, tint, toLink, loader } from "./engine.js";

export function mountSnippets(root = document) {
  const worldBlock = root.querySelector("figure.snippet[data-world] pre.program");
  const world = worldBlock ? worldBlock.textContent.replace(/\s+$/, "") + "\n\n" : "";

  for (const figure of root.querySelectorAll("figure.snippet")) {
    const program = figure.querySelector("pre.program");
    const text = program.textContent;
    const whole = figure.hasAttribute("data-with-world") ? world + text : text;
    const refused = program.dataset.expect === "refused";
    let shown = figure.querySelector("pre.output");
    program.innerHTML = tint(text);

    const bar = document.createElement("div");
    bar.className = "bar";
    const label = document.createElement("span");
    label.className = "label " + (refused ? "refused" : "ok");
    label.textContent = refused ? "The compiler refuses this" : (shown ? "What it says" : "An example");
    const runButton = document.createElement("button");
    runButton.type = "button";
    runButton.className = "button small";
    runButton.textContent = "Run it";
    const open = document.createElement("a");
    open.className = "button small";
    open.textContent = "Open in the playground";
    open.href = "playground.html#p=" + toLink(whole);
    const status = document.createElement("span");
    status.setAttribute("role", "status");
    const say = loader(status);
    bar.append(label, status, runButton, open);
    program.after(bar);

    runButton.addEventListener("click", async () => {
      runButton.disabled = true;
      runButton.setAttribute("aria-busy", "true");
      figure.classList.add("working");
      const live = document.createElement("div");
      live.className = "output";
      try {
        const result = await play(whole, "run", [], say);
        runButton.textContent = "Run it again";
        if (result.state === "waiting") result.events.push(["note", "This program asks a question. Open it in the playground to answer."]);
        if (!result.events.length) result.events.push(["note", "It ran, and said nothing."]);
        show(live, result.events);
      } catch (error) {
        failed(live, error);
        runButton.textContent = "Run it";
      }
      say("");
      figure.classList.remove("working");
      runButton.removeAttribute("aria-busy");
      if (shown) shown.replaceWith(live); else bar.after(live);
      shown = live;
      runButton.disabled = false;
    });
  }
}
