"""
Telegram Quiz Bot with negative marking functionality
Based on the original multi_id_quiz_bot.py but with added negative marking features
"""

import json
import logging
import os
import random
import asyncio
import re
import requests
from bs4 import BeautifulSoup
import trafilatura
from typing import Dict, List, Optional
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler, PollAnswerHandler

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment variable
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7631768276:AAFWUidQIXRnw-CLxaNAPvc0YGef6u1iZWQ")

# Conversation states
QUESTION, OPTIONS, ANSWER, CATEGORY = range(4)
EDIT_SELECT, EDIT_QUESTION, EDIT_OPTIONS = range(4, 7)
CLONE_URL, CLONE_MANUAL = range(7, 9)
CUSTOM_ID = range(9, 10)

# URL extraction states for conversation handler
URL_INPUT, URL_CONFIRMATION, CATEGORY_SELECTION = range(100, 103)

# Data files
QUESTIONS_FILE = "questions.json"
USERS_FILE = "users.json"

# ---------- NEGATIVE MARKING ADDITIONS ----------
# Negative marking configuration
NEGATIVE_MARKING_ENABLED = True
DEFAULT_PENALTY = 0.25  # Default penalty for incorrect answers (0.25 points)
MAX_PENALTY = 1.0       # Maximum penalty for incorrect answers (1.0 points)
MIN_PENALTY = 0.0       # Minimum penalty for incorrect answers (0.0 points)

# Category-specific penalties
CATEGORY_PENALTIES = {
    "General Knowledge": 0.25,
    "Science": 0.5,
    "History": 0.25,
    "Geography": 0.25,
    "Entertainment": 0.25,
    "Sports": 0.25
}

# New file to track penalties
PENALTIES_FILE = "penalties.json"

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
    # Return 0 if negative marking is disabled
    if not NEGATIVE_MARKING_ENABLED:
        return 0
    
    # Get category-specific penalty or default
    penalty = CATEGORY_PENALTIES.get(category, DEFAULT_PENALTY)
    
    # Ensure penalty is within allowed range
    return max(MIN_PENALTY, min(MAX_PENALTY, penalty))

def apply_penalty(user_id, category):
    """Apply penalty to a user for an incorrect answer"""
    penalty = get_penalty_for_category(category)
    if penalty > 0:
        return update_user_penalties(user_id, penalty)
    return 0

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

def get_extended_user_stats(user_id):
    """Get extended user statistics with penalty information"""
    try:
        user_data = get_user_data(user_id)
        
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
# ---------- END NEGATIVE MARKING ADDITIONS ----------

def load_questions():
    """Load questions from the JSON file"""
    try:
        if os.path.exists(QUESTIONS_FILE):
            with open(QUESTIONS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading questions: {e}")
        return {}

def save_questions(questions):
    """Save questions to the JSON file"""
    try:
        with open(QUESTIONS_FILE, 'w') as f:
            json.dump(questions, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving questions: {e}")

def get_next_question_id():
    """Get the next available question ID"""
    questions = load_questions()
    if not questions:
        return 1
    # Find highest numerical ID
    max_id = 0
    for qid in questions.keys():
        # Handle the case where we have lists of questions under an ID
        try:
            id_num = int(qid)
            if id_num > max_id:
                max_id = id_num
        except ValueError:
            pass
    return max_id + 1

def get_question_by_id(question_id):
    """Get a question by its ID"""
    questions = load_questions()
    question_list = questions.get(str(question_id), [])
    # If it's a list, return the first item, otherwise return the item itself
    if isinstance(question_list, list) and question_list:
        return question_list[0]
    return question_list

def delete_question_by_id(question_id):
    """Delete a question by its ID"""
    questions = load_questions()
    if str(question_id) in questions:
        del questions[str(question_id)]
        save_questions(questions)
        return True
    return False

def add_question_with_id(question_id, question_data):
    """Add a question with a specific ID, preserving existing questions with the same ID"""
    questions = load_questions()
    str_id = str(question_id)
    
    if str_id in questions:
        # If the ID exists but isn't a list, convert it to a list
        if not isinstance(questions[str_id], list):
            questions[str_id] = [questions[str_id]]
        # Add the new question to the list
        questions[str_id].append(question_data)
    else:
        # Create a new list with this question
        questions[str_id] = [question_data]
    
    save_questions(questions)
    return True

def get_user_data(user_id):
    """Get user data from file"""
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                users = json.load(f)
                return users.get(str(user_id), {"total_answers": 0, "correct_answers": 0})
        return {"total_answers": 0, "correct_answers": 0}
    except Exception as e:
        logger.error(f"Error loading user data: {e}")
        return {"total_answers": 0, "correct_answers": 0}

def save_user_data(user_id, data):
    """Save user data to file"""
    try:
        users = {}
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                users = json.load(f)
        
        users[str(user_id)] = data
        
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving user data: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the command /start is issued."""
    user = update.effective_user
    welcome_text = (
        f"👋 Hello, {user.first_name}!\n\n"
        "Welcome to the Quiz Bot with Negative Marking. Here's what you can do:\n\n"
        "💡 /quiz - Start a new quiz (auto-sequence)\n"
        "📊 /stats - View your quiz statistics with penalties\n"
        "➕ /add - Add a new question to the quiz bank\n"
        "✏️ /edit - Edit an existing question\n"
        "❌ /delete - Delete a question\n"
        "🔄 /poll2q - Convert a Telegram poll to a quiz question\n"
        "🌐 /url2q - Extract questions from a Google URL with quiz content\n"
        "⚙️ /negmark - Configure negative marking settings\n"
        "🧹 /resetpenalty - Reset your penalties\n"
        "ℹ️ /help - Show this help message\n\n"
        "Let's test your knowledge with some fun quizzes!\n\n"
        "🆕 NEW FEATURE: Use /url2q to automatically extract multiple-choice questions from any Google link containing quizzes!"
    )
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help message."""
    await start(update, context)

# ---------- NEGATIVE MARKING COMMAND ADDITIONS ----------
async def extended_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display extended user statistics with penalty information."""
    user = update.effective_user
    stats = get_extended_user_stats(user.id)
    
    percentage = (stats["correct_answers"] / stats["total_answers"] * 100) if stats["total_answers"] > 0 else 0
    adjusted_percentage = (stats["adjusted_score"] / stats["total_answers"] * 100) if stats["total_answers"] > 0 else 0
    
    stats_text = (
        f"📊 Statistics for {user.first_name}\n\n"
        f"Total questions answered: {stats['total_answers']}\n"
        f"Correct answers: {stats['correct_answers']}\n"
        f"Incorrect answers: {stats['incorrect_answers']}\n"
        f"Success rate: {percentage:.1f}%\n\n"
        f"Penalty points: {stats['penalty_points']:.2f}\n"
        f"Raw score: {stats['raw_score']}\n"
        f"Adjusted score: {stats['adjusted_score']:.2f}\n"
        f"Adjusted success rate: {adjusted_percentage:.1f}%\n\n"
    )
    
    # Add information about negative marking status
    negative_marking_status = "enabled" if NEGATIVE_MARKING_ENABLED else "disabled"
    stats_text += f"Note: Negative marking is currently {negative_marking_status}."
    
    await update.message.reply_text(stats_text)

async def negative_marking_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show and manage negative marking settings."""
    keyboard = [
        [InlineKeyboardButton("Enable Negative Marking", callback_data="neg_mark_enable")],
        [InlineKeyboardButton("Disable Negative Marking", callback_data="neg_mark_disable")],
        [InlineKeyboardButton("Reset All Penalties", callback_data="neg_mark_reset")],
        [InlineKeyboardButton("Back", callback_data="neg_mark_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔧 Negative Marking Settings\n\n"
        "You can enable/disable negative marking or reset penalties.",
        reply_markup=reply_markup
    )

async def negative_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback queries from negative marking settings."""
    query = update.callback_query
    await query.answer()
    
    global NEGATIVE_MARKING_ENABLED
    
    if query.data == "neg_mark_enable":
        NEGATIVE_MARKING_ENABLED = True
        await query.edit_message_text("✅ Negative marking has been enabled.")
    
    elif query.data == "neg_mark_disable":
        NEGATIVE_MARKING_ENABLED = False
        await query.edit_message_text("✅ Negative marking has been disabled.")
    
    elif query.data == "neg_mark_reset":
        reset_user_penalties()
        await query.edit_message_text("✅ All user penalties have been reset.")
    
    elif query.data == "neg_mark_back":
        # Exit settings
        await query.edit_message_text("Settings closed. Use /negmark to access settings again.")

async def reset_user_penalty_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset penalties for a specific user."""
    args = context.args
    
    if args and len(args) > 0:
        try:
            user_id = int(args[0])
            reset_user_penalties(user_id)
            await update.message.reply_text(f"✅ Penalties for user ID {user_id} have been reset.")
        except ValueError:
            await update.message.reply_text("❌ Please provide a valid numeric user ID.")
    else:
        # Reset current user's penalties
        user_id = update.effective_user.id
        reset_user_penalties(user_id)
        await update.message.reply_text("✅ Your penalties have been reset.")
# ---------- END NEGATIVE MARKING COMMAND ADDITIONS ----------

# ---------- URL TO QUESTION FUNCTIONALITY ----------
def fetch_url_content(url: str) -> Optional[str]:
    """Fetch content from a URL using Trafilatura with enhanced multilingual support"""
    try:
        # Configure trafilatura for better content extraction
        config = {
            'include_comments': False,
            'include_tables': True,
            'no_fallback': False,  # Allow fallback methods
            'target_language': 'auto',  # Auto-detect language
            'include_formatting': True  # Include some formatting to preserve structure
        }
        
        # Fetch with custom headers to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,hi;q=0.8',  # Include Hindi in accepted languages
            'Accept-Encoding': 'gzip, deflate, br'
        }
        
        downloaded = trafilatura.fetch_url(url, headers=headers)
        if downloaded:
            # Try to extract with enhanced settings
            content = trafilatura.extract(downloaded, config=config, output_format='text', favor_precision=True)
            
            # If content is too short, try with different settings
            if not content or len(content) < 100:
                content = trafilatura.extract(downloaded, output_format='text', favor_recall=True)
                
            if content:
                # Post-process to clean up and format
                content = re.sub(r'\s+', ' ', content)  # Normalize whitespace
                content = re.sub(r'\n\s*\n+', '\n\n', content)  # Normalize line breaks
                return content
                
        # If all extraction methods fail, return None
        return None
    except Exception as e:
        logger.error(f"Error fetching URL content: {e}")
        return None

def fetch_url_content_with_bs4(url: str) -> Optional[str]:
    """Fetch content from a URL using requests and BeautifulSoup as a backup method with enhanced multilingual support"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,hi;q=0.8',  # Include Hindi in accepted languages
            'Accept-Encoding': 'gzip, deflate, br'
        }
        
        # Set longer timeout for potentially slow sites
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Try to detect encoding if not specified
        if response.encoding == 'ISO-8859-1':
            encodings = requests.utils.get_encodings_from_content(response.text)
            if encodings:
                response.encoding = encodings[0]
            else:
                # Default to UTF-8 for many non-English sites
                response.encoding = 'utf-8'
                
        # Parse with the correct encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Try to find the main content area first for better extraction
        main_content = None
        
        # Look for common content containers
        content_candidates = soup.select('article, .content, .post-content, .entry-content, main, #content, .main-content, .questions, .quiz')
        if content_candidates:
            # Use the largest content area as it's likely to contain the main content
            main_content = max(content_candidates, key=lambda x: len(x.get_text()))
            soup = main_content  # Focus on this content
        
        # Remove script, style, and other non-content elements
        for element in soup(["script", "style", "header", "footer", "nav", "aside", "iframe", "meta", "noscript"]):
            element.extract()
            
        # Get text with appropriate formatting
        text = ''
        for element in soup.find_all(['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li']):
            # Add spacing based on element type
            if element.name.startswith('h'):
                text += '\n\n' + element.get_text().strip() + '\n'
            elif element.name == 'li':
                text += '\n• ' + element.get_text().strip()
            else:
                text += '\n' + element.get_text().strip()
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
        text = re.sub(r'\n\s*\n+', '\n\n', text)  # Normalize line breaks
        
        # If the text is too short, try a more aggressive approach
        if len(text) < 100:
            # Try getting all text as a fallback
            text = soup.get_text(separator='\n')
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return text
    except Exception as e:
        logger.error(f"Error fetching URL content with BS4: {e}")
        return None

def extract_questions_from_text(text: str) -> List[Dict]:
    """
    Extract questions and answers from text content
    Returns a list of question dictionaries in the format:
    {
        'question': 'What is the capital of France?',
        'options': ['Paris', 'London', 'Berlin', 'Madrid'],
        'correct_answer': 0,  # Index of correct answer
        'category': 'General Knowledge'
    }
    """
    if not text:
        return []
    
    extracted_questions = []
    
    # Pattern for matching multiple-choice questions
    # Looking for patterns like:
    # 1. Question text?
    # a) Option 1
    # b) Option 2
    # c) Option 3
    # Answer: a
    
    # Split text into lines for processing
    lines = text.split('\n')
    
    # More inclusive patterns for multilingual content
    # Handle both English and Hindi/other languages question formats
    question_pattern = re.compile(r'^(?:\d+[\.\)\-]|\([a-zA-Z0-9]\)|\*|●|•|Q\.?\s*\d*\.?)\s*(.*\??)')
    option_pattern = re.compile(r'^(?:[a-zA-Z]\)?\.?|\([a-zA-Z]\)|\d+[\.\)]|\([0-9]\)|[०-९][\.\)])\s*(.+)')
    answer_pattern = re.compile(r'(?:answer|correct|solution|ans|उत्तर|सही\s*उत्तर)[\s:\-—]+(?:[a-zA-Z]\)?|\([a-zA-Z]\)|\d+\.?|)?\s*([a-zA-Z0-9].+)', re.IGNORECASE)
    
    # Specifically look for Hindi numbering as well
    hindi_option_pattern = re.compile(r'^[०-९][\.\)]\s*(.+)')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        question_match = question_pattern.match(line)
        
        if question_match:
            question_text = question_match.group(1).strip()
            options = []
            correct_answer = None
            option_indices = {}
            
            # Look for options in subsequent lines
            j = i + 1
            option_index = 0
            while j < len(lines) and not question_pattern.match(lines[j].strip()):
                option_line = lines[j].strip()
                
                # Try regular option pattern first
                option_match = option_pattern.match(option_line)
                
                # If that fails, try Hindi option pattern
                if not option_match:
                    option_match = hindi_option_pattern.match(option_line)
                
                if option_match:
                    option_text = option_match.group(1).strip()
                    options.append(option_text)
                    # Store the mapping of option letter/number to index
                    if option_line[0].isalpha():
                        option_key = option_line[0].lower()
                    elif option_line[0] in '०१२३४५६७८९':
                        # Convert Hindi numerals to English
                        hindi_to_english = {'०': '0', '१': '1', '२': '2', '३': '3', '४': '4', 
                                          '५': '5', '६': '6', '७': '7', '८': '8', '९': '9'}
                        option_key = hindi_to_english[option_line[0]]
                    else:
                        # Get the first number in the string
                        match = re.search(r'\d+', option_line)
                        option_key = match.group(0) if match else option_line.split('.')[0].strip()
                    
                    option_indices[option_key] = option_index
                    option_index += 1
                
                # Check if this line contains the answer
                answer_match = answer_pattern.match(option_line)
                if answer_match:
                    answer_text = answer_match.group(1).strip().lower()
                    # The answer might be a letter or the full text of the correct option
                    if answer_text in option_indices:
                        correct_answer = option_indices[answer_text]
                    elif len(answer_text) == 1 and answer_text.isalpha():
                        # If the answer is just a single letter like 'a', 'b', etc.
                        letter_index = ord(answer_text) - ord('a')
                        if 0 <= letter_index < len(options):
                            correct_answer = letter_index
                    else:
                        # Try to match the answer text to one of the options
                        for idx, opt in enumerate(options):
                            if opt.lower() == answer_text:
                                correct_answer = idx
                                break
                
                j += 1
            
            # If we have a question with at least 2 options
            if question_text and len(options) >= 2:
                # If no correct answer was found, default to the first option
                if correct_answer is None:
                    correct_answer = 0
                
                extracted_questions.append({
                    'question': question_text,
                    'options': options,
                    'correct_answer': correct_answer,
                    'category': 'General Knowledge'  # Default category, can be changed later
                })
            
            i = j
        else:
            i += 1
    
    # Try a different approach if no questions were found
    if not extracted_questions:
        extracted_questions = extract_questions_alternative(text)
    
    return extracted_questions

def extract_questions_alternative(text: str) -> List[Dict]:
    """Alternative method to extract questions from less structured content"""
    extracted_questions = []
    
    # More aggressive approach for Hindi and multilingual content
    # Try to identify questions based on structure and patterns
    
    # Method 1: Find blocks that look like questions with options
    question_blocks = re.split(r'\n\s*\n|\n-{3,}|\n_{3,}|\n\*{3,}', text)
    
    for block in question_blocks:
        lines = block.strip().split('\n')
        if len(lines) < 3:  # Need at least a question and two options
            continue
        
        # Try to identify the question line (any line that might look like a question)
        question_line = None
        for i, line in enumerate(lines):
            # Question might have a number/bullet at start, might end with ?, 
            # or just be the first substantial line
            if ('?' in line or 
                re.match(r'^\d+[\.\)]', line) or 
                re.match(r'^Q\.', line, re.IGNORECASE) or
                re.match(r'^[०-९]+[\.\)]', line) or  # Hindi numbers
                (i == 0 and len(line) > 10)):
                question_line = line.strip()
                # Remove question numbers if present
                question_line = re.sub(r'^[०-९\d]+[\.\)]\s*', '', question_line)
                question_line = re.sub(r'^Q\.?\s*', '', question_line, flags=re.IGNORECASE)
                break
        
        if not question_line and len(lines) > 0:
            # If we couldn't identify a question, use the first line as fallback
            question_line = lines[0].strip()
            
        # Look for options with various patterns
        options = []
        option_indices = {}
        option_index = 0
        
        # Match patterns like: A) Option, (A) Option, A. Option, 1) Option, etc.
        # Also match Hindi options
        option_patterns = [
            r'^[A-Da-d][\.\)]\s+(.+)$',
            r'^\([A-Da-d]\)\s+(.+)$',
            r'^[0-9][\.\)]\s+(.+)$',
            r'^\([0-9]\)\s+(.+)$',
            r'^[०-९][\.\)]\s+(.+)$',
            r'^\([०-९]\)\s+(.+)$'
        ]
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            matched = False
            for pattern in option_patterns:
                option_match = re.match(pattern, line)
                if option_match:
                    option_text = option_match.group(1).strip()
                    options.append(option_text)
                    
                    # Store option key mapping
                    if line[0].isalpha():
                        option_key = line[0].lower()
                    elif line[0] in '०१२३४५६७८९':
                        hindi_to_english = {'०': '0', '१': '1', '२': '2', '३': '3', '४': '4', 
                                         '५': '5', '६': '6', '७': '7', '८': '8', '९': '9'}
                        option_key = hindi_to_english[line[0]]
                    else:
                        option_key = re.search(r'\d+', line).group(0) if re.search(r'\d+', line) else ''
                    
                    option_indices[option_key] = option_index
                    option_index += 1
                    matched = True
                    break
        
        # If we found at least 2 options
        if question_line and len(options) >= 2:
            # Try to find the correct answer
            correct_answer = None
            answer_patterns = [
                r'(?:सही\s*उत्तर|उत्तर|answer|correct|ans|right)[\s:\-—]+([A-Da-d\d०-९])',
                r'(?:Correct|Answer|Solution)\s*(?:is|:)\s*([A-Da-d\d])',
                r'(?:उत्तर|Answer)[\s:\-—]+([A-Da-d\d०-९])'
            ]
            
            for i, line in enumerate(lines):
                for pattern in answer_patterns:
                    answer_match = re.search(pattern, line, re.IGNORECASE)
                    if answer_match:
                        answer_key = answer_match.group(1).lower()
                        
                        # Convert Hindi numerals if needed
                        if answer_key in '०१२३४५६७८९':
                            hindi_to_english = {'०': '0', '१': '1', '२': '2', '३': '3', '४': '4', 
                                             '५': '5', '६': '6', '७': '7', '८': '8', '९': '9'}
                            answer_key = hindi_to_english[answer_key]
                        
                        # If answer is a letter, convert to index
                        if answer_key.isalpha():
                            letter_index = ord(answer_key) - ord('a')
                            if 0 <= letter_index < len(options):
                                correct_answer = letter_index
                        # If answer is a number, use it as index-1 (since options are 1-based)
                        elif answer_key.isdigit():
                            num_index = int(answer_key) - 1
                            if 0 <= num_index < len(options):
                                correct_answer = num_index
                        # If we have direct mapping of the option label
                        elif answer_key in option_indices:
                            correct_answer = option_indices[answer_key]
                        break
                
                if correct_answer is not None:
                    break
            
            # Default to the first option if no answer found
            if correct_answer is None:
                correct_answer = 0
                
            extracted_questions.append({
                'question': question_line,
                'options': options,
                'correct_answer': correct_answer,
                'category': 'General Knowledge'  # Default category
            })
    
    # Try yet another approach if still no questions
    if not extracted_questions:
        # Look for any blocks that have a numbered/lettered list that might be options
        for block in question_blocks:
            lines = block.strip().split('\n')
            if len(lines) < 3:  # Need at least a question and two options
                continue
            
            # Count lines that match option patterns
            option_count = 0
            for line in lines:
                if (re.match(r'^[A-Da-d][\.\)]', line) or 
                    re.match(r'^\([A-Da-d]\)', line) or
                    re.match(r'^[0-9][\.\)]', line) or
                    re.match(r'^\([0-9]\)', line) or
                    re.match(r'^[०-९][\.\)]', line)):
                    option_count += 1
            
            # If we have at least 2 options in this block
            if option_count >= 2:
                # Use first line as question, or find a line that might be a question
                question_line = lines[0].strip()
                for i, line in enumerate(lines):
                    if i == 0 or '?' in line or len(line) > 20:
                        question_line = line.strip()
                        break
                
                # Extract options
                options = []
                for line in lines:
                    if (re.match(r'^[A-Da-d][\.\)]', line) or 
                        re.match(r'^\([A-Da-d]\)', line) or
                        re.match(r'^[0-9][\.\)]', line) or
                        re.match(r'^\([0-9]\)', line) or
                        re.match(r'^[०-९][\.\)]', line)):
                        # Extract the option text after the marker
                        option_text = re.sub(r'^[A-Da-d0-9०-९][\.\)]|\([A-Da-d0-9०-९]\)\s*', '', line).strip()
                        options.append(option_text)
                
                # If we got at least 2 options
                if len(options) >= 2:
                    extracted_questions.append({
                        'question': question_line,
                        'options': options,
                        'correct_answer': 0,  # Default to first option
                        'category': 'General Knowledge'  # Default category
                    })
    
    return extracted_questions

async def start_url_extraction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the URL extraction process"""
    await update.message.reply_text(
        "Please send me a Google URL containing quiz questions. "
        "I'll extract the questions and add them to the question bank.\n\n"
        "You can send a URL to a quiz page or a search result page."
    )
    return URL_INPUT

async def process_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the URL sent by the user"""
    url = update.message.text.strip()
    
    # Validate URL (basic check)
    if not url.startswith(('http://', 'https://')):
        await update.message.reply_text(
            "That doesn't look like a valid URL. "
            "Please send a valid URL starting with http:// or https://.\n\n"
            "You can try again or use /cancel to exit."
        )
        return URL_INPUT
    
    # Store the URL in context
    context.user_data['url'] = url
    
    # Tell the user we're processing the URL
    processing_message = await update.message.reply_text("Processing URL... This might take a moment.")
    
    # Try to fetch content using Trafilatura first
    content = fetch_url_content(url)
    
    # If Trafilatura failed, try with BeautifulSoup
    if not content:
        await update.message.reply_text("First extraction method failed, trying alternative approach...")
        content = fetch_url_content_with_bs4(url)
    
    if not content:
        await update.message.reply_text(
            "❌ Failed to extract content from the URL. "
            "The site might be blocking scraping or the URL might be invalid.\n\n"
            "Please try another URL or use /cancel to exit."
        )
        return URL_INPUT
    
    # Extract questions from the content
    questions = extract_questions_from_text(content)
    
    # Store extracted questions in context
    context.user_data['extracted_questions'] = questions
    
    # Update the processing message
    await processing_message.edit_text(f"Processing complete! Found {len(questions)} questions.")
    
    if not questions:
        await update.message.reply_text(
            "❌ No questions found in the URL content. "
            "The URL might not contain properly formatted quiz questions.\n\n"
            "Please try another URL or use /cancel to exit."
        )
        return URL_INPUT
    
    # Show the first extracted question as a preview
    if questions:
        question = questions[0]
        preview_text = (
            f"📝 Found {len(questions)} questions! Here's a preview of the first one:\n\n"
            f"Question: {question['question']}\n\n"
            f"Options:\n"
        )
        
        for i, option in enumerate(question['options']):
            correct_mark = "✓ " if i == question['correct_answer'] else ""
            preview_text += f"{i+1}. {correct_mark}{option}\n"
        
        preview_text += f"\nCorrect answer: {question['correct_answer'] + 1}"
        
        # Create confirmation buttons
        keyboard = [
            [
                InlineKeyboardButton("✅ Add All Questions", callback_data="url_confirm_add_all"),
                InlineKeyboardButton("❌ Cancel", callback_data="url_cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(preview_text, reply_markup=reply_markup)
        return URL_CONFIRMATION
    
    return ConversationHandler.END

async def confirm_questions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle confirmation of extracted questions"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "url_cancel":
        await query.edit_message_text("Operation cancelled. No questions were added.")
        return ConversationHandler.END
    
    if query.data == "url_confirm_add_all":
        # Show category selection keyboard
        categories = [
            "General Knowledge",
            "Science",
            "History",
            "Geography",
            "Entertainment",
            "Sports",
            "Other"
        ]
        
        keyboard = []
        for category in categories:
            keyboard.append([InlineKeyboardButton(category, callback_data=f"url_category_{category}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Please select a category for these questions:",
            reply_markup=reply_markup
        )
        return CATEGORY_SELECTION
    
    return ConversationHandler.END

async def select_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle selection of category for the extracted questions"""
    query = update.callback_query
    await query.answer()
    
    # Extract the category from callback data
    category = query.data.replace("url_category_", "")
    
    # Get extracted questions from context
    questions = context.user_data.get('extracted_questions', [])
    
    if not questions:
        await query.edit_message_text("❌ Error: No questions found in memory. Please try again.")
        return ConversationHandler.END
    
    # Set the category for all questions
    for question in questions:
        question['category'] = category
    
    # Add questions to the database
    questions_added = 0
    next_id = get_next_question_id()
    
    for question in questions:
        # Convert to the format expected by add_question_with_id
        question_data = {
            'question': question['question'],
            'options': question['options'],
            'answer': question['correct_answer'],
            'category': question['category']
        }
        add_question_with_id(next_id, question_data)
        next_id += 1
        questions_added += 1
    
    await query.edit_message_text(
        f"✅ Successfully added {questions_added} questions to the category '{category}'!\n\n"
        f"You can now use these questions in your quizzes."
    )
    
    # Clean up context data
    if 'extracted_questions' in context.user_data:
        del context.user_data['extracted_questions']
    if 'url' in context.user_data:
        del context.user_data['url']
    
    return ConversationHandler.END

async def url_extraction_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the URL extraction process"""
    await update.message.reply_text("URL extraction cancelled.")
    
    # Clean up context data
    if 'extracted_questions' in context.user_data:
        del context.user_data['extracted_questions']
    if 'url' in context.user_data:
        del context.user_data['url']
    
    return ConversationHandler.END
# ---------- END URL TO QUESTION FUNCTIONALITY ----------

# Original function (unchanged)
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display user statistics."""
    # Call the extended stats command instead to show penalties
    await extended_stats_command(update, context)

async def add_question_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the process of adding a new question."""
    await update.message.reply_text(
        "Let's add a new quiz question! First, send me the question text."
    )
    return QUESTION

async def add_question_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the question text and ask for options."""
    context.user_data["new_question"] = {"question": update.message.text}
    await update.message.reply_text(
        "Great! Now send me the answer options, one per line. For example:\n\n"
        "Paris\n"
        "London\n"
        "Berlin\n"
        "Rome"
    )
    return OPTIONS

async def add_question_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the options and ask for the correct answer."""
    options = update.message.text.split('\n')
    context.user_data["new_question"]["options"] = options
    
    options_text = "\n".join([f"{i}. {opt}" for i, opt in enumerate(options)])
    await update.message.reply_text(
        f"Options saved! Now tell me which one is correct (0-{len(options)-1}):\n\n{options_text}"
    )
    return ANSWER

async def add_question_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the correct answer and create the question."""
    try:
        answer = int(update.message.text)
        options = context.user_data["new_question"]["options"]
        
        if 0 <= answer < len(options):
            new_question = context.user_data["new_question"]
            new_question["answer"] = answer
            
            # Ask for custom ID or auto-generate
            keyboard = [
                [InlineKeyboardButton("Auto-generate ID", callback_data="auto_id")],
                [InlineKeyboardButton("Specify custom ID", callback_data="custom_id")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "How would you like to assign an ID to this question?",
                reply_markup=reply_markup
            )
            return CUSTOM_ID
        else:
            await update.message.reply_text(
                f"Please enter a valid option number between 0 and {len(options)-1}."
            )
            return ANSWER
    except ValueError:
        await update.message.reply_text(
            "Please enter a valid number."
        )
        return ANSWER

async def custom_id_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle ID selection method."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "auto_id":
        # Auto-generate ID and continue to category
        categories = ["General Knowledge", "Science", "History", "Geography", "Entertainment", "Sports"]
        keyboard = [[InlineKeyboardButton(cat, callback_data=f"category_{cat}")] for cat in categories]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Select a category for this question:",
            reply_markup=reply_markup
        )
        return CATEGORY
    else:
        # Ask user to input a custom ID
        await query.edit_message_text(
            "Please enter a numeric ID for this question. If the ID already exists, your question will be added to that ID without overwriting existing questions."
        )
        context.user_data["awaiting_custom_id"] = True
        return CUSTOM_ID

async def custom_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom ID input."""
    try:
        custom_id = int(update.message.text)
        context.user_data["custom_id"] = custom_id
        
        # Show category selection
        categories = ["General Knowledge", "Science", "History", "Geography", "Entertainment", "Sports"]
        keyboard = [[InlineKeyboardButton(cat, callback_data=f"category_{cat}")] for cat in categories]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Select a category for this question:",
            reply_markup=reply_markup
        )
        return CATEGORY
    except ValueError:
        await update.message.reply_text(
            "Please enter a valid numeric ID."
        )
        return CUSTOM_ID

async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle category selection."""
    query = update.callback_query
    await query.answer()
    
    category = query.data.replace("category_", "")
    new_question = context.user_data["new_question"]
    new_question["category"] = category
    
    # Save the question with appropriate ID
    if context.user_data.get("custom_id"):
        question_id = context.user_data["custom_id"]
    else:
        question_id = get_next_question_id()
    
    # Add question to ID (preserving existing questions)
    add_question_with_id(question_id, new_question)
    
    await query.edit_message_text(
        f"✅ Question added successfully with ID: {question_id}\n\n"
        f"Question: {new_question['question']}\n"
        f"Category: {category}"
    )
    
    # Clean up
    if "custom_id" in context.user_data:
        del context.user_data["custom_id"]
    if "awaiting_custom_id" in context.user_data:
        del context.user_data["awaiting_custom_id"]
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current operation."""
    await update.message.reply_text(
        "Operation cancelled."
    )
    # Clean up any custom ID related data
    if "custom_id" in context.user_data:
        del context.user_data["custom_id"]
    if "awaiting_custom_id" in context.user_data:
        del context.user_data["awaiting_custom_id"]
    
    return ConversationHandler.END

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a question by ID."""
    # Check if ID was provided with command
    args = context.args
    if args and len(args) > 0:
        try:
            question_id = int(args[0])
            if delete_question_by_id(question_id):
                await update.message.reply_text(f"Question with ID {question_id} has been deleted.")
            else:
                await update.message.reply_text(f"No question found with ID {question_id}.")
        except ValueError:
            await update.message.reply_text("Please provide a valid numeric ID.")
    else:
        # If no ID provided, show list of questions
        questions = load_questions()
        if not questions:
            await update.message.reply_text("No questions available to delete.")
            return
        
        message = "To delete a question, use /delete <id>. Available questions:\n\n"
        for qid, question_list in questions.items():
            if isinstance(question_list, list):
                message += f"ID: {qid} - {len(question_list)} questions\n"
            else:
                message += f"ID: {qid} - {question_list.get('question', 'Untitled')[:30]}...\n"
        
        await update.message.reply_text(message)

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a quiz session with random questions."""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    # Load all questions
    all_questions = load_questions()
    if not all_questions:
        await update.message.reply_text("No questions available. Add some with /add first!")
        return
    
    # Initialize quiz state
    context.chat_data["quiz"] = {
        "active": True,
        "current_index": 0,
        "questions": [],
        "sent_polls": {},
        "participants": {},
        "chat_id": chat_id,
        "creator": {
            "id": user.id,
            "name": user.first_name,
            "username": user.username
        }
    }
    
    # Flatten list of all questions
    all_question_list = []
    for qid, questions in all_questions.items():
        if isinstance(questions, list):
            for q in questions:
                q["id"] = qid
                all_question_list.append(q)
        else:
            questions["id"] = qid
            all_question_list.append(questions)
    
    # Select random questions
    num_questions = min(5, len(all_question_list))
    selected_questions = random.sample(all_question_list, num_questions)
    context.chat_data["quiz"]["questions"] = selected_questions
    
    # Include negative marking information in the message
    negative_status = "ENABLED" if NEGATIVE_MARKING_ENABLED else "DISABLED"
    
    await update.message.reply_text(
        f"Starting a quiz with {num_questions} questions! Questions will automatically proceed after 30 seconds.\n\n"
        f"❗ Negative marking is {negative_status} - incorrect answers will deduct points!\n\n"
        f"First question coming up..."
    )
    
    # Send first question with slight delay
    await asyncio.sleep(2)
    await send_question(context, chat_id, 0)

async def send_question(context, chat_id, question_index):
    """Send a quiz question and schedule next one."""
    quiz = context.chat_data.get("quiz", {})
    
    if not quiz.get("active", False):
        return
    
    questions = quiz.get("questions", [])
    
    if question_index >= len(questions):
        # End of quiz
        await end_quiz(context, chat_id)
        return
    
    # Get current question
    question = questions[question_index]
    
    # Send the poll
    message = await context.bot.send_poll(
        chat_id=chat_id,
        question=question["question"],
        options=question["options"],
        type="quiz",
        correct_option_id=question["answer"],
        is_anonymous=False,
        open_period=25  # Close poll after 25 seconds
    )
    
    # Store poll information
    poll_id = message.poll.id
    sent_polls = quiz.get("sent_polls", {})
    sent_polls[str(poll_id)] = {
        "question_index": question_index,
        "message_id": message.message_id,
        "answers": {}
    }
    quiz["sent_polls"] = sent_polls
    quiz["current_index"] = question_index
    context.chat_data["quiz"] = quiz
    
    # Schedule next question or end of quiz
    if question_index + 1 < len(questions):
        # Schedule next question
        asyncio.create_task(schedule_next_question(context, chat_id, question_index + 1))
    else:
        # Last question, schedule end of quiz
        asyncio.create_task(schedule_end_quiz(context, chat_id))

async def schedule_next_question(context, chat_id, next_index):
    """Schedule the next question with delay."""
    await asyncio.sleep(30)  # Wait 30 seconds
    
    # Check if quiz is still active
    quiz = context.chat_data.get("quiz", {})
    if quiz.get("active", False):
        await send_question(context, chat_id, next_index)

async def schedule_end_quiz(context, chat_id):
    """Schedule end of quiz with delay."""
    await asyncio.sleep(30)  # Wait 30 seconds after last question
    
    # End the quiz
    await end_quiz(context, chat_id)

# ---------- NEGATIVE MARKING POLL ANSWER MODIFICATIONS ----------
async def poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle poll answers from users with negative marking."""
    answer = update.poll_answer
    poll_id = answer.poll_id
    user = answer.user
    selected_options = answer.option_ids
    
    # Debug log
    logger.info(f"Poll answer received from {user.first_name} (ID: {user.id}) for poll {poll_id}")
    
    # Check all chat data to find the quiz this poll belongs to
    for chat_id, chat_data in context.application.chat_data.items():
        quiz = chat_data.get("quiz", {})
        
        if not quiz.get("active", False):
            continue
        
        sent_polls = quiz.get("sent_polls", {})
        
        if str(poll_id) in sent_polls:
            poll_info = sent_polls[str(poll_id)]
            question_index = poll_info.get("question_index", 0)
            questions = quiz.get("questions", [])
            
            if question_index < len(questions):
                question = questions[question_index]
                correct_answer = question.get("answer", 0)
                category = question.get("category", "General Knowledge")
                
                # Initialize answers dict if needed
                if "answers" not in poll_info:
                    poll_info["answers"] = {}
                
                # Record the answer
                is_correct = False
                if selected_options and len(selected_options) > 0:
                    is_correct = selected_options[0] == correct_answer
                
                poll_info["answers"][str(user.id)] = {
                    "user_name": user.first_name,
                    "username": user.username,
                    "option_id": selected_options[0] if selected_options else None,
                    "is_correct": is_correct
                }
                
                # Update participants dictionary
                participants = quiz.get("participants", {})
                if str(user.id) not in participants:
                    participants[str(user.id)] = {
                        "name": user.first_name,
                        "username": user.username or "",
                        "correct": 0,
                        "answered": 0,
                        "participation": 0  # For backward compatibility
                    }
                
                participants[str(user.id)]["answered"] += 1
                participants[str(user.id)]["participation"] += 1  # For backward compatibility
                if is_correct:
                    participants[str(user.id)]["correct"] += 1
                
                # NEGATIVE MARKING ADDITION: Apply penalty for incorrect answers
                if NEGATIVE_MARKING_ENABLED and not is_correct:
                    # Get and apply penalty
                    penalty = get_penalty_for_category(category)
                    if penalty > 0:
                        # Record the penalty in the user's answer
                        user_answer = poll_info["answers"][str(user.id)]
                        user_answer["penalty"] = penalty
                        # Apply the penalty to the user's record
                        current_penalty = update_user_penalties(user.id, penalty)
                        logger.info(f"Applied penalty of {penalty} to user {user.id}, total penalties: {current_penalty}")
                
                # Save back to quiz
                quiz["participants"] = participants
                sent_polls[str(poll_id)] = poll_info
                quiz["sent_polls"] = sent_polls
                context.application.chat_data[chat_id] = chat_data
                
                # Update user global stats
                user_stats = get_user_data(user.id)
                user_stats["total_answers"] = user_stats.get("total_answers", 0) + 1
                if is_correct:
                    user_stats["correct_answers"] = user_stats.get("correct_answers", 0) + 1
                save_user_data(user.id, user_stats)
                
                break
# ---------- END NEGATIVE MARKING POLL ANSWER MODIFICATIONS ----------

# ---------- NEGATIVE MARKING END QUIZ MODIFICATIONS ----------
async def end_quiz(context, chat_id):
    """End the quiz and display results with all participants and penalties."""
    quiz = context.chat_data.get("quiz", {})
    
    if not quiz.get("active", False):
        return
    
    # Mark quiz as inactive
    quiz["active"] = False
    context.chat_data["quiz"] = quiz
    
    # Get quiz data
    questions = quiz.get("questions", [])
    questions_count = len(questions)
    participants = quiz.get("participants", {})
    
    # If no participants recorded, try to reconstruct from poll answers
    if not participants:
        participants = {}
        sent_polls = quiz.get("sent_polls", {})
        
        for poll_id, poll_info in sent_polls.items():
            for user_id, answer in poll_info.get("answers", {}).items():
                if user_id not in participants:
                    participants[user_id] = {
                        "name": answer.get("user_name", f"User {user_id}"),
                        "username": answer.get("username", ""),
                        "correct": 0,
                        "answered": 0,
                        "participation": 0  # For backward compatibility
                    }
                
                participants[user_id]["answered"] += 1
                participants[user_id]["participation"] += 1  # For backward compatibility
                if answer.get("is_correct", False):
                    participants[user_id]["correct"] += 1
    
    # Make sure quiz creator is in participants
    creator = quiz.get("creator", {})
    creator_id = str(creator.get("id", ""))
    if creator_id and creator_id not in participants:
        participants[creator_id] = {
            "name": creator.get("name", "Quiz Creator"),
            "username": creator.get("username", ""),
            "correct": 0,
            "answered": 0,
            "participation": 0  # For backward compatibility
        }
    
    # NEGATIVE MARKING ADDITION: Calculate scores with penalties
    final_scores = []
    for user_id, user_data in participants.items():
        user_name = user_data.get("name", f"User {user_id}")
        correct_count = user_data.get("correct", 0)
        participation_count = user_data.get("participation", user_data.get("answered", 0))
        
        # Get penalty points for this user
        penalty_points = get_user_penalties(user_id)
        
        # Calculate adjusted score
        adjusted_score = max(0, correct_count - penalty_points)
        
        final_scores.append({
            "user_id": user_id,
            "name": user_name,
            "correct": correct_count,
            "participation": participation_count,
            "penalty": penalty_points,
            "adjusted_score": adjusted_score
        })
    
    # Sort by adjusted score (highest first) and then by raw score
    final_scores.sort(key=lambda x: (x["adjusted_score"], x["correct"]), reverse=True)
    
    # Create results message
    results_message = f"🏁 The quiz has finished!\n\n{questions_count} questions answered\n\n"
    
    # Format results
    if final_scores:
        if NEGATIVE_MARKING_ENABLED:
            results_message += "❗ Negative marking was enabled for this quiz\n\n"
        
        winner_data = final_scores[0]
        winner_name = winner_data.get("name", "Quiz Taker")
        
        results_message += f"🏆 Congratulations to the winner: {winner_name}!\n\n"
        results_message += "📊 Final Ranking 📊\n"
        
        # Show all participants with ranks
        for i, data in enumerate(final_scores):
            rank_emoji = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
            
            name = data.get("name", f"Player {i+1}")
            correct = data.get("correct", 0)
            participation = data.get("participation", 0)
            penalty = data.get("penalty", 0)
            adjusted = data.get("adjusted_score", correct)
            
            percentage = (correct / questions_count * 100) if questions_count > 0 else 0
            adjusted_percentage = (adjusted / questions_count * 100) if questions_count > 0 else 0
            
            if NEGATIVE_MARKING_ENABLED and penalty > 0:
                # Include penalty information
                results_message += (
                    f"{rank_emoji} {name}: {correct}/{participation} ({percentage:.1f}%)\n"
                    f"   Penalty: -{penalty:.2f} points\n"
                    f"   Final score: {adjusted:.2f} points ({adjusted_percentage:.1f}%)\n\n"
                )
            else:
                # Standard format without penalties
                results_message += f"{rank_emoji} {name}: {correct}/{participation} ({percentage:.1f}%)\n"
    else:
        results_message += "No participants found for this quiz."
    
    # Send results
    await context.bot.send_message(
        chat_id=chat_id,
        text=results_message
    )
# ---------- END NEGATIVE MARKING END QUIZ MODIFICATIONS ----------

async def poll_to_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Convert a Telegram poll to a quiz question."""
    await update.message.reply_text(
        "To convert a Telegram poll to a quiz question, please forward me a poll message."
        "\n\nMake sure it's the poll itself, not just text."
    )

async def handle_forwarded_poll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a forwarded poll message."""
    message = update.message
    
    if message.forward_from_chat and hasattr(message, 'poll') and message.poll:
        poll = message.poll
        
        # Extract poll data
        question_text = poll.question
        options = [option.text for option in poll.options]
        
        # Store in context for later
        context.user_data["poll2q"] = {
            "question": question_text,
            "options": options
        }
        
        # Create keyboard for selecting correct answer
        keyboard = []
        for i, option in enumerate(options):
            short_option = option[:20] + "..." if len(option) > 20 else option
            keyboard.append([InlineKeyboardButton(
                f"{i}. {short_option}", 
                callback_data=f"poll_answer_{i}"
            )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"I've captured the poll: '{question_text}'\n\n"
            f"Please select the correct answer:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "That doesn't seem to be a poll message. Please forward a message containing a poll."
        )

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle selection of correct answer for poll conversion."""
    query = update.callback_query
    await query.answer()
    
    answer_index = int(query.data.replace("poll_answer_", ""))
    poll_data = context.user_data.get("poll2q", {})
    poll_data["answer"] = answer_index
    context.user_data["poll2q"] = poll_data
    
    # Ask for custom ID or auto-generate
    keyboard = [
        [InlineKeyboardButton("Auto-generate ID", callback_data="pollid_auto")],
        [InlineKeyboardButton("Specify custom ID", callback_data="pollid_custom")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Selected answer: {answer_index}. {poll_data['options'][answer_index]}\n\n"
        f"How would you like to assign an ID to this question?",
        reply_markup=reply_markup
    )

async def handle_poll_id_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ID method selection for poll conversion."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "pollid_auto":
        # Show category selection
        categories = ["General Knowledge", "Science", "History", "Geography", "Entertainment", "Sports"]
        keyboard = [[InlineKeyboardButton(cat, callback_data=f"pollcat_{cat}")] for cat in categories]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Select a category for this question:",
            reply_markup=reply_markup
        )
    else:
        # Ask for custom ID
        await query.edit_message_text(
            "Please send me the custom ID number you want to use for this question. "
            "If the ID already exists, your question will be added to that ID without overwriting existing questions."
        )
        context.user_data["awaiting_poll_id"] = True

async def handle_poll_custom_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle custom ID input for poll conversion."""
    if context.user_data.get("awaiting_poll_id"):
        try:
            custom_id = int(update.message.text)
            context.user_data["poll_custom_id"] = custom_id
            del context.user_data["awaiting_poll_id"]
            
            # Show category selection
            categories = ["General Knowledge", "Science", "History", "Geography", "Entertainment", "Sports"]
            keyboard = [[InlineKeyboardButton(cat, callback_data=f"pollcat_{cat}")] for cat in categories]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "Select a category for this question:",
                reply_markup=reply_markup
            )
        except ValueError:
            await update.message.reply_text(
                "Please send a valid numeric ID."
            )

async def handle_poll_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle category selection for poll conversion."""
    query = update.callback_query
    await query.answer()
    
    category = query.data.replace("pollcat_", "")
    poll_data = context.user_data.get("poll2q", {})
    poll_data["category"] = category
    
    # Determine question ID
    if context.user_data.get("poll_custom_id"):
        question_id = context.user_data["poll_custom_id"]
        del context.user_data["poll_custom_id"]
    else:
        question_id = get_next_question_id()
    
    # Add the question with the ID (preserving existing questions)
    add_question_with_id(question_id, poll_data)
    
    # Get how many questions are now at this ID
    questions = load_questions()
    question_count = len(questions[str(question_id)]) if isinstance(questions[str(question_id)], list) else 1
    
    await query.edit_message_text(
        f"✅ Question added successfully with ID: {question_id}\n\n"
        f"This ID now has {question_count} question(s)\n\n"
        f"Question: {poll_data['question']}\n"
        f"Category: {category}\n"
        f"Options: {len(poll_data['options'])}\n"
        f"Correct answer: {poll_data['answer']}. {poll_data['options'][poll_data['answer']]}"
    )

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Basic command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("stats", stats_command))  # This calls extended_stats_command
    application.add_handler(CommandHandler("delete", delete_command))
    
    # NEGATIVE MARKING ADDITION: Add new command handlers
    application.add_handler(CommandHandler("negmark", negative_marking_settings))
    application.add_handler(CommandHandler("resetpenalty", reset_user_penalty_command))
    application.add_handler(CallbackQueryHandler(negative_settings_callback, pattern=r"^neg_mark_"))
    
    # URL to Question command and handlers
    url_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("url2q", start_url_extraction)],
        states={
            URL_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_url)],
            URL_CONFIRMATION: [CallbackQueryHandler(confirm_questions, pattern=r'^url_')],
            CATEGORY_SELECTION: [CallbackQueryHandler(select_category, pattern=r'^url_category_')]
        },
        fallbacks=[CommandHandler("cancel", url_extraction_cancel)]
    )
    application.add_handler(url_conv_handler)
    
    # Poll to question command and handlers
    application.add_handler(CommandHandler("poll2q", poll_to_question))
    application.add_handler(MessageHandler(
        filters.FORWARDED & ~filters.COMMAND, 
        handle_forwarded_poll
    ))
    application.add_handler(CallbackQueryHandler(handle_poll_answer, pattern=r"^poll_answer_"))
    application.add_handler(CallbackQueryHandler(handle_poll_id_selection, pattern=r"^pollid_"))
    application.add_handler(CallbackQueryHandler(handle_poll_category, pattern=r"^pollcat_"))
    
    # Custom ID message handler for poll
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_poll_custom_id,
        lambda update, context: context.user_data.get("awaiting_poll_id", False)
    ))
    
    # Add question conversation handler
    add_question_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_question_start)],
        states={
            QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_text)],
            OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_options)],
            ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_answer)],
            CUSTOM_ID: [
                CallbackQueryHandler(custom_id_callback, pattern=r"^(auto_id|custom_id)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_id_input, 
                    lambda update, context: context.user_data.get("awaiting_custom_id", False)
                )
            ],
            CATEGORY: [CallbackQueryHandler(category_callback, pattern=r"^category_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(add_question_handler)
    
    # Poll Answer Handler - CRITICAL for tracking all participants
    application.add_handler(PollAnswerHandler(poll_answer))
    
    # Start the Bot
    application.run_polling()

if __name__ == "__main__":
    main()
