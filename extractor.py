"""
extractor.py - Core Extraction Engine (Enhanced with Semantic Search)
Project: Docstract - Intelligent Document Processor
Author: Ankur Sharma

What this does:
    - Takes raw unstructured text as input
    - Takes a Pydantic schema as input
    - If document is large: uses ChromaDB semantic search first
    - If document is small: sends directly to LLM (faster, no memory cost)
    - Returns (validated Pydantic object, token_usage dict) tuple
    - Token usage enables real cost tracking in batch_processor.py
"""

import os
import json
import re
from groq import Groq
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError
from typing import Type

load_dotenv()


# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

client      = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL       = "qwen/qwen3.6-27b"
TEMPERATURE = 0
MAX_TOKENS  = 1000

# If document exceeds this word count, use semantic search.
# 1000 words ≈ 6000 characters — handles invoices, resumes,
# and emails in full without loading the embedding model.
# Semantic search only kicks in for genuinely large documents.
SEMANTIC_SEARCH_THRESHOLD = 2000


# ─────────────────────────────────────────────
# HELPER: Strip backticks from LLM response
# ─────────────────────────────────────────────

def extract_json(text: str) -> dict | None:
    """Strip markdown fences and parse JSON."""
    cleaned = re.sub(r"```(?:json)?\n?", "", text)
    cleaned = cleaned.replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


# ─────────────────────────────────────────────
# HELPER: Get semantic search queries per schema
# ─────────────────────────────────────────────

def get_search_queries(schema: Type[BaseModel]) -> list[str]:
    """
    Return relevant search queries for each schema type.
    These queries find the most relevant chunks for extraction.
    """
    schema_name = schema.__name__.lower()

    if "invoice" in schema_name:
        return [
            "vendor company name billing address",
            "invoice number date due date",
            "line items services description amount",
            "subtotal total GST tax amount",
            "GSTIN phone email contact"
        ]
    elif "resume" in schema_name:
        return [
            "candidate name email phone contact",
            "work experience company role duration",
            "education degree university qualification",
            "technical skills programming languages",
            "projects achievements certifications"
        ]
    elif "email" in schema_name:
        return [
            "sender receiver email address",
            "subject date email content body",
            "action items tasks deadlines",
            "key points summary updates"
        ]
    else:
        return ["main content key information"]


# ─────────────────────────────────────────────
# CORE: Extract with semantic search
# ─────────────────────────────────────────────

def extract_with_semantic_search(
    raw_text: str,
    schema: Type[BaseModel],
    doc_id: str = "document"
) -> str:
    """
    Use ChromaDB semantic search to find relevant chunks,
    then combine them into a focused context for the LLM.
    Only called for documents over SEMANTIC_SEARCH_THRESHOLD words.
    """
    from chunker import chunk_document
    from embedder import embed_document
    from semantic_search import search_chunks

    print(f"   Chunking document...")
    chunks = chunk_document(raw_text, doc_id)
    print(f"   Found {len(chunks)} chunk(s)")

    print(f"   Embedding chunks...")
    embed_document(raw_text, doc_id)

    queries = get_search_queries(schema)

    all_relevant_text = set()
    for query in queries:
        results = search_chunks(query, filename=doc_id, top_k=2)
        for result in results:
            all_relevant_text.add(result["text"])

    focused_context     = "\n\n---\n\n".join(all_relevant_text)
    word_count_original = len(raw_text.split())
    word_count_focused  = len(focused_context.split())

    print(f"   Reduced: {word_count_original} words to {word_count_focused} words")
    reduction = round((1 - word_count_focused / max(word_count_original, 1)) * 100)
    print(f"   Token reduction: ~{reduction}%")

    return focused_context


# ─────────────────────────────────────────────
# CORE: Main extraction function
# ─────────────────────────────────────────────

def extract(
    raw_text: str,
    schema: Type[BaseModel],
    doc_id: str = "document",
    use_semantic_search: bool = None
) -> tuple:
    """
    Extract structured data from unstructured text using LLM.

    Automatically decides whether to use semantic search based
    on document length (threshold: 1000 words / ~6000 chars).

    Documents under 1000 words go straight to Groq — no embeddings
    loaded, no ChromaDB, minimal memory usage.

    Returns:
        tuple: (validated Pydantic object or None, token_usage dict)
               token_usage = {
                   "prompt_tokens":     int,
                   "completion_tokens": int,
                   "total_tokens":      int
               }
    """

    # Default token usage returned on failure
    empty_tokens = {
        "prompt_tokens":     0,
        "completion_tokens": 0,
        "total_tokens":      0
    }

    # ── Auto-detect whether to use semantic search ────────────────────
    word_count = len(raw_text.split())

    if use_semantic_search is None:
        use_semantic_search = word_count > SEMANTIC_SEARCH_THRESHOLD

    if use_semantic_search:
        print(f"   Document: {word_count} words - using semantic search")
        context = extract_with_semantic_search(raw_text, schema, doc_id)
    else:
        print(f"   Document: {word_count} words - sending full text (under threshold)")
        context = raw_text

    # ── Build schema description for prompt ──────────────────────────
    schema_fields = {}
    for field_name, field_info in schema.model_fields.items():
        schema_fields[field_name] = str(field_info.annotation)

    schema_description = json.dumps(schema_fields, indent=2)

    # ── System prompt ─────────────────────────────────────────────────
    system_prompt = """You are a precise data extraction engine.
Your job is to extract structured information from unstructured text.

Rules:
1. Return ONLY valid JSON. No text before or after it.
2. No markdown, no backticks, no code fences.
3. Match the exact field names provided in the schema.
4. If a field value is not found in the text, use null.
5. Do NOT hallucinate or make up values.
6. Do NOT add fields that are not in the schema.
7. For list fields, return a JSON array even if empty."""

    # ── User prompt ───────────────────────────────────────────────────
    user_prompt = f"""Extract information from the document below and return it as JSON.

SCHEMA TO FOLLOW (field name: expected type):
{schema_description}

DOCUMENT:
{context}

Return ONLY the JSON object. Nothing else."""

    # ── API call ──────────────────────────────────────────────────────
    try:
        print(f"   Calling LLM...")
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt}
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            reasoning_format="hidden"   # hides <think> blocks (Qwen 3.6 27B)
        )

        raw_output = response.choices[0].message.content or ""
        # Safety net: strip any leftover <think>...</think> blocks
        raw_output = re.sub(r'<think>.*?</think>', '', raw_output, flags=re.DOTALL).strip()

        # ── Capture real token usage ──────────────────────────────────
        token_usage = {
            "prompt_tokens":     response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens":      response.usage.total_tokens
        }

        print(f"   Tokens used: {token_usage['total_tokens']} "
              f"(prompt: {token_usage['prompt_tokens']}, "
              f"completion: {token_usage['completion_tokens']})")
        print(f"   Raw output preview: {raw_output[:100]}...")

        # ── Parse JSON ────────────────────────────────────────────────
        parsed = extract_json(raw_output)

        if parsed is None:
            print("   ERROR: JSON parsing failed")
            print(f"   Raw output was: {raw_output}")
            return None, token_usage

        # ── Validate against Pydantic schema ──────────────────────────
        validated = schema(**parsed)
        print(f"   Extraction successful")
        return validated, token_usage

    except ValidationError as e:
        print(f"   ERROR: Validation failed: {e}")
        return None, empty_tokens

    except Exception as e:
        import traceback
        print(f"   ERROR: {e}")
        traceback.print_exc()
        return None, empty_tokens


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    from schemas.invoice import Invoice

    with open("sample_documents/invoices/invoice_001.txt", "r") as f:
        raw_text = f.read()

    print("=" * 60)
    print("Testing extractor on invoice_001.txt")
    print("=" * 60)

    result, tokens = extract(raw_text, Invoice, doc_id="invoice_001")

    if result:
        print("\nEXTRACTED DATA:")
        print(result.model_dump_json(indent=2))
        print(f"\nTokens used: {tokens['total_tokens']}")
    else:
        print("\nExtraction returned None")
