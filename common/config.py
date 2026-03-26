import json
import os
import sys


def _app_base_dir() -> str:
    """Return runtime base directory (exe dir when frozen, project root in source mode)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _load_runtime_settings() -> dict:
    """
    Load optional runtime settings from JSON.
    Priority order:
    1) DAILY_REVIEWER_SETTINGS_FILE (explicit path)
    2) daily_reviewer_settings.json beside executable/project
    3) daily_reviewer_settings.json in current working directory
    """
    candidates = []

    explicit_path = os.getenv("DAILY_REVIEWER_SETTINGS_FILE")
    if explicit_path:
        candidates.append(explicit_path)

    app_default = os.path.join(_app_base_dir(), "daily_reviewer_settings.json")
    candidates.append(app_default)

    cwd_default = os.path.join(os.getcwd(), "daily_reviewer_settings.json")
    if cwd_default != app_default:
        candidates.append(cwd_default)

    checked = set()
    for path in candidates:
        normalized = os.path.abspath(path)
        if normalized in checked:
            continue
        checked.add(normalized)

        if not os.path.exists(normalized):
            continue

        try:
            with open(normalized, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                print(f"Loaded runtime settings from: {normalized}")
                return loaded
            print(f"Warning: Settings file is not a JSON object: {normalized}")
        except (OSError, json.JSONDecodeError) as e:
            print(f"Warning: Failed to load settings file '{normalized}': {e}")

    return {}


def _get_setting(name: str, default):
    if name in _RUNTIME_SETTINGS:
        return _RUNTIME_SETTINGS[name]
    return os.getenv(name, default)


def _get_int_setting(name: str, default: int, minimum: int | None = None) -> int:
    raw = _get_setting(name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        print(f"Warning: Invalid integer for {name}={raw!r}. Using default {default}.")
        return default

    if minimum is not None and value < minimum:
        print(f"Warning: {name} must be >= {minimum}. Using default {default}.")
        return default
    return value


def _get_float_setting(name: str, default: float, minimum: float | None = None) -> float:
    raw = _get_setting(name, default)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        print(f"Warning: Invalid float for {name}={raw!r}. Using default {default}.")
        return default

    if minimum is not None and value < minimum:
        print(f"Warning: {name} must be >= {minimum}. Using default {default}.")
        return default
    return value


_RUNTIME_SETTINGS = _load_runtime_settings()

# Google Sheets Configuration
# Name of your Google Sheet (e.g., "AI Learning Flashcards")
GOOGLE_SHEET_NAME = str(_get_setting("GOOGLE_SHEET_NAME", "AI Learning Flashcards"))
# Name of the worksheet (tab) within your Google Sheet
WORKSHEET_NAME = str(_get_setting("WORKSHEET_NAME", "Flashcards"))

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
EASY_MULTIPLIER = _get_float_setting("EASY_MULTIPLIER", 2.0, minimum=0.1)
MEDIUM_MULTIPLIER = _get_float_setting("MEDIUM_MULTIPLIER", 1.2, minimum=0.1)
HARD_RESET_INTERVAL = _get_int_setting("HARD_RESET_INTERVAL", 1, minimum=1)

# New: Easy Streak Delay Configuration
# These are additional days to add to the interval when a card is rated EASY multiple times.
EASY_STREAK_DELAY_1 = _get_int_setting("EASY_STREAK_DELAY_1", 0, minimum=0)    # First EASY rating (interval * EASY_MULTIPLIER)
EASY_STREAK_DELAY_2 = _get_int_setting("EASY_STREAK_DELAY_2", 7, minimum=0)    # Second consecutive EASY rating: +7 days
EASY_STREAK_DELAY_3 = _get_int_setting("EASY_STREAK_DELAY_3", 14, minimum=0)   # Third consecutive EASY rating: +14 days
EASY_STREAK_DELAY_4 = _get_int_setting("EASY_STREAK_DELAY_4", 30, minimum=0)   # Fourth or more consecutive EASY rating: +30 days
# The absolute values (7, 14, 30) can be adjusted to your preference.

# Daily Reviewer Configuration
NUM_CARDS_TO_REVIEW = _get_int_setting("NUM_CARDS_TO_REVIEW", 5, minimum=1)
# New: Priority Slot Configuration for Review Session
PRIORITY_SLOTS_NEW = _get_int_setting("PRIORITY_SLOTS_NEW", 2, minimum=0)        # Number of slots for completely new cards (first review)
PRIORITY_SLOTS_HARD = _get_int_setting("PRIORITY_SLOTS_HARD", 1, minimum=0)       # Number of slots for cards rated HARD
PRIORITY_SLOTS_EMERGING = _get_int_setting("PRIORITY_SLOTS_EMERGING", 1, minimum=0)   # Number of slots for cards emerging from a long "too easy" delay
                               # (These are minimums, more can be added if available)