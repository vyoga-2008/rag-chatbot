"""
Per-session chat memory, persisted in SQLite so follow-up questions
can reference earlier turns even across server restarts.
"""
from langchain_community.chat_message_histories import SQLChatMessageHistory
from config import SQLITE_DB_PATH

CONNECTION_STRING = f"sqlite:///{SQLITE_DB_PATH}"


def get_session_history(session_id: str) -> SQLChatMessageHistory:
    """
    Returns a LangChain-compatible chat history object bound to this
    session_id. Reading/writing messages automatically persists to SQLite.
    """
    return SQLChatMessageHistory(
        session_id=session_id,
        connection=CONNECTION_STRING,
    )


def get_recent_messages(session_id: str, limit: int = 6):
    """
    Returns the last `limit` messages for a session as a list of
    (role, content) tuples — used to build the prompt context.
    """
    history = get_session_history(session_id)
    messages = history.messages[-limit:]
    return [(m.type, m.content) for m in messages]
