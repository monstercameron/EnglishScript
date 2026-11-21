self.workerStart = {
  patience: 60,
  async python(url) {
    if (typeof WebAssembly !== "object" || typeof WebAssembly.compile !== "function") {
      throw new Error("WebAssembly is unavailable in this browser. Enable WebAssembly or try another browser, then reload.");
    }
    try {
      await WebAssembly.compile(new Uint8Array([0, 97, 115, 109, 1, 0, 0, 0]));
    } catch (_) {
      throw new Error("WebAssembly is blocked or unavailable. Check browser security settings or try another browser, then reload.");
    }
    try {
      importScripts(url + "pyodide.js");
      if (typeof loadPyodide !== "function") throw new Error();
    } catch (_) {
      throw new Error("Could not load Pyodide loader pyodide.js. Check your connection or content blocker, then reload.");
    }
    const seconds = self.workerStart.runtimePatience;
    let timer;
    const late = new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error("The Python runtime didn't load within " + seconds + " seconds. Check your connection and access to cdn.jsdelivr.net, then reload.")), seconds * 1000);
    });
    const runtime = loadPyodide({ indexURL: url }).catch(() => {
      throw new Error("Could not initialize Pyodide or download its runtime files. Check your connection and access to cdn.jsdelivr.net, then reload.");
    });
    try {
      return await Promise.race([runtime, late]);
    } finally {
      clearTimeout(timer);
    }
  },
  runtimePatience: 120,
  async download(path, kind, format) {
    let response;
    try {
      response = await fetch(new URL(path, self.location.href), { cache: "no-cache", signal: self.workerStart.deadline() });
    } catch (error) {
      if (error && error.name === "TimeoutError") throw new Error("Could not download " + kind + " " + path + ": the server did not answer within " + self.workerStart.patience + " seconds. Check your connection, then reload.");
      throw new Error("Could not download " + kind + " " + path + ". Check your connection, then reload.");
    }
    if (!response.ok) throw new Error("Could not download " + kind + " " + path + " (HTTP " + response.status + "). Check the site files and reload.");
    try {
      return await response[format]();
    } catch (_) {
      throw new Error("Could not read " + kind + " " + path + ". Check your connection, then reload.");
    }
  },
  deadline() {
    return typeof AbortSignal === "function" && typeof AbortSignal.timeout === "function" ? AbortSignal.timeout(self.workerStart.patience * 1000) : undefined;
  },
  unpack(python, archive) {
    try {
      python.unpackArchive(archive, "zip", { extractDir: "/site" });
    } catch {
      throw new Error("Could not unpack compiler archive englishscript.zip. Reload to download it again.");
    }
  }
};
