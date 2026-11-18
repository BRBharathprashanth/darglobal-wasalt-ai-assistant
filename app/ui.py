
import os

import requests
import streamlit as st


# API endpoint
API_URL = os.getenv(
    "API_URL",
    "http://127.0.0.1:8000/chat"
)


# Page configuration
st.set_page_config(
    page_title="DarGlobal & Wasalt AI Assistant",
    page_icon="🏡",
    layout="wide"
)


# Custom styling
st.markdown(
    """
    <style>
    .main {
        background-color: #f7f8fa;
    }

    .header {
        padding: 20px;
        background: linear-gradient(120deg, #172554, #334155);
        border-radius: 12px;
        color: white;
        margin-bottom: 25px;
    }

    .stChatMessage {
        border-radius: 12px;
    }

    .source-box {
        background: #eef2ff;
        padding: 12px;
        border-radius: 8px;
        margin-top: 8px;
        font-size: 13px;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# Header
st.markdown(
    """
    <div class="header">
        <h1>🏡 DarGlobal & Wasalt AI Assistant</h1>
        <p>
            Explore real estate projects, properties and locations
            through AI-powered assistance.
        </p>
    </div>
    """,
    unsafe_allow_html=True
)


# Sidebar
with st.sidebar:

    st.title("About Assistant")

    st.write(
        "Ask questions about DarGlobal developments "
        "and Wasalt property information."
    )

    st.divider()

    st.subheader("Example questions")

    examples = [
        "Tell me about DarGlobal projects in Dubai.",
        "What properties are available in Riyadh?",
        "Which Saudi cities are covered by Wasalt?",
        "Tell me about Shams Al Riyadh."
    ]

    for example in examples:

        if st.button(
            example,
            use_container_width=True
        ):
            st.session_state.pending_question = example

    st.divider()

    if st.button(
        "Clear conversation",
        use_container_width=True
    ):
        st.session_state.messages = []
        st.rerun()

    st.caption(
        "Powered by FastAPI, BM25 and OpenRouter"
    )


# Chat history
if "messages" not in st.session_state:
    st.session_state.messages = []


# Display previous messages
for message in st.session_state.messages:

    with st.chat_message(message["role"]):

        st.markdown(message["content"])

        if message.get("sources"):

            with st.expander("View sources"):

                for source in message["sources"]:

                    st.markdown(
                        f"**{source['source_id']}. "
                        f"{source['title']}**"
                    )

                    if source.get("url"):
                        st.markdown(
                            f"[Open source]({source['url']})"
                        )


# User question
question = st.chat_input(
    "Ask about DarGlobal projects or Wasalt properties..."
)


# Handle example question buttons
if "pending_question" in st.session_state:

    question = st.session_state.pop(
        "pending_question"
    )


# Process question
if question:

    st.session_state.messages.append({
        "role": "user",
        "content": question
    })

    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):

        with st.spinner(
            "Searching knowledge base and generating answer..."
        ):

            try:

                response = requests.post(
                    API_URL,
                    json={"question": question},
                    timeout=(15, 150)
                )

                response.raise_for_status()

                result = response.json()

                answer = result.get(
                    "answer",
                    "No answer returned."
                )

                sources = result.get(
                    "sources",
                    []
                )

                st.markdown(answer)

                if sources:

                    with st.expander("View sources"):

                        for source in sources:

                            st.markdown(
                                f"**{source['source_id']}. "
                                f"{source['title']}**"
                            )

                            if source.get("url"):

                                st.markdown(
                                    f"[Open source]({source['url']})"
                                )

                st.session_state.messages.append({

                    "role": "assistant",

                    "content": answer,

                    "sources": sources

                })

            except requests.exceptions.Timeout:

                error_message = (
                    "The AI service took too long to respond. "
                    "Please try again."
                )

                st.error(error_message)

                st.session_state.messages.append({

                    "role": "assistant",

                    "content": error_message,

                    "sources": []

                })

            except requests.RequestException as exc:

                error_message = (
                    f"Unable to connect to the AI backend: {exc}"
                )

                st.error(error_message)

                st.session_state.messages.append({

                    "role": "assistant",

                    "content": error_message,

                    "sources": []

                })
