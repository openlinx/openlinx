// Seam 9 wiring: 070-add-html-report owns the planned Report script tests here.
import assert from "node:assert/strict";
import { test } from "node:test";

test("node --test finds and runs the tests in tests/js", () => {
  assert.equal(typeof test, "function");
});
