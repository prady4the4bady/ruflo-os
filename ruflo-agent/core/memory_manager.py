import os
import time
from collections import deque
from typing import List, Dict, Optional
import structlog
import chromadb
from chromadb.config import Settings

logger = structlog.get_logger(__name__)

class MemoryManager:
    """ChromaDB-backed agent memory with short-term, long-term, episodic, semantic."""

    def __init__(self, db_path: str = "/var/ruflo/memory", max_short_term: int = 20):
        self.max_short_term = max_short_term
        self.short_term = deque(maxlen=max_short_term)  # Last N actions
        self.episodic = []  # Past task summaries
        self.semantic = []  # Learned facts

        # ChromaDB for long-term vector store
        self.db_path = db_path
        os.makedirs(db_path, exist_ok=True)
        try:
            self.client = chromadb.PersistentClient(path=db_path)
            self.collection = self.client.get_or_create_collection("ruflo_memory")
            logger.info("ChromaDB initialized", path=db_path)
        except Exception as e:
            logger.error("Failed to initialize ChromaDB", error=str(e))
            self.collection = None

    def store_observation(self, text: str, metadata: Optional[Dict] = None) -> None:
        """Store observation in short-term and long-term memory."""
        obs = {
            "text": text,
            "timestamp": time.time(),
            "metadata": metadata or {}
        }
        self.short_term.append(obs)

        if self.collection:
            try:
                self.collection.add(
                    documents=[text],
                    metadatas=[metadata or {}],
                    ids=[f"obs_{int(time.time() * 1000)}"]
                )
            except Exception as e:
                logger.error("Failed to store in ChromaDB", error=str(e))

    def query_relevant(self, task: str, k: int = 5) -> List[str]:
        """Query relevant memories for current task."""
        if not self.collection:
            return [m["text"] for m in self.short_term][-k:]

        try:
            results = self.collection.query(
                query_texts=[task],
                n_results=k
            )
            return results.get("documents", [[]])[0]
        except Exception as e:
            logger.error("Memory query failed", error=str(e))
            return []

    def add_episodic(self, task_summary: str, success: bool) -> None:
        """Add task summary to episodic memory."""
        self.episodic.append({
            "summary": task_summary,
            "success": success,
            "timestamp": time.time()
        })

    def add_semantic(self, fact: str) -> None:
        """Add learned fact to semantic memory."""
        if fact not in self.semantic:
            self.semantic.append(fact)

    def summarize_and_compress(self) -> None:
        """Compress old memories periodically."""
        if len(self.episodic) > 100:
            # Summarize old episodic memories (placeholder)
            self.episodic = self.episodic[-50:]
            logger.info("Episodic memory compressed")

        if self.collection:
            # ChromaDB handles compression internally
            pass

    def get_short_term(self) -> list:
        return list(self.short_term)

    def get_stats(self) -> dict:
        return {
            "short_term_count": len(self.short_term),
            "episodic_count": len(self.episodic),
            "semantic_count": len(self.semantic),
            "long_term_count": self.collection.count() if self.collection else 0
        }