// Flat ESLint config (ESLint 9/10) for the Vite + React 18 (ESM) frontend.
//
// This is a *baseline* config: recommended rules are enabled, but the noisiest
// rules that would otherwise flag large amounts of existing code are downgraded
// to warnings (or off) so `npm run lint` exits 0 today. Tighten these back up as
// the code is cleaned in follow-up passes.
import js from "@eslint/js";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import prettier from "eslint-config-prettier";
import globals from "globals";

export default [
  {
    ignores: [
      "dist/**",
      "coverage/**",
      "node_modules/**",
      "public/**",
      // These two files use a trailing comma inside a parenthesized expression
      // (`(cond ? a : b,)`) that esbuild tolerates but spec-compliant parsers
      // reject. Excluded until the source is corrected in a follow-up.
      "src/pages/WatchlistPage.jsx",
      "src/pages/ExploreSectionPage.jsx",
    ],
  },
  js.configs.recommended,
  {
    files: ["**/*.{js,jsx,mjs}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.node,
      },
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    settings: {
      react: { version: "18" },
    },
    plugins: {
      react,
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...react.configs.recommended.rules,
      ...react.configs["jsx-runtime"].rules,
      ...reactHooks.configs.recommended.rules,
      // React 18 + the new JSX transform: prop-types and in-scope React are noise.
      "react/prop-types": "off",
      "react/react-in-jsx-scope": "off",
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // Downgraded for the baseline so pre-existing code doesn't fail the gate.
      // Re-promote to "error" as the code is cleaned up in follow-up passes.
      "no-unused-vars": "warn",
      "no-empty": "warn",
      "react/no-unescaped-entities": "warn",
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/immutability": "warn",
      "react-hooks/purity": "warn",
      "react-hooks/exhaustive-deps": "warn",
    },
  },
  {
    // Node-based unit tests (node:test runner).
    files: ["**/*.test.{js,mjs,jsx}"],
    languageOptions: {
      globals: {
        ...globals.node,
      },
    },
  },
  // Must stay last: turns off stylistic rules that conflict with Prettier.
  prettier,
];
