import logging
import chromadb
from typing import List, Dict
import config

logger = logging.getLogger(__name__)

class Memory:
    def __init__(self):
        self.client = None
        self.collection = None

    def load(self):
        try:
            # We persist data to the CHROMA_DB_PATH
            # config.CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True) is handled by chromadb
            self.client = chromadb.PersistentClient(path=str(config.CHROMA_DB_PATH))
            self.collection = self.client.get_or_create_collection(name="jarvis_memory")
            logger.info("ChromaDB Memory loaded ✓")
        except Exception as e:
            logger.error(f"Failed to load ChromaDB: {e}")
            self.client = None

    def add_turn(self, user_text: str, jarvis_response: str):
        if not self.collection:
            return
        
        # Combine user and jarvis response into a single document representing the turn
        document = f"User: {user_text}\nJARVIS: {jarvis_response}"
        # Use a timestamp as an ID
        import time
        doc_id = str(time.time())
        
        try:
            self.collection.add(
                documents=[document],
                metadatas=[{"role": "conversation_turn"}],
                ids=[doc_id]
            )
            logger.debug("Added turn to memory.")
        except Exception as e:
            logger.error(f"Failed to add turn to memory: {e}")

    def get_relevant_context(self, query: str, n_results: int = 3) -> str:
        if not self.collection or self.collection.count() == 0:
            return ""
        
        try:
            # Prevent requesting more results than we have
            results_to_fetch = min(n_results, self.collection.count())
            if results_to_fetch == 0:
                return ""
            
            results = self.collection.query(
                query_texts=[query],
                n_results=results_to_fetch
            )
            
            documents = results.get("documents", [[]])[0]
            if not documents:
                return ""
                
            context = "Previous Conversation Context:\n"
            for doc in documents:
                context += f"- {doc}\n"
            return context
        except Exception as e:
            logger.error(f"Failed to retrieve context: {e}")
            return ""
