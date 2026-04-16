# Phase 2: LLM Integration & Memory Persistence

Questo documento riepiloga le evoluzioni architetturali apportate al progetto `pending-orders-langgraph` durante la Fase 2.

## Obiettivi Raggiunti

1. **Gestione Tipizzata dello Stato (Pydantic)**
Abbiamo aggiornato `app/state/schema.py` in modo da utilizzare `pydantic.BaseModel` (es. `TicketStructured`, `CustomerContext`, `Recommendation`) al posto di semplici dizionari nativi. Questo garantisce validazione in input, strutture standardizzate a runtime e compatibilità totale con l'estrazione dati guidata dai LLM.

2. **Integrazione LLM (ChatGoogleGenerativeAI)**
   - È stato creato il modulo `app/config/llm.py` per esporre un'istanza `default_llm` pronta all'uso.
   - Tutti i riferimenti a Google GenAI (sotto `langchain-google-genai`) attingono alla variabile d'ambiente `GOOGLE_API_KEY`.
   - Il modello prediletto per lo sviluppo rapido è `gemini-2.5-flash`.

3. **Nodi Intelligenti (Structured Output)**
   - **Triage** (`app/nodes/triage.py`): Non usa più le espressioni regolari. Analizza il ticket tramite LangChain Prompt Template per estrarre il subset desiderato, instanziando in modo rigoroso l'oggetto `TicketStructured`.
   - **Recommendation** (`app/nodes/recommendation.py`): Da regole hardcoded "if-else" si è passati a prompt direzionali (agente esperto customer service). Il LLM processa i dati e formula un action decision in un oggetto `Recommendation`.

4. **Persistenza (MemorySaver)**
   Nel builder (`app/graphs/pending_orders.py`) è stato instanziato un `MemorySaver` dalla libreria checkpoint. Questo abilita la "memoria" degli stati, feature vitale per operare con loop human-in-the-loop o semplicemente per analizzare i super-passaggi in iterazioni multiple su LangGraph Studio.

5. **Test & Infrastructure**
   - Inserito un primissimo test unitario `test_nodes.py` eseguibile tramite `pytest` per far scattare un sanity check della sintassi sul DAG di LangGraph in CI/CD pipeline.
   - Installata la dipendenza e aggiornato il relativo `requirements.txt`.

## Next Steps Operativi

Affinché la versione 2 sia eseguibile:
- Riavvia il server di LangGraph, avendo cura che `GOOGLE_API_KEY` sia presente nel file `.env`.
- Entra nello Studio e avvia un task immettendo un raw ticket text (es. `"Il cliente C-1002 si lamenta di un ordine non arrivato."`) godendoti l'analisi prodotta in automatico dall'intelligenza artificiale per triage e raccomandazioni.
