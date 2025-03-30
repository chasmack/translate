"""
Module: update-vocab.py

Description:
    This module provides functionality to synchronize Russian vocabulary files
    between a Google Drive folder and a local file system directory. It leverages
    the Google Drive API to interact with Google Drive and manage file
    transfers.

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
    - Configure the following constants:
        - SCOPES: The required Google Drive API scopes.
        - DRIVE_PATH: The path to the vocabulary folder in Google Drive.
        - FS_PATH: The local file system path to the vocabulary directory.
    - Set the environment variables:
        - OAUTH2_CREDS: Path to the OAuth 2.0 credentials JSON file.
        - OAUTH2_TOKEN: Path to the OAuth 2.0 token JSON file.
    - Run the script directly: `python update-vocab.py`

Functions:
    - get_service(): Authenticates with Google Drive and returns a Drive API
        service object.
    - get_folder_id(service, folder_name, parent_id): Retrieves the ID of a
        folder in Google Drive.
    - get_files_in_folder(service, folder_id): Lists files in a specified
        Google Drive folder.
    - update_vocab(service, files): Compares and synchronizes files between
        Google Drive and the local file system.
    - export_drive_file(service, drive_file, out_file): Exports a Google Docs
        file.
    - main(): Orchestrates the overall process of folder navigation, file
        listing, and synchronization.

Notes:
    - The script assumes that each Google Doc in the Drive folder corresponds
        to a local file with the same name (spaces replaced by underscores) and
        a ".rus" extension.
    - The script exports Google Docs as plain text files.
    - The script will create the `token.json` file if it does not exist.
    - The script will prompt the user to authenticate if the `token.json` is
        invalid or missing.
"""

import os
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

OAUTH2_CREDS = os.environ.get("OAUTH2_CREDS")
OAUTH2_TOKEN = os.environ.get("OAUTH2_TOKEN")

if not OAUTH2_CREDS or not OAUTH2_TOKEN:
    raise ValueError("OAUTH2_CREDS and OAUTH2_TOKEN environment variables not set.")

DRIVE_PATH = "/Russian/Anki Vocab/"
FS_PATH = "/home/charlie/russian/anki-vocab/"


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


def get_folder_id(service, folder_name, parent_id=None):
    """Get the ID of a folder using its name and parent ID."""

    # Folder hierarchy starts at "root"
    if parent_id is None:
        parent_id = "root"

    q = f"name = '{folder_name}' and '{parent_id}' in parents"
    q += " and mimeType = 'application/vnd.google-apps.folder'"

    response = (
        service.files().list(q=q, spaces="drive", fields="files(id, name)").execute()
    )
    files = response.get("files", [])
    if len(files) == 0:
        # Folder not found
        return None
    elif len(files) == 1:
        # Folder found, return its ID
        return files[0]["id"]
    else:
        raise ValueError(
            f"Multiple folders found: name='{folder_name}' parent='{parent_id}"
        )


def get_files_in_folder(service, folder_id):
    """Get all Google Docs files in a folder by its ID."""

    files = []
    page_token = None
    q = f"'{folder_id}' in parents"
    q += " and trashed = false"
    q += " and mimeType = 'application/vnd.google-apps.document'"

    while True:
        response = (
            service.files()
            .list(
                q=q,
                spaces="drive",
                fields="nextPageToken, files(id, name, modifiedTime)",
                orderBy="modifiedTime",
                pageToken=page_token,
            )
            .execute()
        )
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken", None)
        if page_token is None:
            break

    return files


def update_vocab(service, files):
    """Update local text files with corresponding Google Docs on Drive."""

    for drive_file in files:
        drive_file_name = drive_file["name"]
        fs_file_name = drive_file_name.replace(" ", "_") + ".rus"
        fs_file_path = os.path.join(FS_PATH, fs_file_name)

        # Google Drive modification time strings are UTC.

        drive_mod_time_str = drive_file["modifiedTime"]
        # Prior to Python 3.11 fromisoformat() did not support UTC offsets.
        # drive_mod_time = datetime.fromisoformat(drive_mod_time_str, tz=timezone.utc)
        iso_format = "%Y-%m-%dT%H:%M:%S.%f%z"
        drive_mod_time = datetime.strptime(drive_mod_time_str, iso_format)

        if os.path.exists(fs_file_path) and os.path.isfile(fs_file_path):

            # Local modification timestamps are local time and converted to UTC.
            fs_mod_timestamp = os.path.getmtime(fs_file_path)
            fs_mod_time = datetime.fromtimestamp(fs_mod_timestamp, tz=timezone.utc)

            print(f"{drive_file_name}: ", end="")
            if drive_mod_time > fs_mod_time:
                print("Updating...")
                export_drive_file(service, drive_file, fs_file_path)
            else:
                print("Up to date")

            # print(f"  drive: {drive_mod_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            # print(f"  local: {fs_mod_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        else:
            print(f"{drive_file_name}: Downloading...")
            export_drive_file(service, drive_file, fs_file_path)

            # with open(fs_file_path, "wb") as f:
            #     fh = service.files().export_media(
            #             fileId=drive_file["id"], mimeType="text/plain"
            #         ).execute()
            #     f.write(fh)

            # print(f"  drive: {drive_mod_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            # print(f"  local: None")


def export_drive_file(service, drive_file, out_file):
    """Export a Google Docs file to plain text."""

    # Download content from Drive stripping any BOM.
    content = (
        service.files()
        .export_media(fileId=drive_file["id"], mimeType="text/plain")
        .execute()
        .decode("utf-8-sig")
    )

    with open(out_file, "w") as f:
        f.write(content)


def main():
    """Initialize Google Drive API service and update local files."""

    service = get_service()

    folder_path = DRIVE_PATH.strip("/").split("/")

    # Navigate to the target folder on Drive.
    folder_id = None
    for folder in folder_path:
        parent_id = folder_id
        folder_id = get_folder_id(service, folder, parent_id)
        if folder_id is None:
            print(f"Folder '{folder}' not found.")
            return

    files = get_files_in_folder(service, folder_id)

    update_vocab(service, files)


if __name__ == "__main__":

    main()
