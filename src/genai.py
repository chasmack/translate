import os
import json
from pydantic import BaseModel, Field
from typing import List, Optional


from google import genai


GEMINI_API_KEY = "/home/charlie/dev/translate/credentials/gemini_api_key.txt"


class AnkiNote(BaseModel):
    russian: str = Field(
        description="The original unmodified russian text provided in the input."
    )
    section: str = Field(
        description="Copy of the unmodified section name provided in the input.",
    )
    stressed_russian: str = Field(
        default=None,
        description="The russian text input with acute accents on stressed vowels.",
    )
    romanize: str = Field(
        default=None, description="Latin transliteration using the BGN/PCGN system."
    )
    english: str = Field(
        default=None, description="The English translation of the russian text."
    )
    spelling_error: Optional[str] = Field(
        default=None,
        description="If a spelling error is detected in russian text, describe it. Otherwise, null.",
    )


class AnkiNoteList(BaseModel):
    notes: List[AnkiNote]


system_instruction = """
    You are a Russian linguistic expert. Process the provided JSON list of Russian words and phrases.

    RULES:
    1. PRIMARY CHECK: For each item, verify the spelling of 'russian'.
    2. IF MISSPELLED: 
       - Populate 'spelling_error' with a brief explanation.
       - You MUST leave 'stressed_russian', 'romanize', and 'english' unpopulated.
       - You MUST still echo the original 'russian' and 'section' fields.
    3. IF CORRECT:
       - Set 'spelling_error' to a JSON null.
       - STRESSED: Populate 'stressed_russian' using the combining acute accent (U+0301).
       - ROMANIZE: Use BGN/PCGN style (e.g., 'щ'->'shch', 'й'->'y', 'ё'->'yo', 'ь'->').
       - TRANSLATE: Provide the 'english' translation.
    4. ECHO: Always return the 'section' and 'russian' fields exactly as they were received.
"""

input_data = json.dumps(
    [
        {"russian": "один", "section": "Numbers"},
        {"russian": "цетыре", "section": "Numbers"},
        {"russian": "бежать", "section": "Verbs"},
    ],
    ensure_ascii=False,
)

request_prompt = f"Process these Russian texts according to the schema: {input_data}"

try:
    with open(GEMINI_API_KEY, "r") as f:
        key = f.read()

except FileNotFoundError:
    print(f"Error: API Key File '{GEMINI_API_KEY}' not found")
except Exception as e:
    print(f"API Key File error: {e}")

client = genai.Client(api_key=key)

response = client.models.generate_content(
    model="gemini-2.5-flash-lite",
    contents=request_prompt,
    config={
        "response_mime_type": "application/json",
        "response_json_schema": AnkiNoteList.model_json_schema(),
        "system_instruction": system_instruction,
    },
)

# print(
#     f"response: {json.dumps(json.loads(response.text), ensure_ascii=False, indent=2)}"
# )

raw_data = AnkiNoteList.model_validate_json(response.text)

for note in raw_data.notes:
    print(f"{note}")
    if note.spelling_error is not None:
        print(f"Error in {note.section}:'{note.russian}': {note.spelling_error}")
