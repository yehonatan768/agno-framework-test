from __future__ import annotations

from agno.models.ollama import Ollama


def build_model(*, provider: str, model_id: str) -> Ollama:
    """
    Ollama-only LLM factory.

    The entire project should import ONLY:
      from src.llm import build_model

    Supported:
      provider = "ollama"
      model_id = e.g. "llama3.1:8b"
    """
    p = (provider or "").strip().lower()
    if p not in {"ollama", ""}:
        raise ValueError(f"Ollama-only build. Unsupported provider: {p!r}")

    mid = (model_id or "llama3.1:8b").strip()

    return Ollama(
        id=mid,
        host="http://localhost:11434",
    )
