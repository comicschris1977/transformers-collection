"""
One-time script to pull the Transformers collection Google Sheet and save as CSV.
Uses OAuth2 credentials from the Email Helper project.
Will open a browser for Sheets permission if not yet authorized.
"""

import csv
import json
import os
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

CREDENTIALS_FILE = r"C:\Projects\Email Helper\credentials.json"
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "..", "sheets_token.json")
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), "..", "collection_raw.csv")

# Use the write scope across all scripts so the shared token doesn't get into
# a "readonly was issued, now write is asked" refresh-error loop.  Read is a
# subset of write, so this still works for fetch-only use.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

SHEET_ID = "1CuOqorcf4HISBHVAE0DdECzDICNo-FW0w53LjCwu92w"
GID = "0"


def get_credentials():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return creds


def fetch_sheet(creds):
    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SHEET_ID, range="A1:ZZ").execute()
    return result.get("values", [])


def save_csv(rows):
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    print(f"Saved {len(rows) - 1} rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    print("Authenticating with Google Sheets...")
    creds = get_credentials()
    print("Fetching sheet data...")
    rows = fetch_sheet(creds)
    if not rows:
        print("No data found in sheet.")
        sys.exit(1)
    print(f"Found {len(rows)} rows (including header). First row: {rows[0]}")
    save_csv(rows)
    print("Done.")
