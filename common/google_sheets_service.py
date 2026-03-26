import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date
import json
import os
from dotenv import load_dotenv

from common.config import (
    GOOGLE_SHEET_NAME, WORKSHEET_NAME, SHEET_HEADERS,
    COL_ID, COL_CHAT_TEXT, COL_PROCESSED, COL_FLASHCARDS,
    COL_TAG, COL_DIFFICULTY, COL_INTERVAL, COL_LAST_REVIEWED, COL_NEXT_REVIEW
)

# Load environment variables from .env file
load_dotenv()

# --- Google Sheets Authentication ---
def get_google_sheet_client():
    """
    Authenticates with Google Sheets using a service account and returns a gspread client.
    Prioritizes JSON content from env var, then falls back to file path from env var.
    """
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        
        creds_json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_CREDENTIALS_JSON")
        if creds_json_str:
            # Authenticate using JSON content directly from environment variable
            creds_info = json.loads(creds_json_str)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
            print("Authenticated with Google Sheets using JSON from environment.")
        else:
            # Fallback to file path from environment variable (for local dev mostly).
            # Supports both *_PATH and legacy GOOGLE_SERVICE_ACCOUNT_CREDENTIALS.
            creds_path = (
                os.getenv("GOOGLE_SERVICE_ACCOUNT_CREDENTIALS_PATH")
                or os.getenv("GOOGLE_SERVICE_ACCOUNT_CREDENTIALS")
                or "./google_credentials.json"
            )
            if not creds_path or not os.path.exists(creds_path):
                raise FileNotFoundError(
                    f"Google service account credentials file not found at: {creds_path}. "
                    "Please ensure GOOGLE_SERVICE_ACCOUNT_CREDENTIALS_PATH, "
                    "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS, or "
                    "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS_JSON is set."
                )
            creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
            print(f"Authenticated with Google Sheets using credentials file at '{creds_path}'.")
        
        client = gspread.authorize(creds)
        print("Successfully authorized gspread client.")
        return client
    except Exception as e:
        print(f"Error authenticating with Google Sheets: {e}")
        raise

def get_worksheet():
    """
    Retrieves the specified worksheet from the Google Sheet.
    """
    client = get_google_sheet_client()
    try:
        sheet = client.open(GOOGLE_SHEET_NAME)
        worksheet = sheet.worksheet(WORKSHEET_NAME)
        print(f"Successfully accessed worksheet '{WORKSHEET_NAME}' in sheet '{GOOGLE_SHEET_NAME}'.")
        return worksheet
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"Error: Google Sheet '{GOOGLE_SHEET_NAME}' not found. Please check the name and sharing permissions.")
        raise
    except gspread.exceptions.WorksheetNotFound:
        print(f"Error: Worksheet '{WORKSHEET_NAME}' not found in '{GOOGLE_SHEET_NAME}'.")
        raise
    except Exception as e:
        print(f"Error accessing worksheet: {e}")
        raise

# --- Data Handling Utilities ---
def row_to_dict(row_values, headers):
    """Converts a list of row values into a dictionary using provided headers."""
    if not row_values:
        return {}
    return dict(zip(headers, row_values))

def dict_to_row(data_dict, headers):
    """Converts a dictionary into a list of row values based on provided headers order."""
    return [str(data_dict.get(header, "")) for header in headers]

# --- Google Sheets Read Operations ---
def get_all_records():
    """
    Fetches all records from the worksheet as a list of dictionaries.
    Each dictionary represents a row with column headers as keys.
    """
    worksheet = get_worksheet()
    data = worksheet.get_all_values()
    if not data:
        return [], SHEET_HEADERS

    # Assuming the first row is headers
    headers = data[0]
    # Check if the actual headers match our expected headers
    if headers != SHEET_HEADERS:
        print("Warning: Google Sheet headers do not exactly match expected configuration.")
        print(f"Expected: {SHEET_HEADERS}")
        print(f"Actual:   {headers}")
        # For now, we'll proceed with actual headers for mapping, but this could cause issues.
        # A robust system might raise an error or try to map based on partial matches.
    
    records = []
    for row_values in data[1:]:  # Skip header row
        record_dict = row_to_dict(row_values, headers)
        
        # Type conversion for specific fields for easier processing later
        try:
            record_dict[COL_PROCESSED] = record_dict.get(COL_PROCESSED, 'FALSE').upper() == 'TRUE'
            record_dict[COL_INTERVAL] = int(record_dict.get(COL_INTERVAL) or 0)
            
            # Parse dates, handle empty strings for new cards
            last_reviewed_str = record_dict.get(COL_LAST_REVIEWED)
            record_dict[COL_LAST_REVIEWED] = datetime.strptime(last_reviewed_str, '%Y-%m-%d').date() \
                                             if last_reviewed_str else None
            next_review_str = record_dict.get(COL_NEXT_REVIEW)
            record_dict[COL_NEXT_REVIEW] = datetime.strptime(next_review_str, '%Y-%m-%d').date() \
                                           if next_review_str else None
            
            # Parse flashcards JSON string
            flashcards_str = record_dict.get(COL_FLASHCARDS)
            record_dict[COL_FLASHCARDS] = json.loads(flashcards_str) if flashcards_str else []

        except (ValueError, TypeError, json.JSONDecodeError) as e:
            print(f"Warning: Could not convert types for row: {record_dict}. Error: {e}")
            # Potentially mark this row as problematic or skip it. For now, we'll keep it as is.
            pass # Keep original string values if conversion fails

        records.append(record_dict)
    return records, headers

def get_unprocessed_chat_texts():
    """
    Fetches rows from Google Sheets where 'processed' is FALSE.
    Returns a list of dictionaries, each representing an unprocessed chat.
    """
    all_records, headers = get_all_records()
    unprocessed_records = [
        record for record in all_records
        if not record.get(COL_PROCESSED, False) and record.get(COL_CHAT_TEXT)
    ]
    print(f"Found {len(unprocessed_records)} unprocessed chat texts.")
    return unprocessed_records, headers

def get_flashcards_for_review(today: date):
    """
    Fetches flashcards where next_review date is today or earlier,
    OR flashcards that have been processed with flashcards generated but
    haven't had their next_review date set yet (i.e., new cards).
    Returns a list of dictionaries.
    """
    all_records, headers = get_all_records()
    due_cards = [
        record for record in all_records
        if (
            (record.get(COL_NEXT_REVIEW) and record[COL_NEXT_REVIEW] <= today) # Cards with a set next_review date
            or (
                not record.get(COL_NEXT_REVIEW) # Or cards with no next_review date (newly processed)
                and isinstance(record.get(COL_FLASHCARDS), list)
                and len(record.get(COL_FLASHCARDS)) > 0
                and record.get(COL_PROCESSED) # And they must be processed
            )
        )
    ]
    print(f"Found {len(due_cards)} flashcard records due for review today ({today}).")
    return due_cards, headers



# --- Google Sheets Write/Update Operations ---
def update_row_by_id(record_id, data_to_update: dict, headers):
    """
    Updates a specific row in the Google Sheet identified by its 'id'.
    data_to_update is a dictionary where keys are column headers and values are the new data.
    """
    worksheet = get_worksheet()
    # Find the row index (gspread is 1-indexed)
    # We assume 'id' column is the first in SHEET_HEADERS for simplicity, adjust if not.
    try:
        id_col_index = headers.index(COL_ID) + 1 # +1 because gspread is 1-indexed for columns
        cell = worksheet.find(str(record_id), in_column=id_col_index)
        row_index = cell.row
    except gspread.exceptions.CellNotFound:
        print(f"Error: Record with ID '{record_id}' not found for update.")
        return False
    except ValueError:
        print(f"Error: Column '{COL_ID}' not found in headers for update_row_by_id.")
        return False

    # Prepare values for update, ensuring they are in the correct order and format
    updates = []
    for col_header in headers:
        if col_header in data_to_update:
            value = data_to_update[col_header]
            # Special handling for boolean and date types
            if col_header == COL_PROCESSED:
                value = 'TRUE' if value else 'FALSE'
            elif col_header in [COL_LAST_REVIEWED, COL_NEXT_REVIEW] and isinstance(value, date):
                value = value.strftime('%Y-%m-%d')
            elif col_header == COL_FLASHCARDS and isinstance(value, list):
                value = json.dumps(value) # Convert list of dicts to JSON string
            
            updates.append((row_index, headers.index(col_header) + 1, value))
    
    if updates:
        # gspread.worksheet.update_cells takes a list of Cell objects or a list of (row, col, value) tuples
        # For simplicity, we will update individual cells using batch_update if there are many updates
        # or worksheet.update_cell if only a few.
        # Let's use worksheet.update_cell for now for clarity, assuming a few updates per row.
        for r, c, val in updates:
            worksheet.update_cell(r, c, val)
        print(f"Successfully updated record with ID '{record_id}'.")
        return True
    return False

def append_new_flashcard(flashcard_data: dict):
    """
    Appends a new flashcard record to the Google Sheet.
    flashcard_data is a dictionary containing all required fields.
    """
    worksheet = get_worksheet()
    
    # Ensure flashcard_data has all required fields for a new entry
    # and format them correctly for Google Sheets
    row_data = {
        COL_ID: flashcard_data.get(COL_ID, str(datetime.now().timestamp())), # Generate ID if not provided
        COL_CHAT_TEXT: flashcard_data.get(COL_CHAT_TEXT, ""),
        COL_PROCESSED: 'TRUE' if flashcard_data.get(COL_PROCESSED, False) else 'FALSE',
        COL_FLASHCARDS: json.dumps(flashcard_data.get(COL_FLASHCARDS, [])),
        COL_TAG: flashcard_data.get(COL_TAG, "Untagged"),
        COL_DIFFICULTY: flashcard_data.get(COL_DIFFICULTY, "MEDIUM"), # Default difficulty
        COL_INTERVAL: str(flashcard_data.get(COL_INTERVAL, 1)),     # Default interval
        COL_LAST_REVIEWED: flashcard_data.get(COL_LAST_REVIEWED, datetime.now().date()).strftime('%Y-%m-%d'),
        COL_NEXT_REVIEW: flashcard_data.get(COL_NEXT_REVIEW, datetime.now().date()).strftime('%Y-%m-%d'),
    }
    
    # Convert dict to ordered list based on SHEET_HEADERS
    values_to_append = dict_to_row(row_data, SHEET_HEADERS)
    
    try:
        worksheet.append_row(values_to_append)
        print(f"Successfully appended new flashcard entry with ID: {row_data[COL_ID]}.")
        return True
    except Exception as e:
        print(f"Error appending new row to Google Sheets: {e}")
        return False