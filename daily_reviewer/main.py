import random
from datetime import date, datetime
import json
import os
import sys # Import sys for exit()
import collections # New import for defaultdict

from common.google_sheets_service import get_flashcards_for_review, update_row_by_id
from daily_reviewer.spaced_repetition_logic import calculate_next_review_params
from daily_reviewer.ui import FlashcardUI
from common.config import (
    COL_ID, COL_FLASHCARDS, COL_DIFFICULTY, COL_INTERVAL,
    COL_LAST_REVIEWED, COL_NEXT_REVIEW, COL_EASY_STREAK, # New import
    NUM_CARDS_TO_REVIEW,
    PRIORITY_SLOTS_NEW, PRIORITY_SLOTS_HARD, PRIORITY_SLOTS_EMERGING, # New imports for priority
    SHEET_HEADERS
)

LOCK_FILE = "daily_reviewer.lock"


def normalize_flashcard_for_ui(flashcard_qa: dict) -> dict | None:
    # ... (existing code, no changes needed here)
    if not isinstance(flashcard_qa, dict):
        return None

    question = flashcard_qa.get("Q") or flashcard_qa.get("question")
    answer = flashcard_qa.get("A") or flashcard_qa.get("answer")

    if not isinstance(question, str) or not isinstance(answer, str):
        return None

    question = question.strip()
    answer = answer.strip()
    if not question or not answer:
        return None

    normalized = dict(flashcard_qa)
    normalized["Q"] = question
    normalized["A"] = answer
    # Ensure easy_streak is present for the UI, default to 0 if not
    normalized[COL_EASY_STREAK] = int(flashcard_qa.get(COL_EASY_STREAK, 0)) 
    return normalized

def _is_pid_running(pid: int) -> bool:
    # ... (existing code, no changes needed here)
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True

def acquire_lock():
    # ... (existing code, no changes needed here)
    if os.path.exists(LOCK_FILE):
        existing_pid = None
        try:
            with open(LOCK_FILE, "r") as f:
                content = f.read().strip()
                existing_pid = int(content) if content else None
        except (OSError, ValueError):
            existing_pid = None

        if existing_pid and _is_pid_running(existing_pid):
            print(f"Lock file '{LOCK_FILE}' exists (PID {existing_pid} is active). Exiting.")
            sys.exit(0)

        print(f"Found stale lock file '{LOCK_FILE}'. Removing it and continuing.")
        try:
            os.remove(LOCK_FILE)
        except OSError as e:
            print(f"Could not remove stale lock file: {e}. Exiting.")
            sys.exit(1)
    try:
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
        print(f"Lock acquired with PID {os.getpid()}.")
        return True
    except IOError as e:
        print(f"Could not create lock file: {e}. Exiting.")
        sys.exit(1)
    
def release_lock():
    # ... (existing code, no changes needed here)
    if os.path.exists(LOCK_FILE):
        try:
            os.remove(LOCK_FILE)
            print("Lock released.")
        except OSError as e:
            print(f"Error removing lock file: {e}")

# NEW: Helper function to prioritize and select cards
def select_cards_for_session(all_due_individual_flashcards: list[dict], today: date) -> list[dict]:
    """
    Selects a balanced set of flashcards for the review session based on priority.

    Args:
        all_due_individual_flashcards (list[dict]): A flattened list of all individual
                                                    flashcards that are currently due,
                                                    each with its 'parent_record_id'.
        today (date): The current date.

    Returns:
        list[dict]: A list of selected flashcards for the current session.
    """
    
    # Categorize cards into priority queues
    priority_queues = collections.defaultdict(list) # Stores lists of individual flashcards

    for card_data in all_due_individual_flashcards:
        # Ensure default values for new fields if not present
        card_difficulty = card_data.get(COL_DIFFICULTY, "MEDIUM").upper()
        card_last_reviewed = card_data.get(COL_LAST_REVIEWED)
        card_easy_streak = card_data.get(COL_EASY_STREAK, 0)
        
        # Priority 1: New Flashcards (never reviewed, or interval is 1 and streak is 0)
        if card_last_reviewed is None or (card_data.get(COL_INTERVAL, 0) == 1 and card_easy_streak == 0):
            priority_queues['new'].append(card_data)
        # Priority 2: Hard-Rated Flashcards
        elif card_difficulty == "HARD":
            priority_queues['hard'].append(card_data)
        # Priority 3: "Too Easy" Cards Emerging from Delay (easy_streak >= 2 and due today)
        elif card_easy_streak >= 2: # No need to check `due today` here explicitly, as `all_due_individual_flashcards` already handles this.
            priority_queues['emerging_easy'].append(card_data)
        # Priority 4: Medium-Rated Flashcards
        elif card_difficulty == "MEDIUM":
            priority_queues['medium'].append(card_data)
        # Priority 5: Regularly Easy Flashcards
        elif card_difficulty == "EASY":
            priority_queues['easy'].append(card_data)
        else: # Fallback for any unhandled state
            priority_queues['medium'].append(card_data)

    session_cards = []
    selected_keys = set()

    def card_key(card: dict) -> tuple:
        return (card.get('parent_record_id'), card.get('original_index'))

    def add_cards(cards: list[dict], limit: int | None = None):
        added = 0
        for card in cards:
            key = card_key(card)
            if key in selected_keys:
                continue
            session_cards.append(card)
            selected_keys.add(key)
            added += 1
            if limit is not None and added >= limit:
                break
    
    # Shuffle each priority queue to ensure randomness within priority
    for key in priority_queues:
        random.shuffle(priority_queues[key])

    # 1. Add new cards
    add_cards(priority_queues['new'], PRIORITY_SLOTS_NEW)
    
    # 2. Add hard cards
    add_cards(priority_queues['hard'], PRIORITY_SLOTS_HARD)

    # 3. Add emerging easy cards
    add_cards(priority_queues['emerging_easy'], PRIORITY_SLOTS_EMERGING)

    # 4. Fill remaining slots from ALL remaining due cards.
    # This prevents under-filling when most cards are in the 'new' bucket.
    remaining_slots = NUM_CARDS_TO_REVIEW - len(session_cards)
    if remaining_slots > 0:
        backfill_pool = (
            priority_queues['new'][PRIORITY_SLOTS_NEW:] +
            priority_queues['hard'][PRIORITY_SLOTS_HARD:] +
            priority_queues['emerging_easy'][PRIORITY_SLOTS_EMERGING:] +
            priority_queues['medium'] +
            priority_queues['easy']
        )
        random.shuffle(backfill_pool)
        add_cards(backfill_pool, remaining_slots)

    # Final shuffle for the session to mix card types once selected
    random.shuffle(session_cards) 

    return session_cards[:NUM_CARDS_TO_REVIEW] # Ensure we don't exceed the total limit


def run_daily_review():
    # Acquire lock at the very beginning
    acquire_lock()

    print(f"\n--- Starting Daily Flashcard Review at {datetime.now().isoformat()} ---")
    today = date.today()
    print(f"Today's date: {today}")

    try:
        FlashcardUI._close_all_requested = False
        all_due_card_records, headers = get_flashcards_for_review(today)

        if not all_due_card_records:
            print("No flashcard records are due for review today. Keep up the good work!")
            return

        # NEW: Flatten all due individual flashcards and associate them with their parent record_id
        all_due_individual_flashcards = []
        for record in all_due_card_records:
            record_id = record.get(COL_ID)
            if not record_id: # Skip malformed records
                continue
            
            if record.get(COL_FLASHCARDS) and isinstance(record[COL_FLASHCARDS], list):
                for flashcard_qa in record[COL_FLASHCARDS]:
                    normalized_card = normalize_flashcard_for_ui(flashcard_qa)
                    if not normalized_card:
                        print(f"  Skipping malformed individual flashcard in record {record_id}.")
                        continue

                    # Check if this specific individual flashcard is due
                    flashcard_next_review_str = normalized_card.get(COL_NEXT_REVIEW)
                    flashcard_next_review = datetime.strptime(flashcard_next_review_str, '%Y-%m-%d').date() \
                                            if flashcard_next_review_str else date.min

                    if flashcard_next_review <= today:
                        # Attach parent_record_id and the original index for easy lookup later
                        individual_card_data = normalized_card.copy()
                        individual_card_data['parent_record_id'] = record_id
                        # Store original index to update the correct card in the list later
                        individual_card_data['original_index'] = record[COL_FLASHCARDS].index(flashcard_qa)
                        all_due_individual_flashcards.append(individual_card_data)
        
        if not all_due_individual_flashcards:
            print("No individual flashcards found due among the fetched records. Check your data.")
            return

        print(f"Found {len(all_due_individual_flashcards)} individual flashcards due across records.")
        
        # NEW: Select cards for the session using the priority logic
        session_cards = select_cards_for_session(all_due_individual_flashcards, today)
        
        print(f"Reviewing {len(session_cards)} flashcards in this session.")
        
        # NEW: Group session cards by parent_record_id for efficient sheet updates
        records_to_update = collections.defaultdict(lambda: {
            'flashcards': [], 
            'original_record_full': None, 
            'earliest_next_review': date.max
        })

        # Pre-populate records_to_update with current state of all original records
        # This is crucial so we don't accidentally lose skipped cards from the original list
        for original_record in all_due_card_records:
            rec_id = original_record.get(COL_ID)
            if rec_id:
                records_to_update[rec_id]['original_record_full'] = original_record
                records_to_update[rec_id]['flashcards'] = original_record.get(COL_FLASHCARDS, [])[:] # Deep copy the list

        terminate_session = False

        for i, flashcard_to_review in enumerate(session_cards):
            parent_record_id = flashcard_to_review['parent_record_id']
            original_index = flashcard_to_review['original_index']
            
            print(f"\n--- Reviewing Card {i+1}/{len(session_cards)} (Parent ID: {parent_record_id}) ---")
            
            # --- UI Integration ---
            # Pass a copy of the flashcard to UI, as UI might modify it internally
            ui = FlashcardUI(flashcard_to_review.copy()) # Pass a copy
            difficulty_rating_input = ui.run() 

            if FlashcardUI._close_all_requested:
                print("Close requested from UI. Ending the full review session.")
                terminate_session = True
                break

            if difficulty_rating_input is None:
                print("User closed UI for current flashcard without rating. Skipping this card's update.")
                # If skipped, the card retains its original state in records_to_update['flashcards']
                # since we are only updating specific indices.
                continue
            # --- End UI Integration ---

            difficulty_rating = difficulty_rating_input
            
            # Retrieve current easy streak for this specific flashcard
            current_easy_streak = flashcard_to_review.get(COL_EASY_STREAK, 0)
            
            # Calculate new SR parameters for THIS individual flashcard
            new_individual_interval, new_individual_next_review, new_easy_streak = calculate_next_review_params(
                difficulty_rating, 
                flashcard_to_review.get(COL_INTERVAL, 1), # Default to 1 if not set
                today, # Last reviewed date is today
                current_easy_streak # Pass current easy streak
            )

            # Update THIS individual flashcard's data in the records_to_update structure
            # Ensure we update the correct card at its original index within its parent list
            updated_card_in_memory = records_to_update[parent_record_id]['flashcards'][original_index]
            updated_card_in_memory[COL_DIFFICULTY] = difficulty_rating
            updated_card_in_memory[COL_INTERVAL] = new_individual_interval
            updated_card_in_memory[COL_LAST_REVIEWED] = today.strftime('%Y-%m-%d')
            updated_card_in_memory[COL_NEXT_REVIEW] = new_individual_next_review.strftime('%Y-%m-%d')
            updated_card_in_memory[COL_EASY_STREAK] = new_easy_streak # Update easy streak

            # Update earliest next review for the parent record
            records_to_update[parent_record_id]['earliest_next_review'] = min(
                records_to_update[parent_record_id]['earliest_next_review'], 
                new_individual_next_review
            )
            
        # After reviewing all session cards, update Google Sheets for all modified records
        for record_id, data in records_to_update.items():
            if data['original_record_full']: # Only update if we actually fetched this record
                # Recalculate parent next_review based on ALL child cards (including skipped ones)
                # We need to iterate through the *final* list of flashcards for this record
                # to find the true earliest next_review, considering those not shown in this session.
                true_earliest_next_review_for_parent = date.max
                for fc in data['flashcards']:
                    fc_next_review_str = fc.get(COL_NEXT_REVIEW)
                    fc_next_review_date = datetime.strptime(fc_next_review_str, '%Y-%m-%d').date() if fc_next_review_str else date.max
                    true_earliest_next_review_for_parent = min(true_earliest_next_review_for_parent, fc_next_review_date)

                data_to_update = {
                    COL_FLASHCARDS: data['flashcards'], # Save the entire modified list back
                    COL_LAST_REVIEWED: today, # Parent record was touched today
                    COL_NEXT_REVIEW: true_earliest_next_review_for_parent, # Parent is due when its earliest child is due
                }
                update_row_by_id(record_id, data_to_update, headers)
                print(f"Updated record ID {record_id}: True Earliest Next Review={true_earliest_next_review_for_parent.strftime('%Y-%m-%d')}")
            
            if terminate_session:
                break


    except Exception as e:
        print(f"An error occurred during daily review: {e}")
    finally:
        release_lock()
    
    print(f"--- Daily Flashcard Review Finished at {datetime.now().isoformat()} ---")

if __name__ == "__main__":
    run_daily_review()