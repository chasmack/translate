"""
Module: anki_update.py

Description:
    This module provides functionality to synchronize Russian vocabulary files
    between a Google Drive folder and a local file system directory and generate
    Anki text import files from the vocabulary word lists.

Key Features:
    - Authentication: Handles OAuth 2.0 authentication with Google Drive using
        credentials stored in JSON files.
    - Folder Navigation: Navigates a specified folder path within Google Drive
        to locate the target vocabulary folder.
    - File Listing: Retrieves a list of Google Docs files within the target
        folder, including their names and last modified timestamps.
    - File Comparison: Compares the last modified timestamps of files in Google
        Drive with corresponding files in the local file system.
    - File Synchronization:
        - Downloads a file from Google Drive to the local file system if the
        local file is missing.
        - Updates a local file with the content from Google Drive if the Drive
        file has been modified more recently than the local file.
    - File Export: Exports Google Docs files from Google Drive as plain text
        files (.rus extension) to the local file system.
    - Error Handling: Includes basic error handling for missing folders and
        multiple folders with the same name.
    - Timezone Handling: Correctly handles timezone offsets when comparing
        timestamps.

Dependencies:
    - google-auth
    - google-auth-oauthlib
    - google-api-python-client
    - os
    - datetime

Usage:


Functions:


Notes:


"""

import os
import traceback
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from anki_import_ai import translate_text
from anki_import_ai import APIConfigError, InputTextSpellingError

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

OAUTH2_CREDS = os.environ.get("OAUTH2_CREDS")
OAUTH2_TOKEN = os.environ.get("OAUTH2_TOKEN")

if not OAUTH2_CREDS or not OAUTH2_TOKEN:
    raise ValueError("OAUTH2_CREDS and OAUTH2_TOKEN environment variables not set.")

DRIVE_PATH = "/Russian/Anki/"
FS_PATH = "/home/charlie/russian/anki/"

ANKI_PARENT_DECK = "Russian"
ANKI_NOTETYPE = "Russian Vocab"
ANKI_SOUNDFILE_PREFIX = "RUSSIAN_VOCAB"


def get_service():
    """Get credentials and create a Google Drive API service."""

    creds = None

    # The file token.json stores the user's access and refresh tokens,
    # and is created automatically when the authorization flow completes
    # for the first time.
    if os.path.exists(OAUTH2_TOKEN):
        creds = Credentials.from_authorized_user_file(OAUTH2_TOKEN, SCOPES)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH2_CREDS, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open(OAUTH2_TOKEN, "w") as token:
            token.write(creds.to_json())

    service = build("drive", "v3", credentials=creds)

    return service


def get_folder_id(service, path, parent_id=None):
    """Get the Drive folder ID using its full path."""

    # Default folder hierarchy starts at "root"
    if parent_id is None:
        parent_id = "root"

    for folder_name in path.strip("/").split("/"):
        q = f"name = '{folder_name}' and '{parent_id}' in parents"
        q += " and mimeType = 'application/vnd.google-apps.folder'"

        response = (
            service.files()
            .list(q=q, spaces="drive", fields="files(id, name)")
            .execute()
        )
        files = response.get("files", [])
        if len(files) == 0:
            raise ValueError(
                f"Folder not found: name='{folder_name}' parent='{parent_id}"
            )
        elif len(files) == 1:
            # Folder found
            folder_id = files[0]["id"]
        else:
            raise ValueError(
                f"Multiple folders found: name='{folder_name}' parent='{parent_id}"
            )
        # Update parent for next iteration
        parent_id = folder_id

    return folder_id


def get_drive_files(service, folder_id):
    """Get a list of Google Docs files in a Drive folder."""

    files = []

    q = f"'{folder_id}' in parents"
    q += " and trashed = false"
    q += " and mimeType = 'application/vnd.google-apps.document'"

    page_token = None
    while True:
        response = (
            service.files()
            .list(
                q=q,
                spaces="drive",
                fields="nextPageToken, files(name, id, modifiedTime)",
                orderBy="name",
                pageToken=page_token,
            )
            .execute()
        )
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken", None)
        if page_token is None:
            break

    return files


def get_drive_content(service, file):
    """Export a Google Docs file contents as plain text."""

    # Download content from Drive stripping any BOM.
    file["content"] = (
        service.files()
        .export_media(fileId=file["id"], mimeType="text/plain")
        .execute()
        .decode("utf-8-sig")
    )


def parse_content(content):
    """Parse content for semicolon delimited words and phrases."""

    # build a list of vocabulary words and phrases with section information
    texts = []

    # section headers added to each word
    section = ""

    for line in content.splitlines():
        line = line.strip()
        if len(line) == 0:
            continue
        if line.startswith("#"):
            section = line[1:].strip()
            continue

        # split line at semicolons
        for text in line.split(";"):
            # watch for blank words
            text = text.strip()
            if len(text) > 0:
                texts.append((text, section))

    # remove duplicates
    texts = list(dict.fromkeys(texts).keys())

    return texts


def diff_drive_content(service, file):
    """Compare Drive content with the corresponding local file."""

    # Google Drive modification time strings are UTC.
    # Prior to Python 3.11 fromisoformat() did not support UTC offsets.
    # file["modifiedTime"] = datetime.fromisoformat(file["modifiedTime"], tz=timezone.utc)
    iso_format = "%Y-%m-%dT%H:%M:%S.%f%z"
    file["modifiedTime"] = datetime.strptime(file["modifiedTime"], iso_format)

    local_path = f"{file['localPath']}.rus"
    if os.path.exists(local_path) and os.path.isfile(local_path):

        # Local modification timestamps are local time and converted to UTC.
        local_modtime = os.path.getmtime(local_path)
        local_modtime = datetime.fromtimestamp(local_modtime, tz=timezone.utc)

        if file["modifiedTime"] < local_modtime:
            # local content is up to date
            file["texts"] = []
            file["deletes"] = []
            file["content"] = ""

        else:
            # Drive file has been modified, compare and update contents

            get_drive_content(service, file)

            drive_texts = parse_content(file["content"])
            with open(local_path, "r") as f:
                local_content = f.read()
            local_texts = parse_content(local_content)

            # new words for Anki import
            file["texts"] = list(set(drive_texts) - set(local_texts))

            # words to be removed from the Anki deck
            file["deletes"] = list(set(local_texts) - set(drive_texts))

    else:
        # new Drive file, get the content
        get_drive_content(service, file)
        file["texts"] = parse_content(file["content"])
        file["deletes"] = []


def update_local_file(service, file):
    """Update local text file with corresponding Drive file."""

    local_name = file["localPath"] + ".rus"
    with open(local_name, "w") as f:
        f.write(file["content"])


def main():
    """Initialize Google Drive API service and update local files."""

    service = get_service()

    folder_id = get_folder_id(service, DRIVE_PATH)

    files = get_drive_files(service, folder_id)

    for file in files:

        # Replace space in Drive file name with underbar and add the local path
        file["localPath"] = os.path.join(FS_PATH, file["name"].replace(" ", "_"))

        diff_drive_content(service, file)
        deckname = "::".join([ANKI_PARENT_DECK, file["name"]])

        if len(file["texts"]) > 0:
            print(f"Processing {file['name']}")
            try:
                translate_text(
                    file["texts"],
                    file["localPath"] + ".txt",
                    deckname=deckname,
                    notetype=ANKI_NOTETYPE,
                    soundfile_prefix=ANKI_SOUNDFILE_PREFIX,
                )
            except APIConfigError as e:
                print(f"Gemini API Configuration Error: {e}")
                exit()
            except InputTextSpellingError as e:
                print(f"Spelling Errors:\n{e}")
                exit()
            except Exception as e:
                traceback.print_exc()
                exit()

        for text in file["deletes"]:
            russian, section = text
            print(f"Delete: deck:{deckname} section:{section} russian:{russian}")

        if file["content"]:
            # Drive file is either new or has been updated.
            update_local_file(service, file)

            n = len(file["texts"])
            print(
                f"{file['name']} updated, {n} {'note' if n == 1 else 'notes'} created."
            )


if __name__ == "__main__":

    main()
