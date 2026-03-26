from flask import Flask, request, jsonify
from common.google_sheets_service import get_unprocessed_chat_texts, update_row_by_id
from backend_processor.openai_service import generate_flashcards_from_chat
from common.config import (
    COL_ID,
    COL_CHAT_TEXT,
    COL_PROCESSED,
    COL_FLASHCARDS,
    COL_DIFFICULTY,
    COL_INTERVAL,
    COL_LAST_REVIEWED,
    COL_NEXT_REVIEW,
    COL_EASY_STREAK,
)
from datetime import datetime, date
import os
from threading import Lock
from dotenv import load_dotenv

# Load environment variables for local testing
load_dotenv()

app = Flask(__name__)
_RUN_LOCK = Lock()

# --- Configuration for API Key ---
API_SECRET_KEY = os.getenv("API_SECRET_KEY")
if not API_SECRET_KEY:
    print("WARNING: API_SECRET_KEY environment variable is not set. API endpoint will be insecure for local testing.")
    print("Please set API_SECRET_KEY in your .env file or Render environment variables.")


# --- Core Processing Logic Function ---
def _execute_processing_logic(unprocessed_records: list[dict], headers: list[str]) -> int:
    """
    Executes the logic to process unprocessed chat texts and update Google Sheets.
    This function is called by the Flask /run endpoint.

    Args:
        unprocessed_records (list[dict]): List of dictionaries, each representing an unprocessed chat.
        headers (list[str]): The column headers from the Google Sheet.

    Returns:
        int: The number of records successfully processed.
    """
    processed_count = 0
    for record in unprocessed_records:
        record_id = record.get(COL_ID)
        chat_text = record.get(COL_CHAT_TEXT)

        if not record_id or not chat_text:
            print(f"Skipping malformed record: {record}")
            continue

        print(f"Processing chat ID: {record_id}")
        print(f"Chat Text (first 100 chars): {chat_text[:100]}...")

        try:
            flashcards = generate_flashcards_from_chat(chat_text)

            if flashcards:
                # Initialize each generated flashcard with default SR parameters
                initialized_flashcards = []
                for card in flashcards:
                    card_with_sr = card.copy()
                    card_with_sr[COL_DIFFICULTY] = "MEDIUM"
                    card_with_sr[COL_INTERVAL] = 1
                    card_with_sr[COL_LAST_REVIEWED] = None
                    card_with_sr[COL_NEXT_REVIEW] = date.today().strftime('%Y-%m-%d')
                    card_with_sr[COL_EASY_STREAK] = 0
                    initialized_flashcards.append(card_with_sr)

                # Update the record in Google Sheets
                data_to_update = {
                    COL_PROCESSED: True,
                    COL_FLASHCARDS: initialized_flashcards,
                    # For newly generated records, they are immediately reviewable:
                    COL_DIFFICULTY: "MEDIUM", # Default for the whole set
                    COL_INTERVAL: 1,          # Default for the whole set
                    COL_LAST_REVIEWED: None,  # No review for the set yet
                    COL_NEXT_REVIEW: date.today(), # Set to today so it's picked up by reviewer
                    COL_EASY_STREAK: 0,       # Initialize easy streak for the set
                }
                update_row_by_id(record_id, data_to_update, headers)
                processed_count += 1
            else:
                print(
                    f"No flashcards generated for chat ID {record_id}. "
                    "Leaving as unprocessed so it can be retried."
                )
                # If no flashcards are generated, we might still want to mark as processed
                # or have a separate flag for "processing_failed" to avoid infinite retries on bad input.
                # For now, following the previous logic of leaving as unprocessed.

        except Exception as e:
            print(f"Error processing record ID {record_id}: {e}")
            # Continue to next record even if one fails
    return processed_count


# --- Flask Routes ---
@app.route("/")
def home():
    """Health check endpoint."""
    return "Flashcard Backend Service is alive!"

@app.route("/run", methods=["GET", "HEAD"])
@app.route("/run/<path_key>", methods=["GET", "HEAD"])
def run_processing(path_key=None):
    """
    Endpoint to trigger the flashcard processing logic.
    Requires an API key for authorization.
    """
    print(f"--- Received /run request at {datetime.now().isoformat()} ---")

    # 1. API Key Protection
    auth_header = request.headers.get("Authorization", "")
    bearer_token = auth_header.replace("Bearer ", "", 1).strip() if auth_header.startswith("Bearer ") else ""
    request_key = (
        path_key
        or request.args.get("key")
        or request.headers.get("X-API-Key")
        or bearer_token
    )
    if not API_SECRET_KEY or request_key != API_SECRET_KEY:
        print("Unauthorized attempt to access /run.")
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    if not _RUN_LOCK.acquire(blocking=False):
        print("A processing run is already in progress. Skipping overlapping trigger.")
        return jsonify({"status": "busy", "message": "Processing already in progress"}), 200

    try:
        # 2. Optimization: Check if there are any unprocessed rows before doing heavy lifting
        try:
            # We need headers for update_row_by_id later, so fetch them once
            unprocessed_records, headers = get_unprocessed_chat_texts()

            if not unprocessed_records:
                print("No new rows found to process. Returning idle status.")
                return jsonify({"status": "idle", "message": "No new rows to process"}), 200

            print(f"Found {len(unprocessed_records)} unprocessed rows. Starting processing.")

        except Exception as e:
            print(f"Error checking for unprocessed rows or fetching headers: {e}")
            return jsonify({"status": "error", "message": f"Failed to check for unprocessed rows: {e}"}), 500

        # 3. Execute processing logic
        try:
            processed_count = _execute_processing_logic(unprocessed_records, headers)
            print(f"--- Processing finished. Processed {processed_count} new entries. ---")
            return jsonify({"status": "success", "message": f"Successfully processed {processed_count} new entries"}), 200
        except Exception as e:
            print(f"An unhandled error occurred during processing: {e}")
            return jsonify({"status": "error", "message": f"Processing failed: {e}"}), 500
    finally:
        _RUN_LOCK.release()

if __name__ == "__main__":
    # When running locally, Flask uses a default port.
    # For Render, it will use the PORT environment variable set by Render itself.
    # We set a default port here for local development.
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))