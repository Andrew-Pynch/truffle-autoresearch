# Fleet Dashboard

React web dashboard for the autoresearch control server. Visualizes experiment data, controls researchers, and wraps Truffle device operations.

Built with React + Vite, served as static files by the FastAPI control server on port 8420.

## Setup

Requires Node.js 22+ (use `nvm use 22` if needed).

```bash
npm install
```

## Development

```bash
npm run dev
```

Starts a Vite dev server on port 5173 with API proxy to `http://localhost:8420`. The control server must be running separately.

## Production Build

```bash
npm run build
```

Outputs to `dist/`, which the control server mounts at `/` as static files. No separate deployment needed - just build and the control server serves it.

## Features

### Fleet Status Cards
Per-machine cards showing experiment count, best val_bpb, and researcher running state. Auto-refreshes every 10 seconds. Color-coded: RTX 4090 = cyan, RTX 3080 = emerald.

### Optimization Trajectory Chart
Recharts line chart showing val_bpb over experiment number for both machines. "Keep" experiments are shown as larger filled dots, "discard" experiments as smaller hollow dots. Crash experiments (val_bpb = 0) are filtered out. Outliers are clipped via `allowDataOverflow` to keep the interesting convergence zone prominent. Auto-refreshes every 30 seconds.

### Fleet Control Panel
Start/Stop Researcher and Sync Results buttons per machine. Shows loading spinners during operations and success/error feedback.

### Truffle Operations Panel
Buttons for Scan, List Apps, Validate App, and Deploy App. All commands execute on big-ron (4090) via SSH through the `/api/truffile/{command}` endpoint. Command output (stdout/stderr) is displayed in a terminal-style output area.

### Live Log Viewer
Collapsible section with tabs for each machine. Shows the last 100 lines of `autoresearch/run.log` in a monospace terminal aesthetic. Auto-refreshes every 15 seconds when expanded. Auto-scrolls to bottom.

## Authentication

API token is stored in localStorage (default: `test`). Editable via the input field in the header. Passed as `Authorization: Bearer {token}` on all API calls.

## Project Structure

```
src/
  main.jsx                        -- React entry point
  App.jsx                         -- Main layout, auth state, polling
  App.css                         -- Dark theme styles
  api.js                          -- Fetch wrapper with auth
  components/
    Header.jsx                    -- Title, connection indicator, token input
    FleetStatusCards.jsx           -- Per-machine status cards
    TrajectoryChart.jsx            -- Recharts optimization trajectory (hero element)
    ControlPanel.jsx               -- Start/stop/sync buttons
    TrufflePanel.jsx               -- Truffile command buttons + output
    LogViewer.jsx                  -- Tabbed terminal log viewer
```

## Design

Dark theme inspired by Grafana/Datadog. Optimized for desktop screen share (interview demos). Color scheme:
- RTX 4090: cyan (`#22d3ee`)
- RTX 3080: emerald (`#34d399`)
- Truffle: amber (`#fbbf24`)

## Dependencies

- `react`, `react-dom` -- UI framework
- `recharts` -- Charting library
- `lucide-react` -- Icon library
- `@vitejs/plugin-react` -- Vite React plugin
