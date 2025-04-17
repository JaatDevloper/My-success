# OCR + PDF Text Extraction + Block-Level Deduplication
import os
import pytesseract
import pdfplumber
import fitz  # PyMuPDF
from PIL import Image
import re

# Setup Tesseract path
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"
os.environ['TESSDATA_PREFIX'] = "/usr/share/tesseract-ocr/5/tessdata"

# Import additional libraries for web scraping
try:
    import requests
    from bs4 import BeautifulSoup
    import trafilatura
    from urllib.parse import urlparse
    WEB_SCRAPING_SUPPORT = True
except ImportError:
    WEB_SCRAPING_SUPPORT = False

# Web scraper functions - integrated directly into main file
def get_website_text_content(url):
    """
    Extract readable text content from a website URL using trafilatura.
    
    Args:
        url (str): The website URL to scrape
        
    Returns:
        str: The extracted text content
    """
    try:
        downloaded = trafilatura.fetch_url(url)
        text = trafilatura.extract(downloaded)
        return text
    except Exception as e:
        logger.error(f"Error extracting text from website: {e}")
        return ""

def detect_language(text):
    """
    Detect if the text contains Hindi characters.
    
    Args:
        text (str): The text to check
        
    Returns:
        str: 'hi' if Hindi characters are detected, 'en' otherwise
    """
    # Simple Hindi character detection
    hindi_pattern = re.compile(r'[\u0900-\u097F]')
    if hindi_pattern.search(text):
        return 'hi'
    
    return 'en'

def extract_questions_with_options(text):
    """
    Extract questions and their options from text content.
    Works with both English and Hindi text.
    Enhanced to better preserve original option text.
    
    Args:
        text (str): The text content to process
        
    Returns:
        list: List of dictionaries containing questions with their options and answers
    """
    if not text:
        return []
    
    # Detect language
    language = detect_language(text)
    
    # Split text into lines and remove empty lines
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Initialize variables
    questions = []
    current_question = None
    current_options = []
    correct_answer = None
    
    # Patterns for question detection
    # Look for lines ending with question mark or starting with Q. or Question
    question_patterns = [
        r'^.*\?$',  # Ends with question mark
        r'^Q\.?\s*\d*\.?\s+.*',  # Starts with Q. or Q followed by number
        r'^Question\s*\d*\.?\s+.*',  # Starts with "Question" possibly followed by number
        r'^\d+\.\s+.*\?$',  # Numbered question ending with question mark
        r'^प्रश्न\s*\d*\.?\s+.*',  # Hindi "Question" possibly followed by number
    ]
    
    # Patterns for option detection
    # Look for lines starting with A., B., C., D. or 1., 2., 3., 4. or (a), (b), etc.
    option_patterns = [
        # English patterns - Most common first for better performance
        r'^[A-D]\.?\s+(.+)',  # A. Option text
        r'^\([A-D]\)\s+(.+)',  # (A) Option text
        r'^[a-d]\.?\s+(.+)',  # a. Option text
        r'^\([a-d]\)\s+(.+)',  # (a) Option text
        r'^\d+\.\s+(.+)',  # 1. Option text
        r'^\(\d+\)\s+(.+)',  # (1) Option text
        # Hindi specific patterns
        r'^पहला विकल्प\s*:?\s+(.+)',  # पहला विकल्प: Option text
        r'^दूसरा विकल्प\s*:?\s+(.+)',  # दूसरा विकल्प: Option text
        r'^तीसरा विकल्प\s*:?\s+(.+)',  # तीसरा विकल्प: Option text
        r'^चौथा विकल्प\s*:?\s+(.+)',  # चौथा विकल्प: Option text
        # Universal option markers for Hindi
        r'^विकल्प\s+[क-घ]\s*:?\s+(.+)',  # विकल्प क: Option text
        r'^[क-घ]\.\s+(.+)',  # क. Option text
        r'^\([क-घ]\)\s+(.+)',  # (क) Option text
    ]
    
    # Pattern for answer detection
    answer_patterns = [
        r'^(Answer|Ans|Correct Answer|Solution)s?\s*:?\s*([A-D]|\d+|[क-घ])',
        r'^सही उत्तर\s*:?\s*([A-D]|\d+|[क-घ])',
        r'^उत्तर\s*:?\s*([A-D]|\d+|[क-घ])'
    ]
    
    # State tracking
    in_options_section = False
    option_count = 0
    option_markers = []
    
    # Process each line
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check if this line is a question
        is_question = any(re.match(pattern, line) for pattern in question_patterns) or '?' in line
        
        # If we found a question and we already have a current question, save the previous one
        if is_question and current_question:
            # If we have options for the previous question, save it
            if current_options:
                # Create question data structure
                q_data = {
                    'question': current_question,
                    'options': current_options.copy(),
                    'correct_answer': correct_answer if correct_answer is not None else 0
                }
                questions.append(q_data)
            
            # Reset for new question
            current_options = []
            correct_answer = None
            in_options_section = False
            option_count = 0
            option_markers = []
        
        # Process current line
        if is_question:
            # Store the question
            current_question = line
            # Make sure question ends with question mark
            if not current_question.endswith('?'):
                current_question = current_question + '?'
            in_options_section = True  # Start looking for options after a question
        
        # Check if this line is an option
        elif in_options_section:
            is_option = False
            option_text = None
            
            # Try to match against option patterns
            for pattern in option_patterns:
                match = re.match(pattern, line)
                if match:
                    is_option = True
                    
                    # Extract option text directly from regex capture group when possible
                    if match.groups():
                        option_text = match.group(1).strip()
                    else:
                        # Fall back to splitting if no capture group (shouldn't happen with current patterns)
                        marker_text = line.split(None, 1)
                        option_text = marker_text[1] if len(marker_text) > 1 else ""
                    
                    # Extract marker for tracking
                    marker = line.split()[0].rstrip('.:)')
                    marker = marker.strip('()')
                    option_markers.append(marker)
                    
                    # Special handling for Hindi options to ensure we're getting the complete text
                    if "विकल्प" in line and option_text:
                        # Further cleanup of Hindi option text if needed
                        if ":" in option_text and option_text.startswith("विकल्प"):
                            parts = option_text.split(":", 1)
                            if len(parts) > 1:
                                option_text = parts[1].strip()
                    
                    # Add the option with the full text preserved
                    current_options.append(option_text.strip())
                    option_count += 1
                    break
            
            # If not an option, check if it's an answer
            if not is_option:
                for pattern in answer_patterns:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        # Extract the answer marker - should be the correct group
                        ans_marker = None
                        if match.group(2) if len(match.groups()) > 1 else None:
                            ans_marker = match.group(2)
                        else:
                            ans_marker = match.group(1)
                        
                        # Try to convert the answer to a zero-based index
                        if ans_marker.isdigit():
                            # If numeric, convert to zero-based index
                            correct_answer = int(ans_marker) - 1
                        elif ans_marker.upper() in 'ABCD':
                            # If A, B, C, D, convert to 0, 1, 2, 3 (case insensitive)
                            correct_answer = ord(ans_marker.upper()) - ord('A')
                        elif ans_marker in 'क ख ग घ':
                            # If Hindi letters, convert to 0, 1, 2, 3
                            hindi_letter_map = {'क': 0, 'ख': 1, 'ग': 2, 'घ': 3}
                            correct_answer = hindi_letter_map.get(ans_marker, 0)
                        break
                
                # If we have enough options and hit a non-option line, we might be done with this question's options
                if option_count >= 2 and (i+1 >= len(lines) or not any(re.match(pattern, lines[i+1]) for pattern in option_patterns)):
                    # Only end options section if the next line looks like a new question or an answer
                    next_is_question = False
                    if i+1 < len(lines):
                        next_is_question = any(re.match(pattern, lines[i+1]) for pattern in question_patterns) or '?' in lines[i+1]
                    
                    if next_is_question or (i+1 >= len(lines)):
                        in_options_section = False
        
        i += 1
    
    # Don't forget the last question
    if current_question and current_options:
        q_data = {
            'question': current_question,
            'options': current_options.copy(),
            'correct_answer': correct_answer if correct_answer is not None else 0
        }
        questions.append(q_data)
    
    # Clean up and validate questions
    validated_questions = []
    for q in questions:
        # Ensure we have at least 2 options
        if len(q['options']) >= 2:
            # Make sure correct_answer is within the range of options
            if q['correct_answer'] is not None and (q['correct_answer'] < 0 or q['correct_answer'] >= len(q['options'])):
                q['correct_answer'] = 0
            
            # Ensure options don't contain default Hindi placeholders
            actual_options = [opt for opt in q['options'] if opt and not opt.startswith("विकल्प")]
            if len(actual_options) >= 2:
                q['options'] = actual_options
                validated_questions.append(q)
    
    return validated_questions

def scrape_questions_from_url(url):
    """
    Scrape questions with options from a given URL.
    
    Args:
        url (str): The website URL to scrape for questions
        
    Returns:
        list: List of dictionaries containing questions with their options and answers
    """
    # Get website content
    content = get_website_text_content(url)
    if not content:
        return []
    
    # Extract questions with options
    return extract_questions_with_options(content)

def extract_text_from_pdf(file_path):
    try:
        # Try with pdfplumber first
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
        if text.strip():
            return text.splitlines()
    except Exception as e:
        print("pdfplumber failed:", e)

    try:
        # Fallback to PyMuPDF
        text = ""
        doc = fitz.open(file_path)
        for page in doc:
            t = page.get_text()
            if t:
                text += t + "\n"
        if text.strip():
            return text.splitlines()
    except Exception as e:
        print("PyMuPDF failed:", e)

    # Final fallback: OCR with Tesseract
    try:
        text = ""
        doc = fitz.open(file_path)
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            t = pytesseract.image_to_string(img, lang='hin')
            if t:
                text += t + "\n"
        return text.splitlines()
    except Exception as e:
        print("Tesseract OCR failed:", e)
        return []

def group_and_deduplicate_questions(lines):
    blocks = []
    current_block = []
    seen_blocks = set()

    for line in lines:
        if re.match(r'^Q[\.:\d]', line.strip(), re.IGNORECASE) and current_block:
            block_text = "\n".join(current_block).strip()
            if block_text not in seen_blocks:
                seen_blocks.add(block_text)
                blocks.append(current_block)
            current_block = []
        current_block.append(line.strip())

    if current_block:
        block_text = "\n".join(current_block).strip()
        if block_text not in seen_blocks:
            seen_blocks.add(block_text)
            blocks.append(current_block)

    final_lines = []
    for block in blocks:
        final_lines.extend(block)
        final_lines.append("")  # spacing
    return final_lines


"""
Enhanced Telegram Quiz Bot with PDF Import & Hindi Support
- Based on the original multi_id_quiz_bot.py
- Added negative marking features
- Added PDF import with automatic question extraction
- Added Hindi language support for PDFs
"""

# Import libraries for PDF handling
try:
    import PyPDF2
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

try:
    from PIL import Image
    IMAGE_SUPPORT = True
except ImportError:
    IMAGE_SUPPORT = False

import tempfile
TEMP_DIR = tempfile.mkdtemp()

import json
import re
import logging
import os
import random
import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler, PollAnswerHandler

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment variable
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7631768276:AAEkA0oEuyv0nYMQ_M-JTuLnrn9oHUI0X68")

# Conversation states
QUESTION, OPTIONS, ANSWER, CATEGORY = range(4)
EDIT_SELECT, EDIT_QUESTION, EDIT_OPTIONS = range(4, 7)
CLONE_URL, CLONE_MANUAL = range(7, 9)
CUSTOM_ID = range(9, 10)

# PDF import conversation states (use high numbers to avoid conflicts)
PDF_UPLOAD, PDF_CUSTOM_ID, PDF_PROCESSING = range(100, 103)

# Web scraping import states
WEB_URL, WEB_CUSTOM_ID, WEB_PROCESSING = range(200, 203)

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

# ---------- PDF IMPORT UTILITIES ----------
def detect_language(text):
    """
    Simple language detection to identify if text contains Hindi
    Returns 'hi' if Hindi characters are detected, 'en' otherwise
    """
    # Unicode ranges for Hindi (Devanagari script)
    hindi_range = range(0x0900, 0x097F + 1)
    
    for char in text:
        if ord(char) in hindi_range:
            return 'hi'
    
    return 'en'

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    welcome_text = (
        f"✨ 𝙒𝙚𝙡𝙘𝙤𝙢𝙚, {user.mention_html()} ✨\n\n"
        "🧠 <b>𝗤𝘂𝗶𝘇 𝗠𝗮𝘀𝘁𝗲𝗿 𝗕𝗼𝘁</b> is here to challenge your mind and test your skills!\n\n"
        "<b>𝗛𝗲𝗿𝗲'𝘀 𝘄𝗵𝗮𝘁 𝘆𝗼𝘂 𝗰𝗮𝗻 𝗱𝗼:</b>\n"
        "• ⚡ <b>Start a Quiz:</b> /quiz\n"
        "• 📊 <b>Check Stats:</b> /stats\n"
        "• ➕ <b>Add Question:</b> /add\n"
        "• ✏️ <b>Edit Question:</b> /edit\n"
        "• ❌ <b>Delete Question:</b> /delete\n"
        "• 🔄 <b>Poll to Quiz:</b> /poll2q\n"
        "• ℹ️ <b>Help & Commands:</b> /help\n\n"
        
        "📄 <b>𝗜𝗺𝗽𝗼𝗿𝘁 & Custom ID:</b>\n"
        "• 📥 <b>Import from PDF:</b> /pdfimport\n"
        "• 🌐 <b>Import from Website:</b> /webscrape\n"
    )
    
    # Send initial welcome message
    await update.message.reply_html(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = (
        "🤖 <b>Quiz Bot Help</b> 🤖\n\n"
        "<b>Basic Commands:</b>\n"
        "• /start - Start the bot\n"
        "• /help - Show this help message\n"
        "• /quiz - Start a quiz\n"
        "• /stats - Show your statistics\n\n"
        
        "<b>Question Management:</b>\n"
        "• /add - Add a new question manually\n"
        "• /edit - Edit an existing question\n"
        "• /delete - Delete a question\n"
        "• /list - List all questions\n"
        "• /search - Search for questions\n\n"
        
        "<b>Import & Export:</b>\n"
        "• /pdfimport - Import questions from a PDF file\n"
        "• /webscrape - Import questions from a website\n"
        "• /poll2q - Convert a poll to a quiz question\n\n"
        
        "<b>Advanced Features:</b>\n"
        "• Supports Hindi questions and answers\n"
        "• Negative marking system\n"
        "• Custom question IDs for organization\n"
    )
    await update.message.reply_html(help_text)

def add_question_to_database(question, options, correct_answer, category):
    """Add a question to the database"""
    question_id = get_next_question_id()
    
    question_data = {
        "question": question,
        "options": options,
        "correct_answer": correct_answer,
        "category": category
    }
    
    # Add the question with the next available ID
    questions = load_questions()
    questions[str(question_id)] = question_data
    save_questions(questions)
    
    return question_id

async def add_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the /add command to add a new question."""
    await update.message.reply_text("Please enter the question text:")
    return QUESTION

async def question_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the question input."""
    context.user_data["question"] = update.message.text
    await update.message.reply_text("Please enter the options, one per line:")
    return OPTIONS

async def options_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the options input."""
    options_text = update.message.text
    options = [option.strip() for option in options_text.split('\n') if option.strip()]
    
    if len(options) < 2:
        await update.message.reply_text("Please provide at least 2 options, one per line:")
        return OPTIONS
    
    context.user_data["options"] = options
    
    # Create inline keyboard for answer selection
    keyboard = []
    for i, option in enumerate(options):
        # Truncate option text for button if too long
        btn_text = option[:30] + "..." if len(option) > 30 else option
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"answer_{i}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please select the correct answer:", reply_markup=reply_markup)
    return ANSWER

async def answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the answer selection."""
    query = update.callback_query
    await query.answer()
    
    # Extract the selected answer index
    selected_answer = int(query.data.split('_')[1])
    context.user_data["correct_answer"] = selected_answer
    
    # Create category selection keyboard
    categories = ["General Knowledge", "Science", "History", "Geography", "Entertainment", "Sports", "Custom"]
    keyboard = [[InlineKeyboardButton(cat, callback_data=f"cat_{cat}")] for cat in categories]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text("Please select a category:", reply_markup=reply_markup)
    return CATEGORY

async def category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the category selection."""
    query = update.callback_query
    await query.answer()
    
    selected_category = query.data.split('_', 1)[1]
    
    if selected_category == "Custom":
        await query.edit_message_text("Please enter a custom category name:")
        return CATEGORY
    
    # Add the question to the database
    question = context.user_data.get("question", "")
    options = context.user_data.get("options", [])
    correct_answer = context.user_data.get("correct_answer", 0)
    
    question_id = add_question_to_database(question, options, correct_answer, selected_category)
    
    await query.edit_message_text(f"Question added successfully with ID: {question_id}")
    return ConversationHandler.END

async def custom_category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom category input."""
    custom_category = update.message.text.strip()
    
    # Add the question to the database
    question = context.user_data.get("question", "")
    options = context.user_data.get("options", [])
    correct_answer = context.user_data.get("correct_answer", 0)
    
    question_id = add_question_to_database(question, options, correct_answer, custom_category)
    
    await update.message.reply_text(f"Question added successfully with ID: {question_id}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a quiz to the user."""
    questions = load_questions()
    
    if not questions:
        await update.message.reply_text("No questions available. Add some with /add first!")
        return
    
    args = context.args
    if args:
        # Use specific question ID if provided
        try:
            specific_id = args[0]
            if specific_id in questions:
                question_id = specific_id
                logger.info(f"Using specific question ID: {question_id}")
            else:
                await update.message.reply_text(f"Question with ID {specific_id} not found. Sending a random question instead.")
                question_id = random.choice(list(questions.keys()))
        except (ValueError, IndexError):
            await update.message.reply_text("Invalid question ID. Sending a random question instead.")
            question_id = random.choice(list(questions.keys()))
    else:
        # Pick a random question ID
        question_id = random.choice(list(questions.keys()))
    
    logger.info(f"Selected question ID: {question_id}")
    question_data = questions[question_id]
    
    # Handle the case where we have a list of questions under this ID
    if isinstance(question_data, list):
        question_data = random.choice(question_data)
        logger.info("Selected question from a list of questions with the same ID")
    
    # Extract question details
    question_text = question_data.get("question", "")
    options = question_data.get("options", [])
    correct_option = question_data.get("correct_answer", 0)
    category = question_data.get("category", "General Knowledge")
    
    logger.info(f"Sending quiz question: {question_text}")
    logger.info(f"Options: {options}")
    logger.info(f"Correct option index: {correct_option}")
    
    # Ensure correct_option is within valid range
    if correct_option < 0 or correct_option >= len(options):
        logger.warning(f"Invalid correct_option index {correct_option}, defaulting to 0")
        correct_option = 0
    
    # Create a poll
    await context.bot.send_poll(
        chat_id=update.effective_chat.id,
        question=question_text,
        options=options,
        type="quiz",
        correct_option_id=correct_option,
        explanation=f"Category: {category} | ID: {question_id}",
        is_anonymous=False
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user statistics."""
    user_id = update.effective_user.id
    stats = get_extended_user_stats(user_id)
    
    stats_text = (
        "📊 <b>Your Quiz Statistics</b> 📊\n\n"
        f"Total questions answered: {stats['total_answers']}\n"
        f"Correct answers: {stats['correct_answers']}\n"
        f"Incorrect answers: {stats['incorrect_answers']}\n\n"
    )
    
    if NEGATIVE_MARKING_ENABLED:
        stats_text += (
            f"Penalty points: {stats['penalty_points']}\n"
            f"Raw score: {stats['raw_score']}\n"
            f"Adjusted score: {stats['adjusted_score']}\n\n"
            "<i>Note: Negative marking is enabled</i>"
        )
    
    await update.message.reply_html(stats_text)

async def poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle poll answers."""
    answer = update.poll_answer
    user_id = answer.user.id
    
    # Get the poll data
    poll_id = answer.poll_id
    selected_option = answer.option_ids[0] if answer.option_ids else None
    
    # We need to match this poll_id with a question, but we don't store this mapping
    # This is just a basic stats tracking without checking correctness
    
    user_data = get_user_data(user_id)
    user_data["total_answers"] = user_data.get("total_answers", 0) + 1
    
    # Only count as correct if the user selected the correct option
    # This is estimated based on the data we have
    poll = context.bot_data.get(poll_id)
    if poll and "correct_option_id" in poll and selected_option == poll["correct_option_id"]:
        user_data["correct_answers"] = user_data.get("correct_answers", 0) + 1
    elif poll and "correct_option_id" in poll:
        # Apply penalty for incorrect answer
        category = poll.get("category", "General Knowledge")
        apply_penalty(user_id, category)
    
    save_user_data(user_id, user_data)

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a question by ID."""
    args = context.args
    
    if not args:
        await update.message.reply_text("Please provide a question ID to delete. Usage: /delete [ID]")
        return
    
    try:
        question_id = args[0]
        if delete_question_by_id(question_id):
            await update.message.reply_text(f"Question with ID {question_id} deleted successfully.")
        else:
            await update.message.reply_text(f"No question found with ID {question_id}.")
    except Exception as e:
        await update.message.reply_text(f"Error deleting question: {e}")

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all questions with their IDs."""
    questions = load_questions()
    
    if not questions:
        await update.message.reply_text("No questions available.")
        return
    
    # Create a paginated list of questions
    page_size = 10
    all_ids = list(questions.keys())
    
    # Get the requested page from arguments
    args = context.args
    try:
        page = int(args[0]) if args else 1
    except ValueError:
        page = 1
    
    # Ensure page is valid
    total_pages = (len(all_ids) + page_size - 1) // page_size
    page = max(1, min(page, total_pages))
    
    # Get the IDs for the current page
    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, len(all_ids))
    page_ids = all_ids[start_idx:end_idx]
    
    # Create the message
    message = f"📋 <b>Questions List</b> (Page {page}/{total_pages}):\n\n"
    
    for qid in page_ids:
        question_data = questions[qid]
        
        # Handle the case where we have a list of questions under this ID
        if isinstance(question_data, list):
            for i, q in enumerate(question_data):
                message += f"• ID: {qid} ({i+1}/{len(question_data)})\n"
                message += f"  {q.get('question', '')[:50]}...\n"
        else:
            message += f"• ID: {qid}\n"
            message += f"  {question_data.get('question', '')[:50]}...\n"
    
    # Add navigation instructions
    message += f"\nUse /list [page_number] to navigate pages (1-{total_pages})"
    
    await update.message.reply_html(message)

async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the edit conversation by asking for a question ID."""
    await update.message.reply_text("Please enter the ID of the question you want to edit:")
    return EDIT_SELECT

async def edit_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the question ID selection for editing."""
    question_id = update.message.text.strip()
    question_data = get_question_by_id(question_id)
    
    if not question_data:
        await update.message.reply_text(f"No question found with ID {question_id}. Please try again or use /cancel to abort.")
        return EDIT_SELECT
    
    context.user_data["edit_id"] = question_id
    context.user_data["edit_data"] = question_data
    
    # Display the current question
    message = f"Editing Question ID: {question_id}\n\n"
    message += f"Question: {question_data.get('question', '')}\n\n"
    message += "Options:\n"
    
    for i, option in enumerate(question_data.get("options", [])):
        correct = "✓" if i == question_data.get("correct_answer", 0) else ""
        message += f"{i+1}. {option} {correct}\n"
    
    message += f"\nCategory: {question_data.get('category', 'General Knowledge')}"
    
    keyboard = [
        [InlineKeyboardButton("Edit Question Text", callback_data="edit_question")],
        [InlineKeyboardButton("Edit Options", callback_data="edit_options")],
        [InlineKeyboardButton("Cancel", callback_data="edit_cancel")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message, reply_markup=reply_markup)
    return EDIT_SELECT

async def edit_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle button presses in the edit menu."""
    query = update.callback_query
    await query.answer()
    
    action = query.data
    
    if action == "edit_question":
        await query.edit_message_text("Please enter the new question text:")
        return EDIT_QUESTION
    elif action == "edit_options":
        options = context.user_data["edit_data"].get("options", [])
        options_text = "\n".join(options)
        await query.edit_message_text(
            "Please enter the new options, one per line:\n\n"
            "Current options:\n"
            f"{options_text}"
        )
        return EDIT_OPTIONS
    elif action == "edit_cancel":
        await query.edit_message_text("Edit cancelled.")
        return ConversationHandler.END
    
    return EDIT_SELECT

async def edit_question_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the new question text input."""
    new_question = update.message.text.strip()
    question_id = context.user_data["edit_id"]
    question_data = context.user_data["edit_data"].copy()
    
    # Update the question text
    question_data["question"] = new_question
    
    # Save the updated question
    questions = load_questions()
    questions[question_id] = question_data
    save_questions(questions)
    
    await update.message.reply_text(f"Question updated successfully!\n\nNew question: {new_question}")
    return ConversationHandler.END

async def edit_options_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the new options input."""
    new_options = [opt.strip() for opt in update.message.text.split('\n') if opt.strip()]
    
    if len(new_options) < 2:
        await update.message.reply_text("Please provide at least 2 options, one per line:")
        return EDIT_OPTIONS
    
    question_id = context.user_data["edit_id"]
    question_data = context.user_data["edit_data"].copy()
    
    # Update the options
    question_data["options"] = new_options
    
    # Ensure correct_answer is still valid
    if question_data.get("correct_answer", 0) >= len(new_options):
        question_data["correct_answer"] = 0
    
    # Create keyboard for selecting the correct answer
    keyboard = []
    for i, option in enumerate(new_options):
        btn_text = option[:30] + "..." if len(option) > 30 else option
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"correct_{i}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Store the updated data temporarily
    context.user_data["edit_data"] = question_data
    
    await update.message.reply_text("Please select the correct answer:", reply_markup=reply_markup)
    return EDIT_OPTIONS

async def edit_correct_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the correct answer selection."""
    query = update.callback_query
    await query.answer()
    
    correct_idx = int(query.data.split('_')[1])
    question_id = context.user_data["edit_id"]
    question_data = context.user_data["edit_data"].copy()
    
    # Update the correct answer
    question_data["correct_answer"] = correct_idx
    
    # Save the updated question
    questions = load_questions()
    questions[question_id] = question_data
    save_questions(questions)
    
    options_display = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(question_data["options"])])
    await query.edit_message_text(
        f"Question updated successfully!\n\n"
        f"New options:\n{options_display}\n\n"
        f"Correct answer: {correct_idx + 1}. {question_data['options'][correct_idx]}"
    )
    return ConversationHandler.END

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search for questions containing a specific term."""
    args = context.args
    
    if not args:
        await update.message.reply_text("Please provide a search term. Usage: /search [term]")
        return
    
    search_term = " ".join(args).lower()
    questions = load_questions()
    
    if not questions:
        await update.message.reply_text("No questions available.")
        return
    
    # Search through all questions
    results = []
    
    for qid, q_data in questions.items():
        # Handle the case where we have a list of questions under this ID
        if isinstance(q_data, list):
            for i, q in enumerate(q_data):
                question_text = q.get("question", "").lower()
                if search_term in question_text:
                    results.append((qid, i, q))
        else:
            question_text = q_data.get("question", "").lower()
            if search_term in question_text:
                results.append((qid, 0, q_data))
    
    # Display search results
    if not results:
        await update.message.reply_text(f"No questions found containing '{search_term}'.")
        return
    
    message = f"🔍 <b>Search Results for '{search_term}'</b>:\n\n"
    
    for qid, idx, q_data in results[:10]:  # Limit to first 10 results
        if idx > 0:
            message += f"• ID: {qid} ({idx+1})\n"
        else:
            message += f"• ID: {qid}\n"
        
        question_text = q_data.get("question", "")
        # Highlight the search term
        highlight = question_text.lower().replace(search_term, f"<b>{search_term}</b>")
        message += f"  {highlight[:100]}...\n\n"
    
    if len(results) > 10:
        message += f"And {len(results) - 10} more results..."
    
    await update.message.reply_html(message)

async def poll_to_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Convert a forwarded poll to a quiz question."""
    # Check if the message contains a poll
    if not update.message.forward_from and not update.message.poll:
        await update.message.reply_text("Please forward a poll message to convert it to a quiz question.")
        return
    
    # Extract poll data
    poll = update.message.poll
    if not poll:
        await update.message.reply_text("No poll found in the forwarded message.")
        return
    
    # Extract question and options
    question_text = poll.question
    options = [option.text for option in poll.options]
    
    # If it's already a quiz poll, we can get the correct answer
    correct_option = 0  # Default to first option
    if poll.type == "quiz" and poll.correct_option_id is not None:
        correct_option = poll.correct_option_id
    
    # Store in user data for the conversation
    context.user_data["poll_question"] = question_text
    context.user_data["poll_options"] = options
    context.user_data["poll_correct"] = correct_option
    
    # Display extracted information
    message = f"✅ <b>Poll extracted successfully</b>\n\n"
    message += f"<b>Question:</b> {question_text}\n\n"
    message += "<b>Options:</b>\n"
    
    for i, option in enumerate(options):
        marker = "✓" if i == correct_option else ""
        message += f"{i+1}. {option} {marker}\n"
    
    keyboard = [
        [InlineKeyboardButton("Save as Quiz Question", callback_data="save_poll")],
        [InlineKeyboardButton("Cancel", callback_data="cancel_poll")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_html(message, reply_markup=reply_markup)

async def poll_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button presses in the poll to question conversion."""
    query = update.callback_query
    await query.answer()
    
    action = query.data
    
    if action == "save_poll":
        # Save the poll as a question
        question = context.user_data.get("poll_question", "")
        options = context.user_data.get("poll_options", [])
        correct = context.user_data.get("poll_correct", 0)
        
        # Default to General Knowledge category
        category = "General Knowledge"
        
        # Add to database
        question_id = add_question_to_database(question, options, correct, category)
        
        await query.edit_message_text(f"Poll saved as quiz question with ID: {question_id}")
    
    elif action == "cancel_poll":
        await query.edit_message_text("Poll to question conversion cancelled.")

# ---------- PDF IMPORT ----------
async def pdf_import_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the PDF import process."""
    await update.message.reply_text(
        "📄 Send me a PDF file containing quiz questions, and I'll import them.\n\n"
        "The PDF should contain questions with clearly marked options.\n"
        "Each question should ideally end with a question mark (?).\n"
        "Supports both English and Hindi content.\n\n"
        "Send a PDF file or /cancel to abort."
    )
    return PDF_UPLOAD

async def pdf_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle PDF file upload."""
    # Check if the message contains a document
    if not update.message.document:
        await update.message.reply_text("Please send a PDF file. Try again or use /cancel to abort.")
        return PDF_UPLOAD
    
    # Check if it's a PDF
    document = update.message.document
    if not document.mime_type == "application/pdf":
        await update.message.reply_text("The file must be a PDF. Try again or use /cancel to abort.")
        return PDF_UPLOAD
    
    # Download the file
    file_id = document.file_id
    file = await context.bot.get_file(file_id)
    pdf_path = os.path.join(TEMP_DIR, f"{file_id}.pdf")
    await file.download_to_drive(pdf_path)
    
    # Store the path for later processing
    context.user_data["pdf_path"] = pdf_path
    
    # Ask for a custom ID prefix (optional)
    keyboard = [
        [InlineKeyboardButton("Use Default IDs", callback_data="pdf_default_id")],
        [InlineKeyboardButton("Specify Custom ID", callback_data="pdf_custom_id")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Would you like to use the default question IDs or specify a custom ID range?",
        reply_markup=reply_markup
    )
    return PDF_CUSTOM_ID

async def pdf_id_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the ID selection for PDF import."""
    query = update.callback_query
    await query.answer()
    
    action = query.data
    
    if action == "pdf_default_id":
        # Use default IDs
        context.user_data["pdf_custom_id"] = None
        
        # Proceed to processing
        await query.edit_message_text("Processing PDF... This may take a while for large files.")
        return await pdf_process_handler(update, context)
    
    elif action == "pdf_custom_id":
        # Ask for custom ID
        await query.edit_message_text(
            "Please enter a custom ID (number) for the questions. All imported questions will be stored under this ID."
        )
        return PDF_CUSTOM_ID
    
    return PDF_CUSTOM_ID

async def pdf_custom_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom ID input for PDF import."""
    custom_id = update.message.text.strip()
    
    # Validate the ID
    try:
        custom_id = int(custom_id)
        context.user_data["pdf_custom_id"] = custom_id
    except ValueError:
        await update.message.reply_text("Invalid ID. Please enter a numeric ID or use /cancel to abort.")
        return PDF_CUSTOM_ID
    
    # Proceed to processing
    await update.message.reply_text("Processing PDF... This may take a while for large files.")
    return await pdf_process_handler(update, context)

async def pdf_process_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the PDF and extract questions."""
    # Get stored data
    pdf_path = context.user_data.get("pdf_path")
    custom_id = context.user_data.get("pdf_custom_id")
    
    # Extract text from PDF
    try:
        lines = extract_text_from_pdf(pdf_path)
        if not lines or len(lines) < 5:  # Too few lines
            raise ValueError("Could not extract enough text from the PDF")
    except Exception as e:
        # PDF processing failed
        error_message = f"Error processing PDF: {e}"
        
        if isinstance(update.callback_query, object):
            await update.callback_query.edit_message_text(error_message)
        else:
            await update.message.reply_text(error_message)
        
        # Clean up
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        
        return ConversationHandler.END
    
    # Clean up
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    
    # Group and deduplicate the questions
    processed_lines = group_and_deduplicate_questions(lines)
    
    # Convert to single string for processing
    text_content = "\n".join(processed_lines)
    
    # Extract questions from the text
    questions_data = extract_questions_with_options(text_content)
    
    if not questions_data:
        error_message = "No valid questions found in the PDF. Make sure questions are clearly formatted with options."
        
        if isinstance(update.callback_query, object):
            await update.callback_query.edit_message_text(error_message)
        else:
            await update.message.reply_text(error_message)
        
        return ConversationHandler.END
    
    # Save extracted questions
    num_imported = 0
    
    for q_data in questions_data:
        # Skip incomplete questions
        if not q_data.get("question") or len(q_data.get("options", [])) < 2:
            continue
        
        # Set up question data
        question_data = {
            "question": q_data["question"],
            "options": q_data["options"],
            "correct_answer": q_data.get("correct_answer", 0),
            "category": "Imported"
        }
        
        # Add to database
        if custom_id:
            add_question_with_id(custom_id, question_data)
        else:
            question_id = get_next_question_id()
            questions = load_questions()
            questions[str(question_id)] = question_data
            save_questions(questions)
        
        num_imported += 1
    
    # Report results
    success_message = f"✅ Successfully imported {num_imported} questions from the PDF."
    
    if custom_id:
        success_message += f"\nAll questions stored under ID: {custom_id}"
    
    if num_imported < len(questions_data):
        success_message += f"\n⚠️ {len(questions_data) - num_imported} questions were skipped due to incomplete data."
    
    if isinstance(update.callback_query, object):
        await update.callback_query.edit_message_text(success_message)
    else:
        await update.message.reply_text(success_message)
    
    return ConversationHandler.END

# ---------- WEB SCRAPING IMPORT ----------
async def web_scrape_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the web scraping import process."""
    await update.message.reply_text(
        "🌐 Send me a URL of a website containing quiz questions, and I'll import them.\n\n"
        "The website should contain questions with clearly marked options.\n"
        "Each question should ideally end with a question mark (?).\n"
        "Supports both English and Hindi content.\n\n"
        "Send a URL or /cancel to abort."
    )
    return WEB_URL

async def web_url_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle URL input for web scraping."""
    url = update.message.text.strip()
    
    # Simple URL validation
    try:
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise ValueError("Invalid URL format")
    except Exception:
        await update.message.reply_text("Invalid URL. Please enter a valid website URL or use /cancel to abort.")
        return WEB_URL
    
    # Store the URL for later processing
    context.user_data["web_url"] = url
    
    # Ask for a custom ID prefix (optional)
    keyboard = [
        [InlineKeyboardButton("Use Default IDs", callback_data="web_default_id")],
        [InlineKeyboardButton("Specify Custom ID", callback_data="web_custom_id")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Would you like to use the default question IDs or specify a custom ID range?",
        reply_markup=reply_markup
    )
    return WEB_CUSTOM_ID

async def web_id_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the ID selection for web scraping import."""
    query = update.callback_query
    await query.answer()
    
    action = query.data
    
    if action == "web_default_id":
        # Use default IDs
        context.user_data["web_custom_id"] = None
        
        # Proceed to processing
        await query.edit_message_text("Scraping website... This may take a while.")
        return await web_process_handler(update, context)
    
    elif action == "web_custom_id":
        # Ask for custom ID
        await query.edit_message_text(
            "Please enter a custom ID (number) for the questions. All imported questions will be stored under this ID."
        )
        return WEB_CUSTOM_ID
    
    return WEB_CUSTOM_ID

async def web_custom_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom ID input for web scraping."""
    custom_id = update.message.text.strip()
    
    # Validate the ID
    try:
        custom_id = int(custom_id)
        context.user_data["web_custom_id"] = custom_id
    except ValueError:
        await update.message.reply_text("Invalid ID. Please enter a numeric ID or use /cancel to abort.")
        return WEB_CUSTOM_ID
    
    # Proceed to processing
    await update.message.reply_text("Scraping website... This may take a while.")
    return await web_process_handler(update, context)

async def web_process_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the web page and extract questions."""
    # Get stored data
    url = context.user_data.get("web_url")
    custom_id = context.user_data.get("web_custom_id")
    
    # Check if web scraping is supported
    if not WEB_SCRAPING_SUPPORT:
        error_message = "Web scraping is not supported. Required libraries are not installed."
        
        if isinstance(update.callback_query, object):
            await update.callback_query.edit_message_text(error_message)
        else:
            await update.message.reply_text(error_message)
        
        return ConversationHandler.END
    
    # Scrape the website
    try:
        # Use the enhanced web scraper for better question extraction
        questions_data = scrape_questions_from_url(url)
        
        if not questions_data:
            error_message = "No valid questions found on the website. Make sure questions are clearly formatted with options."
            
            if isinstance(update.callback_query, object):
                await update.callback_query.edit_message_text(error_message)
            else:
                await update.message.reply_text(error_message)
            
            return ConversationHandler.END
    except Exception as e:
        # Web scraping failed
        error_message = f"Error scraping website: {e}"
        
        if isinstance(update.callback_query, object):
            await update.callback_query.edit_message_text(error_message)
        else:
            await update.message.reply_text(error_message)
        
        return ConversationHandler.END
    
    # Save extracted questions
    num_imported = 0
    
    for q_data in questions_data:
        # Skip incomplete questions
        if not q_data.get("question") or len(q_data.get("options", [])) < 2:
            continue
        
        # Set up question data
        question_data = {
            "question": q_data["question"],
            "options": q_data["options"],
            "correct_answer": q_data.get("correct_answer", 0),
            "category": "Web Imported"
        }
        
        # Add to database
        if custom_id:
            add_question_with_id(custom_id, question_data)
        else:
            question_id = get_next_question_id()
            questions = load_questions()
            questions[str(question_id)] = question_data
            save_questions(questions)
        
        num_imported += 1
    
    # Report results
    success_message = f"✅ Successfully imported {num_imported} questions from the website."
    
    if custom_id:
        success_message += f"\nAll questions stored under ID: {custom_id}"
    
    if num_imported < len(questions_data):
        success_message += f"\n⚠️ {len(questions_data) - num_imported} questions were skipped due to incomplete data."
    
    if isinstance(update.callback_query, object):
        await update.callback_query.edit_message_text(success_message)
    else:
        await update.message.reply_text(success_message)
    
    return ConversationHandler.END

async def webscrape_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Alias for web_scrape_command."""
    return await web_scrape_command(update, context)

async def quickscrape_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quickly scrape a URL provided as an argument."""
    args = context.args
    
    if not args:
        await update.message.reply_text("Please provide a URL. Usage: /quickscrape [url] [starting_id (optional)]")
        return
    
    url = args[0]
    
    # Check for custom starting ID if provided
    custom_id = None
    if len(args) > 1:
        try:
            custom_id = int(args[1])
            logger.info(f"Using custom starting ID: {custom_id}")
        except ValueError:
            await update.message.reply_text("Invalid ID format. Please use a numeric ID.")
            return
    
    # Simple URL validation
    try:
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise ValueError("Invalid URL format")
    except Exception:
        await update.message.reply_text("Invalid URL. Please enter a valid website URL.")
        return
    
    # Check if web scraping is supported
    if not WEB_SCRAPING_SUPPORT:
        await update.message.reply_text("Web scraping is not supported. Required libraries are not installed.")
        return
    
    # Send a processing message
    message = await update.message.reply_text("🔍 Scraping website... This may take a while.")
    
    # Scrape the website
    try:
        # Use the enhanced web scraper for better question extraction
        questions_data = scrape_questions_from_url(url)
        
        if not questions_data:
            await message.edit_text("❌ No valid questions found on the website. Make sure questions are clearly formatted with options.")
            return
    except Exception as e:
        # Web scraping failed
        await message.edit_text(f"❌ Error scraping website: {e}")
        return
    
    # Log the extracted questions (for debugging)
    logger.info(f"Found {len(questions_data)} questions from URL: {url}")
    for i, q in enumerate(questions_data):
        logger.info(f"Question {i+1}: {q['question'][:50]}...")
        logger.info(f"Options: {q['options']}")
        logger.info(f"Correct Answer: {q['correct_answer']}")
    
    # Save extracted questions
    num_imported = 0
    imported_questions = []
    
    # Determine the starting ID based on user input or auto-generate
    next_id = custom_id if custom_id is not None else get_next_question_id()
    logger.info(f"Starting with question ID: {next_id}")
    
    for q_data in questions_data:
        # Skip incomplete questions
        if not q_data.get("question") or len(q_data.get("options", [])) < 2:
            logger.warning(f"Skipping question with incomplete data: {q_data.get('question', 'No question')}")
            continue
        
        # Filter out any option that contains Hindi placeholder markers or is empty
        valid_options = []
        for opt in q_data.get("options", []):
            # Skip empty options or options that are just the Hindi markers
            if not opt or opt.strip() == "" or opt.startswith("पहला विकल्प") or opt.startswith("दूसरा विकल्प") or opt.startswith("तीसरा विकल्प") or opt.startswith("चौथा विकल्प"):
                continue
            valid_options.append(opt)
        
        # Skip if we don't have enough valid options
        if len(valid_options) < 2:
            logger.warning(f"Skipping question with insufficient valid options: {q_data.get('question', 'No question')}")
            continue
            
        # Adjust correct answer index if needed
        correct_answer = q_data.get("correct_answer", 0)
        if correct_answer < 0 or correct_answer >= len(valid_options):
            correct_answer = 0
        
        # Set up question data
        question_data = {
            "question": q_data["question"],
            "options": valid_options,
            "correct_answer": correct_answer,
            "category": "Web Imported"
        }
        
        # Calculate the current question ID
        question_id = next_id + num_imported
        
        # Add to database with specified ID using add_question_with_id
        # This preserves any existing questions with the same ID
        add_question_with_id(question_id, question_data)
        logger.info(f"Added question with ID: {question_id}")
        
        # Store for preview
        imported_questions.append((question_id, question_data))
        num_imported += 1
    
    # Report results
    success_message = f"✅ Successfully imported {num_imported} questions from the website."
    
    if num_imported > 0:
        success_message += f"\nQuestion IDs: {next_id} to {next_id + num_imported - 1}"
    
    if num_imported < len(questions_data):
        success_message += f"\n⚠️ {len(questions_data) - num_imported} questions were skipped due to incomplete data."
    
    # Display a preview of the first few questions
    if num_imported > 0:
        success_message += "\n\n📝 Preview of imported questions:"
        
        # Show up to 3 questions as preview
        preview_count = min(3, num_imported)
        for i in range(preview_count):
            q_id, q = imported_questions[i]
            
            # Format options for display (with proper lettering)
            options_text = ""
            for j, opt in enumerate(q["options"][:4]):  # Limit to first 4 options
                correct_mark = "✓" if j == q["correct_answer"] else ""
                options_text += f"\n   {chr(65+j)}. {opt} {correct_mark}"
            
            # Add to preview
            success_message += f"\n\n🔹 Question {q_id}: {q['question']}{options_text}"
    
    await message.edit_text(success_message)

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("quickscrape", quickscrape_command))

    # Poll to Question conversion
    application.add_handler(CommandHandler("poll2q", poll_to_question))
    application.add_handler(CallbackQueryHandler(poll_button_handler, pattern="^(save|cancel)_poll$"))

    # Add question conversation handler
    add_question_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_handler)],
        states={
            QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, question_handler)],
            OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, options_handler)],
            ANSWER: [CallbackQueryHandler(answer_handler, pattern="^answer_")],
            CATEGORY: [
                CallbackQueryHandler(category_handler, pattern="^cat_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_category_handler)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(add_question_handler)

    # Edit question conversation handler
    edit_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("edit", edit_command)],
        states={
            EDIT_SELECT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_select_handler),
                CallbackQueryHandler(edit_button_handler, pattern="^edit_")
            ],
            EDIT_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_question_handler)],
            EDIT_OPTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_options_handler),
                CallbackQueryHandler(edit_correct_handler, pattern="^correct_")
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(edit_conv_handler)

    # PDF import conversation handler
    pdf_import_handler = ConversationHandler(
        entry_points=[CommandHandler("pdfimport", pdf_import_command)],
        states={
            PDF_UPLOAD: [MessageHandler(filters.ATTACHMENT & ~filters.COMMAND, pdf_upload_handler)],
            PDF_CUSTOM_ID: [
                CallbackQueryHandler(pdf_id_button_handler, pattern="^pdf_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, pdf_custom_id_handler)
            ],
            PDF_PROCESSING: [MessageHandler(filters.ALL & ~filters.COMMAND, pdf_process_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(pdf_import_handler)

    # Web scraping import conversation handler
    web_scrape_handler = ConversationHandler(
        entry_points=[
            CommandHandler("webscrape", web_scrape_command),
            CommandHandler("webimport", web_scrape_command)
        ],
        states={
            WEB_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, web_url_handler)],
            WEB_CUSTOM_ID: [
                CallbackQueryHandler(web_id_button_handler, pattern="^web_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, web_custom_id_handler)
            ],
            WEB_PROCESSING: [MessageHandler(filters.ALL & ~filters.COMMAND, web_process_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(web_scrape_handler)

    # Handle poll answers
    application.add_handler(PollAnswerHandler(poll_answer))

    # Start the Bot
    application.run_polling()

if __name__ == "__main__":
    main()
