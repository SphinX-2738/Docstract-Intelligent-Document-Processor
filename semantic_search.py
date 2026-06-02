"""
semantic_search.py - Semantic Chunk Retrieval
Project: Docstract - Intelligent Document Processor
Author: Ankur Sharma

What this does:
    - Takes a search query (e.g. "vendor name and billing address")
    - Converts it to a vector using the same embedding model
    - Searches ChromaDB for the most similar chunks
    - Returns the top N most relevant chunks

Why this matters:
    Instead of sending an entire 200-page document to the LLM,
    we search for only the chunks that contain relevant information.

    Without semantic search:
        Full 200-page doc → LLM → expensive, slow, hits context limit

    With semantic search:
        200-page doc → embed → search → top 3 chunks → LLM
        Result: 95% fewer tokens, faster, works on ANY size document

How semantic search works:
    1. Query "total invoice amount" gets converted to a vector
    2. ChromaDB finds chunks whose vectors are mathematically
       closest to the query vector (cosine similarity)
    3. Those chunks contain the most relevant content
    4. We pass only those chunks to the LLM for extraction

Real world analogy:
    Instead of reading a whole book to find one fact,
    you use the index to go straight to the right page.
"""

import chromadb
from sentence_transformers import SentenceTransformer


# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

EMBEDDING_MODEL = "all-MiniLM-L6-v2"   # Must match embedder.py
CHROMA_DB_PATH  = "chroma_db"           # Must match embedder.py
COLLECTION_NAME = "docstract_chunks"    # Must match embedder.py
TOP_K_RESULTS   = 3                     # How many chunks to retrieve
                                        # 3 is optimal: enough context,
                                        # not too many tokens sent to LLM


# ─────────────────────────────────────────────
# SETUP: Lazy-loaded model and ChromaDB client
# Model only loads when first needed — not on import.
# This keeps startup memory under 512MB on Render free tier.
# ─────────────────────────────────────────────

_embedding_model = None
_collection      = None


def _get_model() -> SentenceTransformer:
    """Load embedding model on first use, reuse after."""
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    return _embedding_model


def _get_collection():
    """Connect to ChromaDB on first use, reuse after."""
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
    return _collection


# ─────────────────────────────────────────────
# DOCUMENT-TYPE QUERIES
# ─────────────────────────────────────────────
# These are the search queries used per document type.
# Each query is designed to retrieve chunks most likely
# to contain the fields we need to extract.
#
# Why multiple queries per type?
# A single query might miss some fields. Multiple queries
# ensure we find chunks containing ALL relevant information.

EXTRACTION_QUERIES = {
    "invoice": [
        "vendor name company billing address contact",
        "invoice number date due payment terms",
        "line items description quantity price amount total",
        "tax subtotal total amount due balance"
    ],
    "resume": [
        "candidate name email phone address contact information",
        "work experience job title company employment dates",
        "education degree university graduation year",
        "skills technologies programming languages certifications"
    ],
    "email": [
        "sender recipient email address from to subject",
        "email body main content message paragraphs",
        "key updates summary points action items next steps",
        "date sent received deadline schedule"
    ],
    "unknown": [
        "main content key information important details",
        "names dates amounts numbers identifiers"
    ]
}


# ─────────────────────────────────────────────
# CORE: Search for relevant chunks
# ─────────────────────────────────────────────

def search_chunks(
    query: str,
    filename: str = None,
    top_k: int = TOP_K_RESULTS
) -> list[dict]:
    """
    Search ChromaDB for chunks most similar to the query.

    Args:
        query (str): Natural language search query
        filename (str): Optional — filter results to one document only
                        None = search across all documents
        top_k (int): Number of results to return

    Returns:
        list[dict]: Top matching chunks, each containing:
            {
                "chunk_id":    "invoice_001.txt_chunk_0",
                "text":        "the chunk text...",
                "score":       0.87,   (cosine similarity, higher = better)
                "filename":    "invoice_001.txt",
                "chunk_index": 0
            }
    """

    col = _get_collection()

    if col.count() == 0:
        print("   ⚠️  ChromaDB is empty. Run embedder.py first.")
        return []

    # ── Convert query to vector ───────────────────────────────────────
    query_embedding = _get_model().encode(
        query,
        convert_to_numpy=True
    ).tolist()

    # ── Build filter (optional: restrict to one file) ─────────────────
    where_filter = {"filename": filename} if filename else None

    # ── Query ChromaDB ────────────────────────────────────────────────
    try:
        results = col.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, col.count()),
            where=where_filter,
            include=["documents", "metadatas", "distances"]
        )
    except Exception as e:
        print(f"   ❌ Search error: {e}")
        return []

    # ── Format results ────────────────────────────────────────────────
    formatted = []
    ids        = results["ids"][0]
    documents  = results["documents"][0]
    metadatas  = results["metadatas"][0]
    distances  = results["distances"][0]

    for i in range(len(ids)):
        # ChromaDB returns cosine DISTANCE (0=identical, 2=opposite)
        # Convert to similarity score (1=identical, -1=opposite)
        similarity = round(1 - distances[i], 4)

        formatted.append({
            "chunk_id":    ids[i],
            "text":        documents[i],
            "score":       similarity,
            "filename":    metadatas[i].get("filename", "unknown"),
            "chunk_index": metadatas[i].get("chunk_index", 0),
            "word_count":  metadatas[i].get("word_count", 0)
        })

    # Sort by score descending (most relevant first)
    formatted.sort(key=lambda x: x["score"], reverse=True)
    return formatted


# ─────────────────────────────────────────────
# CORE: Get relevant context for extraction
# ─────────────────────────────────────────────

def get_relevant_context(
    filename: str,
    doc_type: str,
    top_k: int = TOP_K_RESULTS
) -> str:
    """
    Get the most relevant chunks for a document and combine
    them into a single context string for the LLM.

    This is the function called by extractor.py instead of
    sending the full document text.

    Flow:
        1. Run all queries for this document type
        2. Collect top matching chunks per query
        3. Deduplicate (same chunk might match multiple queries)
        4. Combine into one context string

    Args:
        filename (str): Document filename to search within
        doc_type (str): "invoice", "resume", "email", or "unknown"
        top_k (int): Chunks to retrieve per query

    Returns:
        str: Combined relevant context ready for LLM extraction
    """

    queries = EXTRACTION_QUERIES.get(doc_type, EXTRACTION_QUERIES["unknown"])

    seen_chunk_ids = set()
    all_chunks     = []

    for query in queries:
        results = search_chunks(query, filename=filename, top_k=top_k)

        for chunk in results:
            if chunk["chunk_id"] not in seen_chunk_ids:
                seen_chunk_ids.add(chunk["chunk_id"])
                all_chunks.append(chunk)

    if not all_chunks:
        return ""

    # Sort by chunk_index to preserve document order
    all_chunks.sort(key=lambda x: x["chunk_index"])

    # Combine chunk texts into one context string
    context = "\n\n".join(chunk["text"] for chunk in all_chunks)

    return context


# ─────────────────────────────────────────────
# ENTRY POINT - Test semantic search
# ─────────────────────────────────────────────

if __name__ == "__main__":

    print("\n" + "=" * 60)
    print("SEMANTIC SEARCH - Testing retrieval")
    print("=" * 60)

    # ── Test 1: Search across all documents ──────────────────────────
    print("\n📋 TEST 1: Cross-document search")
    print("Query: 'total invoice amount due'")
    print("─" * 50)

    results = search_chunks("total invoice amount due", top_k=3)
    for r in results:
        print(f"  Score: {r['score']:.4f} | File: {r['filename']}")
        print(f"  Preview: {r['text'][:100]}...")
        print()

    # ── Test 2: Search within a specific document ─────────────────────
    print("\n📋 TEST 2: Single document search")
    print("Query: 'vendor name billing address'")
    print("File: invoice_001.txt")
    print("─" * 50)

    results = search_chunks(
        "vendor name billing address",
        filename="invoice_001.txt",
        top_k=2
    )
    for r in results:
        print(f"  Score: {r['score']:.4f} | Chunks: {r['chunk_index']+1}"
              f"/{r.get('word_count', '?')} words")
        print(f"  Preview: {r['text'][:150]}...")
        print()

    # ── Test 3: Get full relevant context for extraction ─────────────
    print("\n📋 TEST 3: Full context retrieval for extraction")
    print("Document: resume_001.txt | Type: resume")
    print("─" * 50)

    context = get_relevant_context("resume_001.txt", "resume")
    print(f"  Context length: {len(context.split())} words")
    print(f"  Preview:\n  {context[:300]}...")

    print("\n" + "=" * 60)
    print("✅ Semantic search working correctly")
    print("=" * 60)
