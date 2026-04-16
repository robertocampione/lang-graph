import logging
from app.db.connection import execute_query

logger = logging.getLogger(__name__)

def write_audit_event(node_name: str, summary: str, actor_type: str = "SYSTEM"):
    """
    Safely logs an audit event to the PostgreSQL database.
    Catches exceptions to prevent breaking the orchestrator flow if the DB is unavaliable.
    """
    try:
        query = """
            INSERT INTO audit_events (node_name, summary, actor_type)
            VALUES (%s, %s, %s)
        """
        execute_query(query, (node_name, summary, actor_type))
    except Exception as e:
        logger.error(f"Audit log failed for {node_name}: {e}")
