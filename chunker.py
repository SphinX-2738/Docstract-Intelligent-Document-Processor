"""
chunker.py - Document Chunker
Project: Docstract - Intelligent Document Processor
Author: Ankur Sharma

What this does:
    - Takes a raw document (any size) as input
    - Splits it into overlapping chunks of a fixed word count
    - Returns a list of chunk dicts ready for embedding

Why overlapping chunks?
    If we split without overlap, important context at chunk
    boundaries gets cut in half. For example:
    
    Chunk 1: "...total amount due is"
    Chunk 2: "$4,500 payable by March..."
    
    Without overlap, neither chunk has the full sentence.
    With overlap, both chunks contain the boundary context,
    so semantic search always finds complete information.

Why this matters for extraction:
    Instead of sending a 200-page document to the LLM
    (expensive, slow, hits context limits), we:
    1. Chunk the document here
    2. Embed all chunks (embedder.py)
    3. Find only relevant chunks (semantic_search.py)
    4. Send only those 3-4 chunks to the LLM
    Result: 95% fewer tokens, handles any document size
"""


# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

CHUNK_SIZE    = 200   # Words per chunk
              # Why 200? Large enough to contain complete thoughts,
              # small enough to be specific when searching.
              # 200 words ≈ 250-300 tokens ≈ fits easily in LLM context.

CHUNK_OVERLAP = 50    # Words of overlap between consecutive chunks
              # Why 50? ~25% overlap ensures boundary context
              # is always captured in at least one chunk.


# ─────────────────────────────────────────────
# CORE: Split document into overlapping chunks
# ─────────────────────────────────────────────

def chunk_document(raw_text: str, filename: str = "unknown") -> list[dict]:
    """
    Split a document into overlapping word-based chunks.

    Args:
        raw_text (str): The full document text
        filename (str): Source filename (stored in chunk metadata)

    Returns:
        list[dict]: List of chunk dicts, each containing:
            {
                "chunk_id":   "invoice_001_chunk_0",
                "text":       "the actual chunk text...",
                "word_count": 200,
                "chunk_index": 0,
                "total_chunks": 5,
                "filename":   "invoice_001.txt"
            }

    Example:
        doc = "word1 word2 ... word500"
        chunks = chunk_document(doc, "invoice_001.txt")
        # Returns ~3 chunks of 200 words with 50-word overlap
    """

    if not raw_text or not raw_text.strip():
        print(f"   ⚠️  Empty document: {filename}")
        return []

    # ── Split into words ──────────────────────────────────────────────
    words = raw_text.split()

    if len(words) == 0:
        return []

    # ── Handle short documents (smaller than one chunk) ───────────────
    # If the document is shorter than CHUNK_SIZE, return it as one chunk.
    # No point splitting a 1-page invoice into multiple chunks.
    if len(words) <= CHUNK_SIZE:
        chunk_text = " ".join(words)
        return [{
            "chunk_id":     f"{filename}_chunk_0",
            "text":         chunk_text,
            "word_count":   len(words),
            "chunk_index":  0,
            "total_chunks": 1,
            "filename":     filename
        }]

    # ── Build overlapping chunks ──────────────────────────────────────
    chunks     = []
    start      = 0
    chunk_index = 0
    step       = CHUNK_SIZE - CHUNK_OVERLAP   # How far to advance each time
                                               # 200 - 50 = 150 words per step

    while start < len(words):
        end        = min(start + CHUNK_SIZE, len(words))
        chunk_words = words[start:end]
        chunk_text  = " ".join(chunk_words)

        chunks.append({
            "chunk_id":    f"{filename}_chunk_{chunk_index}",
            "text":        chunk_text,
            "word_count":  len(chunk_words),
            "chunk_index": chunk_index,
            "filename":    filename
        })

        # Stop if we've reached the end
        if end == len(words):
            break

        start       += step
        chunk_index += 1

    # ── Add total_chunks to each chunk (needed for context display) ───
    total = len(chunks)
    for chunk in chunks:
        chunk["total_chunks"] = total

    return chunks


# ─────────────────────────────────────────────
# HELPER: Display chunk summary
# ─────────────────────────────────────────────

def display_chunks(chunks: list[dict]):
    """Print a readable summary of all chunks."""

    if not chunks:
        print("   No chunks to display.")
        return

    total_words = sum(c["word_count"] for c in chunks)
    print(f"\n   Total chunks   : {len(chunks)}")
    print(f"   Total words    : {total_words}")
    print(f"   Chunk size     : {CHUNK_SIZE} words")
    print(f"   Overlap        : {CHUNK_OVERLAP} words")
    print(f"\n   {'Chunk':<12} {'Words':<8} {'Preview'}")
    print(f"   {'─'*55}")

    for chunk in chunks:
        preview = chunk["text"][:60].replace("\n", " ")
        print(f"   {chunk['chunk_id']:<12} "
              f"{chunk['word_count']:<8} "
              f"{preview}...")


# ─────────────────────────────────────────────
# ENTRY POINT - Test the chunker
# ─────────────────────────────────────────────

if __name__ == "__main__":

    print("=" * 60)
    print("Testing chunker on all sample documents")
    print("=" * 60)

    import os

    sample_dirs = [
        "sample_documents/invoices",
        "sample_documents/resumes",
        "sample_documents/emails"
    ]

    for directory in sample_dirs:
        if not os.path.exists(directory):
            print(f"\n⚠️  Directory not found: {directory}")
            continue

        doc_type = directory.split("/")[-1].upper()
        print(f"\n{'─'*60}")
        print(f"📁 {doc_type}")
        print(f"{'─'*60}")

        for filename in sorted(os.listdir(directory)):
            if not filename.endswith(".txt"):
                continue

            filepath = os.path.join(directory, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                raw_text = f.read()

            print(f"\n📄 {filename} ({len(raw_text.split())} words total)")
            chunks = chunk_document(raw_text, filename)
            display_chunks(chunks)

    print("\n" + "=" * 60)
    print("✅ Chunker test complete")
    print("=" * 60)