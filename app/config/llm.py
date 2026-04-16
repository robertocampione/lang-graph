from langchain_google_genai import ChatGoogleGenerativeAI
from app.config.settings import settings

# Inizializziamo il ChatModel. Di default usiamo gemini-2.5-flash per velocità in dev
# La chiave GOOGLE_API_KEY deve essere caricata nel .env (già gestito da settings.py via load_dotenv)
def get_llm(model_name: str = "gemini-2.5-flash") -> ChatGoogleGenerativeAI:
    """
    Restituisce un'istanza del modello LangChain configurato per l'LLM scelto.
    """
    return ChatGoogleGenerativeAI(model=model_name, temperature=0)

# Un'istanza di default pronta all'uso nei nodi.
default_llm = get_llm()
