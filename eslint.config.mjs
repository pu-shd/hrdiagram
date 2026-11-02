import js from "@eslint/js";
import globals from "globals";

export default [
  js.configs.recommended,
  {
    files: ["web/app.js", "web/worker.js"],
    languageOptions: { globals: { ...globals.browser, ...globals.worker } },
    rules: { "no-unused-vars": ["error", { caughtErrors: "none" }] },
  },
];
