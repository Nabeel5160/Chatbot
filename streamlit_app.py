import requests
import streamlit as st

API_BASE = st.sidebar.text_input("API Base URL", value="http://localhost:8000")
SESSION_ID = st.sidebar.text_input("Session ID", value="streamlit-user")

st.title("NYSE_KO_2024 RAG Chatbot")
st.caption("Answers are restricted to the indexed document context.")

question = st.text_area("Ask a question", height=120, placeholder="What was Coca-Cola revenue in 2024?")

if st.button("Ask"):
    if not question.strip():
        st.warning("Enter a question first.")
    else:
        with st.spinner("Querying RAG API..."):
            resp = requests.post(
                f"{API_BASE}/chat",
                json={"question": question, "session_id": SESSION_ID},
                timeout=60,
            )
        if resp.status_code != 200:
            st.error(f"Error {resp.status_code}: {resp.text}")
        else:
            data = resp.json()
            st.subheader("Answer")
            st.write(data.get("answer", ""))
            st.subheader("Sources")
            for src in data.get("sources", []):
                st.write(f"Page {src.get('page')} - {src.get('document')}")
