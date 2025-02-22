# tts.py - text-to-speech examples

import os
import argparse
import subprocess

from google.cloud import texttospeech

MPV_EXEC = ['/usr/bin/mpv', '-', '--really-quiet']


def tts(textfile, outfile, args):

    # Initialize the tts client
    client = texttospeech.TextToSpeechClient()

    with open(textfile, 'r') as f:
        text = f.read()

    if args.ssml:
        synthesis_input = texttospeech.SynthesisInput(ssml=text)
    else:
        synthesis_input = texttospeech.SynthesisInput(text=text)

    # Voice selection parameters
    voice_params = {
        'language_code': 'ru-RU',
        'name': args.voice_name,
        'ssml_gender': getattr(
            texttospeech.SsmlVoiceGender, args.voice_ssml_gender)
        if args.voice_ssml_gender else None
    }

    voice = texttospeech.VoiceSelectionParams(mapping=voice_params)

    # Audio configuration parameters
    config_params = {
        'speaking_rate': args.speaking_rate,
        'pitch': args.pitch,
    }

    if outfile == '-':
        # Generate an mp3 file for the mpv player
        config_params['audio_encoding'] = texttospeech.AudioEncoding.MP3
    else:
        match os.path.splitext(outfile)[1].upper():
            case '.MP3':
                config_params['audio_encoding'] = texttospeech.AudioEncoding.MP3
            case '.WAV':
                config_params['audio_encoding'] = texttospeech.AudioEncoding.LINEAR16
            case '.OGG':
                config_params['audio_encoding'] = texttospeech.AudioEncoding.OGG_OPUS
            case _:
                raise ValueError(f"Invalid encoding format: {outfile}")

    audio_config = texttospeech.AudioConfig(mapping=config_params)

    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config,
    )

    if outfile == '-':
        # pipe data to the mpv player
        proc = subprocess.Popen(MPV_EXEC,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)

        print("Playing results... ", end='', flush=True)
        stderr = proc.communicate(input=response.audio_content)[1]
        print("done.")

        if stderr:
            print(f"Error: {stderr.decode('utf-8')}")

    else:
        with open(outfile, mode='wb') as f:
            f.write(response.audio_content)

        print("Done.")


def list_voices():
    client = texttospeech.TextToSpeechClient()

    # Performs the list voices request
    voices = client.list_voices()

    for voice in voices.voices:
        # Display the voice's name. Example: tpc-vocoded
        print(f"Name: {voice.name}")

        # Display the supported language codes for this voice. Example: "en-US"
        for language_code in voice.language_codes:
            print(f"Supported language: {language_code}")

        ssml_gender = texttospeech.SsmlVoiceGender(voice.ssml_gender)

        # Display the SSML Voice Gender
        print(f"SSML Voice Gender: {ssml_gender.name}")

        # Display the natural sample rate hertz for this voice. Example: 24000
        print(f"Natural Sample Rate Hertz: {voice.natural_sample_rate_hertz}\n")


if __name__ == "__main__":

    # list_voices()
    # exit()

    parser = argparse.ArgumentParser(description="Synthesize Russian speech")

    parser.add_argument("textfile", help="Russian words and phrases")
    parser.add_argument("outfile", help="audio output file or '-' to send output to player")

    parser.add_argument("--ssml", action="store_true", help="enable SSML text input")
    parser.add_argument("--voice_name", help="name of the voice")
    parser.add_argument("--voice_ssml_gender", help="preferred gender of voice")
    parser.add_argument("--speaking_rate", type=float,
                        help="speaking rates between 0.25 and 4.0")
    parser.add_argument("--pitch", type=float,
                        help="speaking pitch between 20.0 and -20.0 (semitones)")

    parser.add_argument("--verbose", "-v", action="store_true",
                        help="increase diagnostic output")
    args = parser.parse_args()

    if args.verbose:
        print(args)

    tts(args.textfile, args.outfile, args)
