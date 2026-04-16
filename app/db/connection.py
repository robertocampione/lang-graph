import psycopg
from psycopg.rows import dict_row
from app.config.settings import settings
import logging

logger = logging.getLogger(__name__)

def get_connection():
    """
    Returns a new PostgreSQL connection based on the POSTGRES_URL environment variable.
    Configured to return rows as dictionaries.
    """
    try:
        conn = psycopg.connect(settings.POSTGRES_URL, row_factory=dict_row)
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise

def fetch_one(query: str, params: tuple = ()) -> dict | None:
    """Execute a query and fetch a single dictionary row."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()

def fetch_all(query: str, params: tuple = ()) -> list[dict]:
    """Execute a query and fetch all rows as a list of dictionaries."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()

def execute_query(query: str, params: tuple = ()) -> None:
    """Execute a DML query and commit the transaction."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
        conn.commit()
