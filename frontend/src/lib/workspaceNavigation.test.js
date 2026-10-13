import assert from "node:assert/strict"
import test from "node:test"

import { safeWorkspaceReturn } from "./workspaceNavigation.js"

test("accepts a local dataset workspace return", () => {
  assert.equal(
    safeWorkspaceReturn("/datasets/primary/workspace?view=database", "secondary"),
    "/datasets/primary/workspace?view=database",
  )
})

test("rejects external and unrelated returns", () => {
  const fallback = "/datasets/secondary/workspace?view=database"
  assert.equal(safeWorkspaceReturn("https://example.com/datasets/x/workspace", "secondary"), fallback)
  assert.equal(safeWorkspaceReturn("//example.com/datasets/x/workspace", "secondary"), fallback)
  assert.equal(safeWorkspaceReturn("/settings", "secondary"), fallback)
})
