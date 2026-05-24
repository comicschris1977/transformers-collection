"""
Fix spelling errors in the Google Sheet to match DB corrections.
Requires Sheets read+write scope — will prompt for re-auth if needed.
"""
import os, sys
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

CREDENTIALS_FILE = r"C:\Projects\Email Helper\credentials.json"
TOKEN_FILE       = os.path.join(os.path.dirname(__file__), "..", "sheets_token.json")
SHEET_ID         = "1CuOqorcf4HISBHVAE0DdECzDICNo-FW0w53LjCwu92w"

# Need write scope this time
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

CORRECTIONS = {
    # wrong spelling  : correct spelling
    "Beachcomer":      "Beachcomber",
    "Blugeon":         "Bludgeon",
    "Bubblebee":       "Bumblebee",
    "Rachet":          "Ratchet",
    "Ratrap":          "Rattrap",
    "Rukus":           "Ruckus",
    "Leige Maximo":    "Liege Maximo",
    "Wierdwolf":       "Weirdwolf",
    "Bone Shaker Hot Wheels": "Bone Shaker",
    "Ironfist / Fisitron":    "Ironfist",
}

def get_credentials():
    creds = None
    # Always do fresh auth for write scope (old token was readonly)
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception:
            creds = None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return creds

def main():
    print("Authenticating...")
    creds = get_credentials()
    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()

    # Read current sheet
    result = sheet.values().get(spreadsheetId=SHEET_ID, range="A1:ZZ").execute()
    rows = result.get("values", [])
    if not rows:
        print("No data found.")
        return

    header = rows[0]
    try:
        name_col = header.index("NAME")
    except ValueError:
        print(f"No NAME column found. Headers: {header}")
        return

    updates = []
    for row_idx, row in enumerate(rows[1:], start=2):  # 1-indexed, skip header
        if len(row) <= name_col:
            continue
        cell_val = row[name_col].strip()
        if cell_val in CORRECTIONS:
            new_val = CORRECTIONS[cell_val]
            col_letter = chr(ord("A") + name_col)
            cell_range = f"{col_letter}{row_idx}"
            updates.append({
                "range": cell_range,
                "values": [[new_val]],
            })
            print(f"  Row {row_idx}: '{cell_val}' -> '{new_val}'")

    if not updates:
        print("No corrections needed — sheet already up to date.")
        return

    body = {"valueInputOption": "RAW", "data": updates}
    sheet.values().batchUpdate(spreadsheetId=SHEET_ID, body=body).execute()
    print(f"\nUpdated {len(updates)} cells in Google Sheet.")

if __name__ == "__main__":
    main()
