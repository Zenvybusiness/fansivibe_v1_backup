# Fansivibe Backend AI Service

Runs Fansivibe's own AI assistant engine. The Flutter app never talks to an AI
provider directly — it calls this service, which returns **typed structured
replies** (`AssistantReply`).

## Why this design (runs on every phone)

Model inference happens **here, on the server**, never on the phone. The Flutter
client is a thin app that sends its on-device user model (wardrobe, face data,
saved looks) with each request and renders the typed reply. This is what lets
Fansivibe run on the lowest-spec phones.

## Start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then point the app at it: `http://<host>:8000` (client default
`http://localhost:8000` — override with `--dart-define=ASSISTANT_BASE_URL=...`).

## Our own AI

The brain is ours (`app/ai/engine.py`):

1. **Intent routing** — `app/ai/intent.py` classifies each message
   (outfit / hairstyle / grooming / wardrobe / navigate / greeting / …).
2. **Tools** — `app/ai/tools.py` builds typed suggestion cards grounded in the
   user's context.
3. **Dialogue policy** — ambiguous questions trigger a clarification flow
   (e.g. "what should I wear?" → occasion options).
4. **Navigation** — the assistant only *requests* a route; the client executes it.
5. **Structured output** — every reply is typed JSON (`AssistantReply`).

### Optional self-hosted model (Ollama)

The LLM only enriches the natural-language reply text; structure stays ours.
Start Ollama with a small model:

```bash
docker compose up -d    # starts Ollama with llama3.1:8b
```

Env vars:

| Var | Default |
|-----|---------|
| `FANSIVIBE_OLLAMA_HOST` | `http://localhost:11434` |
| `FANSIVIBE_OLLAMA_MODEL` | `llama3.1:8b` |
| `FANSIVIBE_DISABLE_LLM` | unset (set `1` to disable) |

Without Ollama the service degrades gracefully to the deterministic rules
engine — the API contract never changes.

## Endpoints

| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET | `/health` | — | `{"status": "ok"}` |
| POST | `/v1/assistant/chat` | `AssistantRequest` | `AssistantReply` |

## Tests

```bash
.venv/bin/python -m pytest -q
```
