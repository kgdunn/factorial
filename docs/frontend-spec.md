# Frontend Specification

UI/UX spec for the SvelteKit frontend. For system architecture, see `architecture.md`.
For development conventions, see the root `CLAUDE.md`.

## Pages & Routes

| Route | Page | Purpose |
|-------|------|---------|
| `/` | Landing / Signup | Welcome page, user registration |
| `/chat` | Agent Chat | Main agent interaction interface |
| `/experiments` | Experiments Dashboard | List user's experiments |
| `/experiments/[id]` | Experiment Detail | Design view, results entry, analysis |
| `/models` | Shared Models Gallery | Browse publicly shared models |

## User Roles / Backgrounds

At signup, users select the role that best matches their background. This helps the agent tailor its language and suggestions.

- Chemical engineer
- Pharmaceutical scientist
- Food scientist
- Academic researcher
- Quality engineer
- Data scientist
- Student
- Other (free text)

## Component Inventory

### Chat Components
| Component | Purpose |
|-----------|---------|
| `ChatWindow` | Main chat container with message list and input |
| `MessageBubble` | Single message (user or agent) |
| `StreamingIndicator` | Shows agent is generating a response |
| `ToolResultCard` | Renders agent tool results (design matrices, charts, analysis tables) |

### Chart Components (ECharts)
| Component | Purpose |
|-----------|---------|
| `BaseChart` | Wrapper around ECharts instance with resize handling |
| `ResponseSurface` | 3D surface plot (echarts-gl) |
| `ContourPlot` | 2D contour plot |
| `MainEffectsPlot` | Factor main effects |
| `InteractionPlot` | Two-factor interaction effects |
| `ParetoChart` | Ranked bar chart of effect magnitudes |
| `NormalProbabilityPlot` | Normal probability plot of effects |
| `ResidualPlot` | Residuals vs predicted, vs run order |

### Design Components
| Component | Purpose |
|-----------|---------|
| `DesignMatrix` | Display/edit the experimental design matrix |
| `FactorEditor` | Add/edit factors (name, levels, type) |
| `ResultsEntryForm` | Enter experimental results incrementally |

## SSE Streaming Protocol

The agent streams responses via Server-Sent Events.

### Flow
1. User sends message via `POST /api/v1/chat`
2. Server returns SSE stream
3. Frontend parses events and renders incrementally

### Event Types
```
event: token
data: {"text": "partial token text"}

event: tool_start
data: {"tool": "create_design", "input": {...}}

event: tool_result
data: {"tool": "create_design", "output": {...}}

event: done
data: {}

event: error
data: {"message": "error description"}
```

### Frontend Handling
- Accumulate `token` events into the current message bubble
- On `tool_start`, show a loading indicator with tool name
- On `tool_result`, render the appropriate `ToolResultCard`
- On `done`, finalize the message
- On `error`, show error state with retry option
- Reconnect on connection drop with exponential backoff

## State Management

Using Svelte 5 runes (not legacy stores):

### Auth State
```ts
// src/lib/state/auth.svelte.ts
let user = $state<User | null>(null);
let token = $state<string | null>(null);
```

### Chat State
```ts
// src/lib/state/chat.svelte.ts
let messages = $state<Message[]>([]);
let isStreaming = $state(false);
```

### Experiment State
```ts
// src/lib/state/experiment.svelte.ts
let currentExperiment = $state<Experiment | null>(null);
let designs = $state<Design[]>([]);
let results = $state<Result[]>([]);
```

## API Integration

- Base URL configured via Vite proxy (`/api` → `http://localhost:8000`) in development
- In production, nginx routes `/api` to the backend service
- All API calls use `fetch` with JSON content type
- Auth token sent via `Authorization: Bearer <token>` header
