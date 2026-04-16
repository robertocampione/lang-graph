import os
from dotenv import load_dotenv
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.documents import Document

load_dotenv()

# We set it to None initially.
vector_store = None

# Simulate realistic enterprise environments (e.g. Proximus Telecom)
proximus_policies = [
    Document(
        page_content="Proximus Fiber delay policy: if installation is delayed by more than 3 days, ticket must be escalated (ESCALE) to Tier 2 Fiber Ops.",
        metadata={"subject": "Fiber installation"}
    ),
    Document(
        page_content="Proximus Mobile subscription delay: up to 7 days is considered standard porting time. We can ALLOW_FOLLOW_ON with a temporary data booster.",
        metadata={"subject": "Mobile subscription"}
    ),
    Document(
        page_content="Proximus Enterprise Platinum SLA: 0 days delay tolerance for dedicated leased lines. Immediately HOLD_CASE and page the standby engineer.",
        metadata={"subject": "Enterprise SLA"}
    ),
    Document(
        page_content="General Billing issues: If the user complains about invoice delays, REQUEST_INFO to get the invoice number.",
        metadata={"subject": "Billing"}
    )
]

def _get_vector_store():
    global vector_store
    if vector_store is None:
        # Initialize the real embedding model (requires GOOGLE_API_KEY)
        embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
        vector_store = InMemoryVectorStore(embeddings)
        vector_store.add_documents(proximus_policies)
    return vector_store

def retrieve_policy_for_tier(query: str, k: int = 2) -> dict:
    """
    RAG retriever: performs genuine semantic search using text-embedding-004
    over the Proximus corporate documents.
    """
    vstore = _get_vector_store()
    results = vstore.similarity_search(query, k=k)
    
    combined_docs = "\n\n".join([f"[{doc.metadata.get('subject', 'Unknown')}]\n{doc.page_content}" for doc in results])
    
    return {
        "query_used": query,
        "policy_text": combined_docs,
        "action_guidance": "Follow the matching Proximus SLAs carefully. Always pick the most restrictive matching rule."
    }
