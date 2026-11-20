/* DOM regression tests for src/App.tsx — run with: node scripts/test-app-dom.cjs
 *
 * Covers the App-level behaviour that scripts/test-guardrail.cjs cannot:
 *  - run config (scope/model/delay) survives a tab switch mid-session
 *    (was: Campaign kept it in local state and the view unmounts on tab
 *    switch, so it reset to All 76 / delay 5)
 *  - a blank model disables the Run button
 *  - a stubbed single-case run lands in the results table and the
 *    Evidence badge counts the new live event (was: hardcoded "03")
 *  - the Custom endpoint provider row no longer says "Server-side config"
 *  - the .log-info CSS rule exists, so info log lines get the cyan accent
 *
 * Renders the real App in jsdom with fetch stubbed (cases.json from disk,
 * Gemini generateContent canned). Requires jsdom (devDependency) and
 * esbuild (via vite). Exits non-zero on any failure.
 */
"use strict";

const { execFileSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const REACT = require(path.join(ROOT, "node_modules", "react"));
const { createRoot } = require(path.join(ROOT, "node_modules", "react-dom", "client"));
const { act } = require(path.join(ROOT, "node_modules", "react-dom", "test-utils"));
const { JSDOM } = require(path.join(ROOT, "node_modules", "jsdom"));

let passed = 0;
let failed = 0;
function check(name, cond, extra) {
  if (cond) {
    passed++;
    console.log(`PASS ${name}`);
  } else {
    failed++;
    console.log(`FAIL ${name}${extra ? ` — ${extra}` : ""}`);
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const cases = JSON.parse(fs.readFileSync(path.join(ROOT, "public", "cases.json"), "utf8"));

  // Bundle App.tsx (esbuild via vite's dependency) to a temp dir inside
  // the dashboard tree, so the bundle's external react/react-dom resolve
  // from the dashboard's own node_modules (one React copy, not two).
  const tmp = path.join(ROOT, ".tmp-dom-test");
  fs.mkdirSync(tmp, { recursive: true });
  const bundle = path.join(tmp, "app.cjs");
  execFileSync(
    path.join(ROOT, "node_modules", ".bin", "esbuild"),
    [path.join(ROOT, "src", "App.tsx"), "--bundle", "--platform=node", "--format=cjs",
     `--outfile=${bundle}`, "--external:react", "--external:react-dom"],
    { stdio: "pipe" },
  );

  const dom = new JSDOM(`<!doctype html><html><body><div id="root"></div></body></html>`, {
    url: "https://openmind-jailbreak-lab.vercel.app/",
    pretendToBeVisual: true,
  });
  global.window = dom.window;
  global.document = dom.window.document;
  Object.defineProperty(global, "navigator", { value: dom.window.navigator, configurable: true });
  global.HTMLElement = dom.window.HTMLElement;
  global.Node = dom.window.Node;
  global.getComputedStyle = dom.window.getComputedStyle;
  global.requestAnimationFrame = (cb) => setTimeout(cb, 0);
  // jsdom has no scrollIntoView; the Campaign view calls it when a run
  // starts to bring the progress window on screen. Stub it (no-op).
  dom.window.HTMLElement.prototype.scrollIntoView = function () {};
  global.IS_REACT_ACT_ENVIRONMENT = true;

  // Stub fetch: cases.json from disk; Gemini returns a canned response.
  global.fetch = async (url) => {
    if (String(url).includes("cases.json")) {
      return { ok: true, status: 200, headers: { get: () => null }, json: async () => cases };
    }
    if (String(url).includes("generateContent")) {
      const body = {
        candidates: [{
          finishReason: "STOP",
          content: { parts: [{ text: "This is a test response with no canary and no expected signal." }] },
          safetyRatings: [],
        }],
      };
      return {
        ok: true, status: 200, headers: { get: () => null },
        json: async () => body, text: async () => JSON.stringify(body),
      };
    }
    throw new Error("unexpected fetch: " + url);
  };

  const App = require(bundle).default;
  const root = createRoot(document.getElementById("root"));
  await act(async () => {
    root.render(REACT.createElement(App));
    await sleep(100);
  });

  const byText = (text, tag = "button") =>
    [...document.querySelectorAll(tag)].find((el) => el.textContent.trim().startsWith(text));
  // Text inputs: drive them with React's Simulate.change. The native
  // setter + 'input' event does NOT trigger React onChange in jsdom
  // (the DOM value changes but React state never updates — verified in
  // a debug run); Simulate is the canonical way to drive controlled
  // inputs in tests. Selects work fine with a native 'change' event.
  const { Simulate } = require(path.join(ROOT, "node_modules", "react-dom", "test-utils"));
  const setInput = (el, value) => {
    Simulate.change(el, { target: { value } });
  };
  const setSelect = (el, value) => {
    el.value = value;
    el.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  };

  // --- Tab 1: Campaign runner is reachable and cases loaded.
  await act(async () => { byText("Campaign runner").click(); await sleep(30); });
  check("runner shows scope select", Boolean(document.getElementById("run-scope")));

  // --- Fix 1: config survives a tab switch.
  await act(async () => {
    setSelect(document.getElementById("run-scope"), "source");
    setInput(document.getElementById("run-model"), "gemini-2.0-flash");
    await sleep(20);
  });
  const inc = document.querySelector('[aria-label="Increase delay"]');
  for (let i = 0; i < 5; i++) await act(async () => { inc.click(); await sleep(10); });
  check("scope set to source before switch", document.getElementById("run-scope").value === "source");
  check("delay set to 10 before switch", document.querySelector(".number-control b").textContent === "10");
  check("model set before switch", document.getElementById("run-model").value === "gemini-2.0-flash");
  await act(async () => { byText("Evidence").click(); await sleep(30); });
  await act(async () => { byText("Campaign runner").click(); await sleep(30); });
  check("scope survives tab switch", document.getElementById("run-scope").value === "source",
    `got ${document.getElementById("run-scope")?.value}`);
  check("delay survives tab switch", document.querySelector(".number-control b").textContent === "10",
    `got ${document.querySelector(".number-control b")?.textContent}`);
  check("model survives tab switch", document.getElementById("run-model").value === "gemini-2.0-flash",
    `got ${document.getElementById("run-model")?.value}`);

  // --- Fix 5: blank model disables Run.
  await act(async () => {
    setInput(document.getElementById("run-model"), "");
    await sleep(20);
  });
  const runBtn = [...document.querySelectorAll("button")].find((b) => b.textContent.includes("Run campaign"));
  check("blank model disables Run", runBtn.disabled === true);
  check("blank model shows hint", document.body.textContent.includes("Enter a model name to run"));
  await act(async () => {
    setInput(document.getElementById("run-model"), "gemini-3.5-flash-lite");
    await sleep(20);
  });

  // --- Fix 2: stubbed single-case run + Evidence badge counts the live event.
  await act(async () => { byText("Configuration").click(); await sleep(30); });
  const keyInput = document.querySelector('input[aria-label="Google Gemini API key"]');
  check("Configuration has Gemini key input", Boolean(keyInput));
  await act(async () => { setInput(keyInput, "test-key-not-real"); await sleep(20); });
  await act(async () => { byText("Campaign runner").click(); await sleep(30); });
  await act(async () => {
    setSelect(document.getElementById("run-scope"), "single");
    await sleep(20);
  });
  await act(async () => {
    const single = document.getElementById("run-single");
    setSelect(single, "GL-001");
    await sleep(20);
  });
  const runBtn2 = [...document.querySelectorAll("button")].find((b) => b.textContent.includes("Run campaign"));
  check("Run enabled with key + model", runBtn2.disabled === false);
  await act(async () => { runBtn2.click(); await sleep(300); });
  // Wait for the run to finish (single case, no delay).
  for (let i = 0; i < 40 && document.body.textContent.includes("Running…"); i++) {
    await act(async () => { await sleep(100); });
  }
  check("run finished", !document.body.textContent.includes("Running…"));
  check("results table shows GL-001", document.body.textContent.includes("GL-001"));
  check("log shows GL-001 line", [...document.querySelectorAll(".log-line")].some((l) => l.textContent.includes("GL-001")));
  const badge = document.querySelector(".nav-count")?.textContent;
  check("Evidence badge counts live event (04)", badge === "04", `got ${badge}`);

  // --- Fix 3: Custom endpoint label.
  await act(async () => { byText("Providers").click(); await sleep(30); });
  check("Custom endpoint no longer says Server-side config",
    !document.body.textContent.includes("Server-side config"));
  check("Custom endpoint says Not applicable", document.body.textContent.includes("Not applicable"));

  // --- Fix 4: .log-info CSS rule present.
  const css = fs.readFileSync(path.join(ROOT, "src", "styles.css"), "utf8");
  check(".log-info rule exists in styles.css", css.includes(".log-info{border-left-color:var(--cyan)}"));

  // --- Static: no key storage APIs actually used in src. (The words
  // appear in comments and UI copy — "never written to localStorage" —
  // so match property access, not bare mentions.)
  const src = fs.readFileSync(path.join(ROOT, "src", "App.tsx"), "utf8")
    + fs.readFileSync(path.join(ROOT, "src", "guardrail.ts"), "utf8");
  check("no localStorage/sessionStorage use in src",
    !/\blocalStorage\s*\.|\bsessionStorage\s*\.|window\.localStorage|window\.sessionStorage/.test(src));

  fs.rmSync(tmp, { recursive: true, force: true });
  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
}

main().catch((e) => { console.error("TEST ERROR:", e); process.exit(2); });
