# translate

Translate Russian words and phrases to English with Google Cloud Translate 
and Text-to-Speech. The results are used to create Russian-English note data
for Anki flashcards. 

The input text file consists of Russian words and phrases to be translated.
Each line can have one or more words or phrases separated by commas.
Blank lines and lines starting with hash (#) are ignored.

The output file is a semicolon delimited text file compatible with Anki text import.

The Anki note records should have following fields -

  * Russian - the Russian word or phrase to be translated from the input textfile
  * Romanize - a romanized representation of the Russian generated by Translate
  * Audio - an MP3 sound clip of the Russian generated by Text-to-Speech
  * English - an English translation of the Russian generated by Translate
  * Notes - additional information on translation and usage not populated by this app

Sound files are saved to the default Anki Media Folder (collection.media) or a
location specified on the command line. A sound filename prefix must be specified
on the command line. A sequential numerical index is added to the sound filename.
