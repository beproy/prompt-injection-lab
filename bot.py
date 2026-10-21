# bot.py
# Core model interaction logic for the Acme Gadgets chatbot.
# Contains no Streamlit code so it can be used by app.py and evaluate.py.

import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

from prompts import SYSTEM_PROMPTS

load_dotenv()


def get_bot_reply(
    history: list[dict],
    user_message: str,
    system_prompt: str | None = None,
    model: str | None = None,
    client: genai.Client | None = None,
) -> str:
    """Send system prompt and conversation history to Gemini and return reply text.

    This function contains no Streamlit code so it can be safely reused in evaluation scripts.
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
