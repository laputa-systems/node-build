import assert from "node:assert/strict";
import test from "node:test";

test("cjs and esm agree", async () => {
  const cjs = await import("./hello.cjs");
  const esm = await import("./hello.mjs");
  assert.equal(cjs.default.answer, 42);
  assert.equal(esm.answer, 42);
});
