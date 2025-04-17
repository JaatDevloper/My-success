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
    await update.message.reply_html(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "🔍 <b>Quiz Master Bot Commands</b> 🔍\n\n"
        
        "📚 <b>General Commands:</b>\n"
        "• /start - Start the bot\n"
        "• /help - Display this help message\n"
        "• /quiz - Start a quiz with random questions\n"
        "• /quizid [ID] - Start a quiz with specific ID\n"
        "• /stats - View your quiz statistics\n\n"
        
        "➕ <b>Adding Questions:</b>\n"
        "• /add - Add a new question manually\n"
        "• /pdfimport - Import questions from PDF\n"
        "• /webscrape - Import from a website\n"
        "• /poll2q - Convert a poll to a question\n\n"
        
        "📝 <b>Managing Questions:</b>\n"
        "• /edit - Edit an existing question\n"
        "• /delete - Delete a question\n"
        "• /list - List all questions\n\n"
        
        "⚙️ <b>Advanced Features:</b>\n"
        "• /settings - Configure bot settings\n"
        "• /customid - Set custom ID for questions\n"
        "• /resetstats - Reset your statistics\n\n"
        
        "💡 <b>Tips:</b>\n"
        "• Use the PDF import feature for bulk questions\n"
        "• Web scraping works best with education sites\n"
        "• Group questions by setting same custom ID\n"
    )
    await update.message.reply_html(help_text)

# -------- ENHANCED WEB SCRAPING FOR QUESTION IMPORT --------
def clean_option_text(text):
    """Clean option text, preserving Hindi characters and question marks properly"""
    # First, strip leading option identifiers like (A), A), a), 1), etc. including Hindi options
    cleaned = re.sub(r'^\s*\(?[A-Za-z0-9क-घ]\)?[\.\):\s]\s*', '', text.strip())
    
    # Remove any trailing punctuation except question marks
    cleaned = re.sub(r'[.,;:!]$', '', cleaned)
    
    # Make sure we're returning actual text, not empty string
    if not cleaned.strip():
        return text.strip()  # Return original if nothing left after cleaning
    
    return cleaned.strip()

def get_website_text_content(url):
    """Get clean text content from a website using trafilatura"""
    try:
        # Try different user agents to avoid bot detection
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36'
        ]
        
        headers = {'User-Agent': random.choice(user_agents)}
        
        # First try with trafilatura's built-in fetcher
        print(f"Attempting to fetch URL with trafilatura: {url}")
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            print("Trafilatura fetch successful, extracting content...")
            text = trafilatura.extract(downloaded, output_format='text', include_comments=False, 
                                     include_tables=True, no_fallback=False)
            if text:
                print(f"Successfully extracted content with trafilatura: {len(text)} characters")
                return text
        
        # If trafilatura fails, try with requests
        print("Trafilatura extraction failed, trying with requests...")
        response = requests.get(url, headers=headers, timeout=15)
        
        # Check if request was successful
        if response.status_code != 200:
            print(f"Request failed with status code: {response.status_code}")
            return None
            
        # Try trafilatura with the downloaded content
        print("Using trafilatura to extract from requests response...")
        html_content = response.text
        text = trafilatura.extract(html_content, output_format='text', include_comments=False,
                                  include_tables=True, no_fallback=False)
        if text:
            print(f"Successfully extracted content with trafilatura from requests: {len(text)} characters")
            return text
        
        # Final fallback: use BeautifulSoup
        print("All trafilatura methods failed, using BeautifulSoup...")
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.extract()
            
        text = soup.get_text(separator='\n')
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        
        result = '\n'.join(lines)
        print(f"BeautifulSoup extraction complete: {len(result)} characters")
        return result
        
    except Exception as e:
        logger.error(f"Error fetching website: {e}")
        print(f"Exception occurred during website fetch: {str(e)}")
        return None

def extract_questions_from_text(text):
    """
    Enhanced function to extract questions and options from text
    with better support for Hindi and question marks
    """
    questions = []
    
    # Split text into lines and clean them
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Enhanced pattern to detect questions (handles both Hindi and English)
    # Supports Q. Q: Q) formats and questions ending with ?
    q_index = -1
    current_question = None
    options = []
    correct_option = None
    
    # Detect if text contains Hindi
    in_hindi = detect_language(text) == 'hi'
    
    # Log the language detection for debugging
    print(f"Text language detection: {'Hindi' if in_hindi else 'English'}")
    
    for i, line in enumerate(lines):
        # Check if line looks like a new question
        # Enhanced to catch more Hindi and English question formats
        q_match = re.search(r'^(Q[\.:)\s]\s*|\d+[\.:)]\s*|प्रश्न\s*\d*[\.:)]?\s*|\(\s*\d+\s*\))', line, re.IGNORECASE)
        question_mark = "?" in line
        
        # A new question is starting
        if q_match or (q_index == -1 and question_mark):
            # Save previous question if exists
            if current_question and options:
                # Determine correct answer
                if correct_option is None and options:
                    correct_option = 0  # Default to first option if none specified
                
                # Add question to our list
                questions.append({
                    "question": current_question,
                    "options": options,
                    "correct_option": correct_option,
                    "language": detect_language(current_question)
                })
            
            # Start a new question
            q_index = i
            
            # Clean the question text
            if q_match:
                question_text = line[q_match.end():].strip()
            else:
                question_text = line.strip()
                
            current_question = question_text
            options = []
            correct_option = None
        
        # Check if line looks like an option
        elif i > q_index and current_question:
            # Enhanced option detection for both English and Hindi formats
            # Match patterns like: A) Option text, (A) Option text, 1. Option text
            # Also match Hindi options like क) आपशन टेक्स्ट, (क) आपशन टेक्स्ट
            
            opt_match = None
            if in_hindi:
                # Hindi option match (क, ख, ग, घ formats)
                opt_match = re.search(r'^\s*\(?([क-घ])\)?[\.\):\s]', line)
                if not opt_match:
                    # English options in Hindi text
                    opt_match = re.search(r'^\s*\(?([A-D]|[1-4])\)?[\.\):\s]', line, re.IGNORECASE)
            else:
                # English options (A, B, C, D or numeric formats)
                opt_match = re.search(r'^\s*\(?([A-D]|[1-4])\)?[\.\):\s]', line, re.IGNORECASE)
            
            # If there's no explicit option marker, try to detect if this is part of a list of options
            # This helps with options that don't have A), B) format but are clearly options
            if not opt_match and len(options) > 0 and len(line) < 100 and not line.endswith('?'):
                # If we already have some options and this line is short, it might be another option
                option_text = line
                options.append(option_text)
                continue
            
            if opt_match:
                option_text = clean_option_text(line)
                
                # Check if this option is marked as correct
                correct_marker = re.search(r'\(\s*correct\s*\)|\(\s*सही\s*\)|\*|✓|√|✅|☑️', line, re.IGNORECASE)
                
                # Add option to list with actual text, not just placeholder
                options.append(option_text)
                
                # If this option is marked as correct, save its index
                if correct_marker:
                    correct_option = len(options) - 1
                    
                # If the option number/letter matches a known answer pattern
                option_id = opt_match.group(1).upper()
                # Map Hindi options to English index
                if option_id in ['क', 'ख', 'ग', 'घ']:
                    hindi_to_eng = {'क': 'A', 'ख': 'B', 'ग': 'C', 'घ': 'D'}
                    option_id = hindi_to_eng.get(option_id, 'A')
                # Map numeric options to letter index
                if option_id in ['1', '2', '3', '4']:
                    option_id = chr(64 + int(option_id))  # 1->A, 2->B, etc.
                
                # Check if this option matches an answer pattern elsewhere in text
                for j in range(i+1, min(i+10, len(lines))):
                    if j < len(lines):
                        ans_line = lines[j].lower()
                        # Check patterns like "Answer: A" or "सही उत्तर: क"
                        if (option_id.lower() in ans_line and 
                            any(marker in ans_line for marker in ['answer', 'correct', 'उत्तर', 'सही'])):
                            correct_option = len(options) - 1
    
    # Don't forget to add the last question
    if current_question and options:
        if correct_option is None and options:
            correct_option = 0  # Default to first option if none specified
        
        # Make sure we have at least 2 options to make a valid quiz
        language = detect_language(current_question)
        is_hindi = language == 'hi'
        
        # Debug output for options
        print(f"Question: {current_question}")
        print(f"Original options: {options}")
        
        # Preserve the actual options exactly as found
        # DO NOT replace them with placeholders like "पहला विकल्प"
        if len(options) < 2:
            # Only add default options if absolutely necessary to meet Telegram's minimum requirement
            print(f"Warning: Not enough options found, adding generic ones to meet 2-option minimum")
            while len(options) < 2:
                if is_hindi:
                    # Use a prefix to indicate these are auto-generated (not ideal but better than replacing original options)
                    options.append(f"Auto-{len(options)+1}: वैकल्पिक विकल्प")
                else:
                    options.append(f"Auto-{len(options)+1}: Alternative option")
        
        # Debug output for final options
        print(f"Final options being saved: {options}")
        
        questions.append({
            "question": current_question,
            "options": options,
            "correct_option": correct_option,
            "language": language
        })
    
    return questions

async def webscrape_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the web scraping conversation."""
    if not WEB_SCRAPING_SUPPORT:
        await update.message.reply_text(
            "Web scraping support is not available. Please install the required dependencies."
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "🌐 <b>Website Quiz Import</b>\n\n"
        "Please send the URL of the webpage containing quiz questions.\n\n"
        "The page should contain questions with options in a structured format.\n"
        "Best results come from educational websites with clear Q&A format.",
        parse_mode='HTML'
    )
    
    return CLONE_URL

async def webscrape_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the URL and scrape questions."""
    url = update.message.text.strip()
    
    # Basic URL validation
    if not url.startswith(('http://', 'https://')):
        await update.message.reply_text("Please provide a valid URL starting with http:// or https://")
        return CLONE_URL
    
    # Store URL in context
    context.user_data['url'] = url
    
    # Notify user we're processing
    processing_message = await update.message.reply_text("⏳ Processing webpage... This may take a few moments.")
    
    try:
        # Get the webpage content
        text_content = get_website_text_content(url)
        
        if not text_content:
            await update.message.reply_text("Could not extract content from the provided URL.")
            return ConversationHandler.END
        
        # Extract questions from the content
        questions = extract_questions_from_text(text_content)
        
        # Store questions in context
        context.user_data['scraped_questions'] = questions
        
        # Provide a preview of what was found
        preview_text = f"Found {len(questions)} potential questions.\n\n"
        
        # Show a preview of the first few questions
        for i, q in enumerate(questions[:3]):
            if i > 0:
                preview_text += "\n"
            
            options_text = "\n".join([f"- {opt}" for opt in q['options'][:3]])
            if len(q['options']) > 3:
                options_text += "\n- ..."
                
            preview_text += f"Question: {q['question'][:50]}{'...' if len(q['question']) > 50 else ''}\n"
            preview_text += f"Options: \n{options_text}\n"
            preview_text += f"Correct Option: {q['correct_option'] + 1}\n"
            preview_text += f"Language: {q['language']}"
        
        # Ask if user wants to set a custom ID
        await processing_message.edit_text(preview_text)
        
        await update.message.reply_text(
            "Would you like to set a custom ID for these questions?\n"
            "This is useful for grouping related questions together.\n\n"
            "Send a number to use as base ID, or 'skip' to use default IDs.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Skip (Use Default IDs)", callback_data="skip_custom_id")]
            ])
        )
        
        return CUSTOM_ID
        
    except Exception as e:
        logger.error(f"Error in web scraping: {e}")
        await update.message.reply_text(
            f"An error occurred while processing the webpage: {str(e)}\n"
            "Please try a different URL or check if the page is accessible."
        )
        return ConversationHandler.END

async def custom_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom ID input for scraped questions."""
    # Check if this is a callback query
    if update.callback_query:
        await update.callback_query.answer()
        custom_id = None  # Use default IDs
    else:
        # It's a text message
        custom_id_text = update.message.text.strip()
        
        if custom_id_text.lower() == 'skip':
            custom_id = None  # Use default IDs
        else:
            try:
                custom_id = int(custom_id_text)
            except ValueError:
                await update.message.reply_text(
                    "Please provide a valid number for the custom ID or type 'skip'."
                )
                return CUSTOM_ID
    
    # Get scraped questions
    questions = context.user_data.get('scraped_questions', [])
    
    if not questions:
        await update.effective_message.reply_text("No questions found to import.")
        return ConversationHandler.END
    
    # Start adding questions
    status_message = await update.effective_message.reply_text(
        f"Importing {len(questions)} questions...\n"
        "0% complete"
    )
    
    questions_added = 0
    base_id = custom_id if custom_id is not None else get_next_question_id()
    
    for i, q in enumerate(questions):
        # Ensure options are preserved exactly as extracted
        options = q['options'].copy() if isinstance(q['options'], list) else []
        
        # Debug logging of options
        print(f"Webscrape extracted options for question {i+1}: {options}")
        
        # Make sure we have at least 2 options to make a valid quiz
        # But DO NOT replace the original options with generic placeholders!
        is_hindi = q['language'] == 'hi'
        if len(options) < 2:
            print(f"Warning: Not enough options for question {i+1}, adding generic ones to meet minimum")
            while len(options) < 2:
                if is_hindi:
                    # Use a prefix to indicate these are auto-generated
                    options.append(f"Auto-{len(options)+1}: वैकल्पिक विकल्प")
                else:
                    options.append(f"Auto-{len(options)+1}: Alternative option")
                    
        # Final options being used        
        print(f"Final options for webscrape question {i+1}: {options}")
        
        # Create question data with preserved options
        question_data = {
            "question": q['question'],
            "options": options,  # Use preserved options
            "correct_option": q['correct_option'],
            "category": "Web Import",
            "language": q['language']
        }
        
        # Add question with sequential ID if custom ID provided, otherwise use auto IDs
        question_id = base_id + i if custom_id is not None else get_next_question_id()
        add_question_with_id(question_id, question_data)
        questions_added += 1
        
        # Update status message periodically
        if i % max(1, len(questions) // 10) == 0:
            progress = int((i / len(questions)) * 100)
            await status_message.edit_text(
                f"Importing {len(questions)} questions...\n"
                f"{progress}% complete"
            )
    
    # Final update
    await status_message.edit_text(
        f"✅ Successfully imported {questions_added} questions!"
    )
    
    # Clear user data
    if 'scraped_questions' in context.user_data:
        del context.user_data['scraped_questions']
    if 'url' in context.user_data:
        del context.user_data['url']
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    await update.message.reply_text("Operation cancelled.")
    
    # Clear user data
    if 'scraped_questions' in context.user_data:
        del context.user_data['scraped_questions']
    if 'url' in context.user_data:
        del context.user_data['url']
        
    return ConversationHandler.END

# Add the quiz functionality
async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a quiz to the user"""
    questions = load_questions()
    if not questions:
        await update.message.reply_text("No questions available. Add some questions first!")
        return
    
    # Get a random question ID
    question_id = random.choice(list(questions.keys()))
    
    # Get the question data
    question_data = questions[question_id]
    
    # If it's a list, pick a random question from the list
    if isinstance(question_data, list):
        question = random.choice(question_data)
    else:
        question = question_data
    
    # Send the question as a poll
    message = await context.bot.send_poll(
        update.effective_chat.id,
        question["question"],
        question["options"],
        type="quiz",
        correct_option_id=question["correct_option"],
        explanation=f"Question ID: {question_id}",
        open_period=30,
        is_anonymous=False
    )
    
    # Save poll ID and question ID to handle answers later
    payload = {
        "question_id": question_id,
        "message_id": message.message_id,
        "chat_id": update.effective_chat.id,
        "category": question.get("category", "General Knowledge")
    }
    
    # Store in bot data
    context.bot_data.setdefault("polls", {})[message.poll.id] = payload

async def quizid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a quiz to the user with a specific ID"""
    # Check if an ID was provided
    if not context.args:
        await update.message.reply_text("Please provide a question ID: /quizid [ID]")
        return
    
    question_id = context.args[0]
    
    # Load all questions
    questions = load_questions()
    
    # Check if the ID exists
    if question_id not in questions:
        await update.message.reply_text(f"Question with ID {question_id} not found!")
        return
    
    # Get the question data
    question_data = questions[question_id]
    
    # If it's a list, pick a random question from the list
    if isinstance(question_data, list):
        question = random.choice(question_data)
    else:
        question = question_data
    
    # Send the question as a poll
    message = await context.bot.send_poll(
        update.effective_chat.id,
        question["question"],
        question["options"],
        type="quiz",
        correct_option_id=question["correct_option"],
        explanation=f"Question ID: {question_id}",
        open_period=30,
        is_anonymous=False
    )
    
    # Save poll ID and question ID to handle answers later
    payload = {
        "question_id": question_id,
        "message_id": message.message_id,
        "chat_id": update.effective_chat.id,
        "category": question.get("category", "General Knowledge")
    }
    
    # Store in bot data
    context.bot_data.setdefault("polls", {})[message.poll.id] = payload

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user statistics"""
    user_id = update.effective_user.id
    
    # Get extended user stats (includes penalties)
    stats = get_extended_user_stats(user_id)
    
    # Prepare stats message
    stats_message = (
        f"📊 <b>Quiz Statistics for {update.effective_user.first_name}</b>\n\n"
        f"🔢 <b>Total Answers:</b> {stats['total_answers']}\n"
        f"✅ <b>Correct Answers:</b> {stats['correct_answers']}\n"
        f"❌ <b>Wrong Answers:</b> {stats['incorrect_answers']}\n"
    )
    
    # Add negative marking info if enabled
    if NEGATIVE_MARKING_ENABLED:
        stats_message += (
            f"\n🔻 <b>Penalty Points:</b> {stats['penalty_points']:.2f}\n"
            f"🏆 <b>Raw Score:</b> {stats['raw_score']}\n"
            f"📈 <b>Adjusted Score:</b> {stats['adjusted_score']:.2f}\n"
        )
    
    # Calculate accuracy
    if stats['total_answers'] > 0:
        accuracy = (stats['correct_answers'] / stats['total_answers']) * 100
        stats_message += f"\n🎯 <b>Accuracy:</b> {accuracy:.1f}%"
    
    await update.message.reply_html(stats_message)

async def reset_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset user statistics"""
    user_id = update.effective_user.id
    
    # Reset scores
    save_user_data(user_id, {"total_answers": 0, "correct_answers": 0})
    
    # Reset penalties if negative marking is enabled
    if NEGATIVE_MARKING_ENABLED:
        reset_user_penalties(user_id)
    
    await update.message.reply_text("Your statistics have been reset!")

async def receive_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle answers to polls/quizzes"""
    answer = update.poll_answer
    poll_id = answer.poll_id
    
    # Get the poll data
    poll_data = context.bot_data.get("polls", {}).get(poll_id)
    if not poll_data:
        return
    
    # Get user data
    user_id = answer.user.id
    user_data = get_user_data(user_id)
    
    # Update total answers
    user_data["total_answers"] = user_data.get("total_answers", 0) + 1
    
    # Check if the answer is correct
    selected_option = answer.option_ids[0] if answer.option_ids else -1
    question = get_question_by_id(poll_data["question_id"])
    
    # If it's a list, try to find the correct one
    if isinstance(question, list):
        # Find the question in the list
        try:
            msg_id = poll_data.get("message_id")
            for q in question:
                if str(q.get("question")) == str(context.bot.polls.get(poll_id, {}).get("question")):
                    question = q
                    break
        except:
            # If we can't match exactly, just use the first one
            question = question[0]
    
    if question and selected_option == question.get("correct_option", -1):
        # Correct answer
        user_data["correct_answers"] = user_data.get("correct_answers", 0) + 1
        feedback = "✅ Correct!"
    else:
        # Wrong answer
        feedback = "❌ Wrong answer!"
        
        # Apply penalties if negative marking is enabled
        if NEGATIVE_MARKING_ENABLED:
            category = poll_data.get("category", "General Knowledge")
            penalty = apply_penalty(user_id, category)
            
            # Include penalty info in feedback
            penalty_value = get_penalty_for_category(category)
            if penalty_value > 0:
                feedback += f" (-{penalty_value} points)"
    
    # Save updated user data
    save_user_data(user_id, user_data)
    
    # Try to send feedback to user
    try:
        await context.bot.send_message(answer.user.id, feedback)
    except:
        # Can't message the user directly, send to chat if possible
        chat_id = poll_data.get("chat_id")
        if chat_id:
            try:
                await context.bot.send_message(
                    chat_id,
                    f"{answer.user.first_name}: {feedback}"
                )
            except:
                pass

# Add question conversation
async def add_question_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the add question conversation."""
    await update.message.reply_text(
        "Let's add a new question. First, please send the question text."
    )
    return QUESTION

async def add_question_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the question text and ask for options."""
    context.user_data["question"] = update.message.text
    
    await update.message.reply_text(
        "Now, please send the options, one per line."
    )
    return OPTIONS

async def add_question_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the options and ask for the correct answer."""
    options_text = update.message.text
    options = [opt.strip() for opt in options_text.split('\n') if opt.strip()]
    
    if len(options) < 2:
        await update.message.reply_text(
            "Please provide at least 2 options, one per line."
        )
        return OPTIONS
    
    context.user_data["options"] = options
    
    # Create option buttons
    keyboard = []
    for i, option in enumerate(options):
        keyboard.append([InlineKeyboardButton(f"{i+1}. {option}", callback_data=str(i))])
    
    await update.message.reply_text(
        "Which option is correct? Select one:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ANSWER

async def add_question_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the correct answer and ask for the category."""
    query = update.callback_query
    await query.answer()
    
    correct_option = int(query.data)
    context.user_data["correct_option"] = correct_option
    
    # Pre-defined categories
    categories = [
        "General Knowledge", "Science", "History", 
        "Geography", "Entertainment", "Sports"
    ]
    
    keyboard = []
    row = []
    for i, category in enumerate(categories):
        row.append(InlineKeyboardButton(category, callback_data=category))
        if (i+1) % 2 == 0:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("Custom Category", callback_data="custom")])
    
    await query.edit_message_text(
        "Select a category for this question:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CATEGORY

async def add_question_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the category and finish adding the question."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "custom":
        await query.edit_message_text(
            "Please type a custom category name:"
        )
        return CATEGORY
    
    context.user_data["category"] = query.data
    
    # Get the next question ID
    question_id = get_next_question_id()
    
    # Create the question data
    question_data = {
        "question": context.user_data["question"],
        "options": context.user_data["options"],
        "correct_option": context.user_data["correct_option"],
        "category": context.user_data["category"],
        "language": detect_language(context.user_data["question"])
    }
    
    # Add the question
    add_question_with_id(question_id, question_data)
    
    await query.edit_message_text(
        f"Question added successfully with ID {question_id}!"
    )
    
    # Clear user data
    context.user_data.clear()
    
    return ConversationHandler.END

async def add_question_custom_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom category input."""
    context.user_data["category"] = update.message.text
    
    # Get the next question ID
    question_id = get_next_question_id()
    
    # Create the question data
    question_data = {
        "question": context.user_data["question"],
        "options": context.user_data["options"],
        "correct_option": context.user_data["correct_option"],
        "category": context.user_data["category"],
        "language": detect_language(context.user_data["question"])
    }
    
    # Add the question
    add_question_with_id(question_id, question_data)
    
    await update.message.reply_text(
        f"Question added successfully with ID {question_id}!"
    )
    
    # Clear user data
    context.user_data.clear()
    
    return ConversationHandler.END

# PDF Import Functionality
async def pdf_import_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the PDF import conversation."""
    if not PDF_SUPPORT:
        await update.message.reply_text(
            "PDF support is not available. Please install PyPDF2."
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📄 <b>PDF Quiz Import</b>\n\n"
        "Please send the PDF file containing quiz questions.\n\n"
        "The PDF should contain questions with options in a structured format.\n"
        "The bot will try to extract them automatically.",
        parse_mode='HTML'
    )
    
    return PDF_UPLOAD

async def pdf_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle PDF file upload."""
    # Check if a file was uploaded
    if not update.message.document:
        await update.message.reply_text("Please send a PDF file.")
        return PDF_UPLOAD
    
    document = update.message.document
    
    # Check if it's a PDF
    if document.mime_type != "application/pdf":
        await update.message.reply_text("Please send a PDF file.")
        return PDF_UPLOAD
    
    # Download the file
    file = await context.bot.get_file(document.file_id)
    file_path = os.path.join(TEMP_DIR, f"{document.file_id}.pdf")
    await file.download_to_drive(file_path)
    
    # Store file path in context
    context.user_data["pdf_path"] = file_path
    
    # Ask for custom ID
    await update.message.reply_text(
        "Would you like to set a custom ID for questions from this PDF?\n"
        "This is useful for grouping related questions together.\n\n"
        "Send a number to use as base ID, or 'skip' to use default IDs.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Skip (Use Default IDs)", callback_data="skip_custom_id")]
        ])
    )
    
    return PDF_CUSTOM_ID

async def pdf_custom_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom ID input for PDF import."""
    # Check if this is a callback query
    if update.callback_query:
        await update.callback_query.answer()
        custom_id = None  # Use default IDs
    else:
        # It's a text message
        custom_id_text = update.message.text.strip()
        
        if custom_id_text.lower() == 'skip':
            custom_id = None  # Use default IDs
        else:
            try:
                custom_id = int(custom_id_text)
            except ValueError:
                await update.message.reply_text(
                    "Please provide a valid number for the custom ID or type 'skip'."
                )
                return PDF_CUSTOM_ID
    
    # Store custom ID in context
    context.user_data["custom_id"] = custom_id
    
    # Start processing PDF
    processing_message = await update.effective_message.reply_text(
        "⏳ Processing PDF... This may take a few moments."
    )
    
    # Get file path
    file_path = context.user_data.get("pdf_path")
    
    if not file_path or not os.path.exists(file_path):
        await processing_message.edit_text("PDF file not found. Please try again.")
        return ConversationHandler.END
    
    # Process PDF in the background
    context.application.create_task(
        process_pdf(update, context, file_path, processing_message)
    )
    
    return PDF_PROCESSING

async def process_pdf(update, context, file_path, processing_message):
    """Process PDF file in the background."""
    try:
        # Extract text from PDF
        lines = extract_text_from_pdf(file_path)
        
        if not lines:
            await processing_message.edit_text(
                "Could not extract text from the PDF. Please make sure it's a text-based PDF."
            )
            return
        
        # Clean up and deduplicate
        lines = group_and_deduplicate_questions(lines)
        
        # Extract questions
        text_content = "\n".join(lines)
        questions = extract_questions_from_text(text_content)
        
        if not questions:
            await processing_message.edit_text(
                "Could not find any questions in the PDF. Please make sure the PDF contains questions in a supported format."
            )
            return
        
        # Add questions to database
        custom_id = context.user_data.get("custom_id")
        base_id = custom_id if custom_id is not None else get_next_question_id()
        
        questions_added = 0
        for i, q in enumerate(questions):
            # Skip if the question or options are invalid
            if not q["question"] or not q["options"] or len(q["options"]) < 2:
                continue
                
            # Create question data
            question_data = {
                "question": q["question"],
                "options": q["options"],
                "correct_option": q["correct_option"],
                "category": "PDF Import",
                "language": q["language"]
            }
            
            # Add question with sequential ID if custom ID provided, otherwise use auto IDs
            question_id = base_id + i if custom_id is not None else get_next_question_id()
            add_question_with_id(question_id, question_data)
            questions_added += 1
        
        # Clean up temporary file
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Send completion message
        await processing_message.edit_text(
            f"✅ Successfully imported {questions_added} questions from the PDF!"
        )
        
        # Send a sample question if any were added
        if questions_added > 0:
            sample_question = questions[0]
            
            # Create options list for display
            options_text = "\n".join([f"- {opt}" for opt in sample_question["options"]])
            
            await update.effective_message.reply_text(
                f"Sample question imported:\n\n"
                f"{sample_question['question']}\n\n"
                f"Options:\n{options_text}\n\n"
                f"Language: {sample_question['language']}"
            )
        
    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        await processing_message.edit_text(
            f"An error occurred while processing the PDF: {str(e)}\n"
            "Please try a different PDF or check the file format."
        )
    
    # Clear user data
    if "pdf_path" in context.user_data:
        del context.user_data["pdf_path"]
    if "custom_id" in context.user_data:
        del context.user_data["custom_id"]

async def pdf_processing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle user interaction during PDF processing."""
    await update.message.reply_text(
        "Your PDF is still being processed. Please wait..."
    )
    return PDF_PROCESSING

# Complete the existing command handlers
async def edit_question_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the edit question conversation."""
    await update.message.reply_text(
        "Please send the ID of the question you want to edit."
    )
    return EDIT_SELECT

async def edit_question_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Select the question to edit."""
    try:
        question_id = update.message.text.strip()
        question = get_question_by_id(question_id)
        
        if not question:
            await update.message.reply_text(
                f"Question with ID {question_id} not found!"
            )
            return ConversationHandler.END
        
        # Store question and ID in context
        context.user_data["edit_question_id"] = question_id
        
        # If it's a list of questions, ask which one to edit
        if isinstance(question, list):
            keyboard = []
            for i, q in enumerate(question):
                keyboard.append([InlineKeyboardButton(
                    f"{i+1}. {q['question'][:30]}...", 
                    callback_data=str(i)
                )])
            
            await update.message.reply_text(
                "Multiple questions found with this ID. Please select one to edit:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # Store list of questions
            context.user_data["edit_question_list"] = question
            return EDIT_SELECT
        
        # Display current question
        options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(question["options"])])
        
        await update.message.reply_text(
            f"Current question:\n\n"
            f"{question['question']}\n\n"
            f"Options:\n{options_text}\n\n"
            f"Correct option: {question['correct_option'] + 1}\n\n"
            f"Please send the new question text, or 'cancel' to stop."
        )
        
        # Store original question
        context.user_data["edit_question_original"] = question
        
        return EDIT_QUESTION
        
    except Exception as e:
        logger.error(f"Error selecting question: {e}")
        await update.message.reply_text(
            "An error occurred. Please try again."
        )
        return ConversationHandler.END

async def edit_question_select_from_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Select a question from a list of questions with the same ID."""
    query = update.callback_query
    await query.answer()
    
    try:
        # Get the selected index
        index = int(query.data)
        
        # Get the question list
        question_list = context.user_data.get("edit_question_list", [])
        
        if not question_list or index >= len(question_list):
            await query.edit_message_text(
                "Invalid selection. Please try again."
            )
            return ConversationHandler.END
        
        # Get the selected question
        question = question_list[index]
        
        # Display current question
        options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(question["options"])])
        
        await query.edit_message_text(
            f"Current question:\n\n"
            f"{question['question']}\n\n"
            f"Options:\n{options_text}\n\n"
            f"Correct option: {question['correct_option'] + 1}\n\n"
            f"Please send the new question text, or reply with 'cancel' to stop."
        )
        
        # Store original question and index
        context.user_data["edit_question_original"] = question
        context.user_data["edit_question_index"] = index
        
        return EDIT_QUESTION
        
    except Exception as e:
        logger.error(f"Error selecting question from list: {e}")
        await query.edit_message_text(
            "An error occurred. Please try again."
        )
        return ConversationHandler.END

async def edit_question_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Edit the question text."""
    text = update.message.text.strip()
    
    if text.lower() == 'cancel':
        await update.message.reply_text("Question editing cancelled.")
        return ConversationHandler.END
    
    # Store new question text
    context.user_data["edit_question_new_text"] = text
    
    # Get original question options
    original_question = context.user_data.get("edit_question_original", {})
    options = original_question.get("options", [])
    
    options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(options)])
    
    await update.message.reply_text(
        f"Current options:\n\n{options_text}\n\n"
        f"Please send the new options, one per line, or 'keep' to keep the current options."
    )
    
    return EDIT_OPTIONS

async def edit_question_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Edit the question options."""
    text = update.message.text.strip()
    
    # Get original question
    original_question = context.user_data.get("edit_question_original", {})
    
    if text.lower() == 'keep':
        # Keep original options
        options = original_question.get("options", [])
        correct_option = original_question.get("correct_option", 0)
    else:
        # Parse new options
        options = [opt.strip() for opt in text.split('\n') if opt.strip()]
        
        if len(options) < 2:
            await update.message.reply_text(
                "Please provide at least 2 options, one per line, or 'keep' to keep the current options."
            )
            return EDIT_OPTIONS
        
        # Default to first option as correct
        correct_option = 0
    
    # Create keyboard for selecting correct option
    keyboard = []
    for i, option in enumerate(options):
        keyboard.append([InlineKeyboardButton(f"{i+1}. {option}", callback_data=str(i))])
    
    await update.message.reply_text(
        "Which option is correct? Select one:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Store new options
    context.user_data["edit_question_new_options"] = options
    
    return ANSWER

async def edit_question_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Set the correct answer and update the question."""
    query = update.callback_query
    await query.answer()
    
    # Get correct option
    correct_option = int(query.data)
    
    # Get question ID and edited values
    question_id = context.user_data.get("edit_question_id")
    question_text = context.user_data.get("edit_question_new_text")
    options = context.user_data.get("edit_question_new_options")
    
    # Get original question for fields to keep
    original_question = context.user_data.get("edit_question_original", {})
    
    # Create updated question
    updated_question = {
        "question": question_text,
        "options": options,
        "correct_option": correct_option,
        "category": original_question.get("category", "General Knowledge"),
        "language": detect_language(question_text)
    }
    
    # Get all questions for this ID
    questions = load_questions()
    questions_list = questions.get(question_id, [])
    
    # Handle single question vs list of questions
    if isinstance(questions_list, list):
        # Get the index of the question to update
        index = context.user_data.get("edit_question_index", 0)
        
        # Update the specific question in the list
        if index < len(questions_list):
            questions_list[index] = updated_question
            questions[question_id] = questions_list
            save_questions(questions)
    else:
        # Replace the single question
        questions[question_id] = updated_question
        save_questions(questions)
    
    await query.edit_message_text(
        f"Question with ID {question_id} has been updated!"
    )
    
    # Clear user data
    for key in list(context.user_data.keys()):
        if key.startswith("edit_question"):
            del context.user_data[key]
    
    return ConversationHandler.END

async def delete_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a question by ID."""
    # Check if an ID was provided
    if not context.args:
        await update.message.reply_text("Please provide a question ID: /delete [ID]")
        return
    
    question_id = context.args[0]
    
    # Try to delete the question
    if delete_question_by_id(question_id):
        await update.message.reply_text(f"Question with ID {question_id} has been deleted!")
    else:
        await update.message.reply_text(f"Question with ID {question_id} not found!")

async def list_questions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all available questions."""
    questions = load_questions()
    
    if not questions:
        await update.message.reply_text("No questions available.")
        return
    
    # Count total questions
    total_count = 0
    for qid, q_list in questions.items():
        if isinstance(q_list, list):
            total_count += len(q_list)
        else:
            total_count += 1
    
    # Prepare message with question count by category
    categories = {}
    for qid, q_list in questions.items():
        if isinstance(q_list, list):
            for q in q_list:
                cat = q.get("category", "Other")
                categories[cat] = categories.get(cat, 0) + 1
        else:
            cat = q_list.get("category", "Other")
            categories[cat] = categories.get(cat, 0) + 1
    
    message = f"📚 <b>Question Database</b>\n\n"
    message += f"Total Questions: {total_count}\n\n"
    
    message += "<b>Categories:</b>\n"
    for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        message += f"• {cat}: {count}\n"
    
    # Trim message if too long
    if len(message) > 4000:
        message = message[:3997] + "..."
    
    await update.message.reply_html(message)

# Poll to Question conversation
async def poll_to_question_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start the poll to question conversation."""
    await update.message.reply_text(
        "Please forward a poll to convert it into a quiz question."
    )
    context.user_data["awaiting_poll"] = True

async def handle_poll_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a forwarded poll."""
    # Check if we're waiting for a poll
    if not context.user_data.get("awaiting_poll", False):
        return
    
    # Check if this message contains a poll
    poll = update.message.poll
    if not poll:
        await update.message.reply_text(
            "That's not a poll. Please forward a poll message."
        )
        return
    
    # Extract poll data
    question_text = poll.question
    options = [opt.text for opt in poll.options]
    
    # Default to first option as correct answer
    correct_option = 0
    
    # Create question data
    question_data = {
        "question": question_text,
        "options": options,
        "correct_option": correct_option,
        "category": "Poll Import",
        "language": detect_language(question_text)
    }
    
    # Get the next question ID
    question_id = get_next_question_id()
    
    # Add the question
    add_question_with_id(question_id, question_data)
    
    # Create keyboard to select correct answer
    keyboard = []
    for i, option in enumerate(options):
        keyboard.append([InlineKeyboardButton(f"{i+1}. {option}", callback_data=f"pollcorrect_{question_id}_{i}")])
    
    await update.message.reply_text(
        f"Poll converted to question with ID {question_id}!\n\n"
        f"Please select the correct answer:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Clear the awaiting poll flag
    del context.user_data["awaiting_poll"]

async def handle_poll_correct_option(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle selection of correct option for a poll."""
    query = update.callback_query
    await query.answer()
    
    # Parse callback data
    _, question_id, option_index = query.data.split("_")
    question_id = question_id
    option_index = int(option_index)
    
    # Get question
    questions = load_questions()
    question = questions.get(question_id)
    
    if not question:
        await query.edit_message_text(
            "Question not found. It may have been deleted."
        )
        return
    
    # Update correct option
    if isinstance(question, list):
        question[0]["correct_option"] = option_index
    else:
        question["correct_option"] = option_index
    
    # Save updated question
    questions[question_id] = question
    save_questions(questions)
    
    await query.edit_message_text(
        f"Question with ID {question_id} has been updated with the correct answer!"
    )

def get_application():
    """Create and configure the Application instance."""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Basic commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("quiz", quiz))
    application.add_handler(CommandHandler("quizid", quizid))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("resetstats", reset_stats))
    application.add_handler(CommandHandler("delete", delete_question))
    application.add_handler(CommandHandler("list", list_questions))
    
    # Poll answer handler
    application.add_handler(PollAnswerHandler(receive_poll_answer))
    
    # Web scraping conversation
    webscrape_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("webscrape", webscrape_start)],
        states={
            CLONE_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, webscrape_url)],
            CUSTOM_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_id_handler),
                CallbackQueryHandler(custom_id_handler, pattern="^skip_custom_id$")
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(webscrape_conv_handler)
    
    # Add question conversation
    add_question_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_question_start)],
        states={
            QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_text)],
            OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_options)],
            ANSWER: [CallbackQueryHandler(add_question_answer)],
            CATEGORY: [
                CallbackQueryHandler(add_question_category),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_custom_category)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(add_question_conv_handler)
    
    # Edit question conversation
    edit_question_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("edit", edit_question_start)],
        states={
            EDIT_SELECT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_question_select),
                CallbackQueryHandler(edit_question_select_from_list)
            ],
            EDIT_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_question_text)],
            EDIT_OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_question_options)],
            ANSWER: [CallbackQueryHandler(edit_question_answer)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(edit_question_conv_handler)
    
    # PDF import conversation
    pdf_import_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("pdfimport", pdf_import_start)],
        states={
            PDF_UPLOAD: [MessageHandler(filters.Document.PDF, pdf_upload)],
            PDF_CUSTOM_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, pdf_custom_id),
                CallbackQueryHandler(pdf_custom_id, pattern="^skip_custom_id$")
            ],
            PDF_PROCESSING: [MessageHandler(filters.TEXT & ~filters.COMMAND, pdf_processing)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(pdf_import_conv_handler)
    
    # Poll to question
    application.add_handler(CommandHandler("poll2q", poll_to_question_start))
    application.add_handler(MessageHandler(filters.POLL, handle_poll_forward))
    application.add_handler(CallbackQueryHandler(handle_poll_correct_option, pattern="^pollcorrect_"))
    
    return application

# Web scraping utility functions
def is_valid_url(url):
    """Check if a URL is valid"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def extract_text_with_trafilatura(html_content):
    """Extract main text content using trafilatura"""
    try:
        text = trafilatura.extract(html_content, output_format='text', include_comments=False, 
                                  include_tables=True, no_fallback=False)
        if text:
            return text
            
        # If trafilatura fails, try BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.extract()
            
        # Get text content
        text = soup.get_text(separator='\n')
        
        # Clean up whitespace
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return '\n'.join(lines)
    except Exception as e:
        logger.error(f"Error extracting text with trafilatura: {e}")
        return None

# QuickScrape command for direct URL import
async def quick_scrape_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Command to directly scrape a URL and save questions with a custom ID
    Usage: /quickscrape [url] [category] [custom_id]
    Example: /quickscrape https://example.com "Science Quiz" 101
    If custom_id is not provided, an auto-generated ID will be used
    """
    # Check arguments
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ Missing URL parameter.\n\n"
            "Usage: /quickscrape [url] [category] [custom_id]\n"
            "Example: /quickscrape https://example.com \"Science Quiz\" 101\n\n"
            "The category and custom_id parameters are optional."
        )
        return
    
    # Extract parameters
    url = context.args[0]
    
    # If URL doesn't start with http:// or https://, add https://
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Get optional category (second argument in quotes)
    category = "Web Scraped"
    if len(context.args) >= 2:
        category = context.args[1]
    
    # Get optional custom ID (third argument)
    custom_id = None
    if len(context.args) >= 3:
        try:
            custom_id = int(context.args[2])
        except ValueError:
            await update.message.reply_text(
                "⚠️ Custom ID must be a number. Using auto-generated ID instead."
            )
    
    # Start processing message
    status_message = await update.message.reply_text(
        f"⏳ Starting quick scrape of URL: {url}\n"
        f"Please wait..."
    )
    
    try:
        # Get the text content
        text_content = get_website_text_content(url)
        
        if not text_content:
            await status_message.edit_text(
                f"❌ Failed to extract content from URL: {url}\n"
                "The website might be blocking scraping or requires JavaScript."
            )
            return
        
        # Extract questions
        questions = extract_questions_from_text(text_content)
        
        if not questions:
            await status_message.edit_text(
                "❌ No questions found on the website.\n\n"
                "The URL was accessible but no quiz questions could be identified."
            )
            return
        
        # Get question ID to use
        question_id = custom_id if custom_id is not None else get_next_question_id()
        
        # Create and save questions
        questions_added = 0
        for i, q in enumerate(questions):
            # Ensure options are preserved exactly as extracted
            # Create question data
            options = q['options'].copy() if isinstance(q['options'], list) else []
            
            # Debug logging of options
            print(f"Extracted options for question {i+1}: {options}")
            
            # Make sure we have at least 2 options to make a valid quiz
            # But DO NOT replace the original options with generic placeholders!
            is_hindi = q['language'] == 'hi'
            if len(options) < 2:
                print(f"Warning: Not enough options for question {i+1}, adding generic ones to meet minimum")
                while len(options) < 2:
                    if is_hindi:
                        # Use a prefix to indicate these are auto-generated
                        options.append(f"Auto-{len(options)+1}: वैकल्पिक विकल्प")
                    else:
                        options.append(f"Auto-{len(options)+1}: Alternative option")
                        
            # Final options being used        
            print(f"Final options for question {i+1}: {options}")
            
            question_data = {
                "question": q['question'],
                "options": options,  # Use preserved options
                "correct_option": q['correct_option'],
                "category": category,
                "language": q['language']
            }
            
            # Add the question
            if custom_id is not None:
                # If custom ID was provided, use sequential IDs
                add_question_with_id(question_id + i, question_data)
            else:
                # Otherwise use the next available ID for each question
                add_question_with_id(get_next_question_id(), question_data)
            
            questions_added += 1
        
        # Success message
        await status_message.edit_text(
            f"✅ Successfully imported {questions_added} questions!\n\n"
            f"• URL: {url}\n"
            f"• Category: {category}\n"
            f"• Questions imported: {questions_added}\n"
            f"• ID: {question_id}\n\n"
            f"You can use these questions in a quiz with:\n"
            f"/quizid {question_id}"
        )
        
    except Exception as e:
        # Log and report any errors
        logger.error(f"Unexpected error in quickscrape for URL {url}: {str(e)}")
        await status_message.edit_text(
            f"❌ An error occurred while processing the URL:\n{str(e)}"
        )

def main():
    """Start the bot."""
    # Create the Application
    application = get_application()
    
    # Add quickscrape command
    application.add_handler(CommandHandler("quickscrape", quick_scrape_command))
    
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
