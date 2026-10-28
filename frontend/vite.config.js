import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");

/** Resolve `./foo.js` to `foo.ts`/`foo.tsx` so JSX waves can keep .js imports. */
function jsToTsResolve() {
  return {
    name: "js-to-ts-resolve",
    enforce: "pre",
    async resolveId(source, importer) {
      if (!importer || source.includes("\0") || !source.endsWith(".js")) return null;
      const resolved = path.resolve(path.dirname(importer), source);
      for (const ext of [".ts", ".tsx"]) {
        const candidate = resolved.replace(/\.js$/, ext);
        if (fs.existsSync(candidate)) return candidate;
      }
      return null;
    },
  };
}

export default defineConfig({
  plugins: [jsToTsResolve(), react()],
  resolve: {
    alias: {
      "@docs": path.resolve(repoRoot, "docs"),
    },
    // TypeScript ESM convention: import "./foo.js" while the source is foo.ts.
    extensionAlias: {
      ".js": [".ts", ".tsx", ".js", ".jsx"],
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    fs: {
      allow: [repoRoot],
    },
    proxy: {
      "/api": "http://127.0.0.1:8788",
    },
  },
});
