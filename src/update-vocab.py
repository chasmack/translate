import datetime
import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

OAUTH2_CREDS = "credentials/credentials.json"
OAUTH2_TOKEN = "credentials/token.json"

DRIVE_PATH = "/Russian/Anki Vocab/"
LOCAL_PATH = "/home/charlie/russian/anki-vocab/"


def get_service():
    """Get credentials and create a Google Drive API service."""

    creds = None

    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
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


def get_folder_id(service, folder_name, parent_id):
    """Get the ID of a folder by its name and parent ID."""
    response = (
        service.files()
        .list(
            q=f"'{parent_id}' in parents and name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder'",
            spaces="drive",
            fields="files(id, name)"
        )
        .execute()
    )
    files = response.get('files', [])
    if len(files) == 0:
        # Folder not found
        return None             
    elif len(files) == 1:
        # Folder found, return its ID
        return files[0]['id']   
    else:
        raise ValueError(f"Multiple folders with the name '{folder_name}' found in the root.")


def get_files_in_folder(service, folder_id):
    """Get all Google Docs files in a folder by its ID."""

    files = []
    page_token = None
    while True:
        response = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.document'",
                spaces="drive",
                fields="nextPageToken, files(id, name, modifiedTime)",
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

    utc_offset = datetime.datetime.now().astimezone().utcoffset()
    
    for drive_file in files:
        drive_file_name = drive_file['name']
        local_file_name = drive_file_name.replace(" ", "_") + ".rus"
        local_file_path = os.path.join(LOCAL_PATH, local_file_name)

        drive_modified_time_str = drive_file['modifiedTime']
        drive_modified_time = datetime.datetime.fromisoformat(drive_modified_time_str[:-1])  # Remove 'Z' and parse

        if os.path.exists(local_file_path) and os.path.isfile(local_file_path):
            local_timestamp = os.path.getmtime(local_file_path)
            local_modified_time = datetime.datetime.fromtimestamp(local_timestamp) - utc_offset

            print(f"{drive_file_name}: ", end="")
            # print(f"  drive: {drive_modified_time.strftime('%Y-%m-%d %H:%M:%S')}")
            # print(f"  local: {local_modified_time.strftime('%Y-%m-%d %H:%M:%S')}")

            if drive_modified_time > local_modified_time:
                print("Updating...")
                with open(local_file_path, "wb") as f:
                    fh = service.files().export_media(
                            fileId=drive_file["id"], mimeType="text/plain"
                        ).execute()
                    f.write(fh)
            else:
                print("Up to date")
                
        else:
            print(f"{drive_file_name}: ", end="")
            # print(f"  drive: {drive_modified_time.strftime('%Y-%m-%d %H:%M:%S')}")
            # print(f"  local: None")
            print("Downloading...")
            with open(local_file_path, "wb") as f:
                fh = service.files().export_media(
                        fileId=drive_file["id"], mimeType="text/plain"
                    ).execute()
                f.write(fh)


def main():

    service = get_service()
    folders = DRIVE_PATH.strip("/").split("/")
        
    folder_id = None
    for folder in folders:
        if folder_id is None:
            parent_id = "root"
        else:
            parent_id = folder_id
        folder_id = get_folder_id(service, folder, parent_id)
        if folder_id is None:
            print(f"Folder '{folder}' not found.")
            return
        # else:
        #     print(f"Found folder '{folder}' with ID: {folder_id}")

    files = get_files_in_folder(service, folder_id)
    
    update_vocab(service, files)


if __name__ == "__main__":
  
    main()
