# Document Chatbot (RAG)

Upload PDF, DOCX, CSV, TXT, or Markdown files and chat with them.
Supports follow-up questions via SQLite-backed memory.

## Stack
- Frontend: Streamlit
- Backend: FastAPI + Uvicorn
- LLM: Gemini 2.5 Flash (via langchain-google-genai)
- Embeddings: BAAI/bge-small-en-v1.5 (local, via HuggingFace)
- Vector DB: ChromaDB
- Memory: SQLite (via LangChain's SQLChatMessageHistory)
- Orchestration: LangChain

## Setup

1. Create a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate      # Windows
   source venv/bin/activate   # macOS/Linux
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and add your Gemini API key:
   ```
   cp .env.example .env
   ```
   Get a key at: https://aistudio.google.com/app/apikey

## Run

Open two terminals.

**Terminal 1 — Backend:**
```
cd backend
uvicorn main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```
cd frontend
streamlit run app.py
```

Then open the Streamlit URL (usually http://localhost:8501), upload your
documents, click "Process Documents", and start chatting.

## Project Structure
```
rag_chatbot/
├── backend/
│   ├── config.py            # settings & env vars
│   ├── document_parser.py   # pdf/docx/csv/txt/md text extraction
│   ├── rag_pipeline.py      # chunking, embedding, ChromaDB, Gemini call
│   ├── memory.py            # SQLite chat history
│   └── main.py              # FastAPI endpoints
├── frontend/
│   └── app.py                # Streamlit UI
├── requirements.txt
├── .env.example
└── README.md
```
