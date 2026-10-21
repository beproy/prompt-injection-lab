import os
import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types

from prompts import SYSTEM_PROMPTS

# 1. Load environment variables from .env
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
default_model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def get_bot_reply(
    history: list[dict],
    user_message: str,
    system_prompt: str | None = None,
    model: str | None = None,
    client: genai.Client | None = None,
) -> str:
    """Send system prompt and conversation history to Gemini and return reply text.

    This function contains no Streamlit code so it can be reused in test scripts.
    """
    if system_prompt is None:
        system_prompt = SYSTEM_PROMPTS["v2_staff_verification"]
    if model is None:
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    if client is None:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    contents = []
    # Convert past messages to Gemini Content objects
    for msg in history:
        # Map 'assistant' (Streamlit convention) to 'model' (Gemini convention)
        role = "model" if msg.get("role") in ("assistant", "model") else "user"
        text = msg.get("text") or msg.get("content") or ""
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=text)],
            )
        )

    # Append the current user message
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_message)],
        )
    )

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
        ),
    )
    return response.text or ""


@st.cache_resource
def get_client(api_key_value: str | None = None) -> genai.Client:
    """Create and cache the Gemini client once so it stays alive across reruns."""
    key = api_key_value or os.getenv("GEMINI_API_KEY")
    return genai.Client(api_key=key)


def main():
    # Configure Streamlit page layout and title
    st.set_page_config(page_title="Acme Gadgets Support", page_icon="🤖")

    st.title("Acme Gadgets Support Chatbot")
    st.caption("Prompt Injection Lab (Configurable Assistant)")

    # Verify API key is available
    if not api_key:
        st.error(
            "Missing GEMINI_API_KEY. Please create a .env file based on .env.example "
            "and add your Gemini API key."
        )
        st.stop()

    # Get cached persistent Gemini client
    client = get_client(api_key)

    # Sidebar controls
    with st.sidebar:
        st.header("Configuration")

        prompt_options = list(SYSTEM_PROMPTS.keys())
        default_index = (
            prompt_options.index("v2_staff_verification")
            if "v2_staff_verification" in prompt_options
            else 0
        )

        selected_prompt_name = st.selectbox(
            "System Prompt",
            options=prompt_options,
            index=default_index,
        )

        selected_model_name = st.text_input(
            "Model Name",
            value=default_model_name,
        )

        st.divider()
        st.header("Lab Controls")
        if st.button("Reset Conversation", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    # Initialize message history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Reset conversation if the prompt or model was changed
    if "current_prompt_name" not in st.session_state:
        st.session_state.current_prompt_name = selected_prompt_name

    if "current_model_name" not in st.session_state:
        st.session_state.current_model_name = selected_model_name

    if (
        st.session_state.current_prompt_name != selected_prompt_name
        or st.session_state.current_model_name != selected_model_name
    ):
        st.session_state.messages = []
        st.session_state.current_prompt_name = selected_prompt_name
        st.session_state.current_model_name = selected_model_name

    # Render previous conversation history in the UI
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["text"])

    # Accept user input and get a response from Gemini
    if prompt := st.chat_input("Ask a question about Acme Gadgets..."):
        # Display the user message immediately
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate assistant response
        with st.chat_message("assistant"):
            try:
                reply = get_bot_reply(
                    history=st.session_state.messages,
                    user_message=prompt,
                    system_prompt=SYSTEM_PROMPTS[selected_prompt_name],
                    model=selected_model_name,
                    client=client,
                )
                st.markdown(reply)
                # Store new turn in session state history
                st.session_state.messages.append({"role": "user", "text": prompt})
                st.session_state.messages.append({"role": "assistant", "text": reply})
            except Exception as e:
                st.error(f"Error communicating with Gemini: {e}")


if __name__ == "__main__":
    main()
