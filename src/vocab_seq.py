# vocab-seq.py - Translate Russian words and phrases to English and
# create an audio vocabulary lesson. SSML generated uses the <seq>
# element to sequence synthesized segments.
#

import os
import argparse
import xml.etree.ElementTree as ET
import subprocess

# Google Cloud Translation and Text-to-Speech libraries
from google.cloud import translate_v3 as translate
from google.cloud import texttospeech

# Google Cloud project ID for authorization
PROJECT_ID = "first-gc-tts-project"
PROJECT_PARENT = f"projects/{PROJECT_ID}/locations/global"

# Audio player
MPV_EXEC = ['/usr/bin/mpv', '-', '--really-quiet']

# Default voice names
VOICE_RUSSIAN_A = "ru-RU-Wavenet-A"
VOICE_RUSSIAN_B = "ru-RU-Wavenet-B"
VOICE_ENGLISH = "en-US-Standard-C"

# Delays between media elements
MEDIA_START_DELAY_RUSSIAN_A = '1200ms'
MEDIA_START_DELAY_RUSSIAN_B = '650ms'
MEDIA_START_DELAY_ENGLISH = '1200ms'

def make_lesson(args):

    # Get the list of russian words and phrases
    texts = []
    with open(args.textfile, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('#') or len(line) == 0:
                continue
            texts += [s.strip() for s in  line.split(',')]

    # Remove duplicates
    texts = list(dict.fromkeys(texts).keys())

    # Initialize the clients and the request parameters
    xlt_client = translate.TranslationServiceClient()
    tts_client = texttospeech.TextToSpeechClient()

    # Voice selection parameters
    voice_params = {
        'language_code': 'ru-RU',
    }

    voice_select = texttospeech.VoiceSelectionParams(mapping=voice_params)

    if args.verbose:
        print(f'Voice Select:\n{voice_select}')

    # Audio configuration parameters
    config_params = {
        'speaking_rate': args.speaking_rate,
        'pitch': args.pitch,
    }

    if args.outfile == '-':
        # Generate an mp3 file for the mpv player
        config_params['audio_encoding'] = texttospeech.AudioEncoding.MP3
    else:
        match os.path.splitext(args.outfile)[1].upper():
            case '.MP3':
                config_params['audio_encoding'] = texttospeech.AudioEncoding.MP3
            case '.WAV':
                config_params['audio_encoding'] = texttospeech.AudioEncoding.LINEAR16
            case '.OGG':
                config_params['audio_encoding'] = texttospeech.AudioEncoding.OGG_OPUS
            case _:
                raise ValueError(f"Invalid encoding format: {args.outfile}")

    audio_config = texttospeech.AudioConfig(mapping=config_params)

    if args.verbose:
        print(f'Audio Config:\n{audio_config}')

    # Make the translation request
    xlt_params = {
        'contents': texts,
        'source_language_code': 'ru',
        'target_language_code': 'en-US',
        'parent': PROJECT_PARENT,
    }
    request = translate.TranslateTextRequest(mapping=xlt_params)
    response = xlt_client.translate_text(request=request)
    texts = list(zip(texts, [t.translated_text for t in response.translations]))

    if args.verbose:
        print('Translations:')
        for rus, eng in texts:
            print(f"{rus} => {eng}")
        print('\n')

    # Create three media elements for each word/phrase
    # to synthesize Russian in voices A and B and English.
    # Media elements take the form -
    #
    # <media xml:id="rus-01a" begin="1000ms">
    #   <speak>
    #     <prosody rate="85% pitch="-2st" volume="+3dB"
    #       <voice name="ru-RU-Wavenet-B">
    #         Медведь
    #       </voice>
    #     </prosody>
    #   </speak>
    # </media>

    prosody_attribs = {}
    if args.speaking_rate is not None:
        prosody_attribs['rate'] = f'{int(round(100 * args.speaking_rate))}%'
    if args.pitch is not None:
        prosody_attribs['pitch'] = f'{args.pitch:+}st'
    if args.volume_gain_db is not None:
        prosody_attribs['volume'] = f'{args.volume_gain_db:+}dB'

     # Initialize the XML root elements
    root = ET.Element('speak')
    seq = ET.SubElement(root, 'seq')

    for i in range(len(texts)):
        rus, eng = texts[i]

        # Russian A media element
        media = ET.Element('media',
                          attrib={
                              'xml:id': f'rus{i:02}a',
                              'begin': MEDIA_START_DELAY_RUSSIAN_A,
                          })
        speak = ET.SubElement(media, 'speak')
        if prosody_attribs:
            prosody = ET.SubElement(speak, 'prosody', attrib=prosody_attribs)
        else:
            # skip the prosody element if the attributes are empty
            prosody = speak
        voice = ET.SubElement(prosody, 'voice',
                                attrib={'name': VOICE_RUSSIAN_A})
        voice.text = rus
        seq.append(media)

        # Russian B media element
        media = ET.Element('media',
                          attrib={
                              'xml:id': f'rus{i:02}b',
                              'begin': f'rus{i:02}a.end+{MEDIA_START_DELAY_RUSSIAN_B}',
                          })
        speak = ET.SubElement(media, 'speak')
        if prosody_attribs:
            prosody = ET.SubElement(speak, 'prosody', attrib=prosody_attribs)
        else:
            # skip the prosody element if the attributes are empty
            prosody = speak
        voice = ET.SubElement(prosody, 'voice',
                                attrib={'name': VOICE_RUSSIAN_B})
        voice.text = rus
        seq.append(media)

        # English translation media element
        media = ET.Element('media',
                          attrib={
                              'xml:id': f'eng{i:02}',
                              'begin': f'rus{i:02}b.end+{MEDIA_START_DELAY_ENGLISH}',
                          })
        speak = ET.SubElement(media, 'speak')
        if prosody_attribs:
            prosody = ET.SubElement(speak, 'prosody', attrib=prosody_attribs)
        else:
            # skip the prosody element if the attributes are empty
            prosody = speak
        voice = ET.SubElement(prosody, 'voice',
                                attrib={'name': VOICE_ENGLISH})
        voice.text = eng
        seq.append(media)

    if args.verbose:
        ET.indent(root, space="  ")

    xml = ET.tostring(root,
                      encoding='unicode',
                      method='xml',
                      xml_declaration=True)

    if args.verbose:
        print(xml + '\n')

    response = tts_client.synthesize_speech(
        input=texttospeech.SynthesisInput(mapping={'ssml': xml}),
        voice=voice_select,
        audio_config=audio_config,)

    if args.outfile == '-':
        # pipe data to the mpv player
        proc = subprocess.Popen(MPV_EXEC,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE)

        print("Playing results... ", end='', flush=True)
        stderr = proc.communicate(input=response.audio_content)[1]
        print("done.")

        if stderr:
            print(f"Error: {stderr.decode('utf-8')}")

    else:
        with open(args.outfile, mode='wb') as f:
            f.write(response.audio_content)

        print("Done.")


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Generate Russian vocabulary lesson")

    # Required arguments
    parser.add_argument("textfile", help="Russian words and phrases")
    parser.add_argument("outfile",
                        help="audio output file or '-' to send to player")

    # Options
    parser.add_argument("--speaking_rate", type=float,
                        help="speaking rates between 0.25 and 4.0")
    parser.add_argument("--pitch", type=int,
                        help="pitch between -20 and +20 (semitones)")
    parser.add_argument("--volume_gain_db", type=int,
                        help="volume between -96 and +16 (decibels)")

    # Debugging
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="increase diagnostic output")
    args = parser.parse_args()

    if args.verbose:
        print(f'\nCommand line arguments:\n{args}\n')

    make_lesson(args)


