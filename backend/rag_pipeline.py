"""
Core RAG logic:
  - ingest_documents(): parse -> chunk -> embed -> store in ChromaDB
  - ask_question(): retrieve relevant chunks -> build prompt with memory -> call Gemini
"""
import os
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from config import (
    EMBEDDING_MODEL,
    LLM_MODEL,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    CHROMA_DB_DIR,
    COLLECTION_NAME,
    TOP_K_RESULTS,
    GOOGLE_API_KEY,
)
from document_parser import parse_document
from memory import get_session_history, get_recent_messages

# --- Initialize embedding model once (reused across requests) ---
_embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

# --- Initialize (or load existing) ChromaDB vector store ---
_vector_store = Chroma(
    collection_name=COLLECTION_NAME,
    embedding_function=_embeddings,
    persist_directory=CHROMA_DB_DIR,
)

# --- Text splitter for chunking ---
_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
)

# --- LLM ---
_llm = ChatGoogleGenerativeAI(
    model=LLM_MODEL,
    google_api_key=GOOGLE_API_KEY,
    temperature=0.2,
)


def ingest_documents(file_paths: list[str]) -> int:
    """
    Parses each file, splits into chunks, embeds, and adds to ChromaDB.
    Returns the number of chunks added.
    """
    all_chunks: list[Document] = []

    for file_path in file_paths:
        raw_text = parse_document(file_path)
        if not raw_text.strip():
            continue

        filename = os.path.basename(file_path)
        chunks = _splitter.split_text(raw_text)

        for i, chunk in enumerate(chunks):
            all_chunks.append(
                Document(
                    page_content=chunk,
                    metadata={"source": filename, "chunk_index": i},
                )
            )

    if all_chunks:
        _vector_store.add_documents(all_chunks)

    return len(all_chunks)


def ask_question(session_id: str, question: str) -> dict:
    """
    Retrieves relevant chunks, builds a prompt with chat history,
    calls Gemini, saves the turn to memory, and returns the answer + sources.
    """
    # 1. Retrieve relevant chunks from ChromaDB
    results = _vector_store.similarity_search(question, k=TOP_K_RESULTS)
    context_text = "\n\n".join(
        f"[Source: {doc.metadata.get('source', 'unknown')}]\n{doc.page_content}"
        for doc in results
    )
    sources = sorted({doc.metadata.get("source", "unknown") for doc in results})

    # 2. Load recent chat history for follow-up context
    history = get_session_history(session_id)
    recent = get_recent_messages(session_id, limit=6)

    # 3. Build the message list for Gemini
    system_prompt = (
        "You are a helpful assistant answering questions using ONLY the "
        "provided document context. If the answer isn't in the context, "
        "say you don't have that information. Use chat history to resolve "
        "follow-up questions (e.g. 'it', 'that', 'the previous one')."
    )

    messages = [SystemMessage(content=system_prompt)]

    for role, content in recent:
        if role == "human":
            messages.append(HumanMessage(content=content))
        elif role == "ai":
            messages.append(AIMessage(content=content))

    user_turn = f"Context:\n{context_text}\n\nQuestion: {question}"
    messages.append(HumanMessage(content=user_turn))

    # 4. Call Gemini
    response = _llm.invoke(messages)
    answer = response.content

    # 5. Persist this turn to SQLite memory
    history.add_user_message(question)
    history.add_ai_message(answer)

    return {"answer": answer, "sources": sources}
