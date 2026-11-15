import { test } from "node:test";
import assert from "node:assert/strict";
import { detectTopology, defaultTopologyContext } from "../topology.ts";

test("detectTopology: darwin -> mac", () => {
  assert.equal(detectTopology({ platform: "darwin", hasWsl: () => false }), "mac");
  assert.equal(detectTopology({ platform: "darwin", hasWsl: () => true }), "mac");
});

test("detectTopology: linux -> linux", () => {
  assert.equal(detectTopology({ platform: "linux", hasWsl: () => false }), "linux");
  assert.equal(detectTopology({ platform: "linux", hasWsl: () => true }), "linux");
});

test("detectTopology: win32 + WSL available -> wsl", () => {
  assert.equal(detectTopology({ platform: "win32", hasWsl: () => true }), "wsl");
});

test("detectTopology: win32 + no WSL -> win", () => {
  assert.equal(detectTopology({ platform: "win32", hasWsl: () => false }), "win");
});

test("detectTopology: unknown platform falls back to linux", () => {
  assert.equal(detectTopology({ platform: "aix", hasWsl: () => false }), "linux");
  assert.equal(detectTopology({ platform: "freebsd", hasWsl: () => false }), "linux");
});

test("defaultTopologyContext exposes process.platform and a hasWsl function", () => {
  const ctx = defaultTopologyContext();
  assert.equal(typeof ctx.platform, "string");
  assert.equal(typeof ctx.hasWsl, "function");
  // hasWsl must be callable and return a boolean (best-effort).
  assert.equal(typeof ctx.hasWsl(), "boolean");
});
