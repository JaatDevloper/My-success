"""
Negative marking extension for the Telegram Quiz Bot
This module extends the functionality of the original quiz bot to support penalties for incorrect answers
"""

import json
import logging
import os

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration constants
CONFIG_FILE = "negative_marking_config.json"
PENALTIES_FILE = "penalties.json"
USERS_FILE = "users.json"

# Default penalty settings
DEFAULT_PENALTY = 0.25
MAX_PENALTY = 1.0
MIN_PENALTY = 0.0
CATEGORY_PENALTIES = {
    "General Knowledge": 0.25,
    "Science": 0.5,
    "History": 0.25,
    "Geography": 0.25,
    "Entertainment": 0.25,
    "Sports": 0.25
}

def load_config():
    """Load negative marking configuration from file"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        # Return default configuration if file doesn't exist
        return {
            "enabled": True,
            "default_penalty": DEFAULT_PENALTY,
            "category_penalties": CATEGORY_PENALTIES
        }
    except Exception as e:
        logger.error(f"Error loading negative marking config: {e}")
        return {
            "enabled": True,
            "default_penalty": DEFAULT_PENALTY,
            "category_penalties": CATEGORY_PENALTIES
        }

def save_config(config):
    """Save negative marking configuration to file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving negative marking config: {e}")
        return False

def load_penalties():
    """Load user penalties from file"""
    try:
        if os.path.exists(PENALTIES_FILE):
            with open(PENALTIES_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading penalties: {e}")
        return {}

def save_penalties(penalties):
    """Save user penalties to file"""
    try:
        with open(PENALTIES_FILE, 'w') as f:
            json.dump(penalties, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving penalties: {e}")
        return False

def get_user_penalties(user_id):
    """Get penalties for a specific user"""
    penalties = load_penalties()
    return penalties.get(str(user_id), 0)

def update_user_penalties(user_id, penalty_value):
    """Update penalties for a specific user"""
    penalties = load_penalties()
    user_id_str = str(user_id)
    
    # Initialize if user doesn't exist
    if user_id_str not in penalties:
        penalties[user_id_str] = 0
    
    # Add penalty
    penalties[user_id_str] += penalty_value
    
    # Save updated penalties
    save_penalties(penalties)
    return penalties[user_id_str]

def get_penalty_for_category(category):
    """Get the penalty value for a specific category"""
    config = load_config()
    
    # Return 0 if negative marking is disabled
    if not config.get("enabled", True):
        return 0
    
    # Get category-specific penalty or default
    category_penalties = config.get("category_penalties", CATEGORY_PENALTIES)
    penalty = category_penalties.get(category, config.get("default_penalty", DEFAULT_PENALTY))
    
    # Ensure penalty is within allowed range
    return max(MIN_PENALTY, min(MAX_PENALTY, penalty))

def get_extended_user_stats(user_id):
    """Get extended user statistics with penalty information"""
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                users = json.load(f)
                user_data = users.get(str(user_id), {"total_answers": 0, "correct_answers": 0})
        else:
            user_data = {"total_answers": 0, "correct_answers": 0}
            
        # Get user penalties
        penalty = get_user_penalties(user_id)
        
        # Calculate incorrect answers
        total = user_data.get("total_answers", 0)
        correct = user_data.get("correct_answers", 0)
        incorrect = total - correct
        
        # Calculate adjusted score
        raw_score = correct
        adjusted_score = max(0, raw_score - penalty)
        
        return {
            "total_answers": total,
            "correct_answers": correct,
            "incorrect_answers": incorrect,
            "penalty_points": penalty,
            "raw_score": raw_score,
            "adjusted_score": adjusted_score
        }
        
    except Exception as e:
        logger.error(f"Error loading extended user stats: {e}")
        return {
            "total_answers": 0,
            "correct_answers": 0,
            "incorrect_answers": 0,
            "penalty_points": 0,
            "raw_score": 0,
            "adjusted_score": 0
        }

def apply_penalty(user_id, category):
    """Apply penalty to a user for an incorrect answer"""
    penalty = get_penalty_for_category(category)
    if penalty > 0:
        return update_user_penalties(user_id, penalty)
    return 0

def toggle_negative_marking(enabled=True):
    """Enable or disable negative marking"""
    config = load_config()
    config["enabled"] = enabled
    return save_config(config)

def update_penalty_settings(default_penalty=None, category_penalties=None):
    """Update penalty settings"""
    config = load_config()
    
    if default_penalty is not None:
        config["default_penalty"] = max(MIN_PENALTY, min(MAX_PENALTY, default_penalty))
    
    if category_penalties is not None:
        # Validate and update category penalties
        for category, penalty in category_penalties.items():
            category_penalties[category] = max(MIN_PENALTY, min(MAX_PENALTY, penalty))
        config["category_penalties"] = category_penalties
    
    return save_config(config)

def is_negative_marking_enabled():
    """Check if negative marking is enabled"""
    config = load_config()
    return config.get("enabled", True)

def reset_user_penalties(user_id=None):
    """Reset penalties for a user or all users"""
    penalties = load_penalties()
    
    if user_id:
        # Reset for specific user
        penalties[str(user_id)] = 0
    else:
        # Reset for all users
        penalties = {}
    
    return save_penalties(penalties)