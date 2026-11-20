# OPENMIND // Neon Security Dashboard

A responsive cyberpunk-style frontend for the OpenMind-Jailbreak-Lab project. Built with React + Vite and designed for Vercel or Render static hosting.

## What is included

- Neon-dark responsive dashboard with animated scanline/grid effects.
- Overview, campaign runner, provider matrix, and evidence views.
- Provider selection and bounded campaign settings.
- Demo mode clearly labels synthetic data.
- Optional API connection through `VITE_API_BASE_URL`.
- No provider API keys are stored in the browser.

## Run locally

```bash
npm install
cp .env.example .env
npm run dev
```

Open the local URL printed by Vite.

## Build

```bash
npm run build
npm run preview
```

## Deploy to Vercel

1. Push this folder to a GitHub repository.
2. Import that repository in Vercel.
3. Framework preset: **Vite**.
4. Build command: `npm run build`.
5. Output directory: `dist`.
6. If connecting an API, set `VITE_API_BASE_URL` in Project Settings → Environment Variables.
7. Deploy.

`vercel.json` includes an SPA rewrite so dashboard routes resolve correctly.

## Deploy to Render

1. Push this folder to GitHub.
2. In Render, create **New → Static Site** and select the repository.
3. Build command: `npm install && npm run build`.
4. Publish directory: `dist`.
5. Add `VITE_API_BASE_URL` if your backend is deployed separately.
6. Deploy.

`render.yaml` is included as a Blueprint option.

## Connect the Python evaluation engine

This package is a frontend. It does not bundle or reimplement the Python lab. Deploy the Python service separately (for example, as a Render web service), then set `VITE_API_BASE_URL` to that service's base URL.

The UI expects this optional endpoint:

- `POST /api/campaigns`
- JSON request body:
  ```json
  {
    "providers": ["gemini"],
    "suite": "guardrail-lab",
    "max_requests": 20,
    "workers": 2,
    "timeout_seconds": 45
  }
  ```

The API should return JSON, ideally including a campaign/run identifier and status. The exact adapter is not assumed here: wire this route to your existing Python CLI or service after confirming its actual interface. Until an API base URL is configured, the Run Campaign button operates in clearly marked local demo mode and does not contact a model.

## Security notes

- Never put provider API keys in `VITE_*` variables; Vite exposes those values to the browser.
- Keep credentials in backend environment variables / hosting secrets.
- Add authentication, authorization, rate limits, request validation, and spend limits before exposing campaign execution publicly.
- Use reviewed benign test cases and retain human review of candidate findings.
