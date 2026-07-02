"""
Central configuration for the RAG chatbot backend.
All other modules import settings from here instead of hardcoding values.
"""
import os
from dotenv import load_dotenv

load_dotenv()  # reads variables from a .env file in the project root

# --- API Keys ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# --- Storage paths ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploaded_docs")
CHROMA_DB_DIR = os.path.join(BASE_DIR, "chroma_store")
SQLITE_DB_PATH = os.path.join(BASE_DIR, "chat_memory.db")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(CHROMA_DB_DIR, exist_ok=True)

# --- Models ---
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
LLM_MODEL = "gemini-2.5-flash"

# --- Chunking ---
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

# --- Retrieval ---
TOP_K_RESULTS = 4

# --- Collection name in Chroma ---
COLLECTION_NAME = "documents"
