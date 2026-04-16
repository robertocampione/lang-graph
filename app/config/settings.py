import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _embedding_model() -> str:
    model = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001").strip()
    if model == "models/gemini-embedding-001":
        return "gemini-embedding-001"
    return model


class Settings:
    """Project-wide settings and configuration."""
    LANGCHAIN_TRACING_V2 = _env_bool("LANGCHAIN_TRACING_V2", False)
    LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT", "pending-orders-langgraph")

    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    TRIAGE_MODEL = os.getenv("TRIAGE_MODEL", "gemini-2.5-flash")
    REASONING_MODEL = os.getenv("REASONING_MODEL", "gemini-2.5-flash")
    UTILITY_MODEL = os.getenv("UTILITY_MODEL", "gemini-2.5-flash")
    EMBEDDING_MODEL = _embedding_model()
    TRIAGE_TEMPERATURE = _env_float("TRIAGE_TEMPERATURE", 0.0)
    LLM_TIMEOUT_SECONDS = _env_int("LLM_TIMEOUT_SECONDS", 30)
    ENABLE_LLM_TRACE = _env_bool("ENABLE_LLM_TRACE", True)
    ENABLE_AUTO_EXECUTE = _env_bool("ENABLE_AUTO_EXECUTE", True)
    AUTO_EXECUTE_MIN_CONFIDENCE = _env_float("AUTO_EXECUTE_MIN_CONFIDENCE", 0.95)

    POSTGRES_URL = os.getenv("POSTGRES_URL", "postgresql://postgres:postgres@localhost:5433/langgraph")
    if not POSTGRES_URL:
        raise ValueError("POSTGRES_URL environment variable is not set")

settings = Settings()
