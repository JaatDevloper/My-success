"""
Configuration file for the Telegram Quiz Bot with negative marking
"""

# Negative marking configuration
DEFAULT_PENALTY = 0.25  # Default penalty for incorrect answers (0.25 points)
MAX_PENALTY = 1.0       # Maximum penalty for incorrect answers (1.0 points)
MIN_PENALTY = 0.0       # Minimum penalty for incorrect answers (0.0 points)

# Category-specific penalties (optional)
CATEGORY_PENALTIES = {
    "General Knowledge": 0.25,
    "Science": 0.5,
    "History": 0.25,
    "Geography": 0.25,
    "Entertainment": 0.25,
    "Sports": 0.25
}

# File names (keep consistent with original bot)
QUESTIONS_FILE = "questions.json"
USERS_FILE = "users.json"

# Negative marking configuration file
CONFIG_FILE = "negative_marking_config.json"

# New file to track penalties
PENALTIES_FILE = "penalties.json"