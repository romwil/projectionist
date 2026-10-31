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
import jsxA11y from "eslint-plugin-jsx-a11y";
import prettier from "eslint-config-prettier";
import globals from "globals";
import tseslint from "typescript-eslint";

// A11Y-005: jsx-a11y's recommended set catches real a11y regressions
// (missing alt text, bad aria-*, non-interactive elements with click
// handlers, etc.) — downgraded to warnings, same as everything else in
// this baseline config, so `npm run lint` stays at 0 errors while still
// surfacing the problem.
const jsxA11yWarnRules = Object.fromEntries(
  Object.keys(jsxA11y.flatConfigs.recommended.rules)
    .filter((name) => name.startsWith("jsx-a11y/"))
    .map((name) => [name, "warn"]),
);

export default [
  {
    ignores: [
      "dist/**",
      "coverage/**",
      "node_modules/**",
      "public/**",
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
      "jsx-a11y": jsxA11y,
    },
    rules: {
      ...react.configs.recommended.rules,
      ...react.configs["jsx-runtime"].rules,
      ...reactHooks.configs.recommended.rules,
      ...jsxA11yWarnRules,
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
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parser: tseslint.parser,
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
      "@typescript-eslint": tseslint.plugin,
      "jsx-a11y": jsxA11y,
    },
    rules: {
      ...react.configs.recommended.rules,
      ...react.configs["jsx-runtime"].rules,
      ...reactHooks.configs.recommended.rules,
      ...jsxA11yWarnRules,
      "react/prop-types": "off",
      "react/react-in-jsx-scope": "off",
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // Match the JSX baseline: unused stays warn, not error.
      "no-unused-vars": "off",
      // Type-only `React.ReactNode` / namespace refs and DOM lib types; tsc already checks undef.
      "no-undef": "off",
      "@typescript-eslint/no-unused-vars": "warn",
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
