// Bundles the Obsidian plugin to a single CommonJS main.js.
//
// Run with: `npm run build` (invoked via `node esbuild.config.mjs`).
import esbuild from "esbuild";
import builtinModules from "builtin-modules";
import { existsSync, mkdirSync } from "node:fs";

const outdir = process.cwd();

// esbuild.config.mjs itself is git-ignored as *.js is banned, except this file.
const external = [
  "obsidian",
  "electron",
  "@codemirror/autocomplete",
  "@codemirror/collab",
  "@codemirror/commands",
  "@codemirror/language",
  "@codemirror/lint",
  "@codemirror/search",
  "@codemirror/state",
  "@codemirror/view",
  "@lezer/common",
  "@lezer/highlight",
  "@lezer/lr",
  ...builtinModules,
];

if (!existsSync(outdir)) mkdirSync(outdir, { recursive: true });

esbuild
  .build({
    entryPoints: ["src/main.ts"],
    bundle: true,
    outfile: "main.js",
    format: "cjs",
    target: "es2020",
    platform: "node",
    logLevel: "info",
    sourcemap: false,
    treeShaking: true,
    external,
  })
  .then(() => {
    console.log("esbuild: main.js written");
  })
  .catch((err) => {
    console.error(err);
    process.exit(1);
  });
