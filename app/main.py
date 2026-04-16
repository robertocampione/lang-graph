"""
Pending Orders LangGraph — Application Entrypoint

This is the main module exported for LangGraph Studio (via langgraph.json).
It delegates graph construction to the graphs module.
"""

# Import configuration to ensure env vars are loaded early
from app.config.settings import settings

from app.graphs.pending_orders import build_pending_orders_graph

# The compiled graph instance required by LangGraph Studio
graph = build_pending_orders_graph()

if __name__ == "__main__":
    # A simple smoke test to verify it compiles when run manually
    print("Graph nodes:", list(graph.nodes.keys()))
    print("Graph compiled successfully!")
