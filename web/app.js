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
  const loadDetails = element("load-details");
  const imageResources = element("image-resources");
  const resourceNote = /** @type {HTMLDetailsElement} */ (element("resource-note"));
  const maxFileBytes = 250 * 1024 * 1024;
  const maxPixels = 19_000_000;
  let checkingImage = false;
  let imageWithinLimits = false;
  let selectionVersion = 0;
  let ready = false;
  let busy = false;
  /** @type {Worker} */
  let worker;
  /** @type {string[]} */
  let urls = [];
  let stem = "stars";
  let job = 0;

  /** @param {number} bytes */
  function mib(bytes) {
    return (bytes / 1024 ** 2).toLocaleString(undefined, { maximumFractionDigits: 1 });
  }
  /**
   * Read only a bounded primary FITS header for the size note. Astropy remains
   * responsible for full validation and for images in extension HDUs.
   * @param {ArrayBuffer} bytes
   * @returns {{width: number, height: number} | null}
   */
  function primaryDimensions(bytes) {
    const text = new TextDecoder("ascii").decode(bytes);
    if (!text.startsWith("SIMPLE  =")) return null;
    /** @type {Map<string, number>} */
    const values = new Map();
    let ended = false;
    for (let offset = 0; offset + 80 <= text.length; offset += 80) {
      const card = text.slice(offset, offset + 80);
      const key = card.slice(0, 8).trim();
      if (key === "END") { ended = true; break; }
      if (!["NAXIS", "NAXIS1", "NAXIS2", "NAXIS3"].includes(key) || card[8] !== "=") continue;
      const value = card.slice(10).split("/")[0].trim();
      if (!/^\+?\d+$/.test(value)) return null;
      values.set(key, Number(value));
    }
    const width = values.get("NAXIS1");
    const height = values.get("NAXIS2");
    if (!ended || values.get("NAXIS") !== 3 || values.get("NAXIS3") !== 3 || !width || !height ||
        !Number.isSafeInteger(width) || !Number.isSafeInteger(height) || !Number.isSafeInteger(width * height)) return null;
    return { width, height };
  }
  async function describeSelection() {
    const version = ++selectionVersion;
    const file = input.files?.[0];
    imageResources.classList.remove("over-limit");
    checkingImage = false;
    imageWithinLimits = false;
    if (!file) {
      imageResources.textContent = "Choose an image to see its size and dimensions.";
      update();
      return;
    }
    const fileSize = `${mib(file.size)} MiB file`;
    if (file.size > maxFileBytes) {
      imageResources.textContent = `${fileSize}. Exceeds the 250-MiB file limit.`;
      imageResources.classList.add("over-limit");
      resourceNote.open = true;
      update();
      return;
    }
    checkingImage = true;
    imageWithinLimits = true;
    imageResources.textContent = `${fileSize}. Checking image dimensions…`;
    update();
    try {
      // Inspect at most 32 FITS header blocks (~90 KiB), never the whole image.
      const bytes = await file.slice(0, 2880 * 32).arrayBuffer();
      if (version !== selectionVersion) return;
      const dimensions = primaryDimensions(bytes);
      if (dimensions) {
        const { width, height } = dimensions;
        const pixels = width * height;
        const megapixels = (pixels / 1_000_000).toLocaleString(undefined, { maximumFractionDigits: 2 });
        const description = `${width.toLocaleString()} × ${height.toLocaleString()} pixels (${megapixels} megapixels) · ${fileSize}.`;
        imageWithinLimits = pixels <= maxPixels;
        imageResources.textContent = imageWithinLimits
          ? `${description} RGB array alone: ${mib(pixels * 3 * 8)} MiB; processing needs additional memory.`
          : `${description} Exceeds the 19-megapixel limit.`;
        imageResources.classList.toggle("over-limit", !imageWithinLimits);
        if (!imageWithinLimits) resourceNote.open = true;
      } else {
        imageResources.textContent = `${fileSize}. Dimensions will be checked during analysis.`;
      }
    } catch {
      if (version === selectionVersion) imageResources.textContent = `${fileSize}. Dimensions will be checked during analysis.`;
    } finally {
      if (version === selectionVersion) {
        checkingImage = false;
        update();
      }
    }
  }
  const deviceMemory = /** @type {Navigator & { deviceMemory?: number }} */ (navigator).deviceMemory;
  element("browser-memory").textContent = typeof deviceMemory === "number" && Number.isFinite(deviceMemory) && deviceMemory > 0
    ? `The browser reports about ${deviceMemory} GiB of device RAM (rounded). This is installed RAM, not free memory or a per-page allowance.`
    : "Memory information is not reported by this browser.";

  function clearResults() {
    for (const url of urls) URL.revokeObjectURL(url);
    urls = [];
    results.hidden = true;
    /** @type {HTMLImageElement} */ (element("plot")).removeAttribute("src");
  }
  function update() {
    generate.disabled = !ready || busy || checkingImage || !imageWithinLimits || !input.files?.length;
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
    loadDetails.hidden = true;
    status.textContent = "Loading the analysis tools… The first load can take a moment.";
    worker = new Worker("worker.js?v=20261102b", { type: "module" });
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
        fail("The analysis tools could not load. Try Reload tool, or share Loading details with your instructor.");
        element("load-error").textContent = `${data.stage || "Startup"}: ${String(data.message || "Unknown startup error").slice(0, 2000)}`;
        loadDetails.hidden = false;
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
    void describeSelection();
  });
  generate.addEventListener("click", async () => {
    const file = input.files?.[0];
    if (!file || !ready || busy || checkingImage || !imageWithinLimits) return;
    clearResults();
    error.hidden = true;
    if (file.size > maxFileBytes) {
      fail("Choose a FITS file no larger than 250 MiB.");
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
