"""
agent/memory.py
ChromaDB-backed long-term memory with:
  - HuggingFace local embeddings (no API cost)
  - App-layer Fernet encryption for stored document text
  - Two collections: personal_memory + session_context
  - Hybrid write-decision: heuristic first, Groq fallback
"""
import os
import re
import logging
import hashlib
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet
import chromadb
from chromadb.config import Settings

log = logging.getLogger(__name__)

DATA_DIR     = Path("data/chroma")
KEY_FILE     = Path("data/.memory_key")
PERSONAL_COL = "personal_memory"
SESSION_COL  = "session_context"

# Heuristic patterns that suggest a durable personal fact worth storing
_PERSONAL_FACT_RE = re.compile(
    r"\b(?:my name is|i(?:'m| am)|i live in|i work (?:at|for|as)|"
    r"i(?:'m| am) (?:a|an)|i (?:study|studied)|my (?:job|role|profession|hobby|favourite|favorite)|"
    r"i (?:like|love|hate|prefer|enjoy|use|own|have)|remember (?:that )?i|"
    r"i was born|my (?:age|birthday|location|city|country|language))\b",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────────────────────────────────────
# Encryption helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_or_create_key() -> bytes:
    """Load the Fernet key from disk, or generate and save a new one."""
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes()
    key = Fernet.generate_key()
    KEY_FILE.write_bytes(key)
    # Restrict file permissions on Windows as much as possible
    try:
        import stat
        KEY_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass
    log.info("Generated new memory encryption key at %s", KEY_FILE)
    return key


class _Crypto:
    def __init__(self):
        self._fernet = Fernet(_load_or_create_key())

    def encrypt(self, text: str) -> str:
        return self._fernet.encrypt(text.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Embeddings (lazy-loaded to avoid startup delay)
# ─────────────────────────────────────────────────────────────────────────────

_embeddings = None


def _get_embeddings():
    global _embeddings
    if _embeddings is None:
        from langchain_huggingface import HuggingFaceEmbeddings
        _embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        log.info("HuggingFace embeddings loaded")
    return _embeddings


# ─────────────────────────────────────────────────────────────────────────────
# Memory store
# ─────────────────────────────────────────────────────────────────────────────

class MemoryStore:
    """
    Manages two ChromaDB collections:
      - personal_memory: durable facts about the user
      - session_context: ephemeral content from the current session (page analysis, etc.)
    All stored document texts are Fernet-encrypted at rest.
    """

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._crypto   = _Crypto()
        self._client   = chromadb.PersistentClient(
            path=str(DATA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        self._personal = self._client.get_or_create_collection(
            PERSONAL_COL, metadata={"hnsw:space": "cosine"}
        )
        self._session  = self._client.get_or_create_collection(
            SESSION_COL, metadata={"hnsw:space": "cosine"}
        )
        log.info(
            "MemoryStore ready — personal: %d docs, session: %d docs",
            self._personal.count(),
            self._session.count(),
        )

    # ── Personal memory ────────────────────────────────────────────────────

    def add_personal_fact(self, text: str, metadata: dict | None = None) -> str:
        """Store a durable personal fact. Returns the generated document ID."""
        doc_id   = hashlib.sha256(text.encode()).hexdigest()[:16]
        enc_text = self._crypto.encrypt(text)
        emb      = _get_embeddings().embed_query(text)

        meta = metadata if (metadata and isinstance(metadata, dict) and len(metadata) > 0) else {"type": "fact"}
        self._personal.upsert(
            ids=[doc_id],
            embeddings=[emb],
            documents=[enc_text],
            metadatas=[meta],
        )
        log.debug("Stored personal fact (id=%s): %s…", doc_id, text[:60])
        return doc_id

    def retrieve_personal_context(self, query: str, n_results: int = 5) -> list[str]:
        """Retrieve the most relevant personal facts for a query."""
        count = self._personal.count()
        if count == 0:
            return []

        emb = _get_embeddings().embed_query(query)
        results = self._personal.query(
            query_embeddings=[emb],
            n_results=min(n_results, count),
        )

        docs: list[str] = []
        for enc_doc in (results.get("documents") or [[]])[0]:
            try:
                docs.append(self._crypto.decrypt(enc_doc))
            except Exception:
                log.warning("Failed to decrypt a memory document — skipping")
        return docs

    # ── Session context ────────────────────────────────────────────────────

    def add_session_content(self, text: str, source: str = "") -> str:
        """Store ephemeral session content (e.g. analysed page text)."""
        doc_id   = hashlib.sha256((text + source).encode()).hexdigest()[:16]
        enc_text = self._crypto.encrypt(text)
        emb      = _get_embeddings().embed_query(text)

        self._session.upsert(
            ids=[doc_id],
            embeddings=[emb],
            documents=[enc_text],
            metadatas=[{"source": source}],
        )
        return doc_id

    def retrieve_session_context(self, query: str, n_results: int = 3) -> list[str]:
        """Retrieve session context relevant to a query."""
        count = self._session.count()
        if count == 0:
            return []

        emb = _get_embeddings().embed_query(query)
        results = self._session.query(
            query_embeddings=[emb],
            n_results=min(n_results, count),
        )

        docs: list[str] = []
        for enc_doc in (results.get("documents") or [[]])[0]:
            try:
                docs.append(self._crypto.decrypt(enc_doc))
            except Exception:
                pass
        return docs

    def clear_session(self) -> None:
        """Clear all session context (call at app start or on demand)."""
        ids = self._session.get()["ids"]
        if ids:
            self._session.delete(ids=ids)
        log.info("Session context cleared")


# ─────────────────────────────────────────────────────────────────────────────
# Write-decision: hybrid heuristic + Groq
# ─────────────────────────────────────────────────────────────────────────────

def should_store_as_memory(user_msg: str, assistant_response: str) -> bool:
    """
    Hybrid decision: heuristic first, Groq only if ambiguous.
    Returns True if the exchange contains a durable personal fact.
    """
    # 1. Fast heuristic — ONLY check the user's message, not the assistant's response.
    #    This prevents "who is Modi" → assistant says "He is a..." from triggering
    #    storage of general knowledge as personal facts.
    if _PERSONAL_FACT_RE.search(user_msg):
        log.debug("Memory write: heuristic match → True")
        return True

    # 2. Heuristic says no — check with Groq only if the user message is substantive
    #    AND looks like it could contain personal information
    if len(user_msg.split()) < 4:
        return False

    # Skip general knowledge questions entirely — they never contain personal facts
    _SKIP_RE = re.compile(
        r"^\s*(?:who is|what is|how to|why|when|where|define|explain)\b",
        re.IGNORECASE,
    )
    if _SKIP_RE.match(user_msg):
        return False

    try:
        import yaml, pathlib, os
        from groq import Groq

        prompt_path = pathlib.Path("prompts/memory_write_decision.yaml")
        decision_prompt = (
            "Does the following exchange reveal a specific, durable personal fact about "
            "the user that is worth storing for future reference? "
            "Reply with exactly one word: YES or NO.\n\n"
            f"User: {user_msg}\nAssistant: {assistant_response}"
        )
        if prompt_path.exists():
            data = yaml.safe_load(prompt_path.read_text(encoding="utf-8"))
            template = data.get("decision_prompt", "")
            if template:
                decision_prompt = template.format(
                    user_msg=user_msg, assistant_response=assistant_response
                )

        from core.config import get_api_key
        client = Groq(api_key=get_api_key("GROQ"))
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": decision_prompt}],
            max_tokens=5,
            temperature=0.0,
        )
        answer = (resp.choices[0].message.content or "NO").strip().upper()
        result = answer.startswith("YES")
        log.debug("Memory write: Groq decision → %s", answer)
        return result

    except Exception as exc:
        log.warning("Memory write Groq check failed: %s", exc)
        return False


# Module-level singleton
_store: MemoryStore | None = None


def get_store() -> MemoryStore:
    global _store
    if _store is None:
        _store = MemoryStore()
    return _store
