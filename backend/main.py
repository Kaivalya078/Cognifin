import os
import queue
import re
import shutil
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

# FastAPI imports
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.sessions import SessionMiddleware

from asset_manager import ensure_index_cache
from auth import (
    JWT_SECRET,
    create_access_token,
    decode_access_token,
    get_current_user,
    get_optional_user,
    hash_password,
    verify_password,
)
from config import settings
from core.app_retrieval import (
    held_years,
    load_global_corpus,
    outside_coverage,
    retrieve_global,
)
from core.citation_verifier import verify_citations

# Phase 5: Confidence + citation verification
from core.confidence_scorer import compute_confidence

# Phase 2.5: Corpus architecture
from core.corpus_manager import CorpusManager, discard, new_session_corpus

# Stage 8B: Multi-corpus routing
from core.corpus_router import CorpusRouter
from core.latency_tracker import LatencyTracker, latency_stats

# Phase 2: Reranking + refinement
# Phase 6: Performance (cache + latency)
from core.response_cache import response_cache

# Phase 1: Retrieval observability
from core.retrieval_pipeline_v2 import refine_results

# Our retrieval pipeline
from core.retriever_pipeline import RetrieverPipeline

# Auth + Database
from db import ensure_indexes, users_collection
from financials.present import assistant_metadata, finish, reminder
from financials.present import prepare as prepare_figures
from generation.citation_fill import drop_unknown_ids, fill_figure_citations
from generation.intent_prompts import build_intent_prompt

# Phase 2: Generation layer
from generation.openai_client import OpenAIClient
from generation.prompt_builder import build_context, build_prompt, extract_citations
from generation.streaming import hold_follow_ups, sse
from query.context_assembler import assemble_context

# Phase 4: Intelligent query understanding
from query.intelligent_parser import (
    init_intelligent_parser,
    is_intelligent_parsing_enabled,
)

# Phase 3: Recall improvement (multi-query, hybrid search, expansion)
from query.multi_query import init_multi_query
from query.query_expander import get_synonym_count

# Stage 6: Query orchestration (parse → plan → execute)
from query.query_orchestrator import intelligent_retrieve, retrieve_context
from query.query_understanding import parse_query
from query.search_plan_builder import build_plan
from routers.conversations import (
    append_to_conversation as db_append_to_conversation,
)
from routers.conversations import (
    create_conversation as db_create_conversation,
)

# Conversation persistence
from routers.conversations import (
    router as conversations_router,
)

# =============================================================================
# FOLLOW-UP QUESTION EXTRACTION
# =============================================================================

def extract_follow_ups(answer: str):
    """
    Split [FOLLOW_UP]: lines from the LLM answer.
    Returns (clean_answer, list_of_follow_up_questions).
    """
    pattern = r'\[FOLLOW_UP\]:\s*(.+?)(?=\n|$)'
    follow_ups = re.findall(pattern, answer)
    clean_answer = re.sub(r'\n*\[FOLLOW_UP\]:\s*.+', '', answer).strip()
    return clean_answer, follow_ups[:3]


# =============================================================================
# PYDANTIC MODELS (Request/Response Schemas)
# =============================================================================

class RetrieveRequest(BaseModel):
    """
    Request schema for the /retrieve endpoint.

    Example:
        {"query": "What are the risk factors?"}
    """
    query: str = Field(
        ...,  # ... means required
        description="The question to search for in the document",
        min_length=3,  # At least 3 characters
        max_length=1000,  # caps prompt cost and search work per request
        examples=["What are the risk factors?"]
    )
    top_k: Optional[int] = Field(
        default=None,
        description="Number of results to return (default: 5)",
        ge=1,  # Greater than or equal to 1
        le=20  # Less than or equal to 20
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID from /upload to include uploaded document in search",
    )


class RetrieveResultItem(BaseModel):
    """
    A single retrieval result.
    """
    chunk_id: str = Field(description="Unique identifier for the chunk")
    score: float = Field(description="Similarity score (0-1, higher is better)")
    snippet: str = Field(description="The text content of the chunk")


class RetrieveResponse(BaseModel):
    """
    Response schema for the /retrieve endpoint.

    Example:
        {
            "query": "What are the risk factors?",
            "top_k": 5,
            "results": [
                {"chunk_id": "chunk_12", "score": 0.87, "snippet": "..."},
                ...
            ]
        }
    """
    query: str = Field(description="The original query")
    top_k: int = Field(description="Number of results returned")
    results: List[RetrieveResultItem] = Field(description="Retrieved chunks")
    filtered_count: int = Field(default=0, description="Number of results filtered out below similarity threshold")


class HealthResponse(BaseModel):
    """
    Response schema for the /health endpoint.
    """
    status: str = Field(description="Service status")
    indexed: bool = Field(description="Whether a document has been indexed")
    num_chunks: int = Field(description="Number of chunks in the index")
    generation_ready: bool = Field(description="Whether OpenAI API is configured")


# --- Auth Models ---

class RegisterRequest(BaseModel):
    """Registration request."""
    name: str = Field(..., min_length=2, description="User display name")
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=6, description="Password (min 6 chars)")


class LoginRequest(BaseModel):
    """Login request."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="Password")


class AuthResponse(BaseModel):
    """Response for register and login."""
    token: str = Field(description="JWT access token")
    user: dict = Field(description="User info (id, name, email)")


# --- Phase 2: Chat Models ---

class ChatRequest(BaseModel):
    """
    Request schema for the /chat endpoint.

    Example:
        {"question": "What are the risk factors?"}
    """
    question: str = Field(
        ...,
        description="The question to ask about the document",
        min_length=3,
        max_length=1000,  # caps prompt cost and search work per request
        examples=["What are the risk factors?"]
    )
    top_k: Optional[int] = Field(
        default=None,
        description="Number of evidence chunks to retrieve (default: 5)",
        ge=1,
        le=20
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID from /upload to include uploaded document in search",
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="Existing conversation ID to append to. If omitted, a new conversation is created.",
    )


class EvidenceItem(BaseModel):
    """
    A single piece of evidence used to generate the answer.
    """
    chunk_id: str = Field(description="Chunk identifier")
    snippet: str = Field(description="Text content of the chunk")
    page_number: int = Field(default=0, description="1-based page in the source PDF (0 = unknown)")
    document_label: str = Field(default="", description="Human-readable document label, e.g. TCS_DRHP_2024_v1")
    pdf_url: str = Field(default="", description="Basename of the source PDF")


class ChatResponse(BaseModel):
    """
    Response schema for the /chat endpoint.
    """
    answer: str = Field(description="The generated answer grounded in document evidence")
    citations: List[str] = Field(description="Chunk IDs cited in the answer")
    evidence: List[EvidenceItem] = Field(description="Evidence chunks used to generate the answer")
    conversation_id: Optional[str] = Field(default=None, description="MongoDB conversation ID for persistence")
    metadata: dict = Field(default_factory=dict, description="Pipeline metadata: confidence, latency, intent, sources")
    follow_ups: List[str] = Field(default_factory=list, description="Suggested follow-up questions")



# --- Stage 8B: Upload Models ---

class UploadResponse(BaseModel):
    """
    Response schema for the /upload endpoint.
    """
    session_id: str = Field(description="Session ID for subsequent queries")
    chunks: int = Field(description="Number of chunks created from the uploaded document")
    company: str = Field(description="Company name used for the upload")
    year: str = Field(description="Year assigned to the upload")
    document_type: str = Field(description="Document type assigned to the upload")


# =============================================================================
# GLOBAL STATE
# =============================================================================

# We use global instances that persist across requests
# These are initialized when the server starts (see lifespan below)
pipeline: Optional[RetrieverPipeline] = None
llm_client: Optional[OpenAIClient] = None

# Phase 2.5: Corpus manager wraps pipeline for metadata-aware retrieval
corpus_manager: Optional[CorpusManager] = None

# Stage 8B: Corpus router for multi-corpus support
corpus_router: Optional[CorpusRouter] = None


# =============================================================================
# LIFESPAN (Startup/Shutdown Events)
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage the application lifecycle.

    Read-only startup: loads pre-ingested corpus from index_cache/.
    Never ingests documents — use ingest.py or batch_ingest_annual_reports.py.

    Opens index_cache/lancedb + document_registry.json (core.app_retrieval.
    load_global_corpus), which refuses an index built with another config.
    """
    global pipeline, llm_client, corpus_manager, corpus_router

    print("\n" + "="*60)
    print("🚀 Cognifin - Starting Up (Read-Only Mode)")
    print("="*60)

    start_time = time.time()

    cache_dir = settings.INDEX_CACHE_DIR

    # Initialize the OpenAI client
    llm_client = OpenAIClient()

    ensure_index_cache(cache_dir)  # remote mode: download before checking for it
    pipeline, corpus_manager = load_global_corpus(cache_dir)

    # Stage 8B: Initialize corpus router with global corpus
    corpus_router = CorpusRouter(corpus_manager)

    # Ensure MongoDB indexes
    ensure_indexes()

    # Phase 3: Initialize multi-query generator
    if init_multi_query(llm_client):
        print(f"📝 Multi-query enabled (synonyms: {get_synonym_count()} groups)")
    else:
        print("⚠️  Multi-query disabled — using single query")

    # Phase 4: Initialize intelligent query parser
    if init_intelligent_parser(llm_client):
        print("🧠 Intelligent query parser enabled")
    else:
        print("⚠️  Intelligent parsing disabled — using rule-based parser")

    if llm_client.is_configured:
        threading.Thread(target=prewarm_showcase, daemon=True).start()

    elapsed = time.time() - start_time
    print(f"\n✅ Corpus loaded in {elapsed:.2f}s "
          f"({corpus_manager.num_chunks} chunks, "
          f"{len(corpus_manager.documents)} documents)")

    print("\n" + "="*60)
    print("📖 Open http://localhost:8000/docs for Swagger UI")
    print("="*60 + "\n")

    # Yield control to the application
    yield

    # Shutdown
    print("\n👋 Shutting down Cognifin...")


# =============================================================================
# FASTAPI APPLICATION
# =============================================================================

app = FastAPI(
    title="Cognifin",
    description="""
## 🔍 Indian Financial Document Analyzer

**Phase 1: Retrieval Pipeline** + **Phase 2: RAG Generation** + **Stage 8B: Upload Support**

This API provides semantic search and AI-powered Q&A over Indian financial documents (SEBI DRHP/RHP, annual reports).

### How it works:
1. A global corpus of NIFTY annual reports is loaded at startup
2. Users can upload additional PDFs for session-scoped retrieval
3. Query `/retrieve` to find relevant passages (evidence only)
4. Query `/chat` for AI-generated answers grounded in the document

### Endpoints:
- **GET /health** — Service health check
- **POST /upload** — Upload a PDF for session-scoped retrieval
- **POST /retrieve** — Semantic retrieval (returns evidence)
- **POST /chat** — RAG Q&A (grounded answer + citations + evidence)
    """,
    version="3.0.0",
    lifespan=lifespan
)

# Add CORS middleware (allows frontend to call this API)
# Set ALLOWED_ORIGINS in production to restrict access
_allowed_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session middleware — required by Authlib for OAuth state (CSRF protection)
app.add_middleware(
    SessionMiddleware,
    secret_key=JWT_SECRET,
)

def _rate_key(request: Request) -> str:
    """Signed-in callers are limited per account, everyone else per IP."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        try:
            return "user:" + decode_access_token(auth_header[7:])["sub"]
        except HTTPException:
            pass
    return "ip:" + get_remote_address(request)


def _require_session_owner(session_id: Optional[str], user: Optional[dict]) -> None:
    """An upload session answers only its uploader. Same 404 whether it never existed,
    expired or belongs to someone else, so ids can't be probed."""
    if session_id is None:
        return
    if not user or corpus_router is None or corpus_router.owner(session_id) != user["user_id"]:
        raise HTTPException(status_code=404,
                            detail="Upload session not found or expired. Upload the PDF again.")


def _chat_limit(key: str) -> str:
    if key.startswith("ip:"):
        return f"{settings.ANON_FREE_QUESTIONS}/day"
    return settings.RATE_LIMIT_CHAT


# ponytail: in-memory counters, per process, reset on restart. Pass
# storage_uri="redis://..." before running more than one worker.
limiter = Limiter(key_func=_rate_key)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
def _rate_limited(request: Request, exc: RateLimitExceeded):
    if request.url.path in ("/chat", "/chat/stream") and _rate_key(request).startswith("ip:"):
        detail = (f"You've used your {settings.ANON_FREE_QUESTIONS} free questions for today. "
                  "Sign in to keep asking.")
    else:
        detail = f"Too many requests ({exc.detail}). Please wait and try again."
    return JSONResponse(status_code=429, content={"detail": detail})


# Google OAuth router
from routers.google_auth import router as google_auth_router  # noqa: E402

# Conversations router (user-scoped CRUD)
app.include_router(conversations_router)
app.include_router(google_auth_router)

# Serve source PDFs at /pdfs/<filename> so the frontend "Open PDF" link works.
# Falls back gracefully if the data directory doesn't exist.
_PDF_DIR = os.path.join(os.path.dirname(__file__), "data")
if os.path.isdir(_PDF_DIR):
    app.mount("/pdfs", StaticFiles(directory=_PDF_DIR), name="pdfs")


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Health Check",
    description="Check if the service is running and a document is indexed."
)
def health_check():
    """
    Health check endpoint.

    Returns:
        - status: "ok" if service is running
        - indexed: True if a document has been indexed
        - num_chunks: Number of chunks in the index

    Use this to verify the service is running before the demo!
    """
    global corpus_manager, llm_client

    is_indexed = corpus_manager is not None and corpus_manager.is_indexed
    num_chunks = corpus_manager.num_chunks if is_indexed else 0
    gen_ready = llm_client is not None and llm_client.is_configured

    return HealthResponse(
        status="ok",
        indexed=is_indexed,
        num_chunks=num_chunks,
        generation_ready=gen_ready
    )


# =============================================================================
# STAGE 8B: UPLOAD ENDPOINT
# =============================================================================

@app.post(
    "/upload",
    tags=["Upload"],
    summary="Upload PDF",
    description="Upload a PDF for session-scoped retrieval. Streams server-sent events: stage (chunking, embedding done/total, indexing), then final (UploadResponse) or error.",
)
@limiter.limit("5/hour")
def upload_document(
    request: Request,
    file: UploadFile = File(..., description="PDF file to upload"),
    company_name: str = Form(..., description="Company name for the document"),
    year: Optional[str] = Form(default=None, description="Fiscal year (e.g. '2024')"),
    document_type: Optional[str] = Form(
        default=None, description="Document type (default: 'Annual_Report')"
    ),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload a PDF for session-scoped retrieval.

    Creates an in-memory corpus that is NOT persisted to disk and does NOT
    modify the global NIFTY corpus. The returned session_id can be passed
    to /retrieve and /chat to include this document in search results.

    Args:
        file: The PDF file to upload
        company_name: Company name (used for scoping and metadata)
        year: Fiscal year (defaults to '2024')
        document_type: Filing type (defaults to 'Annual_Report')

    Returns:
        session_id, chunk count, and metadata used
    """
    global corpus_router

    if corpus_router is None:
        raise HTTPException(
            status_code=503,
            detail="Server not ready. Please wait for startup to complete.",
        )

    # Apply defaults
    year = year or "2024"
    document_type = document_type or "Annual_Report"

    # Reject non-PDFs by content, not by the client-supplied name or type
    if file.file.read(5) != b"%PDF-":
        raise HTTPException(status_code=415, detail="Only PDF files are accepted.")
    file.file.seek(0)
    max_bytes = settings.UPLOAD_MAX_MB * 1024 * 1024

    # Save uploaded file to a temp location
    tmp_dir = None
    try:
        tmp_dir = tempfile.mkdtemp(prefix="finsight_upload_")
        # Fixed name: file.filename is client-controlled ("../../x" escapes tmp_dir)
        tmp_path = os.path.join(tmp_dir, "upload.pdf")

        written = 0
        with open(tmp_path, "wb") as f:
            while chunk := file.file.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"PDF exceeds the {settings.UPLOAD_MAX_MB} MB limit.",
                    )
                f.write(chunk)

        # Isolated corpus on a temporary store (shares embedding model weights);
        # the router deletes the store when the session is evicted.
        session_corpus = new_session_corpus(RetrieverPipeline())
        q, abandoned, _ = _start_ingest(session_corpus, tmp_dir, tmp_path,
                                        company_name, year, document_type,
                                        owner=current_user["user_id"])
        tmp_dir = None  # the worker owns the temp dir from here
        return StreamingResponse(_ingest_stream(q, abandoned),
                                 media_type="text/event-stream", headers=SSE_HEADERS)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Upload error: {str(e)}",
        ) from e
    finally:
        # Clean up temp file (only when we failed before the stream took over)
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _start_ingest(session_corpus, tmp_dir: str, tmp_path: str,
                  company_name: str, year: str, document_type: str, owner: Optional[str] = None):
    """Ingest an uploaded PDF on a worker thread that owns all cleanup.

    Returns (queue, abandoned, thread). The queue receives ("stage", info)
    items, then ("final", UploadResponse dict) or ("error", {detail, status}).
    The worker removes the temp dir before reporting the end, and discards the
    corpus on failure or when the stream was abandoned, so the response
    stream never has to wait for it.
    """
    q: queue.Queue = queue.Queue()
    abandoned = threading.Event()

    def report(name, **info):
        if abandoned.is_set():  # client gone: stop embedding at the next slice
            raise RuntimeError("upload abandoned by the client")
        q.put(("stage", {"name": name, **info}))

    def work():
        # Every path ends with exactly one terminal item, or the stream waits forever.
        registered = False
        try:
            n = session_corpus.add_document(
                pdf_path=tmp_path, company=company_name, document_type=document_type,
                year=year, progress=report,
            )
            shutil.rmtree(tmp_dir, ignore_errors=True)
            if abandoned.is_set():
                discard(session_corpus)
                return
            # ponytail: a client leaving after this point leaves an orphan session
            # until the router evicts it; nothing else references it.
            session_id = str(uuid4())
            final = UploadResponse(
                session_id=session_id, chunks=n, company=company_name,
                year=year, document_type=document_type,
            ).model_dump()
            corpus_router.register_session(session_id, session_corpus, owner=owner)
            registered = True
            q.put(("final", final))
        except BaseException as e:
            if not registered:
                try:
                    discard(session_corpus)
                except Exception:
                    pass
            shutil.rmtree(tmp_dir, ignore_errors=True)
            q.put(("error", {"detail": f"Upload error: {e}", "status": 500}))

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    return q, abandoned, worker


def _ingest_stream(q: queue.Queue, abandoned: threading.Event):
    """SSE frames from an ingest queue; marks the ingest abandoned if closed early."""
    try:
        while True:
            kind, data = q.get()
            yield sse(kind, data)
            if kind in ("final", "error"):
                return
    finally:
        abandoned.set()


# =============================================================================
# RETRIEVE ENDPOINT
# =============================================================================

@app.post(
    "/retrieve",
    response_model=RetrieveResponse,
    tags=["Retrieval"],
    summary="Semantic Retrieval",
    description="Find the most relevant chunks for a given query."
)
@limiter.limit("30/minute")
def retrieve(request: Request, body: RetrieveRequest,
             current_user: Optional[dict] = Depends(get_optional_user)):
    """
    Main retrieval endpoint.

    This is the core of Cognifin Phase 1:
    1. Takes a natural language query
    2. Embeds it using the same model as the document
    3. Finds the top-K most similar chunks
    4. Returns the chunks as "evidence"

    Args:
        request: Contains the query and optional top_k parameter

    Returns:
        - query: The original query (for reference)
        - top_k: Number of results
        - results: List of chunks with scores and snippets

    Raises:
        503: If no document has been indexed yet
    """
    global corpus_manager, corpus_router

    # Check if corpus is ready
    if corpus_manager is None or not corpus_manager.is_indexed:
        raise HTTPException(
            status_code=503,
            detail="No document indexed. Please ensure PDF_PATH is set correctly and restart the server."
        )

    _require_session_owner(body.session_id, current_user)

    # Get top_k (use request value or default from env)
    top_k = body.top_k if body.top_k is not None else settings.TOP_K

    try:
        final_k = settings.FINAL_K
        parsed = None

        if body.session_id is not None:
            # Session path: build plan manually, route through corpus_router
            entities = corpus_manager.list_available_entities()
            companies = entities.get("companies", [])
            parsed = parse_query(body.query, companies)
            plan = build_plan(parsed, top_k)
            results = corpus_router.execute_plan(
                plan,
                embed_query=lambda q: pipeline.embed_query(q),
                session_id=body.session_id,
            )
        else:
            # Global-only path: use standard orchestrator
            results, parsed = retrieve_context(
                raw_query=body.query,
                corpus_manager=corpus_manager,
                embed_query=lambda q: pipeline.embed_query(q),
                default_top_k=top_k,
            )

        # Phase 2: Refinement pipeline (rerank → boost → dedup → enrich)
        results = refine_results(
            results=results,
            query=body.query,
            parsed_query=parsed,
            corpus=corpus_manager,
            final_k=final_k,
        )

        # Convert to response format
        result_items = [
            RetrieveResultItem(
                chunk_id=r.chunk_id,
                score=round(r.score, 4),  # Round to 4 decimal places
                snippet=r.snippet
            )
            for r in results
        ]

        return RetrieveResponse(
            query=body.query,
            top_k=len(result_items),
            results=result_items,
            filtered_count=top_k - len(result_items) if len(result_items) < top_k else 0,
        )

    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Retrieval error: {str(e)}"
        ) from e


# =============================================================================
# PHASE 2: CHAT ENDPOINT (RAG Generation)
# =============================================================================

# The suggested questions on the chat welcome screen (frontend ChatPage.jsx).
# Keep the two lists identical: a pinned cache hit needs the exact text.
SHOWCASE_QUESTIONS = [
    "What was TCS's consolidated revenue from operations in FY2024?",
    "When did the amalgamation of HDFC Limited with HDFC Bank become effective?",
    "Which acquisitions did the Infosys board approve in fiscal 2025?",
    "What was Hindustan Unilever's profit after tax in FY2025?",
]


def prewarm_showcase() -> None:
    """Answer the showcase questions once and pin them, so a visitor's first click is instant."""
    for q in SHOWCASE_QUESTIONS:
        try:
            response_cache.set(q, answer_question(q), pin=True)
        except Exception as e:
            print(f"⚠️  Pre-warm failed for '{q}': {e}")


# Query intent (rule-based or intelligent parser) → intent_prompts.py template
_STRUCTURED_PROMPTS = {"comparison": "compare", "compare": "compare",
                       "temporal": "trend", "trend": "trend"}


def _parsed(parsed, key) -> list:
    v = parsed.get(key) if isinstance(parsed, dict) else getattr(parsed, key, None)
    return list(v or [])


REFUSAL = "Not available in the provided documents."


def _prepare_figures(question: str, parsed):
    """Financials-table rows for this question, or None. Never fails a chat."""
    def get(key):
        return _parsed(parsed, key)
    try:
        return prepare_figures(question, get("companies"), [str(y) for y in get("years")])
    except Exception as e:
        print(f"⚠️  Financials router skipped: {e}")
        return None


def answer_question(question: str, session_id: Optional[str] = None,
                    top_k: Optional[int] = None) -> dict:
    """The final payload of answer_events (what /chat, eval and pre-warm use)."""
    for kind, data in answer_events(question, session_id, top_k):
        if kind == "final":
            return data
    raise RuntimeError("Answer pipeline ended without a result")


def _stage(tracker: LatencyTracker, name: str):
    return ("stage", {"name": name, "ms": tracker.get_breakdown()[name]})


def answer_events(question: str, session_id: Optional[str] = None,
                  top_k: Optional[int] = None):
    """
    Run the RAG pipeline, or serve it from the response cache, as events:
    ("stage", {name, ms}) per tracked step, ("token", {text}) per streamed
    piece of the answer, then ("final", payload). A cache hit is only "final".
    Nothing is cached unless the LLM stream completed.

    Returns a user-independent payload (answer, citations, evidence, metadata,
    follow_ups). The prompt carries no per-user context, so one cached answer is
    correct for everyone — which is why conversation_id is never part of it.
    Raises KeyError / ValueError / RuntimeError from the pipeline.
    """
    cached = response_cache.get(question, session_id)
    if cached:
        print(f"⚡ Cache HIT for: '{question[:60]}...'")
        yield "final", {**cached, "metadata": {**cached.get("metadata", {}), "cached": True}}
        return

    tracker = LatencyTracker()
    top_k = top_k if top_k is not None else settings.TOP_K
    final_k = settings.FINAL_K
    intent = "lookup"
    parsed = None

    if session_id is not None:
        # Session path: build plan manually, route through corpus_router
        print(f"\n💬 Chat request (session {session_id[:8]}...): '{question[:60]}...'")
        with tracker.track("retrieval"):
            entities = corpus_manager.list_available_entities()
            companies = entities.get("companies", [])
            parsed = parse_query(question, companies)
            plan = build_plan(parsed, top_k)
            results = corpus_router.execute_plan(
                plan,
                embed_query=lambda q: pipeline.embed_query(q),
                session_id=session_id,
            )
        yield _stage(tracker, "retrieval")

        with tracker.track("reranking"):
            results = refine_results(
                results=results,
                query=question,
                parsed_query=parsed,
                corpus=corpus_manager,
                final_k=final_k,
            )
        yield _stage(tracker, "reranking")

        context, chunk_ids = build_context(results)

    elif is_intelligent_parsing_enabled():
        # Phase 4: Intelligent retrieval pipeline
        print(f"\n🧠 Chat request (Phase 4): '{question[:60]}...'")
        with tracker.track("intelligent_retrieve"):
            step_results, iq = intelligent_retrieve(
                raw_query=question,
                corpus_manager=corpus_manager,
                embed_query=lambda q: pipeline.embed_query(q),
                pipeline=pipeline,
                default_top_k=top_k,
            )
        yield _stage(tracker, "intelligent_retrieve")

        intent = iq.intent
        parsed = iq   # companies/years for the financials router
        print(f"   Intent: {iq.intent} | Complexity: {iq.complexity} | "
              f"Strategy: {iq.retrieval_strategy} | Parse: {iq.parse_method}")

        with tracker.track("context_assembly"):
            context, chunk_ids = assemble_context(step_results, intent=iq.intent)
        yield _stage(tracker, "context_assembly")

        results = []
        for step_r in step_results.values():
            results.extend(step_r)

    else:
        # Global-only path: use standard orchestrator
        print(f"\n💬 Chat request: '{question[:60]}...'")
        with tracker.track("retrieval"):
            _, results, parsed = retrieve_global(
                question, pipeline=pipeline, corpus_manager=corpus_manager,
                top_k=top_k, final_k=final_k,
            )
        yield _stage(tracker, "retrieval")

        if parsed:
            intent = parsed.get("intent", "lookup") if isinstance(parsed, dict) else getattr(parsed, "intent", "lookup")

        context, chunk_ids = build_context(results)

    # Verified figures from the financials table ride alongside the RAG chunks.
    fin = _prepare_figures(question, parsed)
    if fin:
        context = fin.block + "\n\n" + context
        chunk_ids = list(chunk_ids) + list(fin.ids)
    # A year none of the named companies has a report for, with no verified row: refuse
    # (the frontend shows the upload card) rather than read another year's report.
    # Uploaded PDFs (session path) are never refused here.
    asked = _parsed(parsed, "companies"), [str(y) for y in _parsed(parsed, "years")]
    refuse = (session_id is None and fin is None and all(asked)
              and outside_coverage(*asked, held_years(corpus_manager)))
    if refuse:
        results, chunk_ids = [], []

    # Build the prompt and generate. Comparisons and trends get prompts that
    # demand tables over entities/periods; everything else keeps the generic
    # prompt, whose grounding rules are tuned against over-refusal.
    prompt_intent = _STRUCTURED_PROMPTS.get(intent)
    if prompt_intent:
        system_prompt, user_message = build_intent_prompt(context, question, prompt_intent)
    else:
        system_prompt, user_message = build_prompt(context, question)
    user_message += reminder(fin)
    raw = []

    def deltas():
        for d in llm_client.generate_stream(system_prompt, user_message):
            raw.append(d)
            yield d

    if refuse:
        print("🚫 Asked year is outside the corpus for these companies; refusing without the LLM")
        raw.append(REFUSAL)
        yield "token", {"text": REFUSAL}
    else:
        print(f"🤖 Generating answer with {llm_client.model}...")
        for text in hold_follow_ups(deltas()):
            yield "token", {"text": text}
    raw_answer = "".join(raw).strip()

    answer, follow_ups = extract_follow_ups(raw_answer)
    # Phase 6.0: cite figures the model stated but left uncited, only on exact matches
    # with a passage it was shown (fin rows first, the same order as the context).
    model_answer = answer
    context_items = [(e["chunk_id"], e["snippet"]) for e in (fin.evidence if fin else [])]
    context_items += [(r.chunk_id, r.snippet) for r in results]
    answer, filled = fill_figure_citations(drop_unknown_ids(answer, chunk_ids), context_items)
    citations = extract_citations(answer, chunk_ids)
    confidence, conf_label = compute_confidence(results, answer, question, citations)
    citation_check = verify_citations(answer, chunk_ids)

    evidence = [
        EvidenceItem(
            chunk_id=r.chunk_id,
            snippet=r.snippet,
            page_number=r.page_number,
            document_label=r.document_label,
            pdf_url=r.pdf_url,
        ).model_dump()
        for r in results
    ] + [EvidenceItem(**e).model_dump() for e in (fin.evidence if fin else [])]

    total_ms = tracker.get_total_ms()
    breakdown = tracker.get_breakdown()
    latency_stats.record(breakdown)
    top_score = max((r.score for r in results), default=0.0)

    print(
        f"✅ Answer generated ({len(citations)} citations, "
        f"intent={intent}, confidence={confidence:.2f}, "
        f"latency={total_ms:.0f}ms)"
    )

    payload = {
        "answer": answer,
        "citations": citations,
        "evidence": evidence,
        "metadata": {
            "confidence": confidence,
            "confidence_label": conf_label,
            "intent": intent,
            "latency_ms": round(total_ms),
            "latency_breakdown": breakdown,
            "sources_used": len(results),
            "top_score": round(top_score, 3),
            "cached": False,
            "model": llm_client.model,
            "citation_check": citation_check,
            "citation_fill": filled,
            # The numbers check reads the model's own answer: filled fin markers would
            # pull derived figures into it and raise false "unmatched" flags.
            **finish(fin, model_answer),
        },
        "follow_ups": follow_ups,
    }
    response_cache.set(question, payload, session_id)
    yield "final", payload


def persist_exchange(user_id: str, conversation_id: Optional[str],
                     question: str, payload: dict) -> Optional[str]:
    """Save the Q/A pair to the user's conversation; returns its id."""
    now_iso = datetime.now(timezone.utc).isoformat()
    user_msg = {"role": "user", "content": question, "metadata": {}, "timestamp": now_iso}
    assistant_msg = {
        "role": "assistant",
        "content": payload["answer"],
        "metadata": assistant_metadata(payload),
        "timestamp": now_iso,
    }
    try:
        if conversation_id:
            db_append_to_conversation(conversation_id, user_id, user_msg, assistant_msg)
        else:
            title = question[:60] + ("..." if len(question) > 60 else "")
            conversation_id = db_create_conversation(user_id, title, user_msg, assistant_msg)
    except Exception as persist_err:
        # Don't fail the request if persistence fails — log and continue
        print(f"⚠️  Conversation persistence error: {persist_err}")
    return conversation_id


def _error_status(e: Exception) -> int:
    """HTTP status for a pipeline failure (shared by /chat and /chat/stream)."""
    if isinstance(e, KeyError):
        return 404
    if isinstance(e, ValueError):
        return 503
    if isinstance(e, RuntimeError):
        return 502
    return 500


def _error_detail(e: Exception) -> str:
    known = isinstance(e, (KeyError, ValueError, RuntimeError))
    return str(e) if known else f"Generation error: {str(e)}"


def _require_chat_ready() -> None:
    if corpus_manager is None or not corpus_manager.is_indexed:
        raise HTTPException(
            status_code=503,
            detail="No document indexed. Please ensure PDF_PATH is set correctly and restart the server."
        )
    if llm_client is None or not llm_client.is_configured:
        raise HTTPException(
            status_code=503,
            detail="OpenAI API key is not configured. Please set OPENAI_API_KEY in your .env file and restart the server."
        )


SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@app.post(
    "/chat",
    response_model=ChatResponse,
    tags=["Generation"],
    summary="RAG Chat",
    description="Ask a question and get an AI-generated answer grounded in the document."
)
@limiter.shared_limit(_chat_limit, scope="chat")
def chat(request: Request, body: ChatRequest,
         current_user: Optional[dict] = Depends(get_optional_user)):
    """Answer (fresh or cached), then persist to the caller's conversation."""
    _require_chat_ready()
    _require_session_owner(body.session_id, current_user)

    try:
        payload = answer_question(body.question, body.session_id, body.top_k)
    except Exception as e:
        raise HTTPException(status_code=_error_status(e), detail=_error_detail(e)) from e

    # Anonymous trial answers aren't saved; there is no account to save them to.
    conv_id = None
    if current_user:
        conv_id = persist_exchange(
            current_user["user_id"], body.conversation_id, body.question, payload
        )
    return ChatResponse(**payload, conversation_id=conv_id)


@app.post(
    "/chat/stream",
    tags=["Generation"],
    summary="RAG Chat (streamed)",
    description="Like /chat, as server-sent events: stage, token, then final (or error).",
)
@limiter.shared_limit(_chat_limit, scope="chat")
def chat_stream(request: Request, body: ChatRequest,
                current_user: Optional[dict] = Depends(get_optional_user)):
    _require_chat_ready()
    _require_session_owner(body.session_id, current_user)

    def gen():
        try:
            for kind, data in answer_events(body.question, body.session_id, body.top_k):
                if kind != "final":
                    yield sse(kind, data)
                    continue
                conv_id = None
                if current_user:
                    conv_id = persist_exchange(
                        current_user["user_id"], body.conversation_id, body.question, data
                    )
                yield sse("final", ChatResponse(**data, conversation_id=conv_id).model_dump())
        except Exception as e:
            yield sse("error", {"detail": _error_detail(e), "status": _error_status(e)})

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)


# =============================================================================
# AUTHENTICATION ENDPOINTS
# =============================================================================

@app.post(
    "/register",
    response_model=AuthResponse,
    tags=["Auth"],
    summary="Register",
    description="Create a new user account.",
)
@limiter.limit("10/minute")
def register(request: Request, body: RegisterRequest):
    """Register a new user with name, email, and password."""
    email = body.email.lower()

    # Check for duplicate email
    if users_collection.find_one({"email": email}):
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists.",
        )

    now = datetime.now(timezone.utc)
    user_doc = {
        "name": body.name,
        "email": email,
        "password_hash": hash_password(body.password),
        "created_at": now,
    }
    result = users_collection.insert_one(user_doc)
    user_id = str(result.inserted_id)

    token = create_access_token(user_id, email, body.name)

    return AuthResponse(
        token=token,
        user={"id": user_id, "name": body.name, "email": email},
    )


@app.post(
    "/login",
    response_model=AuthResponse,
    tags=["Auth"],
    summary="Login",
    description="Authenticate with email and password.",
)
@limiter.limit("10/minute")
def login(request: Request, body: LoginRequest):
    """Validate credentials and return a JWT token."""
    user = users_collection.find_one({"email": body.email.lower()})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password.",
        )

    user_id = str(user["_id"])
    token = create_access_token(user_id, user["email"], user["name"])

    return AuthResponse(
        token=token,
        user={"id": user_id, "name": user["name"], "email": user["email"]},
    )


@app.get(
    "/",
    tags=["System"],
    summary="Root",
    description="Redirect to documentation."
)
def root():
    """
    Root endpoint - provides a friendly welcome message.
    """
    return {
        "message": "Welcome to Cognifin!",
        "docs": "Visit /docs for the interactive API documentation",
        "health": "Visit /health to check service status",
    }


# =============================================================================
# RUN DIRECTLY (for development)
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    # Run the server
    # In production, use: uvicorn main:app --host 0.0.0.0 --port 8000
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True  # Auto-reload on code changes
    )
