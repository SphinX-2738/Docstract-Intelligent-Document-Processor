"""
embedder.py - Chunk Embedder & ChromaDB Store
Project: Docstract - Intelligent Document Processor
Author: Ankur Sharma

What this does:
    - Takes chunks from chunker.py as input
    - Converts each chunk into a vector (embedding) using
      a free local sentence-transformers model
    - Stores vectors + original text in ChromaDB
    - ChromaDB enables fast semantic similarity search later

What is an embedding?
    An embedding converts text into a list of ~384 numbers
    that represent the MEANING of the text.

    "Invoice total amount due" → [0.23, -0.11, 0.87, ...]
    "Payment owed to vendor"  → [0.21, -0.09, 0.85, ...]

    These two sentences mean similar things, so their vectors
    are mathematically close. ChromaDB uses this to find
    relevant chunks when we search for a query like
    "what is the total amount on this invoice?"

Why local embeddings (not OpenAI)?
    - sentence-transformers runs 100% on your machine
    - Zero API calls, zero cost, works offline
    - The model (all-MiniLM-L6-v2) is small (80MB) but
      powerful enough for document extraction tasks
    - In production you could swap to OpenAI embeddings
      with one line change if you needed higher accuracy
"""

import os
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from chunker import chunk_document


# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
# Why this model?
# - Only 80MB, runs fast on CPU
# - 384-dimensional embeddings (good quality/speed balance)
# - Top performer on semantic similarity benchmarks
# - Used in production by many companies for exactly this use case

CHROMA_DB_PATH  = "chroma_db"
# Local folder where ChromaDB stores its data.
# Gets created automatically on first run.
# On deployment: this folder lives on the server's disk.

COLLECTION_NAME = "docstract_chunks"
# All chunks from all documents go into one ChromaDB collection.
# We filter by filename metadata when searching.


# ─────────────────────────────────────────────
# SETUP: Lazy-loaded model and ChromaDB client
# Model only loads when first needed — not on import.
# This keeps startup memory under 512MB on Render free tier.
# ─────────────────────────────────────────────

_embedding_model = None
_chroma_client   = None
_collection      = None


def _get_model() -> SentenceTransformer:
    """Load embedding model on first use, reuse after."""
    global _embedding_model
    if _embedding_model is None:
        print("Loading embedding model (first use)...")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        print(f"✅ Model loaded: {EMBEDDING_MODEL}")
    return _embedding_model


def _get_collection():
    """Connect to ChromaDB on first use, reuse after."""
    global _chroma_client, _collection
    if _collection is None:
        _chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        _collection = _chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
            # cosine similarity: measures angle between vectors
            # better than euclidean distance for text similarity
        )
        print(f"✅ ChromaDB collection ready: {COLLECTION_NAME}")
    return _collection


# ─────────────────────────────────────────────
# CORE: Embed and store chunks for one document
# ─────────────────────────────────────────────

def embed_document(raw_text: str, filename: str) -> dict:
    """
    Chunk a document, embed all chunks, store in ChromaDB.

    Flow:
        1. Chunk the document (chunker.py)
        2. Delete any existing chunks for this filename
           (prevents duplicates on re-run)
        3. Embed all chunk texts in one batch call
        4. Store embeddings + text + metadata in ChromaDB

    Args:
        raw_text (str): Full document text
        filename (str): Document filename (used as metadata filter key)

    Returns:
        dict: Summary of what was embedded
              {
                  "filename":     "invoice_001.txt",
                  "chunks_count": 3,
                  "status":       "success"
              }
    """

    print(f"\n{'─'*50}")
    print(f"📄 Embedding: {filename}")

    # ── Step 1: Chunk the document ────────────────────────────────────
    chunks = chunk_document(raw_text, filename)

    if not chunks:
        print(f"   ❌ No chunks generated")
        return {"filename": filename, "chunks_count": 0, "status": "failed"}

    print(f"   Chunks generated: {len(chunks)}")

    col = _get_collection()

    # ── Step 2: Delete old entries for this file (clean re-run) ───────
    try:
        existing = col.get(where={"filename": filename})
        if existing["ids"]:
            col.delete(where={"filename": filename})
            print(f"   Deleted {len(existing['ids'])} old chunk(s)")
    except Exception:
        pass   # No existing entries — that's fine

    # ── Step 3: Embed all chunks in one batch ─────────────────────────
    # Batch embedding is much faster than embedding one at a time
    texts = [chunk["text"] for chunk in chunks]

    print(f"   Generating embeddings...")
    embeddings = _get_model().encode(
        texts,
        show_progress_bar=False,
        convert_to_numpy=True
    )
    print(f"   ✅ Embeddings generated: {len(embeddings)} vectors "
          f"(each {len(embeddings[0])} dimensions)")

    # ── Step 4: Store in ChromaDB ─────────────────────────────────────
    col.add(
        ids        = [chunk["chunk_id"] for chunk in chunks],
        embeddings = embeddings.tolist(),
        documents  = texts,
        metadatas  = [
            {
                "filename":     chunk["filename"],
                "chunk_index":  chunk["chunk_index"],
                "total_chunks": chunk["total_chunks"],
                "word_count":   chunk["word_count"]
            }
            for chunk in chunks
        ]
    )

    print(f"   ✅ Stored in ChromaDB")
    print(f"   Total docs in DB now: {col.count()}")

    return {
        "filename":     filename,
        "chunks_count": len(chunks),
        "status":       "success"
    }


# ─────────────────────────────────────────────
# CORE: Embed all sample documents
# ─────────────────────────────────────────────

def embed_all_documents(sample_docs_dir: str = "sample_documents") -> list[dict]:
    """
    Embed every document in the sample_documents folder.

    Args:
        sample_docs_dir (str): Root folder containing doc type subfolders

    Returns:
        list[dict]: Summary of all embedding results
    """
    results = []
    doc_types = ["invoices", "resumes", "emails"]

    for doc_type in doc_types:
        folder = os.path.join(sample_docs_dir, doc_type)

        if not os.path.exists(folder):
            print(f"\n⚠️  Folder not found: {folder}")
            continue

        txt_files = sorted([f for f in os.listdir(folder) if f.endswith(".txt")])

        if not txt_files:
            continue

        print(f"\n{'='*50}")
        print(f"📁 {doc_type.upper()} ({len(txt_files)} files)")

        for filename in txt_files:
            filepath = os.path.join(folder, filename)

            with open(filepath, "r", encoding="utf-8") as f:
                raw_text = f.read()

            result = embed_document(raw_text, filename)
            results.append(result)

    return results


# ─────────────────────────────────────────────
# ENTRY POINT - Embed all documents
# ─────────────────────────────────────────────

if __name__ == "__main__":

    print("=" * 60)
    print("EMBEDDER - Building ChromaDB Vector Store")
    print("=" * 60)

    results = embed_all_documents()

    # ── Summary ───────────────────────────────────────────────────────
    successful = sum(1 for r in results if r["status"] == "success")
    total_chunks = sum(r["chunks_count"] for r in results)

    print("\n" + "=" * 60)
    print("📊 EMBEDDING SUMMARY")
    print("=" * 60)
    print(f"Documents embedded : {successful}/{len(results)}")
    print(f"Total chunks stored: {total_chunks}")
    print(f"ChromaDB location  : {CHROMA_DB_PATH}/")
    print(f"Collection name    : {COLLECTION_NAME}")
    print(f"Total in DB        : {_get_collection().count()}")
    print("=" * 60)
    print("\n✅ Vector store ready. Run semantic_search.py next.")
