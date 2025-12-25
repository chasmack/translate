import os
import json
from pydantic import BaseModel, Field
from typing import List, Optional

from google import genai


GEMINI_API_KEY = "/home/charlie/dev/translate/credentials/gemini_translate_key.txt"
GEMINI_AI_MODEL = "gemini-2.5-pro"
GEMINI_INPUT_CHUNK_SIZE = 20

DEBUG = True


class APIConfigError(Exception):
    pass


# Data schema for the Anki base note. Only fields required for AI processing
# are included here to keep down clutter that could confule the AI.
# The stressed_russian, romanize and english fields are optional. If a spelling
# error is detected Gemini is requested to leave these fields unpopulated.
class AnkiBaseNote(BaseModel):
    russian: str = Field(
        description="The original unmodified russian text provided in the input."
    )
    section: str = Field(
        description="Copy of the unmodified section name provided in the input.",
    )
    stressed_russian: Optional[str] = Field(
        default=None,
        description="The russian text with acute accents (U+0301) on stressed vowels.",
    )
    romanize: Optional[str] = Field(
        default=None, description="Latin transliteration using the BGN/PCGN system."
    )
    english: Optional[str] = Field(
        default=None, description="The English translation of the russian text."
    )
    spelling_error: Optional[str] = Field(
        default=None,
        description="If a spelling error is detected in russian, describe it. Otherwise, null.",
    )


# A list of Anki base notes for JSON schema defination and data validation from Gemini
class AnkiNoteList(BaseModel):
    notes: List[AnkiBaseNote]


# Model for the full Anki note type.
class AnkiNote(AnkiBaseNote):
    audio: Optional[str] = Field(
        default=None,
        description="The filename of the mp3 audio clip saved to the Anki media folder.",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Supplemental information about usage of the Russian.",
    )


system_instruction = """
You are a Russian linguist. Process the JSON list of Russian texts.

RULES:
1. PRIMARY CHECK: Verify the spelling of 'russian'.
2. IF CORRECT or MISPELLED and 'section' is labled "Nonstandard Spelling":
    - Set 'spelling_error' to a JSON null.
    - STRESSED: Populate 'stressed_russian' using the combining acute accent (U+0301).
    - ROMANIZE: Use BGN/PCGN style (e.g., 'щ'->'shch', 'й'->'y', 'ё'->'yo', 'ь'->').
    - TRANSLATE: Provide the 'english' translation.
    - Nonstandard Spelling: Do not add extra commentary to generated fields.
3. IF MISSPELLED: 
    - Populate 'spelling_error' with a brief explanation.
    - Leave 'stressed_russian', 'romanize', and 'english' fields unpopulated.
    - Echo original 'russian' and 'section' fields.
4. ECHO: Return the 'section' and 'russian' fields exactly as they were received.
"""

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

system_instruction = """
Role: Russian Linguist.
COMMANDS:
  CHECK: Verify russian spelling and case. Ignore capitalization and punctuation.
  BYPASS: If section == "Nonstandard Spelling", ignore errors; process as correct.
If CORRECT or BYPASS:
  spelling_error: null
  stressed_russian: Add $U+0301$ to stressed vowels
  romanize: Use BGN/PCGN
  english: Translate. No extra commentary
If MISSPELLED:
  spelling_error: Brief explanation.
  stressed_russian, romanize, english: null
ECHO: Always return original russian and section.
"""

# A list of test data with russian and section.
texts = []
rus = "академия; автобус; банк; бар; врач; газета; девочка; директор".split("; ")
texts += list(zip(rus, ["Words 1"] * len(rus)))
texts += [("офисс", "Nonstandard Spelling")]
rus = "ноль; один; два; три; цетыре; пять".split("; ")
texts += list(zip(rus, ["Numbers"] * len(rus)))
rus = (
    "Привет! Как дела?; У меня всё отлично! Как у тебя?; "
    + "У меня всё хорошо! Я сейчас спешу. Пока, увидимся!; "
    #    + "Это Ольга Петровна - она моя мама.; Это Иван Иванович - он мой папа.; "
    + "Это Ольга Петровна - она моя мама.; Это Иван Иванович - он мои папа.; "
    + "Это Артём и Коля. они мои дети.; Пока! до встречи!"
).split("; ")
texts += list(zip(rus, ["Dialogues 1"] * len(rus)))

# Get the API key from the key file.
try:
    with open(GEMINI_API_KEY, "r", encoding="utf-8") as f:
        api_key = f.read()
except FileNotFoundError as e:
    raise APIConfigError(f"Error: API Key File '{GEMINI_API_KEY}' not found") from e
except Exception as e:
    raise APIConfigError(f"Error: API Key File error: {e}") from e

# Initialize the Gemini client
ai_client = genai.Client(api_key=api_key)

# JSON keys for the request data
request_keys = ["russian", "section"]

# A list to accumulate processed note data.
notes = []

# First process all input texts through Gemini to generate
# translation/transliteration and check for soelling errors.

print(f"Number of texts: {len(texts)}")
# print(f"Texts: {texts}\n")

for i in range(0, len(texts), GEMINI_INPUT_CHUNK_SIZE):

    request_data = texts[i : i + GEMINI_INPUT_CHUNK_SIZE]
    request_data = [dict(zip(request_keys, values)) for values in request_data]

    request_prompt = (
        f"Process these Russian texts according to the schema: "
        + json.dumps(request_data, ensure_ascii=False)
    )

    print(f"Request size: {len(request_data)}")
    # print(f"Request prompt:\n{request_prompt}\n")

    response = ai_client.models.generate_content(
        model=GEMINI_AI_MODEL,
        contents=request_prompt,
        config={
            "response_mime_type": "application/json",
            "response_json_schema": AnkiNoteList.model_json_schema(),
            "system_instruction": system_instruction,
        },
    )

    print("Done.")
    # print(
    #     f"response: {json.dumps(json.loads(response.text), ensure_ascii=False, indent=2)}"
    # )

    # Validate response and change to full ANkiNote model
    for note in AnkiNoteList.model_validate_json(response.text).notes:
        if DEBUG:
            # Ensure spelling_error and data fields are mutually exclusive
            for field in [note.stressed_russian, note.romanize, note.english]:
                assert (note.spelling_error is None) != (
                    field is None
                ), f"AI data error: 'spelling_error' and '{field}': {note}"
        notes.append(AnkiNote(**note.model_dump()))

# Check for spelling errors.
spelling_errors = []
for note in notes:
    if note.spelling_error is not None:
        spelling_errors.append(
            f'{note.section}: "{note.russian}" -- {note.spelling_error}'
        )

if spelling_errors:
    print("\n".join(spelling_errors))
    exit()
else:
    # Continue to TTS generation
    pass

# for note in notes:
#     print(f"{note}")
