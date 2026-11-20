# OPENMIND // Neon Security Dashboard

A responsive cyberpunk-style frontend for the OpenMind-Jailbreak-Lab project. Built with React + Vite and deployed as a static site on Vercel.

## What is included

- Neon-dark responsive dashboard with animated scanline/grid effects.
- Overview, campaign runner, provider matrix, evidence, configuration, and documentation views.
- **In-browser campaign runner:** the Guardrail Lab suite (76 cases) runs directly in your browser against Gemini, case by case, with a live progress window — a progress count and bar, per-case log lines as each case completes, running summary counts, and a results table. No backend is needed.
- Live assessment uses the lab's own rule (canary-only vs mention vs control vs held), the lab system instruction, the GL-010 guard, and the Space's retry policy — implemented in `src/guardrail.ts` and checked against the repo's Python rule.
- Provider keys live in **Configuration**, in page memory only. Gemini is the live runner; the other providers are listed for reference and are not wired yet.
- Demo mode clearly labels synthetic data. Without a Gemini key the runner points you to Configuration instead of pretending to run.

## Run locally

```bash
npm install
npm run dev
```

Open the local URL printed by Vite.

## Build

```bash
npm run build
npm run preview
```

## Test

```bash
npm test
```

This runs the guardrail checks (`scripts/test-guardrail.cjs`: the TypeScript assessment rule against the repo's Python `assess()` on fixtures, the GL-010 guard, the retry policy, and the stop-during-retry/flight/delay behaviour) and verifies `public/cases.json` against a fresh export of the repo's Guardrail Lab cases (`scripts/verify-cases.py`).

## Cases

`public/cases.json` is generated from the repository's Guardrail Lab cases (`modules/guardrail_lab/cases.py` + `source_cases.py`) — 76 rows, 24 core + 52 source-derived safe adaptations. Regenerate it with:

```bash
python3 scripts/generate_cases.py --repo /path/to/OpenMind-Jailbreak-Lab
```

Verify it with `python3 scripts/verify-cases.py --repo /path/to/OpenMind-Jailbreak-Lab`. The file is served at `/cases.json` and fetched by the page at runtime.

## Deploy to Vercel

1. Push this folder to a GitHub repository.
2. Import that repository in Vercel.
3. Framework preset: **Vite**.
4. Build command: `npm run build`.
5. Output directory: `dist`.
6. Deploy.

`vercel.json` includes an SPA rewrite as a safety net. The dashboard has no client-side routes (navigation is tab state), so the rewrite is normally a no-op. Static files in `dist/` (including `cases.json`) take precedence over the rewrite.

## How the live runner works

1. Add a free Gemini API key in **Configuration** (Google AI Studio, free tier). The key is held in React state — page memory only — and sent only to Google's API. Closing or reloading the page forgets it.
2. Open the **Campaign runner**, pick a scope (All 76, Core 24, Source 52, or a single case) and a delay between calls (default 5s, free-tier friendly).
3. Press **Run campaign**. Cases run sequentially; the progress window shows a live count (`CASE 12 OF 76`), a progress bar, one log line per completed case (id, verdict, latency), running summary counts, and a results table. Switching tabs mid-run does not stop the run; the status strip keeps showing live progress.
4. **Stop** aborts the in-flight call and any delay or retry wait immediately. Completed cases are kept; the remaining cases are never sent.
5. Download the JSON report when the run finishes.

Retries mirror the Space: 429/5xx retried up to 3 attempts with Retry-After (cap 60s); a 429 after retries or a 401/403/404 stops the suite; other failures record `partial_run` and the run continues. Each call times out after 60s. GL-010 runs only if GL-009 completed in the same run; otherwise it is recorded as not sent.

## Security notes

- Never put provider API keys in `VITE_*` variables; Vite exposes those values to the browser. Keys go in Configuration (page memory only), never in code, files, logs, or URLs.
- Use reviewed benign test cases and retain human review of candidate findings. A `potential_guardrail_failure` is a candidate signal, never a confirmed bypass on its own.
