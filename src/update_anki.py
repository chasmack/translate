"""
Module: update-anki.py

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
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from anki_import import translate_text

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

OAUTH2_CREDS = os.environ.get("OAUTH2_CREDS")
OAUTH2_TOKEN = os.environ.get("OAUTH2_TOKEN")

if not OAUTH2_CREDS or not OAUTH2_TOKEN:
    raise ValueError("OAUTH2_CREDS and OAUTH2_TOKEN environment variables not set.")

DRIVE_PATH = "/Russian/Anki Vocab/"
FS_PATH = "/home/charlie/russian/anki-vocab/"

BRAIDEN = True
if BRAIDEN:
    ANKI_NOTETYPE = "Braiden Vocab"
    ANKI_PARENT_DECK = "Russian - Braiden"
    ANKI_SOUNDFILE_PREFIX = "BRAIDEN_VOCAB"
else:
    ANKI_NOTETYPE = "RT Vocab"
    ANKI_PARENT_DECK = "Russian"
    ANKI_SOUNDFILE_PREFIX = "RT_VOCAB"


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


def update_local_files(service, file):
    """Update local text file with corresponding Drive file."""

    # Replace space with underbar and add the local path
    file["localName"] = os.path.join(FS_PATH, file["name"].replace(" ", "_"))

    # Google Drive modification time strings are UTC.
    # Prior to Python 3.11 fromisoformat() did not support UTC offsets.
    # file["modifiedTime"] = datetime.fromisoformat(file["modifiedTime"], tz=timezone.utc)
    iso_format = "%Y-%m-%dT%H:%M:%S.%f%z"
    file["modifiedTime"] = datetime.strptime(file["modifiedTime"], iso_format)

    local_name = file["localName"] + ".rus"
    if os.path.exists(local_name) and os.path.isfile(local_name):

        # Local modification timestamps are local time and converted to UTC.
        local_modtime = os.path.getmtime(local_name)
        local_modtime = datetime.fromtimestamp(local_modtime, tz=timezone.utc)

        if file["modifiedTime"] < local_modtime:
            # local content is up to date
            file["words"] = []

        else:
            # Drive file has been modified, compare contents
            drive_content = get_drive_content(service, file)
            drive_words = parse_content(drive_content)
            with open(local_name, "r") as f:
                local_content = f.read()
            local_words = parse_content(local_content)

            # new words for Anki import
            file["words"] = list(set(drive_words) - set(local_words))

            # update the local file
            with open(local_name, "w") as f:
                f.write(drive_content)

    else:
        # new Drive file, get content and download file
        drive_content = get_drive_content(service, file)
        file["words"] = parse_content(drive_content)
        with open(local_name, "w") as f:
            f.write(drive_content)


def get_drive_content(service, file):
    """Export a Google Docs file contents as plain text."""

    # Download content from Drive stripping any BOM.
    content = (
        service.files()
        .export_media(fileId=file["id"], mimeType="text/plain")
        .execute()
        .decode("utf-8-sig")
    )

    return content


def parse_content(content):
    """Parse text for semicolon delimited words and phrases."""

    # build a list of vocabulary words and phrases with tags
    words = []

    # section headers added as tags
    tags = ""

    for line in content.splitlines():
        line = line.strip()
        if len(line) == 0:
            continue
        if line.startswith("#"):
            tags = line[1:].strip()
            continue

        # split line at semicolons
        for word in line.split(";"):
            # watch for final semicolon
            if len(word) > 0:
                words.append((word.strip(), tags))

    # remove duplicates
    words = list(dict.fromkeys(words).keys())

    return words


def main():
    """Initialize Google Drive API service and update local files."""

    service = get_service()

    folder_id = get_folder_id(service, DRIVE_PATH)

    files = get_drive_files(service, folder_id)

    for file in files:
        update_local_files(service, file)

        if len(file["words"]) > 0:
            translate_text(
                file["words"],
                file["localName"] + ".txt",
                deckname="::".join([ANKI_PARENT_DECK, file["name"]]),
                notetype=ANKI_NOTETYPE,
                romanize=True,
                soundfile_prefix=ANKI_SOUNDFILE_PREFIX,
            )
            # print(f"{file["name"]}: {len(file["words"])} records created.")


if __name__ == "__main__":

    main()
