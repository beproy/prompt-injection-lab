import os
import streamlit as st
from dotenv import load_dotenv
from google import genai

from bot import get_bot_reply
from prompts import SYSTEM_PROMPTS

# 1. Load environment variables from .env
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
default_model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


@st.cache_resource
def get_client(api_key_value: str | None = None) -> genai.Client:
    """Create and cache the Gemini client once so it stays alive across reruns."""
    key = api_key_value or os.getenv("GEMINI_API_KEY")
    return genai.Client(api_key=key)


def main():
    # Configure Streamlit page layout and title
    st.set_page_config(page_title="Acme Gadgets Support", page_icon="🤖")

    st.title("Acme Gadgets Support Chatbot")
    st.caption("Prompt Injection Lab (Configurable Assistant & Defenses)")

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

        prompt_options = [
            "v1_never_reveal",
            "v2_staff_verification",
            "v3_hardened",
            "v4_no_secret",
        ]
        # Filter to keys that exist in SYSTEM_PROMPTS
        valid_options = [p for p in prompt_options if p in SYSTEM_PROMPTS]
        default_index = (
            valid_options.index("v2_staff_verification")
            if "v2_staff_verification" in valid_options
            else 0
        )

        selected_prompt_name = st.selectbox(
            "System Prompt",
            options=valid_options,
            index=default_index,
        )

        selected_model_name = st.text_input(
            "Model Name",
            value=default_model_name,
        )

        st.divider()
        st.subheader("Protection Layers (guards.py)")
        enable_input_guard = st.checkbox("Input guard", value=False)
        enable_output_guard = st.checkbox("Output guard", value=False)

        st.divider()
        st.header("Lab Controls")
        if st.button("Reset Conversation", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    # Initialize message history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Reset conversation if prompt, model, or guards configuration changed
    if "current_prompt_name" not in st.session_state:
        st.session_state.current_prompt_name = selected_prompt_name

    if "current_model_name" not in st.session_state:
        st.session_state.current_model_name = selected_model_name

    if "current_input_guard" not in st.session_state:
        st.session_state.current_input_guard = enable_input_guard

    if "current_output_guard" not in st.session_state:
        st.session_state.current_output_guard = enable_output_guard

    if (
        st.session_state.current_prompt_name != selected_prompt_name
        or st.session_state.current_model_name != selected_model_name
        or st.session_state.current_input_guard != enable_input_guard
        or st.session_state.current_output_guard != enable_output_guard
    ):
        st.session_state.messages = []
        st.session_state.current_prompt_name = selected_prompt_name
        st.session_state.current_model_name = selected_model_name
        st.session_state.current_input_guard = enable_input_guard
        st.session_state.current_output_guard = enable_output_guard

    # Render previous conversation history in the UI
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["text"])

    # Accept user input and get a response from Gemini
    if prompt := st.chat_input("Ask a question about Acme Gadgets..."):
        # Display the user message immediately
        with st.chat_message("user"):
            st.markdown(prompt)

        # Assemble active guards list
        active_guards = []
        if enable_input_guard:
            active_guards.append("input")
        if enable_output_guard:
            active_guards.append("output")

        # Generate assistant response
        with st.chat_message("assistant"):
            try:
                reply = get_bot_reply(
                    history=st.session_state.messages,
                    user_message=prompt,
                    system_prompt=SYSTEM_PROMPTS[selected_prompt_name],
                    model=selected_model_name,
                    client=client,
                    guards=active_guards,
                )
                st.markdown(reply)
                # Store new turn in session state history
                st.session_state.messages.append({"role": "user", "text": prompt})
                st.session_state.messages.append({"role": "assistant", "text": reply})
            except Exception as e:
                st.error(f"Error communicating with Gemini: {e}")


if __name__ == "__main__":
    main()
