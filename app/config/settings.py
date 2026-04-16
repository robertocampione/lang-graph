import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings:
    """Project-wide settings and configuration."""
    LANGCHAIN_TRACING_V2 = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT", "pending-orders-langgraph")

    POSTGRES_URL = os.getenv("POSTGRES_URL", "postgresql://postgres:postgres@localhost:5433/langgraph")
    if not POSTGRES_URL:
        raise ValueError("POSTGRES_URL environment variable is not set")

settings = Settings()
