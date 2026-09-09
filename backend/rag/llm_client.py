"""
LLM Client — provider-agnostic chat with automatic fallback.

Rate-limit strategy (free tiers are the binding constraint):
  1. Groq  — primary for NON-grounded text generation + structured extraction.
             Very high RPD on open models, and totally separate from Google's
             quota, so it takes load off Gemini entirely.
  2. Gemini (lite) — fallback when Groq is unavailable / rate-limited / errors.

Grounded features (About Company, Top Asked) do NOT use this module — they
need Gemini's Google Search grounding, which Groq does not offer.

Each provider has its own independent daily quota, so trying them in order
pools the limits instead of hammering a single 20-RPD model.
"""

import os
from typing import Optional, Any
from loguru import logger

from backend.config import settings


def _is_rate_limit(err: Exception) -> bool:
    """Heuristic: does this exception look like a quota / rate-limit error?"""
    msg = str(err).lower()
    return any(
        tok in msg
        for tok in ("429", "rate limit", "resource_exhausted", "quota", "too many requests")
    )


def _groq_model(structured_schema: Optional[type] = None, temperature: float = 0.2):
    """Build a ChatGroq model, or None if Groq isn't configured/installed."""
    if not settings.groq_api_key:
        return None
    try:
        from langchain_groq import ChatGroq
    except ImportError:
        logger.warning("langchain-groq not installed; skipping Groq provider.")
        return None

    os.environ.setdefault("GROQ_API_KEY", settings.groq_api_key)
    llm = ChatGroq(
        model=settings.groq_model,
        temperature=temperature,
        max_tokens=4096,
        max_retries=0,
    )
    if structured_schema is not None:
        return llm.with_structured_output(structured_schema)
    return llm


def _gemini_model(structured_schema: Optional[type] = None, temperature: float = 0.2):
    """Build a ChatGoogleGenerativeAI (lite) model as fallback."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    os.environ.setdefault("GOOGLE_API_KEY", settings.google_api_key)
    llm = ChatGoogleGenerativeAI(
        model=settings.llm_extraction_model,  # lite — 500 RPD, fast
        temperature=temperature,
        max_output_tokens=4096,
        max_retries=0,
        timeout=45,
    )
    if structured_schema is not None:
        return llm.with_structured_output(structured_schema)
    return llm


def chat_invoke(
    messages: Any,
    structured_schema: Optional[type] = None,
    temperature: float = 0.2,
) -> Any:
    """
    Invoke a chat model with Groq→Gemini fallback.

    Args:
        messages: a prompt string, or a list of LangChain message objects.
        structured_schema: optional Pydantic model for structured output.
        temperature: sampling temperature.

    Returns:
        The model response. If structured_schema is set, the parsed object;
        otherwise a LangChain AIMessage (use .content for text).

    Raises:
        The last provider's exception if every provider fails.
    """
    providers = [
        ("groq", lambda: _groq_model(structured_schema, temperature)),
        ("gemini-lite", lambda: _gemini_model(structured_schema, temperature)),
    ]

    last_err: Optional[Exception] = None
    for name, build in providers:
        model = build()
        if model is None:
            continue
        try:
            logger.info(f"LLM invoke via provider: {name} ({settings.groq_model if name == 'groq' else settings.llm_extraction_model})")
            return model.invoke(messages)
        except Exception as e:
            last_err = e
            if _is_rate_limit(e):
                logger.warning(f"Provider {name} rate-limited; falling back. ({e})")
            else:
                logger.warning(f"Provider {name} failed; falling back. ({e})")
            continue

    if last_err is not None:
        raise last_err
    raise RuntimeError("No LLM provider is configured. Set GROQ_API_KEY or GOOGLE_API_KEY.")
