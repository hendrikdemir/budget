// Lint for the page's scripts: npm run check (with the type checks in jsconfig.json).
import js from "@eslint/js";
import globals from "globals";

export default [
  js.configs.recommended,
  {
    files: ["static/js/**/*.js"],
    languageOptions: { ecmaVersion: 2024, sourceType: "module", globals: globals.browser },
    rules: {
      "no-shadow": ["error", { builtinGlobals: false, allow: ["t", "e", "i", "s", "p"] }],
      "no-unused-vars": ["error", { args: "none", caughtErrors: "none" }],
      "no-empty": ["error", { allowEmptyCatch: true }],
      "no-restricted-properties": ["error",
        { property: "innerHTML", message: "Use setHtml(el, html`…`) from html.js, so everything in it is escaped." },
        { property: "outerHTML", message: "Use element(html`…`) from html.js." },
        { property: "insertAdjacentHTML", message: "Use element(html`…`) from html.js." }],
      eqeqeq: ["error", "smart"],
    },
  },
  {
    files: ["static/js/html.js", "static/js/i18n.js"],  // the only places that write HTML into the page
    rules: { "no-restricted-properties": "off" },
  },
];
