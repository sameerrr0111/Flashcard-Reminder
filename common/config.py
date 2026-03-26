import os

# Google Sheets Configuration
# Name of your Google Sheet (e.g., "AI Learning Flashcards")
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "AI Learning Flashcards")
# Name of the worksheet (tab) within your Google Sheet
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "Flashcards")

# Column Headers (ensure these match your Google Sheet exactly)
COL_ID = "id"
COL_CHAT_TEXT = "chat_text"
COL_PROCESSED = "processed"
COL_FLASHCARDS = "flashcards"
COL_TAG = "tag"
COL_DIFFICULTY = "difficulty"
COL_INTERVAL = "interval"
COL_LAST_REVIEWED = "last_reviewed"
COL_NEXT_REVIEW = "next_review"
# New: For easy streak tracking within individual flashcards
COL_EASY_STREAK = "easy_streak"

# Define the order of columns as they appear in your Google Sheet.
# This is crucial for gspread to map data correctly.
SHEET_HEADERS = [
    COL_ID,
    COL_CHAT_TEXT,
    COL_PROCESSED,
    COL_FLASHCARDS,
    COL_TAG,
    COL_DIFFICULTY,
    COL_INTERVAL,
    COL_LAST_REVIEWED,
    COL_NEXT_REVIEW,
]

# Spaced Repetition Configuration
EASY_MULTIPLIER = 2.0
MEDIUM_MULTIPLIER = 1.2
HARD_RESET_INTERVAL = 1

# New: Easy Streak Delay Configuration
# These are additional days to add to the interval when a card is rated EASY multiple times.
EASY_STREAK_DELAY_1 = 0    # First EASY rating (interval * EASY_MULTIPLIER)
EASY_STREAK_DELAY_2 = 7    # Second consecutive EASY rating: +7 days
EASY_STREAK_DELAY_3 = 14   # Third consecutive EASY rating: +14 days
EASY_STREAK_DELAY_4 = 30   # Fourth or more consecutive EASY rating: +30 days
# The absolute values (7, 14, 30) can be adjusted to your preference.

# Daily Reviewer Configuration
NUM_CARDS_TO_REVIEW = 5
# New: Priority Slot Configuration for Review Session
PRIORITY_SLOTS_NEW = 2        # Number of slots for completely new cards (first review)
PRIORITY_SLOTS_HARD = 1       # Number of slots for cards rated HARD
PRIORITY_SLOTS_EMERGING = 1   # Number of slots for cards emerging from a long "too easy" delay
                               # (These are minimums, more can be added if available)