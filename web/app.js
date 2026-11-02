// @ts-check
(() => {
  /** @template {HTMLElement} T @param {string} id @returns {T} */
  function element(id) {
    const value = document.getElementById(id);
    if (!value) throw new Error(`Missing element: ${id}`);
    return /** @type {T} */ (value);
  }
  const input = /** @type {HTMLInputElement} */ (element("image"));
  const generate = /** @type {HTMLButtonElement} */ (element("generate"));
  const cancel = element("cancel");
  const retry = element("retry");
  const status = element("status");
  const error = element("error");
  const results = element("results");
  let ready = false;
  let busy = false;
  /** @type {Worker} */
  let worker;
  /** @type {string[]} */
  let urls = [];
  let stem = "stars";
  let job = 0;

  function clearResults() {
    for (const url of urls) URL.revokeObjectURL(url);
    urls = [];
    results.hidden = true;
    /** @type {HTMLImageElement} */ (element("plot")).removeAttribute("src");
  }
  function update() {
    generate.disabled = !ready || busy || !input.files?.length;
    input.disabled = busy;
    cancel.hidden = !busy;
  }
  /** @param {string} message */
  function fail(message) {
    busy = false;
    error.textContent = message;
    error.hidden = false;
    status.textContent = "Analysis stopped.";
    update();
  }
  function start() {
    ready = false;
    busy = false;
    retry.hidden = true;
    error.hidden = true;
    status.textContent = "Loading the analysis tools… The first load can take a moment.";
    worker = new Worker("worker.js", { type: "module" });
    worker.onerror = () => {
      worker.terminate();
      ready = false;
      fail("The analysis worker stopped. Reload the tool; for a large image, try a smaller crop.");
      retry.hidden = false;
    };
    worker.onmessage = ({ data }) => {
      if (data.type === "ready") {
        ready = true;
        status.textContent = "Ready. Choose an image to begin.";
        update();
      } else if (data.type === "fatal") {
        ready = false;
        fail("The analysis tools could not load. Check your connection and reload the tool.");
        retry.hidden = false;
      } else if (data.job === job && data.type === "error") {
        fail(data.message);
      } else if (data.job === job && data.type === "result") {
        const result = data.result;
        const bytes = Uint8Array.from(atob(result.png), (c) => c.charCodeAt(0));
        const png = URL.createObjectURL(new Blob([bytes], { type: "image/png" }));
        const csv = URL.createObjectURL(new Blob([result.csv], { type: "text/csv;charset=utf-8" }));
        urls = [png, csv];
        /** @type {HTMLImageElement} */ (element("plot")).src = png;
        for (const [id, url, extension] of [["png-download", png, "png"], ["csv-download", csv, "csv"]]) {
          const link = /** @type {HTMLAnchorElement} */ (element(id));
          link.href = url;
          link.download = `${stem}_HR.${extension}`;
        }
        element("summary").textContent = `${result.width} × ${result.height} pixels · ${result.detected.toLocaleString()} detections · ${result.positive_rgb.toLocaleString()} positive RGB measurements · ${result.plotted.toLocaleString()} stars plotted`;
        results.hidden = false;
        busy = false;
        status.textContent = `Diagram ready in ${result.seconds.toFixed(1)} seconds.`;
        update();
      }
    };
    update();
  }
  input.addEventListener("change", () => {
    clearResults();
    error.hidden = true;
    update();
  });
  generate.addEventListener("click", async () => {
    const file = input.files?.[0];
    if (!file || !ready || busy) return;
    clearResults();
    error.hidden = true;
    if (file.size > 160 * 1024 * 1024) {
      fail("Choose a FITS file smaller than 160 MiB.");
      return;
    }
    busy = true;
    const currentJob = ++job;
    stem = file.name.replace(/\.[^.]+$/, "");
    status.textContent = "Measuring stars and drawing the diagram…";
    update();
    try {
      const bytes = await file.arrayBuffer();
      if (job !== currentJob) return;
      worker.postMessage({ type: "analyze", bytes, job: currentJob }, [bytes]);
    } catch {
      if (job === currentJob) fail("This file could not be read. Choose it again and retry.");
    }
  });
  cancel.addEventListener("click", () => {
    ++job;
    worker.terminate();
    start();
  });
  retry.addEventListener("click", () => {
    worker.terminate();
    start();
  });
  window.addEventListener("pagehide", () => {
    worker.terminate();
    for (const url of urls) URL.revokeObjectURL(url);
  });
  start();
})();
