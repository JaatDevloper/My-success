"""
Enhanced Telegram Quiz Bot with Advanced PDF Import & Hindi Support
- Based on the original simple_bot.py
- Features:
  - Improved PDF processing with OCR support
  - Enhanced language detection for Hindi/English
  - Support for various PDF formats
  - Negative marking features
  - PDF import with automatic question extraction
"""

# Import libraries for PDF handling and OCR
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

try:
    import pytesseract
    OCR_SUPPORT = True
except ImportError:
    OCR_SUPPORT = False

try:
    from pdf2image import convert_from_path, convert_from_bytes
    PDF2IMAGE_SUPPORT = True
except ImportError:
    PDF2IMAGE_SUPPORT = False

try:
    from langdetect import detect
    LANGDETECT_SUPPORT = True
except ImportError:
    LANGDETECT_SUPPORT = False

import tempfile
TEMP_DIR = tempfile.mkdtemp()

import json
import logging
import os
import re
import random
import asyncio
import io
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

# PDF import conversation states (use high numbers to avoid conflicts)
PDF_UPLOAD, PDF_CUSTOM_ID, PDF_PROCESSING = range(100, 103)

# OCR configuration states
OCR_CONFIG = range(200, 201)

# Data files
QUESTIONS_FILE = "questions.json"
USERS_FILE = "users.json"
PENALTIES_FILE = "penalties.json"
CONFIG_FILE = "config.json"

# Default OCR configuration
DEFAULT_OCR_CONFIG = {
    "language": "eng+hin",  # Default language for OCR
    "page_limit": 20,       # Maximum number of pages to process
    "min_confidence": 60,   # Minimum confidence score for OCR (0-100)
    "auto_detect_language": True,  # Automatically detect language
    "force_ocr": False      # Force OCR even for text-based PDFs
}

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

# ---------- OCR CONFIGURATION FUNCTIONS ----------
def load_ocr_config():
    """Load OCR configuration from file"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                # If OCR config exists, return it, otherwise return default with any saved settings
                if 'ocr_config' in config:
                    return {**DEFAULT_OCR_CONFIG, **config['ocr_config']}
        return DEFAULT_OCR_CONFIG
    except Exception as e:
        logger.error(f"Error loading OCR configuration: {e}")
        return DEFAULT_OCR_CONFIG

def save_ocr_config(config):
    """Save OCR configuration to file"""
    try:
        all_config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                all_config = json.load(f)
        
        all_config['ocr_config'] = config
        
        with open(CONFIG_FILE, 'w') as f:
            json.dump(all_config, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving OCR configuration: {e}")
        return False

# ---------- BASIC DATABASE FUNCTIONS ----------
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

# ---------- ENHANCED LANGUAGE DETECTION FUNCTIONS ----------
def detect_language_advanced(text):
    """
    Advanced language detection to identify if text contains Hindi
    Returns 'hi' if Hindi is detected, 'en' otherwise
    Improved to better handle mixed language content and Hindi detection
    """
    if not text or len(text.strip()) == 0:
        return 'en'  # Default to English for empty text
    
    # First check for Devanagari script (more efficient)
    hindi_range = range(0x0900, 0x097F + 1)
    
    # Count Devanagari characters
    hindi_chars = sum(1 for char in text if ord(char) in hindi_range)
    
    # If we have a significant number of Hindi characters, classify as Hindi
    # This helps with mixed language texts
    if hindi_chars > 10 or (len(text) > 0 and hindi_chars / len(text) > 0.05):
        return 'hi'
    
    # Extended Hindi detection using common words
    hindi_words = ["में", "है", "का", "की", "और", "से", "को", "एक", "यह", "पर", "हैं", "थे", "गया", "करना"]
    for word in hindi_words:
        if word in text:
            return 'hi'
    
    # If no Devanagari characters found but langdetect is available, use it as fallback
    if LANGDETECT_SUPPORT:
        try:
            # Only use the first 1000 characters to speed up detection
            sample_text = text[:1000]
            # Use langdetect's detect function
            if 'detect' in globals() or 'detect' in locals():
                detected_lang = detect(sample_text)
                if detected_lang == 'hi':
                    return 'hi'
            else:
                # Fallback if langdetect.detect is not available
                pass
        except Exception as e:
            logger.error(f"Language detection error: {e}")
    
    # Default to English if no Hindi detected
    return 'en'

def get_ocr_language_code(text_sample=None):
    """
    Get the appropriate OCR language code based on text sample
    If text_sample is None, use the default language code
    """
    config = load_ocr_config()
    
    # If auto detect is disabled or no text sample, return configured language
    if not config['auto_detect_language'] or text_sample is None:
        return config['language']
    
    # Detect language in the sample
    detected_lang = detect_language_advanced(text_sample)
    
    # Map detected language to tesseract language code
    if detected_lang == 'hi':
        return 'hin+eng'  # Hindi with English fallback
    else:
        return 'eng'  # English only
    
# ---------- PDF PROCESSING FUNCTIONS ----------
def extract_text_from_pdf_page(pdf_reader, page_num):
    """Extract text from a PDF page using PyPDF2"""
    try:
        page = pdf_reader.pages[page_num]
        return page.extract_text()
    except Exception as e:
        logger.error(f"Error extracting text from page {page_num}: {e}")
        return ""

def extract_text_via_ocr(page_image, language='eng+hin'):
    """Extract text from a page image using OCR"""
    if not OCR_SUPPORT:
        return "OCR not available. Please install pytesseract."
    
    try:
        # Set custom configuration for tesseract
        custom_config = f'-l {language} --oem 3 --psm 6'
        
        # Extract text using OCR
        text = pytesseract.image_to_string(page_image, config=custom_config)
        return text
    except Exception as e:
        logger.error(f"OCR error: {e}")
        return ""

def convert_pdf_page_to_image(pdf_bytes, page_num):
    """Convert a PDF page to an image for OCR processing"""
    if not PDF2IMAGE_SUPPORT:
        return None
    
    try:
        # Convert the specific page to an image
        images = convert_from_bytes(
            pdf_bytes, 
            first_page=page_num + 1,  # pdf2image uses 1-based indexing
            last_page=page_num + 1,
            dpi=300  # Higher DPI for better OCR results
        )
        
        if images and len(images) > 0:
            return images[0]
        return None
    except Exception as e:
        logger.error(f"Error converting PDF page to image: {e}")
        return None

def detect_is_scanned_pdf(pdf_reader, sample_pages=3):
    """
    Detect if a PDF is likely a scanned document (needs OCR)
    by checking if it has extractable text
    """
    total_pages = len(pdf_reader.pages)
    pages_to_check = min(sample_pages, total_pages)
    
    # Check random pages for extractable text
    text_content = ""
    for _ in range(pages_to_check):
        page_num = random.randint(0, total_pages - 1)
        page_text = extract_text_from_pdf_page(pdf_reader, page_num)
        text_content += page_text
    
    # If we found less than 100 characters across sample pages, likely a scanned PDF
    if len(text_content.strip()) < 100:
        return True
        
    return False

def extract_text_from_pdf(pdf_bytes, config=None):
    """
    Extract text from a PDF file
    Returns a dictionary with page numbers as keys and text content as values
    Improved to support all PDF formats including non-OCR files
    """
    if config is None:
        config = load_ocr_config()
        
    if not PDF_SUPPORT:
        return {"error": "PDF support not available. Please install PyPDF2."}
    
    result = {}
    
    try:
        # Open the PDF file
        pdf_stream = io.BytesIO(pdf_bytes)
        pdf_reader = PyPDF2.PdfReader(pdf_stream)
        
        # Check if it's a scanned PDF (needs OCR)
        needs_ocr = config['force_ocr'] or detect_is_scanned_pdf(pdf_reader)
        
        # Limit the number of pages to process
        total_pages = len(pdf_reader.pages)
        max_pages = min(config['page_limit'], total_pages)
        
        # Track if OCR is available for when we need it
        ocr_available = PDF2IMAGE_SUPPORT and OCR_SUPPORT and IMAGE_SUPPORT
        
        # Process each page
        for page_num in range(max_pages):
            # First try to extract text with PyPDF2 even if OCR might be needed
            # This ensures we get text from all types of PDFs when possible
            page_text = extract_text_from_pdf_page(pdf_reader, page_num)
            
            # If we got very little text and OCR is indicated, try OCR instead
            if (len(page_text.strip()) < 100 and needs_ocr and ocr_available):
                # Process using OCR
                page_image = convert_pdf_page_to_image(pdf_bytes, page_num)
                if page_image:
                    # If we have a text sample, use it to determine language, otherwise use default
                    text_sample = ""
                    if page_num > 0 and str(page_num-1) in result:
                        text_sample = result[str(page_num-1)]
                    
                    lang_code = get_ocr_language_code(text_sample)
                    ocr_text = extract_text_via_ocr(page_image, language=lang_code)
                    
                    # Only use OCR result if it produced more text than direct extraction
                    if len(ocr_text.strip()) > len(page_text.strip()):
                        page_text = ocr_text
            
            # Store the result, whether from PyPDF2 or OCR
            result[str(page_num)] = page_text
            
            # If OCR is needed but not available, add a note
            if needs_ocr and not ocr_available and len(page_text.strip()) < 100:
                result[str(page_num)] += "\n[Note: This appears to be a scanned page. OCR capability not available. Install pytesseract and pdf2image for better results.]"
        
        return result
    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        return {"error": f"Error processing PDF: {str(e)}"}

# ---------- QUESTION EXTRACTION FUNCTIONS ----------
def clean_text(text):
    """Clean and normalize text"""
    if not text:
        return ""
    
    # Replace multiple spaces/newlines with single space
    text = re.sub(r'\s+', ' ', text)
    # Strip leading/trailing whitespace
    text = text.strip()
    return text

def is_likely_question(text):
    """Check if text is likely a question"""
    # Must have a reasonable length
    if len(text) < 10 or len(text) > 500:
        return False
        
    # Should end with a question mark or have a question word
    question_pattern = r'(^|[^\w])(what|who|where|when|why|how|which)($|[^\w])'
    if text.endswith('?') or re.search(question_pattern, text.lower()):
        return True
    
    # Also check for numbered questions
    numbered_question = r'^\s*\d+[\.\)]\s*.{10,}'
    if re.match(numbered_question, text):
        return True
        
    return False

def is_likely_option(text, option_markers=None):
    """Check if text is likely an answer option"""
    if not option_markers:
        option_markers = ['a)', 'b)', 'c)', 'd)', 'A)', 'B)', 'C)', 'D)', 
                         '(a)', '(b)', '(c)', '(d)', '(A)', '(B)', '(C)', '(D)',
                         'a.', 'b.', 'c.', 'd.', 'A.', 'B.', 'C.', 'D.']
    
    # Check if text starts with an option marker
    for marker in option_markers:
        if text.lstrip().startswith(marker):
            return True
    
    return False

def extract_options_from_text(text, question=None):
    """Extract options from text"""
    options = []
    
    # Common option markers
    option_markers = ['a)', 'b)', 'c)', 'd)', 'A)', 'B)', 'C)', 'D)', 
                     '(a)', '(b)', '(c)', '(d)', '(A)', '(B)', '(C)', '(D)',
                     'a.', 'b.', 'c.', 'd.', 'A.', 'B.', 'C.', 'D.']
    
    # Try to find options by common markers
    for marker in option_markers:
        pattern = rf'{re.escape(marker)}\s*([^\n]*?)(?=\s*(?:{"|".join([re.escape(m) for m in option_markers])}|$))'
        matches = re.findall(pattern, text)
        if matches:
            cleaned_options = [clean_text(opt) for opt in matches]
            if len(cleaned_options) >= 2:  # Need at least 2 options
                return cleaned_options[:4]  # Return up to 4 options
    
    # If no options found with markers, try splitting by newlines and checking each line
    lines = text.split('\n')
    potential_options = []
    
    for line in lines:
        line = line.strip()
        if is_likely_option(line, option_markers):
            # Remove the option marker
            for marker in option_markers:
                if line.lstrip().startswith(marker):
                    option_text = line[line.find(marker) + len(marker):].strip()
                    potential_options.append(option_text)
                    break
    
    if len(potential_options) >= 2:
        return potential_options[:4]
    
    # If still no options found, try to find short answers after the question
    if question and question in text:
        post_question_text = text[text.find(question) + len(question):]
        lines = post_question_text.split('\n')
        short_answers = [line.strip() for line in lines if 5 <= len(line.strip()) <= 100]
        if len(short_answers) >= 2:
            return short_answers[:4]
    
    return options

def extract_questions_from_text(text, language=None):
    """Extract questions and options from text"""
    if not text or len(text.strip()) == 0:
        return []
    
    # Detect language if not provided
    if not language:
        language = detect_language_advanced(text)
    
    # Split text into paragraphs/lines
    paragraphs = text.split('\n')
    
    questions = []
    current_question = None
    current_question_text = ""
    current_options = []
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        # Check if this paragraph looks like a question
        if is_likely_question(para):
            # If we already have a question in progress, save it
            if current_question:
                # Try to extract options if we don't have any
                if not current_options:
                    current_options = extract_options_from_text(current_question_text, current_question)
                
                # Only add if we have options
                if current_options:
                    questions.append({
                        "question": current_question,
                        "options": current_options,
                        "correct_option": 0,  # Default to first option
                        "language": language
                    })
            
            # Start a new question
            current_question = clean_text(para)
            current_question_text = para
            current_options = []
        elif current_question and is_likely_option(para):
            # This paragraph looks like an option for the current question
            # Strip out the option marker
            option_text = re.sub(r'^\s*[(A-Da-d][\.\)]?\s*', '', para)
            current_options.append(clean_text(option_text))
        elif current_question:
            # This could be part of the current question text
            current_question_text += "\n" + para
    
    # Don't forget to process the last question
    if current_question:
        # Try to extract options if we don't have any
        if not current_options:
            current_options = extract_options_from_text(current_question_text, current_question)
        
        # Only add if we have options
        if current_options:
            questions.append({
                "question": current_question,
                "options": current_options,
                "correct_option": 0,  # Default to first option
                "language": language
            })
    
    return questions

def extract_questions_from_pdf(pdf_bytes, custom_id=None, config=None):
    """Extract questions from a PDF file"""
    if not PDF_SUPPORT:
        return {"error": "PDF support not available. Please install PyPDF2."}
    
    if config is None:
        config = load_ocr_config()
    
    try:
        # Extract text from PDF
        extracted_text = extract_text_from_pdf(pdf_bytes, config)
        
        # Check for errors
        if "error" in extracted_text:
            return extracted_text
        
        # Combine all page texts
        all_text = "\n".join(extracted_text.values())
        
        # Detect language of the text
        language = detect_language_advanced(all_text)
        
        # Extract questions
        questions = extract_questions_from_text(all_text, language)
        
        # Prepare response
        result = {
            "success": True,
            "questions": questions,
            "language": language,
            "question_count": len(questions)
        }
        
        # Add custom ID if provided
        if custom_id:
            result["custom_id"] = custom_id
        
        return result
    except Exception as e:
        logger.error(f"Error extracting questions from PDF: {e}")
        return {"error": f"Error extracting questions from PDF: {str(e)}"}

def save_questions_from_pdf(pdf_result, question_id=None):
    """Save extracted questions to the questions database"""
    if "error" in pdf_result:
        return {"error": pdf_result["error"]}
    
    if "questions" not in pdf_result or not pdf_result["questions"]:
        return {"error": "No questions found in PDF"}
    
    # Use provided ID or get next available
    id_to_use = question_id if question_id else get_next_question_id()
    
    # Add each question
    added_count = 0
    for question_data in pdf_result["questions"]:
        # Add category information
        question_data["category"] = "PDF Import"
        
        # Add the question
        if add_question_with_id(id_to_use, question_data):
            added_count += 1
        
        # Increment ID for next question
        id_to_use += 1
    
    return {
        "success": True,
        "added_count": added_count,
        "start_id": question_id if question_id else get_next_question_id() - added_count,
        "end_id": id_to_use - 1,
        "language": pdf_result.get("language", "unknown")
    }

# ---------- BOT COMMAND HANDLERS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the command /start is issued."""
    user = update.effective_user
    welcome_text = (
        f"👋 Hello, {user.first_name}!\n\n"
        "Welcome to the Enhanced Quiz Bot with Advanced PDF Import & Hindi Support.\n\n"
        "📝 Core Features:\n"
        "💡 /quiz - Start a new quiz (auto-sequence)\n"
        "📊 /stats - View your quiz statistics with penalties\n"
        "➕ /add - Add a new question to the quiz bank\n"
        "✏️ /edit - Edit an existing question\n"
        "❌ /delete - Delete a question\n\n"
        
        "📄 PDF Import Features:\n"
        "📥 /pdfimport - Import questions from a PDF file\n"
        "🔍 /ocrconfig - Configure OCR settings for PDF import\n"
        "🆔 /quizid - Start a quiz with a specific custom ID\n"
        "ℹ️ /pdfinfo - Information about PDF import features\n\n"
        
        "🔄 Additional Features:\n"
        "🔄 /poll2q - Convert a Telegram poll to a quiz question\n"
        "⚙️ /negmark - Configure negative marking settings\n"
        "🧹 /resetpenalty - Reset your penalties\n"
        "ℹ️ /help - Show this help message\n\n"
        "Let's test your knowledge with some fun quizzes!"
    )
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help message."""
    await start(update, context)

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

async def negative_marking_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle negative marking setting callbacks."""
    global NEGATIVE_MARKING_ENABLED
    query = update.callback_query
    await query.answer()
    
    if query.data == "neg_mark_enable":
        NEGATIVE_MARKING_ENABLED = True
        await query.edit_message_text("✅ Negative marking has been enabled.")
    
    elif query.data == "neg_mark_disable":
        NEGATIVE_MARKING_ENABLED = False
        await query.edit_message_text("❌ Negative marking has been disabled.")
    
    elif query.data == "neg_mark_reset":
        reset_user_penalties()
        await query.edit_message_text("🧹 All penalties have been reset to zero.")
    
    elif query.data == "neg_mark_back":
        await query.edit_message_text("⚙️ Negative marking settings closed.")

async def reset_penalty_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset penalties for the user."""
    user = update.effective_user
    reset_user_penalties(user.id)
    await update.message.reply_text("🧹 Your penalty points have been reset to zero.")

# ---------- OCR CONFIGURATION HANDLERS ----------
async def ocr_config_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show OCR configuration settings."""
    current_config = load_ocr_config()
    
    # Create keyboard with current settings
    keyboard = [
        [InlineKeyboardButton(f"Language: {current_config['language']}", callback_data="ocr_language")],
        [InlineKeyboardButton(f"Page Limit: {current_config['page_limit']}", callback_data="ocr_page_limit")],
        [InlineKeyboardButton(f"Min Confidence: {current_config['min_confidence']}%", callback_data="ocr_confidence")],
        [InlineKeyboardButton(f"Auto Detect Language: {'On' if current_config['auto_detect_language'] else 'Off'}", callback_data="ocr_auto_detect")],
        [InlineKeyboardButton(f"Force OCR: {'On' if current_config['force_ocr'] else 'Off'}", callback_data="ocr_force")],
        [InlineKeyboardButton("Save & Close", callback_data="ocr_save")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Check for required OCR components
    ocr_status = "⚠️ Some OCR components are missing:\n\n"
    if not OCR_SUPPORT:
        ocr_status += "- pytesseract not installed (OCR engine)\n"
    if not PDF2IMAGE_SUPPORT:
        ocr_status += "- pdf2image not installed (PDF converter)\n"
    if not IMAGE_SUPPORT:
        ocr_status += "- PIL/Pillow not installed (image handling)\n"
    
    if OCR_SUPPORT and PDF2IMAGE_SUPPORT and IMAGE_SUPPORT:
        ocr_status = "✅ All OCR components are properly installed."
    
    await update.message.reply_text(
        "🔧 OCR Configuration Settings\n\n"
        f"{ocr_status}\n\n"
        "Select a setting to change:",
        reply_markup=reply_markup
    )
    
    return OCR_CONFIG

async def ocr_config_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle OCR configuration callbacks."""
    query = update.callback_query
    await query.answer()
    
    config = load_ocr_config()
    
    if query.data == "ocr_language":
        # Show language options
        keyboard = [
            [InlineKeyboardButton("English", callback_data="ocr_lang_eng")],
            [InlineKeyboardButton("Hindi", callback_data="ocr_lang_hin")],
            [InlineKeyboardButton("English + Hindi", callback_data="ocr_lang_eng+hin")],
            [InlineKeyboardButton("Back", callback_data="ocr_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Select OCR language:\n\n"
            "Current setting: " + config['language'],
            reply_markup=reply_markup
        )
        return OCR_CONFIG
    
    elif query.data.startswith("ocr_lang_"):
        # Set language
        lang = query.data[9:]  # Remove 'ocr_lang_' prefix
        config['language'] = lang
        save_ocr_config(config)
        
        # Update the main config menu
        return await show_updated_ocr_config(update, context)
    
    elif query.data == "ocr_page_limit":
        # Show page limit options
        keyboard = [
            [InlineKeyboardButton("5 pages", callback_data="ocr_pages_5")],
            [InlineKeyboardButton("10 pages", callback_data="ocr_pages_10")],
            [InlineKeyboardButton("20 pages", callback_data="ocr_pages_20")],
            [InlineKeyboardButton("50 pages", callback_data="ocr_pages_50")],
            [InlineKeyboardButton("Back", callback_data="ocr_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Select maximum pages to process:\n\n"
            f"Current setting: {config['page_limit']} pages",
            reply_markup=reply_markup
        )
        return OCR_CONFIG
    
    elif query.data.startswith("ocr_pages_"):
        # Set page limit
        pages = int(query.data[10:])  # Remove 'ocr_pages_' prefix
        config['page_limit'] = pages
        save_ocr_config(config)
        
        # Update the main config menu
        return await show_updated_ocr_config(update, context)
    
    elif query.data == "ocr_confidence":
        # Show confidence options
        keyboard = [
            [InlineKeyboardButton("50%", callback_data="ocr_conf_50")],
            [InlineKeyboardButton("60%", callback_data="ocr_conf_60")],
            [InlineKeyboardButton("70%", callback_data="ocr_conf_70")],
            [InlineKeyboardButton("80%", callback_data="ocr_conf_80")],
            [InlineKeyboardButton("Back", callback_data="ocr_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Select minimum OCR confidence level:\n\n"
            f"Current setting: {config['min_confidence']}%",
            reply_markup=reply_markup
        )
        return OCR_CONFIG
    
    elif query.data.startswith("ocr_conf_"):
        # Set confidence level
        conf = int(query.data[9:])  # Remove 'ocr_conf_' prefix
        config['min_confidence'] = conf
        save_ocr_config(config)
        
        # Update the main config menu
        return await show_updated_ocr_config(update, context)
    
    elif query.data == "ocr_auto_detect":
        # Toggle auto detect setting
        config['auto_detect_language'] = not config['auto_detect_language']
        save_ocr_config(config)
        
        # Update the main config menu
        return await show_updated_ocr_config(update, context)
    
    elif query.data == "ocr_force":
        # Toggle force OCR setting
        config['force_ocr'] = not config['force_ocr']
        save_ocr_config(config)
        
        # Update the main config menu
        return await show_updated_ocr_config(update, context)
    
    elif query.data == "ocr_save" or query.data == "ocr_back":
        # Save and return to main menu
        await query.edit_message_text("OCR configuration has been saved.")
        return ConversationHandler.END
    
    return OCR_CONFIG

async def show_updated_ocr_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show updated OCR configuration after changes."""
    query = update.callback_query
    current_config = load_ocr_config()
    
    # Create keyboard with updated settings
    keyboard = [
        [InlineKeyboardButton(f"Language: {current_config['language']}", callback_data="ocr_language")],
        [InlineKeyboardButton(f"Page Limit: {current_config['page_limit']}", callback_data="ocr_page_limit")],
        [InlineKeyboardButton(f"Min Confidence: {current_config['min_confidence']}%", callback_data="ocr_confidence")],
        [InlineKeyboardButton(f"Auto Detect Language: {'On' if current_config['auto_detect_language'] else 'Off'}", callback_data="ocr_auto_detect")],
        [InlineKeyboardButton(f"Force OCR: {'On' if current_config['force_ocr'] else 'Off'}", callback_data="ocr_force")],
        [InlineKeyboardButton("Save & Close", callback_data="ocr_save")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🔧 OCR Configuration Settings\n\n"
        "Settings updated! Select another setting to change:",
        reply_markup=reply_markup
    )
    
    return OCR_CONFIG

async def cancel_ocr_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel OCR configuration."""
    await update.message.reply_text("OCR configuration cancelled.")
    return ConversationHandler.END

# ---------- PDF IMPORT HANDLERS ----------
async def pdf_import_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the PDF import process."""
    await update.message.reply_text(
        "📄 PDF Import Wizard\n\n"
        "Please send me a PDF file containing quiz questions.\n"
        "The bot will extract questions and add them to your quiz database.\n\n"
        "For best results:\n"
        "• PDF should contain clearly formatted questions\n"
        "• Each question should have multiple choice options\n"
        "• File size limit: 20MB\n\n"
        "Type /cancel to abort the import process."
    )
    
    return PDF_UPLOAD

async def pdf_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle PDF upload."""
    # Check if user sent a file
    if not update.message.document:
        await update.message.reply_text("Please send a PDF file. Type /cancel to abort.")
        return PDF_UPLOAD
    
    # Check if it's a PDF
    document = update.message.document
    file_name = document.file_name
    
    if not file_name.lower().endswith('.pdf'):
        await update.message.reply_text("This doesn't appear to be a PDF file. Please send a file with .pdf extension.")
        return PDF_UPLOAD
    
    # Store file ID in user data for later
    context.user_data['pdf_file_id'] = document.file_id
    context.user_data['pdf_file_name'] = file_name
    
    # Ask for custom ID
    keyboard = [
        [InlineKeyboardButton("Auto-assign ID", callback_data="pdf_auto_id")],
        [InlineKeyboardButton("Specify custom ID", callback_data="pdf_custom_id")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"PDF received: {file_name}\n\n"
        "Would you like to auto-assign question IDs or specify a custom starting ID?",
        reply_markup=reply_markup
    )
    
    return PDF_CUSTOM_ID

async def pdf_custom_id_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom ID selection."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "pdf_auto_id":
        # Auto-assign ID - proceed to processing
        context.user_data['custom_id'] = None
        await query.edit_message_text("Using auto-assigned question IDs.")
        
        # Start PDF processing
        return await start_pdf_processing(update, context)
    
    elif query.data == "pdf_custom_id":
        # Ask for custom ID
        await query.edit_message_text(
            "Please enter a starting ID number for the questions.\n"
            "This should be a positive integer (e.g., 100)."
        )
        return PDF_CUSTOM_ID
    
    return PDF_CUSTOM_ID

async def pdf_custom_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom ID input."""
    text = update.message.text
    
    try:
        custom_id = int(text)
        if custom_id <= 0:
            raise ValueError("ID must be positive")
        
        # Store custom ID in user data
        context.user_data['custom_id'] = custom_id
        
        await update.message.reply_text(f"Using custom starting ID: {custom_id}")
        
        # Start PDF processing
        return await start_pdf_processing(update, context)
        
    except ValueError:
        await update.message.reply_text(
            "Invalid ID. Please enter a positive number, or type /cancel to abort."
        )
        return PDF_CUSTOM_ID

async def start_pdf_processing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start processing the PDF file."""
    # Get the progress message method based on update type
    if update.callback_query:
        progress_message = await update.callback_query.message.reply_text(
            "⏳ Processing PDF file...\n\n"
            "This may take some time depending on file size and complexity."
        )
    else:
        progress_message = await update.message.reply_text(
            "⏳ Processing PDF file...\n\n"
            "This may take some time depending on file size and complexity."
        )
    
    # Get PDF file
    file_id = context.user_data.get('pdf_file_id')
    custom_id = context.user_data.get('custom_id')
    
    if not file_id:
        await progress_message.edit_text("Error: PDF file not found.")
        return ConversationHandler.END
    
    try:
        # Download the file
        file = await context.bot.get_file(file_id)
        pdf_bytes = await file.download_as_bytearray()
        
        # Update progress
        await progress_message.edit_text(
            "📄 PDF downloaded successfully.\n"
            "🔍 Extracting text and analyzing content..."
        )
        
        # Extract questions from PDF
        ocr_config = load_ocr_config()
        pdf_result = extract_questions_from_pdf(pdf_bytes, custom_id, ocr_config)
        
        # Check for errors
        if "error" in pdf_result:
            await progress_message.edit_text(f"❌ Error: {pdf_result['error']}")
            return ConversationHandler.END
        
        # Update progress
        await progress_message.edit_text(
            f"✅ Successfully extracted {pdf_result['question_count']} questions.\n"
            f"📝 Language detected: {pdf_result['language']}\n"
            "💾 Saving questions to database..."
        )
        
        # Save questions
        save_result = save_questions_from_pdf(pdf_result, custom_id)
        
        if "error" in save_result:
            await progress_message.edit_text(f"❌ Error: {save_result['error']}")
            return ConversationHandler.END
        
        # Success message
        success_message = (
            f"✅ Successfully imported {save_result['added_count']} questions!\n\n"
            f"📊 Import Summary:\n"
            f"• Questions added: {save_result['added_count']}\n"
            f"• ID range: {save_result['start_id']} - {save_result['end_id']}\n"
            f"• Language: {save_result['language']}\n\n"
            f"Use /quizid {save_result['start_id']} to start a quiz with these questions!"
        )
        
        await progress_message.edit_text(success_message)
        
        # Clear user data
        context.user_data.clear()
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        await progress_message.edit_text(f"❌ Error processing PDF: {str(e)}")
        return ConversationHandler.END

async def pdf_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show information about PDF import features."""
    # Check PDF and OCR support status
    pdf_status = "✅ Available" if PDF_SUPPORT else "❌ Not installed"
    ocr_status = "✅ Available" if OCR_SUPPORT else "❌ Not installed"
    image_status = "✅ Available" if IMAGE_SUPPORT else "❌ Not installed"
    pdf2image_status = "✅ Available" if PDF2IMAGE_SUPPORT else "❌ Not installed"
    langdetect_status = "✅ Available" if LANGDETECT_SUPPORT else "❌ Not installed"
    
    info_text = (
        "📄 PDF Import Features\n\n"
        "This bot can extract quiz questions from PDF files, including:\n"
        "• Text-based PDFs (directly extractable text)\n"
        "• Scanned PDFs (using OCR technology)\n"
        "• Multi-language PDFs (Hindi and English support)\n\n"
        
        "📊 Component Status:\n"
        f"• Basic PDF support: {pdf_status}\n"
        f"• OCR capability: {ocr_status}\n"
        f"• Image processing: {image_status}\n"
        f"• PDF to Image: {pdf2image_status}\n"
        f"• Language detection: {langdetect_status}\n\n"
        
        "📋 Import Process:\n"
        "1. Use /pdfimport to start\n"
        "2. Upload your PDF file\n"
        "3. Choose ID assignment method\n"
        "4. Wait for processing to complete\n\n"
        
        "⚙️ Configuration:\n"
        "• Use /ocrconfig to adjust OCR settings\n"
        "• Configure language, page limits, etc.\n\n"
        
        "For best results, use PDFs with:\n"
        "• Clearly formatted questions and options\n"
        "• Standard fonts and layouts\n"
        "• Limited page count (processing is CPU-intensive)"
    )
    
    await update.message.reply_text(info_text)

async def cancel_pdf_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel PDF import process."""
    await update.message.reply_text("PDF import process cancelled.")
    context.user_data.clear()
    return ConversationHandler.END

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", extended_stats_command))
    application.add_handler(CommandHandler("resetpenalty", reset_penalty_command))
    application.add_handler(CommandHandler("pdfinfo", pdf_info_command))
    
    # Negative marking settings
    application.add_handler(CommandHandler("negmark", negative_marking_settings))
    application.add_handler(CallbackQueryHandler(
        negative_marking_callback, 
        pattern=r"^neg_mark_"
    ))
    
    # OCR configuration conversation handler
    ocr_config_handler = ConversationHandler(
        entry_points=[CommandHandler("ocrconfig", ocr_config_command)],
        states={
            OCR_CONFIG: [
                CallbackQueryHandler(ocr_config_callback)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_ocr_config)]
    )
    application.add_handler(ocr_config_handler)
    
    # PDF import conversation handler
    pdf_import_handler = ConversationHandler(
        entry_points=[CommandHandler("pdfimport", pdf_import_start)],
        states={
            PDF_UPLOAD: [MessageHandler(filters.ATTACHMENT, pdf_upload_handler)],
            PDF_CUSTOM_ID: [
                CallbackQueryHandler(pdf_custom_id_callback, pattern=r"^pdf_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, pdf_custom_id_input)
            ],
            PDF_PROCESSING: []  # Processing is handled in callback
        },
        fallbacks=[CommandHandler("cancel", cancel_pdf_import)]
    )
    application.add_handler(pdf_import_handler)
    
    # Start the Bot
    application.run_polling()

if __name__ == "__main__":
    main()
