from datetime import date, timedelta
from common.config import (
    EASY_MULTIPLIER, MEDIUM_MULTIPLIER, HARD_RESET_INTERVAL,
    EASY_STREAK_DELAY_1, EASY_STREAK_DELAY_2, EASY_STREAK_DELAY_3, EASY_STREAK_DELAY_4 # New imports
)

def calculate_next_review_params(
    difficulty_rating: str, 
    current_interval: int, 
    last_reviewed_date: date,
    current_easy_streak: int = 0 # <--- NEW: Added easy_streak parameter
) -> tuple[int, date, int]: # <--- NEW: Return new_easy_streak as well
    """
    Calculates the new interval, next review date, and updated easy streak
    based on user's difficulty rating and current spaced repetition parameters.

    Args:
        difficulty_rating (str): User's assessment ('EASY', 'MEDIUM', 'HARD').
        current_interval (int): The current interval in days for the flashcard.
        last_reviewed_date (date): The date the flashcard was last reviewed.
        current_easy_streak (int): The current consecutive 'EASY' ratings for the flashcard.

    Returns:
        tuple[int, date, int]: A tuple containing the new interval, the new next_review date,
                               and the updated easy streak.
    """
    
    new_interval = current_interval
    new_easy_streak = current_easy_streak # Initialize with current streak

    if difficulty_rating.upper() == 'EASY':
        new_easy_streak += 1 # Increment streak for EASY rating
        
        # Base interval increase
        new_interval = max(1, int(current_interval * EASY_MULTIPLIER))
        
        # Add escalating delays based on easy_streak
        if new_easy_streak >= 4:
            new_interval += EASY_STREAK_DELAY_4
        elif new_easy_streak == 3:
            new_interval += EASY_STREAK_DELAY_3
        elif new_easy_streak == 2:
            new_interval += EASY_STREAK_DELAY_2
        # For new_easy_streak == 1, EASY_STREAK_DELAY_1 is 0, so no additional delay beyond multiplier
        
    elif difficulty_rating.upper() == 'MEDIUM':
        new_interval = max(1, int(current_interval * MEDIUM_MULTIPLIER))
        new_easy_streak = 0 # Reset streak for non-EASY rating
    elif difficulty_rating.upper() == 'HARD':
        new_interval = HARD_RESET_INTERVAL # Reset to 1 day
        new_easy_streak = 0 # Reset streak for non-EASY rating
    else:
        print(f"Warning: Unknown difficulty rating '{difficulty_rating}'. Defaulting to MEDIUM logic.")
        new_interval = max(1, int(current_interval * MEDIUM_MULTIPLIER))
        new_easy_streak = 0 # Reset streak for unknown rating

    # Ensure interval is at least 1 day, especially after reset or very small initial intervals
    new_interval = max(1, new_interval)
    
    # Calculate the next review date
    new_next_review_date = last_reviewed_date + timedelta(days=new_interval)
    
    return new_interval, new_next_review_date, new_easy_streak # <--- NEW: Return new_easy_streak

# Example usage (for testing)
if __name__ == "__main__":
    today = date.today()
    print(f"Today: {today}")

    # New card, reviewed for the first time
    initial_interval = 1
    initial_last_reviewed = today
    initial_easy_streak = 0 # Added for example

    # Reviewing a new card as EASY
    new_interval_easy, next_review_easy, new_easy_streak_easy = calculate_next_review_params(
        'EASY', initial_interval, initial_last_reviewed, initial_easy_streak
    )
    print(f"Initial: Interval={initial_interval}, Last Reviewed={initial_last_reviewed}, Streak={initial_easy_streak}")
    print(f"Rated EASY (1st time): New Interval={new_interval_easy}, Next Review={next_review_easy}, New Streak={new_easy_streak_easy}") 
    # Should be 2 days from today, Streak=1

    # Simulate second EASY rating for the same card (interval 2, streak 1)
    new_interval_easy_2, next_review_easy_2, new_easy_streak_easy_2 = calculate_next_review_params(
        'EASY', new_interval_easy, today, new_easy_streak_easy # Use today as last_reviewed
    )
    print(f"Rated EASY (2nd time): New Interval={new_interval_easy_2}, Next Review={next_review_easy_2}, New Streak={new_easy_streak_easy_2}") 
    # Should be (2*2)+7 = 11 days from today, Streak=2

    # Simulate third EASY rating for the same card (interval 11, streak 2)
    new_interval_easy_3, next_review_easy_3, new_easy_streak_easy_3 = calculate_next_review_params(
        'EASY', new_interval_easy_2, today, new_easy_streak_easy_2
    )
    print(f"Rated EASY (3rd time): New Interval={new_interval_easy_3}, Next Review={next_review_easy_3}, New Streak={new_easy_streak_easy_3}") 
    # Should be (11*2)+14 = 36 days from today, Streak=3

    # Simulate HARD rating (interval 36, streak 3)
    new_interval_hard_reset, next_review_hard_reset, new_easy_streak_hard_reset = calculate_next_review_params(
        'HARD', new_interval_easy_3, today, new_easy_streak_easy_3
    )
    print(f"Rated HARD: New Interval={new_interval_hard_reset}, Next Review={next_review_hard_reset}, New Streak={new_easy_streak_hard_reset}")
    # Should be 1 day from today, Streak=0

    print("\n--- Subsequent Review (Old Card) ---")
    # Let's say a card was reviewed last 10 days ago, interval 5, streak 0
    prev_interval = 5
    prev_last_reviewed = today - timedelta(days=10) # 10 days ago
    prev_easy_streak = 0

    new_interval_easy_old, next_review_easy_old, new_easy_streak_old = calculate_next_review_params(
        'EASY', prev_interval, today, prev_easy_streak
    )
    print(f"Prev: Interval={prev_interval}, Last Reviewed={prev_last_reviewed}, Streak={prev_easy_streak}")
    print(f"Rated EASY today: New Interval={new_interval_easy_old}, Next Review={next_review_easy_old}, New Streak={new_easy_streak_old}")
    # Should be 10 days from today, Streak=1