# ADR-007: Client-side Model Selection (per-request) instead of Server Env Var

## Status
**Superseded by [ADR-010](010-hardcode-model-no-picker.md)** — the model picker proved unnecessary in practice. The model is now a hardcoded env var in the backend; the extension does not send a `model` field and the `ExplainRequest` schema no longer accepts one.

## Context

Originally the LLM model was a server-side env var (`OPENROUTER_MODEL`). Changing the model required editing `.env` and restarting the API container.

Free OpenRouter models go in and out of upstream rate-limits throughout the day (provider quotas exhaust). The user wants to switch models instantly when one becomes unavailable, without container restarts.

Two ways to expose model selection:
1. Add `model` as a query/body parameter to `/api/explain` and let the client send it per-request.
2. Keep a server-side variable but expose `PATCH /api/config` to change it without restart.

Option 1 makes the model a property of the request (different selections can use different models — useful for "expensive model just for this hard word"). Option 2 keeps the model global; switching is still an extra round-trip.

## Decision

Accept the model as an **optional per-request field** in `POST /api/explain`:

```json
{ "text": "...", "model": "z-ai/glm-4.5-air:free", "source_url": "..." }
```

The backend's behavior:
- If `model` is provided in the request, use it.
- If omitted, fall back to `settings.openrouter_model` (env var), defaulting to `z-ai/glm-4.5-air:free`.

The extension's Options page persists `selectedModel` to `chrome.storage.local`. The service worker reads it on every EXPLAIN and includes it in the request body.

## Consequences

**Positive:**
- Switching models is one dropdown click in the Options page — no restart, no `.env` edit.
- The env var becomes the **fallback**, useful for `curl` testing or if the extension's storage is cleared.
- Each `Word` row can record `model_source` (the model that actually produced this explanation) so the user can later see which model gave which answer.
- Cache key includes the model — switching models is a separate cache namespace automatically.

**Negative / trade-offs:**
- Wider API surface; `ExplainRequest` has one more optional field.
- Need to validate the requested model against the local `openrouter_models` table? Decision: **no** — pass it through. If the model is invalid, OpenRouter will reject the call and the user sees the error. Validation is the wrong layer here.

**Risks:**
- **A user types a non-existent model id** — caller sees a 502 from OpenRouter. Acceptable; documented.
- **The extension forgets to send `model`** — the env-var fallback ensures the API still works. Backward-compatible.

## Notes

The Options page's model dropdown is populated by `GET /api/models` (which reads from the locally-synced `openrouter_models` table). See [ADR 006](006-models-sync-job.md). Selected model is stored as `selectedModel` in `chrome.storage.local`; storage shape is:

```ts
{ backendUrl: string, selectedModel?: string }
```
