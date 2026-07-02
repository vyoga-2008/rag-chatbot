"""
Streamlit frontend for the RAG chatbot.
Lets the user upload documents and chat with them, with follow-up memory.
"""
import uuid
import requests
import streamlit as st

BACKEND_URL = "http://localhost:8000"

st.set_page_config(page_title="Document Chatbot", page_icon="📄")
st.title("📄 Chat with your Documents")

# --- Session setup ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []  # list of {"role": ..., "content": ...}

# --- Sidebar: file upload ---
with st.sidebar:
    st.header("Upload Documents")
    uploaded_files = st.file_uploader(
        "Upload PDF, DOCX, CSV, TXT, or Markdown files",
        type=["pdf", "docx", "csv", "txt", "md"],
        accept_multiple_files=True,
    )

    if st.button("Process Documents", disabled=not uploaded_files):
        with st.spinner("Parsing, chunking, and embedding documents..."):
            files_payload = [
                ("files", (f.name, f.getvalue())) for f in uploaded_files
            ]
            response = requests.post(f"{BACKEND_URL}/upload", files=files_payload)

        if response.status_code == 200:
            data = response.json()
            st.success(
                f"Processed {len(data['files_processed'])} file(s), "
                f"added {data['chunks_added']} chunks."
            )
        else:
            st.error(f"Upload failed: {response.text}")

    st.divider()
    if st.button("Clear Chat (new session)"):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()

# --- Main chat area ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

question = st.chat_input("Ask a question about your documents...")

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = requests.post(
                f"{BACKEND_URL}/chat",
                json={
                    "session_id": st.session_state.session_id,
                    "question": question,
                },
            )

        if response.status_code == 200:
            data = response.json()
            answer = data["answer"]
            sources = data.get("sources", [])
            st.markdown(answer)
            if sources:
                st.caption(f"Sources: {', '.join(sources)}")
        else:
            answer = f"Error: {response.text}"
            st.error(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
