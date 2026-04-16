from langchain_google_genai import ChatGoogleGenerativeAI
from app.config.settings import settings


def get_llm(
    model_name: str,
    *,
    temperature: float = 0.0,
    timeout_seconds: int | None = None,
) -> ChatGoogleGenerativeAI:
    """Create a Google GenAI chat model with deterministic defaults."""
    return ChatGoogleGenerativeAI(
        model=model_name,
        temperature=temperature,
        request_timeout=timeout_seconds,
    )


def get_triage_llm() -> ChatGoogleGenerativeAI:
    """LLM role used only for structured ticket extraction."""
    return get_llm(
        settings.TRIAGE_MODEL,
        temperature=settings.TRIAGE_TEMPERATURE,
        timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
    )


def get_reasoning_llm() -> ChatGoogleGenerativeAI:
    """Optional explainer role. It must not own final business decisions."""
    return get_llm(
        settings.REASONING_MODEL,
        temperature=0.0,
        timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
    )


def get_utility_llm() -> ChatGoogleGenerativeAI:
    """Low-cost utility role for future summarization or formatting tasks."""
    return get_llm(
        settings.UTILITY_MODEL,
        temperature=0.0,
        timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
    )


class LazyTriageLLM:
    """Backward-compatible lazy adapter for tests and existing imports."""

    def with_structured_output(self, schema):
        return get_triage_llm().with_structured_output(schema)


default_llm = LazyTriageLLM()
