import os, sys, html
from google.cloud import texttospeech

def tts(text, outfile):

    # Initialize the tts client
    client = texttospeech.TextToSpeechClient()

    synthesis_input = texttospeech.SynthesisInput(text=text)

    voice = texttospeech.VoiceSelectionParams(
        language_code="ru-RU",
        name="ru-RU-Wavenet-A",
        ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
    )

    file_ext = os.path.splitext(outfile)[1].lower()
    if file_ext == '.mp3':
        audio_encoding = texttospeech.AudioEncoding.MP3
    elif file_ext == '.wav':
        audio_encoding = texttospeech.AudioEncoding.LINEAR16
    elif file_ext == '.ogg':
        audio_encoding = texttospeech.AudioEncoding.OGG_OPUS
    else:
        raise ValueError(f"Bad encoding format: {file_ext}")

    audio_config = texttospeech.AudioConfig(audio_encoding=audio_encoding)

    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )

    with open(outfile, "wb") as out:
        out.write(response.audio_content)

if __name__ == "__main__":

    if len(sys.argv) != 3:
        print("Usage: tts infile outfile")
        exit()

    infile = sys.argv[1]
    outfile = sys.argv[2]

    text = ""
    with open(infile, 'r') as f:
        for line in f:
            text += line.strip()

    escaped_text = html.escape(text)
    print(text)
    print(escaped_text)
    tts(text, outfile)