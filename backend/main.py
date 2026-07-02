"""
FastAPI server exposing the RAG chatbot over HTTP.
Endpoints:
  POST /upload  -> ingest one or more documents
  POST /chat    -> ask a question, get an answer using retrieved context + memory
  GET  /health  -> simple liveness check
"""
import os
import shutil
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import UPLOAD_DIR
from rag_pipeline import ingest_documents, ask_question

app = FastAPI(title="RAG Chatbot API")

# Allow the Streamlit frontend (different port) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: str
    question: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload_documents(files: list[UploadFile] = File(...)):
    saved_paths = []

    for file in files:
        dest_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        saved_paths.append(dest_path)

    chunks_added = ingest_documents(saved_paths)

    return {
        "files_processed": [os.path.basename(p) for p in saved_paths],
        "chunks_added": chunks_added,
    }


@app.post("/chat")
def chat(request: ChatRequest):
    result = ask_question(request.session_id, request.question)
    return result
