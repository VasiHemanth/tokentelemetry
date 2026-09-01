import { test } from "node:test";
import assert from "node:assert/strict";
import {
  SHORTCUTS, defaultBindings, shortcutKey, chordTokens, describeBinding,
  bindingUsesLeader, shortcutRoute, isTypingTarget,
} from "./shortcuts";

test("shortcutKey normalizes bare keys and ignores modifiers", () => {
  assert.equal(shortcutKey({ key: "g", ctrlKey: false, altKey: false, metaKey: false }), "g");
  assert.equal(shortcutKey({ key: "A", ctrlKey: false, altKey: false, metaKey: false }), "a");
  assert.equal(shortcutKey({ key: "?", ctrlKey: false, altKey: false, metaKey: false }), "?");
  assert.equal(shortcutKey({ key: "g", ctrlKey: true, altKey: false, metaKey: false }), null);
  assert.equal(shortcutKey({ key: "g", ctrlKey: false, altKey: true, metaKey: false }), null);
  assert.equal(shortcutKey({ key: "Enter", ctrlKey: false, altKey: false, metaKey: false }), null);
});

test("default bindings assign a key to every shortcut", () => {
  const bindings = defaultBindings();
  for (const s of SHORTCUTS) {
    assert.ok(s.id in bindings, `${s.id} should have a default binding`);
    assert.equal(bindings[s.id], s.defaultKey);
  }
});

test("chord and description mirror the sequence/single kinds", () => {
  const settings = SHORTCUTS.find((s) => s.id === "settings")!;
  assert.deepEqual(chordTokens(settings, "s"), ["g", "s"]);
  assert.equal(describeBinding(settings, "s"), "g then s");

  const help = SHORTCUTS.find((s) => s.id === "help")!;
  assert.deepEqual(chordTokens(help, "?"), ["?"]);
  assert.equal(describeBinding(help, "?"), "?");
});

test("bindingUsesLeader matches only sequence shortcuts with that leader", () => {
  assert.equal(bindingUsesLeader(defaultBindings(), "home", "g"), true);
  assert.equal(bindingUsesLeader(defaultBindings(), "help", "g"), false);
  assert.equal(bindingUsesLeader(defaultBindings(), "help", null), true);
});

test("shortcutRoute resolves the navigation destination", () => {
  assert.equal(shortcutRoute("home"), "/");
  assert.equal(shortcutRoute("analytics"), "/analytics");
  assert.equal(shortcutRoute("help"), "/settings?section=shortcuts");
});

test("isTypingTarget is safe in a non-DOM environment", () => {
  // node:test has no HTMLElement; must not throw and must return false.
  assert.equal(isTypingTarget(null), false);
});
