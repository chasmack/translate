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

    # Voice parameters
    voice_params = dict()
    voice_params['language_code'] = 'ru-RU'
    match args.voice_name:
        case None:
            voice_params['name'] = 'ru-RU-Wavenet-A'
        case _:
            voice_params['name'] = args.voice_name
    match args.voice_ssml_gender:
        case None | "FEMALE":
            voice_params['ssml_gender'] = texttospeech.SsmlVoiceGender.FEMALE
        case "MALE":
            voice_params['ssml_gender'] = texttospeech.SsmlVoiceGender.MALE
        case "NeUTRAL":
            voice_params['ssml_gender'] = texttospeech.SsmlVoiceGender.NEUTRAL
        case _:
            raise ValueError(f"Invalid SSML Gender: {args.voice_ssml_gender}")

    voice = texttospeech.VoiceSelectionParams(mapping=voice_params)

    # Audio configuration parameters
    config_params = dict()

    if outfile == '-':
        # generate an mp3 file for mpv player
        config_params['audio_encoding'] = texttospeech.AudioEncoding.MP3
    else:
        match os.path.splitext(outfile)[1].upper():
            case '.MP3' | '-':
                config_params['audio_encoding'] = texttospeech.AudioEncoding.MP3
            case '.WAV':
                config_params['audio_encoding'] = texttospeech.AudioEncoding.LINEAR16
            case '.OGG':
                config_params['audio_encoding'] = texttospeech.AudioEncoding.OGG_OPUS
            case _:
                raise ValueError(f"Invalid encoding format: {outfile}")

        if (args.speaking_rate is None or
            args.speaking_rate >= 0.25 and args.speaking_rate <= 4.0):
            # speaking rate in range [0.25, 4.0] or None for default (1.0)
            config_params['speaking_rate'] = args.speaking_rate
        else:
            raise ValueError(f"Invalid speaking rate [0.25, 4.0]: {args.speaking_rate}")

    if (args.pitch is None or
        args.pitch >= -20.0 and args.pitch <= 20.0):
        # pitch in range [-20.0, 20.0] or None for default (0.0)
        config_params['pitch'] = args.pitch
    else:
        raise ValueError(f"Invalid pitch [-20.0, 20.0]: {args.pitch}")

    if (args.volume_gain_db is None or
        args.volume_gain_db >= -96.0 and args.volume_gain_db <= 16.0):
        # gain in range [-96.0, 16.0] (dB) or None for default (0.0)
        config_params['volume_gain_db'] = args.volume_gain_db
    else:
        raise ValueError(f"Invalid volume gain [-96.0, 16.0]: {args.volume_gain_db}")

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

        stderr = proc.communicate(input=response.audio_content)[1]

        if stderr:
            print(f"Error: {stderr.decode('utf-8')}")

    else:
        with open(outfile, mode='wb') as f:
            f.write(response.audio_content)

    print("Done")


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
    parser.add_argument("--list_voices", action="store_true", help="list available voices")
    parser.add_argument("--ssml", action="store_true", help="enable SSML text input")

    parser.add_argument("--voice_name", help="name of the voice")
    parser.add_argument("--voice_ssml_gender", help="preferred gender of voice")
    parser.add_argument("--speaking_rate", type=float,
                        help="speaking rates between 0.25 and 4.0")
    parser.add_argument("--pitch", type=float,
                        help="speaking pitch between 20.0 and -20.0 (semitones)")
    parser.add_argument("--volume_gain_db", type=float,
                        help="gain between -96.0 and 16.0 (dB)")

    parser.add_argument("--verbose", "-v", action="store_true",
                        help="increase diagnostic output")
    args = parser.parse_args()

    if args.verbose:
        print(args)

    tts(args.textfile, args.outfile, args)
