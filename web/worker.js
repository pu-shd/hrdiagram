// @ts-check
/** @type {any} */
const context = self;
/** @type {any} */
let runtime;
try {
  // Keep the runtime, wheels, and Python source on the same static origin.
  const runtimeModule = new URL("./vendor/pyodide.mjs", import.meta.url).href;
  const { loadPyodide } = await import(runtimeModule);
  runtime = await loadPyodide({ indexURL: new URL("./vendor/", import.meta.url).href });
  await runtime.loadPackage(["numpy", "scipy", "matplotlib", "astropy"]);
  const response = await fetch("analysis.py");
  if (!response.ok) throw new Error("Analysis source unavailable");
  runtime.runPython(await response.text());
  context.postMessage({ type: "ready" });
} catch {
  context.postMessage({ type: "fatal" });
}
context.onmessage = async (/** @type {MessageEvent} */ { data }) => {
  if (data.type !== "analyze" || !runtime) return;
  const started = performance.now();
  try {
    runtime.FS.writeFile("/input.fit", new Uint8Array(data.bytes));
    const result = JSON.parse(runtime.runPython('json.dumps(analyze("/input.fit"), allow_nan=False)'));
    result.seconds = (performance.now() - started) / 1000;
    context.postMessage({ type: "result", result, job: data.job });
  } catch (error) {
    const message = String(error);
    const explanation = message.match(/ValueError: ([^\n]+)/);
    context.postMessage({
      type: "error", job: data.job,
      message: explanation ? explanation[1] : "The image could not be analyzed. Check its format or try a smaller crop.",
    });
  } finally {
    try { runtime.FS.unlink("/input.fit"); } catch { /* No input was written. */ }
    runtime.runPython("import gc; gc.collect()");
  }
};
