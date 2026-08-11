"""Fansivibe backend AI service.

Runs the "own AI" assistant engine. The Flutter app never talks to an AI
provider directly — it calls this service, which returns typed structured
replies. See `backend/README.md`.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.ai import engine
from app.api import errors
from app.api.routers import analysis, looks, users
from app.models.schemas import AssistantReply, AssistantRequest

app = FastAPI(title="Fansivibe AI", version="0.1.0")

errors.register_error_handlers(app)
app.include_router(analysis.router)
app.include_router(looks.router)
app.include_router(users.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/v1/assistant/chat", response_model=AssistantReply)
def assistant_chat(request: AssistantRequest) -> AssistantReply:
    return engine.handle(request)
