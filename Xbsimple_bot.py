# OCR + PDF Text Extraction + Block-Level Deduplication
import os
import re

# Handle imports with try-except to avoid crashes
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
    # Setup Tesseract path
    pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"
    os.environ['TESSDATA_PREFIX'] = "/usr/share/tesseract-ocr/5/tessdata"
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

def extract_text_from_pdf(file_path):
    """Extract text from a PDF file using multiple methods with fallbacks"""
    # Try with pdfplumber first if available
    if PDFPLUMBER_AVAILABLE:
        try:
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

    # Fallback to PyMuPDF if available
    if PYMUPDF_AVAILABLE:
        try:
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

    # Final fallback: OCR with Tesseract if available
    if PYMUPDF_AVAILABLE and PIL_AVAILABLE and TESSERACT_AVAILABLE:
        try:
            text = ""
            doc = fitz.open(file_path)
            for page in doc:
                pix = page.get_pixmap(dpi=300)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                t = pytesseract.image_to_string(img, lang='hin')
                if t:
                    text += t + "\n"
            return text.splitlines()
        except Exception as e:
            print("Tesseract OCR failed:", e)
    
    # If nothing worked or no extractors available, return empty
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
Enhanced Telegram Quiz Bot with PDF Import, Hindi Support, Advanced Negative Marking & PDF Results
- Based on the original multi_id_quiz_bot.py
- Added advanced negative marking features with customizable values per quiz
- Added PDF import with automatic question extraction
- Added Hindi language support for PDFs
- Added automatic PDF result generation with professional design and INSANE watermark
"""

# Import libraries for PDF generation
try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# Constants for PDF Results
PDF_RESULTS_DIR = "pdf_results"

def ensure_pdf_directory():
    """Ensure the PDF results directory exists and is writable"""
    global PDF_RESULTS_DIR
    
    # Try the default directory
    try:
        # Always set to a known location first
        PDF_RESULTS_DIR = os.path.join(os.getcwd(), "pdf_results")
        os.makedirs(PDF_RESULTS_DIR, exist_ok=True)
        
        # Test write permissions with a small test file
        test_file = os.path.join(PDF_RESULTS_DIR, "test_write.txt")
        with open(test_file, 'w') as f:
            f.write("Test write access")
        # If we get here, the directory is writable
        os.remove(test_file)
        logger.info(f"PDF directory verified and writable: {PDF_RESULTS_DIR}")
        return True
    except Exception as e:
        logger.error(f"Error setting up PDF directory: {e}")
        # If the first attempt failed, try a temporary directory
        try:
            PDF_RESULTS_DIR = os.path.join(os.getcwd(), "temp")
            os.makedirs(PDF_RESULTS_DIR, exist_ok=True)
            logger.info(f"Using alternative PDF directory: {PDF_RESULTS_DIR}")
            return True
        except Exception as e2:
            logger.error(f"Failed to create alternative PDF directory: {e2}")
            # Last resort - use current directory
            PDF_RESULTS_DIR = "."
            logger.info(f"Using current directory for PDF files")
            return False

# Try to set up the PDF directory at startup
try:
    os.makedirs(PDF_RESULTS_DIR, exist_ok=True)
except Exception:
    # If we can't create it now, we'll try again later in ensure_pdf_directory
    pass

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
import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler, PollAnswerHandler

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment variable
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7631768276:AAEUjV-iVGb1_6ZFWxF_VJH4hwsv6yBF4BI")

# Conversation states
QUESTION, OPTIONS, ANSWER, CATEGORY = range(4)
EDIT_SELECT, EDIT_QUESTION, EDIT_OPTIONS = range(4, 7)
CLONE_URL, CLONE_MANUAL = range(7, 9)
CUSTOM_ID = range(9, 10)

# PDF import conversation states (use high numbers to avoid conflicts)
PDF_UPLOAD, PDF_CUSTOM_ID, PDF_PROCESSING = range(100, 103)

# TXT import conversation states (use even higher numbers)
TXT_UPLOAD, TXT_CUSTOM_ID, TXT_PROCESSING = range(200, 203)

# Data files
QUESTIONS_FILE = "questions.json"
USERS_FILE = "users.json"
TEMP_DIR = "temp"

# Create temp directory if it doesn't exist
os.makedirs(TEMP_DIR, exist_ok=True)

# Create PDF Results directory
PDF_RESULTS_DIR = "pdf_results"
os.makedirs(PDF_RESULTS_DIR, exist_ok=True)

# Store quiz results for PDF generation
QUIZ_RESULTS_FILE = "quiz_results.json"
PARTICIPANTS_FILE = "participants.json"

# ---------- ENHANCED NEGATIVE MARKING ADDITIONS ----------
# Negative marking configuration
NEGATIVE_MARKING_ENABLED = True
DEFAULT_PENALTY = 0.25  # Default penalty for incorrect answers (0.25 points)
MAX_PENALTY = 1.0       # Maximum penalty for incorrect answers (1.0 points)
MIN_PENALTY = 0.0       # Minimum penalty for incorrect answers (0.0 points)

# Predefined negative marking options for selection
NEGATIVE_MARKING_OPTIONS = [
    ("None", 0.0),
    ("0.24", 0.24),
    ("0.33", 0.33),
    ("0.50", 0.50),
    ("1.00", 1.0)
]

# Advanced negative marking options with more choices
ADVANCED_NEGATIVE_MARKING_OPTIONS = [
    ("None", 0.0),
    ("Light (0.24)", 0.24),
    ("Moderate (0.33)", 0.33),
    ("Standard (0.50)", 0.50),
    ("Strict (0.75)", 0.75),
    ("Full (1.00)", 1.0),
    ("Extra Strict (1.25)", 1.25),
    ("Competitive (1.50)", 1.5),
    ("Custom", "custom")
]

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

# New file to store quiz-specific negative marking values
QUIZ_PENALTIES_FILE = "quiz_penalties.json"

def load_quiz_penalties():
    """Load quiz-specific penalties from file"""
    try:
        if os.path.exists(QUIZ_PENALTIES_FILE):
            with open(QUIZ_PENALTIES_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading quiz penalties: {e}")
        return {}

def save_quiz_penalties(penalties):
    """Save quiz-specific penalties to file"""
    try:
        with open(QUIZ_PENALTIES_FILE, 'w') as f:
            json.dump(penalties, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving quiz penalties: {e}")
        return False

def get_quiz_penalty(quiz_id):
    """Get negative marking value for a specific quiz ID"""
    penalties = load_quiz_penalties()
    return penalties.get(str(quiz_id), DEFAULT_PENALTY)

def set_quiz_penalty(quiz_id, penalty_value):
    """Set negative marking value for a specific quiz ID"""
    penalties = load_quiz_penalties()
    penalties[str(quiz_id)] = float(penalty_value)
    return save_quiz_penalties(penalties)

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
        penalties[user_id_str] = 0.0
    
    # Convert the penalty value to float and add it
    penalty_float = float(penalty_value)
    penalties[user_id_str] = float(penalties[user_id_str]) + penalty_float
    
    # Save updated penalties
    save_penalties(penalties)
    return penalties[user_id_str]

def get_penalty_for_quiz_or_category(quiz_id, category=None):
    """Get the penalty value for a specific quiz or category"""
    # Return 0 if negative marking is disabled
    if not NEGATIVE_MARKING_ENABLED:
        return 0
    
    # First check if there's a quiz-specific penalty
    quiz_penalties = load_quiz_penalties()
    if str(quiz_id) in quiz_penalties:
        return quiz_penalties[str(quiz_id)]
    
    # Fallback to category-specific penalty
    if category:
        penalty = CATEGORY_PENALTIES.get(category, DEFAULT_PENALTY)
    else:
        penalty = DEFAULT_PENALTY
    
    # Ensure penalty is within allowed range
    return max(MIN_PENALTY, min(MAX_PENALTY, penalty))

def apply_penalty(user_id, quiz_id=None, category=None):
    """Apply penalty to a user for an incorrect answer"""
    penalty = get_penalty_for_quiz_or_category(quiz_id, category)
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
        adjusted_score = raw_score - penalty
        
        # Format penalty as a string with up to 2 decimal places (no trailing zeros)
        formatted_penalty = f"{penalty:.2f}".rstrip("0").rstrip(".") if penalty else "0"
        
        # Format adjusted score with up to 2 decimal places (no trailing zeros)
        formatted_score = f"{adjusted_score:.2f}".rstrip("0").rstrip(".") if adjusted_score else "0"
        
        # Return extended statistics
        return {
            **user_data,
            "incorrect_answers": incorrect,
            "penalty": penalty,
            "formatted_penalty": formatted_penalty,
            "adjusted_score": adjusted_score,
            "formatted_score": formatted_score
        }
    except Exception as e:
        logger.error(f"Error getting extended user stats: {e}")
        return {}

def load_questions():
    """Load questions from file"""
    try:
        if os.path.exists(QUESTIONS_FILE):
            with open(QUESTIONS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading questions: {e}")
        return {}

def save_questions(questions):
    """Save questions to file"""
    try:
        with open(QUESTIONS_FILE, 'w') as f:
            json.dump(questions, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving questions: {e}")
        return False

def get_question_data(question_id):
    """Get data for a specific question"""
    questions = load_questions()
    return questions.get(str(question_id))

def add_question_data(question_id, question_data):
    """Add question data to the questions file"""
    questions = load_questions()
    questions[str(question_id)] = question_data
    return save_questions(questions)

def remove_question_data(question_id):
    """Remove question data from the questions file"""
    questions = load_questions()
    if str(question_id) in questions:
        del questions[str(question_id)]
        return save_questions(questions)
    return False

def load_quiz_results():
    """Load quiz results from file"""
    try:
        if os.path.exists(QUIZ_RESULTS_FILE):
            with open(QUIZ_RESULTS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading quiz results: {e}")
        return {}

def save_quiz_results(results):
    """Save quiz results to file"""
    try:
        with open(QUIZ_RESULTS_FILE, 'w') as f:
            json.dump(results, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving quiz results: {e}")
        return False

def load_participants():
    """Load participants data from file"""
    try:
        if os.path.exists(PARTICIPANTS_FILE):
            with open(PARTICIPANTS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading participants: {e}")
        return {}

def save_participants(participants):
    """Save participants data to file"""
    try:
        with open(PARTICIPANTS_FILE, 'w') as f:
            json.dump(participants, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving participants: {e}")
        return False

def load_users():
    """Load users from file"""
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading users: {e}")
        return {}

def save_users(users):
    """Save users to file"""
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving users: {e}")
        return False

def get_user_data(user_id):
    """Get data for a specific user"""
    users = load_users()
    user_id_str = str(user_id)
    if user_id_str not in users:
        users[user_id_str] = {
            "correct_answers": 0,
            "total_answers": 0,
            "categories": {}
        }
        save_users(users)
    return users.get(user_id_str, {})

def update_user_data(user_id, is_correct, category=None):
    """Update user data when they answer a question"""
    users = load_users()
    user_id_str = str(user_id)
    
    # Initialize user data if not exists
    if user_id_str not in users:
        users[user_id_str] = {
            "correct_answers": 0,
            "total_answers": 0,
            "categories": {}
        }
    
    # Update total answers
    users[user_id_str]["total_answers"] = users[user_id_str].get("total_answers", 0) + 1
    
    # Update correct answers if applicable
    if is_correct:
        users[user_id_str]["correct_answers"] = users[user_id_str].get("correct_answers", 0) + 1
    
    # Update category statistics if available
    if category:
        if "categories" not in users[user_id_str]:
            users[user_id_str]["categories"] = {}
        
        if category not in users[user_id_str]["categories"]:
            users[user_id_str]["categories"][category] = {
                "correct": 0,
                "total": 0
            }
        
        users[user_id_str]["categories"][category]["total"] = users[user_id_str]["categories"][category].get("total", 0) + 1
        
        if is_correct:
            users[user_id_str]["categories"][category]["correct"] = users[user_id_str]["categories"][category].get("correct", 0) + 1
    
    # Save updated users data
    save_users(users)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    user_id = update.effective_user.id
    username = update.effective_user.username or "User"
    
    # Set up user data if first time
    get_user_data(user_id)
    
    help_text = (
        f"Hello {username}! I'm a quiz bot.\n\n"
        "Commands:\n"
        "/add - Add a new question\n"
        "/quiz - Start a quiz with random questions\n"
        "/quiz_id [id] - Start a specific quiz by ID\n"
        "/stats - View your quiz statistics\n"
        "/edit - Edit a question\n"
        "/delete [id] - Delete a question\n"
        "/questions - List all questions\n"
        "/clone - Clone questions from another instance\n"
        "/import_pdf - Import questions from a PDF file\n"
        "/import_txt - Import questions from a text file\n"
        "/poll2q - Convert a poll to a question\n"
    )
    
    await update.message.reply_text(help_text)

async def add_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the /add command."""
    user_id = update.effective_user.id
    
    # Reset conversation data
    context.user_data.clear()
    context.user_data["adding_question"] = True
    
    # Ask if they want to use a custom ID or auto-generate
    keyboard = [
        [InlineKeyboardButton("Auto-generate ID", callback_data="auto_id")],
        [InlineKeyboardButton("Enter custom ID", callback_data="custom_id")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Do you want to use a custom ID for this question or auto-generate one?",
        reply_markup=reply_markup
    )
    
    return QUESTION

async def handle_id_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the selection of ID generation method."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "auto_id":
        # Auto-generate ID
        context.user_data["question_id"] = str(random.randint(10000, 99999))
        await query.edit_message_text(text="Enter the question text:")
        return QUESTION
    elif query.data == "custom_id":
        # Ask for custom ID
        await query.edit_message_text(text="Enter a custom ID for this question:")
        context.user_data["awaiting_custom_id"] = True
        return CUSTOM_ID
    
    return ConversationHandler.END

async def handle_custom_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the custom ID input."""
    custom_id = update.message.text.strip()
    
    # Validate custom ID (only allow alphanumeric characters)
    if not re.match(r'^[a-zA-Z0-9_-]+$', custom_id):
        await update.message.reply_text(
            "Invalid ID format. Please use only letters, numbers, underscores, and hyphens."
        )
        return CUSTOM_ID
    
    # Check if ID already exists
    questions = load_questions()
    if custom_id in questions:
        await update.message.reply_text(
            "This ID already exists. Please choose a different one:"
        )
        return CUSTOM_ID
    
    # Save the custom ID
    context.user_data["question_id"] = custom_id
    
    # Prompt for question text
    await update.message.reply_text("Enter the question text:")
    
    return QUESTION

async def question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle question text input."""
    # This function now only handles question text input, not custom ID
    question_text = update.message.text.strip()
    
    # Save the question text
    context.user_data["question_text"] = question_text
    
    # Ask for options
    await update.message.reply_text(
        "Enter the options, one per line. Start with * for the correct answer."
        "\n\nExample:\n*Option 1\nOption 2\nOption 3"
    )
    
    return OPTIONS

async def options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle option list input."""
    options_text = update.message.text.strip().split('\n')
    
    if len(options_text) < 2:
        await update.message.reply_text(
            "Please provide at least 2 options. Enter the options again, "
            "one per line, with * for the correct answer."
        )
        return OPTIONS
    
    # Process options
    options = []
    correct_answer = None
    
    for i, option in enumerate(options_text):
        if option.startswith('*'):
            correct_answer = i
            option = option[1:].strip()  # Remove the * and any leading space
        options.append(option)
    
    if correct_answer is None:
        await update.message.reply_text(
            "No correct answer marked with *. Please enter the options again, "
            "and mark the correct answer with *."
        )
        return OPTIONS
    
    context.user_data["options"] = options
    context.user_data["correct_answer"] = correct_answer
    
    # Get the categories
    all_questions = load_questions()
    categories = set()
    
    for q_id, q_data in all_questions.items():
        if "category" in q_data:
            categories.add(q_data["category"])
    
    # Prepare category selection keyboard
    keyboard = []
    for category in sorted(categories):
        keyboard.append([InlineKeyboardButton(category, callback_data=f"cat:{category}")])
    
    # Add "New Category" option
    keyboard.append([InlineKeyboardButton("Add New Category", callback_data="cat:new")])
    keyboard.append([InlineKeyboardButton("No Category", callback_data="cat:none")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Select a category or add a new one:",
        reply_markup=reply_markup
    )
    
    return CATEGORY

async def category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle category selection."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cat:new":
        await query.edit_message_text(text="Enter a new category name:")
        context.user_data["awaiting_category"] = True
        return CATEGORY
    elif query.data == "cat:none":
        context.user_data["category"] = None
        return await save_new_question(update, context)
    else:
        category_name = query.data[4:]  # Remove 'cat:' prefix
        context.user_data["category"] = category_name
        return await save_new_question(update, context)

async def category_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle text input for new category."""
    if context.user_data.get("awaiting_category", False):
        category_name = update.message.text.strip()
        context.user_data["category"] = category_name
        context.user_data["awaiting_category"] = False
        return await save_new_question(update, context)
    
    return ConversationHandler.END

async def save_new_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the new question to the database."""
    question_id = context.user_data["question_id"]
    question_text = context.user_data["question_text"]
    options = context.user_data["options"]
    correct_answer = context.user_data["correct_answer"]
    category = context.user_data.get("category")
    
    # Create question data
    question_data = {
        "question": question_text,
        "options": options,
        "correct_answer": correct_answer
    }
    
    if category:
        question_data["category"] = category
    
    # Save the question
    add_question_data(question_id, question_data)
    
    # Create response message
    response = f"Question added with ID: {question_id}\n\n"
    response += f"Question: {question_text}\n\n"
    response += "Options:\n"
    
    for i, option in enumerate(options):
        if i == correct_answer:
            response += f"{i+1}. {option} ✓\n"
        else:
            response += f"{i+1}. {option}\n"
    
    if category:
        response += f"\nCategory: {category}"
    
    if isinstance(update, Update) and update.callback_query:
        await update.callback_query.edit_message_text(text=response)
    else:
        # This means we came from category_text where we have a message not a callback
        await update.message.reply_text(response)
    
    # Clear user data
    context.user_data.clear()
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current operation."""
    await update.message.reply_text("Operation cancelled.")
    context.user_data.clear()
    return ConversationHandler.END

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /quiz command."""
    all_questions = load_questions()
    
    if not all_questions:
        await update.message.reply_text("No questions available. Add some questions first!")
        return
    
    # Get a random question ID
    question_id = random.choice(list(all_questions.keys()))
    
    # Start the quiz with that ID
    await quiz_id(update, context, question_id)

async def quiz_id(update: Update, context: ContextTypes.DEFAULT_TYPE, question_id=None) -> None:
    """Handle the /quiz_id command."""
    # If question_id is not provided, try to get it from arguments
    if question_id is None:
        if not context.args:
            await update.message.reply_text("Please provide a question ID: /quiz_id [id]")
            return
        
        question_id = context.args[0]
    
    # Get the question data
    question_data = get_question_data(question_id)
    
    if not question_data:
        await update.message.reply_text(f"Question with ID {question_id} not found.")
        return
    
    # Extract question details
    question_text = question_data["question"]
    options = question_data["options"]
    correct_answer = question_data["correct_answer"]
    category = question_data.get("category", "Uncategorized")
    
    # Create the quiz message
    message = await context.bot.send_poll(
        chat_id=update.effective_chat.id,
        question=question_text,
        options=options,
        type="quiz",
        correct_option_id=correct_answer,
        is_anonymous=False,
        explanation=f"Question ID: {question_id}",
        explanation_parse_mode="Markdown"
    )
    
    # Store the poll
    poll_id = message.poll.id
    
    # Create or load quiz results
    results = load_quiz_results()
    if poll_id not in results:
        results[poll_id] = {
            "question_id": question_id,
            "category": category,
            "participants": {}
        }
        save_quiz_results(results)
    
    # Create or load participants data
    participants = load_participants()
    if poll_id not in participants:
        participants[poll_id] = {}
    save_participants(participants)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /stats command."""
    user_id = update.effective_user.id
    username = update.effective_user.username or "User"
    
    # Get extended user stats including penalties
    extended_stats = get_extended_user_stats(user_id)
    
    if not extended_stats:
        await update.message.reply_text(f"No statistics available for {username}.")
        return
    
    # Extract statistics
    total_answers = extended_stats.get("total_answers", 0)
    correct_answers = extended_stats.get("correct_answers", 0)
    incorrect_answers = extended_stats.get("incorrect_answers", 0)
    penalty = extended_stats.get("formatted_penalty", "0")
    adjusted_score = extended_stats.get("formatted_score", "0")
    
    # Calculate percentages
    percentage = 0
    if total_answers > 0:
        percentage = (correct_answers / total_answers) * 100
    
    # Prepare the response
    response = f"📊 Statistics for {username} 📊\n\n"
    response += f"Total questions answered: {total_answers}\n"
    response += f"Correct answers: {correct_answers} ({percentage:.1f}%)\n"
    response += f"Incorrect answers: {incorrect_answers}\n"
    
    # Show negative marking details if penalties exist
    if float(penalty) > 0:
        response += f"Negative marking penalty: {penalty}\n"
        response += f"Adjusted score: {adjusted_score}\n"
    
    # Add category statistics if available
    categories = extended_stats.get("categories", {})
    if categories:
        response += "\nCategory Statistics:\n"
        for category, cat_stats in categories.items():
            cat_total = cat_stats.get("total", 0)
            cat_correct = cat_stats.get("correct", 0)
            cat_percentage = 0
            if cat_total > 0:
                cat_percentage = (cat_correct / cat_total) * 100
            response += f"- {category}: {cat_correct}/{cat_total} ({cat_percentage:.1f}%)\n"
    
    await update.message.reply_text(response)

async def edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the /edit command."""
    all_questions = load_questions()
    
    if not all_questions:
        await update.message.reply_text("No questions available to edit.")
        return ConversationHandler.END
    
    # Check if an ID was provided
    if context.args:
        question_id = context.args[0]
        question_data = get_question_data(question_id)
        
        if not question_data:
            await update.message.reply_text(f"Question with ID {question_id} not found.")
            return ConversationHandler.END
        
        context.user_data["edit_id"] = question_id
        context.user_data["edit_data"] = question_data
        
        # Show the question and ask what to edit
        await show_edit_options(update, context)
        return EDIT_SELECT
    
    # If no ID provided, list the questions
    questions_list = "Select a question to edit:\n\n"
    
    for q_id, q_data in all_questions.items():
        # Truncate question text if too long
        q_text = q_data["question"]
        if len(q_text) > 50:
            q_text = q_text[:47] + "..."
        
        questions_list += f"/edit {q_id} - {q_text}\n\n"
    
    await update.message.reply_text(questions_list)
    return ConversationHandler.END

async def show_edit_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the edit options for a question."""
    question_id = context.user_data["edit_id"]
    question_data = context.user_data["edit_data"]
    
    # Format the current question
    message = f"Editing Question ID: {question_id}\n\n"
    message += f"Question: {question_data['question']}\n\n"
    message += "Options:\n"
    
    for i, option in enumerate(question_data["options"]):
        if i == question_data["correct_answer"]:
            message += f"{i+1}. {option} ✓\n"
        else:
            message += f"{i+1}. {option}\n"
    
    if "category" in question_data:
        message += f"\nCategory: {question_data['category']}"
    
    # Create the keyboard with edit options
    keyboard = [
        [InlineKeyboardButton("Edit Question Text", callback_data="edit_question")],
        [InlineKeyboardButton("Edit Options", callback_data="edit_options")],
        [InlineKeyboardButton("Cancel", callback_data="cancel_edit")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=message,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            text=message,
            reply_markup=reply_markup
        )

async def handle_edit_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the selection of what to edit."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "edit_question":
        await query.edit_message_text(text="Enter the new question text:")
        return EDIT_QUESTION
    elif query.data == "edit_options":
        await query.edit_message_text(
            text="Enter the new options, one per line. Start with * for the correct answer.\n"
                "Example:\n"
                "Option 1\n"
                "*Option 2 (correct)\n"
                "Option 3"
        )
        return EDIT_OPTIONS
    elif query.data == "cancel_edit":
        await query.edit_message_text(text="Edit cancelled.")
        context.user_data.clear()
        return ConversationHandler.END
    
    return EDIT_SELECT

async def edit_question_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle editing the question text."""
    question_id = context.user_data["edit_id"]
    question_data = context.user_data["edit_data"]
    
    # Update the question text
    question_data["question"] = update.message.text
    
    # Save the updated question
    add_question_data(question_id, question_data)
    
    await update.message.reply_text(f"Question text updated for ID: {question_id}")
    
    # Clear user data
    context.user_data.clear()
    
    return ConversationHandler.END

async def edit_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle editing the options."""
    question_id = context.user_data["edit_id"]
    question_data = context.user_data["edit_data"]
    
    options_text = update.message.text.strip().split('\n')
    
    if len(options_text) < 2:
        await update.message.reply_text(
            "Please provide at least 2 options. Enter the options again, "
            "one per line, with * for the correct answer."
        )
        return EDIT_OPTIONS
    
    # Process options
    options = []
    correct_answer = None
    
    for i, option in enumerate(options_text):
        if option.startswith('*'):
            correct_answer = i
            option = option[1:].strip()  # Remove the * and any leading space
        options.append(option)
    
    if correct_answer is None:
        await update.message.reply_text(
            "No correct answer marked with *. Please enter the options again, "
            "and mark the correct answer with *."
        )
        return EDIT_OPTIONS
    
    # Update the options and correct answer
    question_data["options"] = options
    question_data["correct_answer"] = correct_answer
    
    # Save the updated question
    add_question_data(question_id, question_data)
    
    await update.message.reply_text(f"Options updated for question ID: {question_id}")
    
    # Clear user data
    context.user_data.clear()
    
    return ConversationHandler.END

async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /delete command."""
    if not context.args:
        await update.message.reply_text("Please provide a question ID: /delete [id]")
        return
    
    question_id = context.args[0]
    
    # Check if the question exists
    question_data = get_question_data(question_id)
    
    if not question_data:
        await update.message.reply_text(f"Question with ID {question_id} not found.")
        return
    
    # Delete the question
    remove_question_data(question_id)
    
    await update.message.reply_text(f"Question with ID {question_id} deleted.")

async def list_questions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /questions command."""
    all_questions = load_questions()
    
    if not all_questions:
        await update.message.reply_text("No questions available.")
        return
    
    # Sort questions by ID
    sorted_questions = sorted(all_questions.items(), key=lambda x: x[0])
    
    # Create a paginated list to avoid message too long errors
    page_size = 10
    total_questions = len(sorted_questions)
    
    # Get page number from args if provided
    page = 1
    if context.args and context.args[0].isdigit():
        page = int(context.args[0])
    
    # Calculate total pages
    total_pages = (total_questions + page_size - 1) // page_size
    
    # Ensure page is within valid range
    page = max(1, min(page, total_pages))
    
    # Calculate start and end indices
    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, total_questions)
    
    # Create the question list
    questions_list = f"📝 Questions List (Page {page}/{total_pages}):\n\n"
    
    for i in range(start_idx, end_idx):
        q_id, q_data = sorted_questions[i]
        
        # Truncate question text if too long
        q_text = q_data["question"]
        if len(q_text) > 50:
            q_text = q_text[:47] + "..."
        
        # Add category if available
        category = f" [{q_data.get('category', 'Uncategorized')}]"
        
        questions_list += f"{q_id}{category}: {q_text}\n\n"
    
    # Add navigation buttons
    if total_pages > 1:
        questions_list += f"Use /questions {page-1} for previous page\n" if page > 1 else ""
        questions_list += f"Use /questions {page+1} for next page\n" if page < total_pages else ""
    
    questions_list += f"\nTotal questions: {total_questions}"
    
    await update.message.reply_text(questions_list)

# PDF Import functionality
async def import_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the PDF import process."""
    # Reset user data
    context.user_data.clear()
    
    # Check if PDF support is enabled
    if not PDF_SUPPORT:
        await update.message.reply_text(
            "PDF import is not available. Missing required libraries."
        )
        return ConversationHandler.END
    
    # Ask if they want to use a custom ID or auto-generate
    keyboard = [
        [InlineKeyboardButton("Auto-generate ID", callback_data="pdf_auto_id")],
        [InlineKeyboardButton("Enter custom ID", callback_data="pdf_custom_id")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Do you want to use a custom ID for the imported questions or auto-generate IDs?",
        reply_markup=reply_markup
    )
    
    return PDF_UPLOAD

async def handle_pdf_id_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the selection of ID generation method for PDF import."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "pdf_auto_id":
        # Auto-generate ID
        context.user_data["pdf_auto_id"] = True
        await query.edit_message_text(text="Please upload the PDF file:")
        return PDF_UPLOAD
    elif query.data == "pdf_custom_id":
        # Ask for custom ID prefix
        await query.edit_message_text(text="Enter a custom ID prefix for the imported questions:")
        context.user_data["pdf_auto_id"] = False
        return PDF_CUSTOM_ID
    
    return ConversationHandler.END

async def handle_pdf_custom_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the custom ID prefix for PDF import."""
    custom_id_prefix = update.message.text.strip()
    
    # Validate custom ID prefix (only allow alphanumeric characters and some special ones)
    if not re.match(r'^[a-zA-Z0-9_-]+$', custom_id_prefix):
        await update.message.reply_text(
            "Invalid ID format. Please use only letters, numbers, underscores, and hyphens."
        )
        return PDF_CUSTOM_ID
    
    # Save the custom ID prefix
    context.user_data["pdf_id_prefix"] = custom_id_prefix
    
    # Ask for PDF upload
    await update.message.reply_text("Please upload the PDF file:")
    
    return PDF_UPLOAD

async def process_pdf_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the uploaded PDF file."""
    if not update.message.document:
        await update.message.reply_text("Please upload a PDF file.")
        return PDF_UPLOAD
    
    # Check file format
    file = update.message.document
    if not file.file_name.lower().endswith('.pdf'):
        await update.message.reply_text("Please upload a PDF file (*.pdf).")
        return PDF_UPLOAD
    
    # Download the file
    file_id = file.file_id
    new_file = await context.bot.get_file(file_id)
    
    # Create temp directory if it doesn't exist
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    # Save the file
    file_path = os.path.join(TEMP_DIR, f"{file_id}.pdf")
    await new_file.download_to_drive(file_path)
    
    # Send processing message
    processing_message = await update.message.reply_text("Processing PDF, please wait...")
    
    # Process the PDF
    context.user_data["pdf_file_path"] = file_path
    
    try:
        # Extract text from PDF
        text_lines = extract_text_from_pdf(file_path)
        
        # Apply deduplication and grouping
        if text_lines:
            text_lines = group_and_deduplicate_questions(text_lines)
        
        # Get question count
        question_count = 0
        for line in text_lines:
            if re.match(r'^Q[\.:\d]', line.strip(), re.IGNORECASE):
                question_count += 1
        
        # Store the extracted text
        context.user_data["pdf_text_lines"] = text_lines
        
        # Update processing message
        await processing_message.edit_text(
            f"PDF processed! Found approximately {question_count} potential questions.\n\n"
            "How do you want to proceed?\n\n"
            "1. Send /pdf_review to see the extracted text\n"
            "2. Send /pdf_import to import all questions\n"
            "3. Send /cancel to abort the import"
        )
        
        return PDF_PROCESSING
    
    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        await processing_message.edit_text(f"Error processing PDF: {e}")
        return ConversationHandler.END

async def review_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the extracted text from PDF."""
    if "pdf_text_lines" not in context.user_data:
        await update.message.reply_text("No PDF data to review. Please start over.")
        return
    
    text_lines = context.user_data["pdf_text_lines"]
    
    if not text_lines:
        await update.message.reply_text("No text extracted from the PDF.")
        return
    
    # Create chunks of text to avoid message too long errors
    chunk_size = 4000
    text_chunks = []
    current_chunk = ""
    
    for line in text_lines:
        if len(current_chunk) + len(line) + 1 > chunk_size:
            text_chunks.append(current_chunk)
            current_chunk = line
        else:
            if current_chunk:
                current_chunk += "\n" + line
            else:
                current_chunk = line
    
    if current_chunk:
        text_chunks.append(current_chunk)
    
    # Send chunks
    for i, chunk in enumerate(text_chunks):
        await update.message.reply_text(
            f"[Chunk {i+1}/{len(text_chunks)}]\n\n{chunk}"
        )
    
    # Remind about import options
    await update.message.reply_text(
        "You can now:\n\n"
        "1. Send /pdf_import to import all questions\n"
        "2. Send /cancel to abort the import"
    )

async def import_pdf_questions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Import questions from the processed PDF."""
    if "pdf_text_lines" not in context.user_data:
        await update.message.reply_text("No PDF data to import. Please start over.")
        return ConversationHandler.END
    
    text_lines = context.user_data["pdf_text_lines"]
    
    if not text_lines:
        await update.message.reply_text("No text extracted from the PDF.")
        return ConversationHandler.END
    
    # Process the text and extract questions
    import_message = await update.message.reply_text("Importing questions, please wait...")
    
    # Initialize counter
    imported_count = 0
    
    # Get the ID prefix or generate random ones
    if context.user_data.get("pdf_auto_id", True):
        # Auto-generate IDs
        id_prefix = f"pdf_{random.randint(100, 999)}_"
    else:
        # Use custom ID prefix
        id_prefix = context.user_data.get("pdf_id_prefix", "pdf_") + "_"
    
    # Regex patterns for question extraction
    question_pattern = re.compile(r'^Q[\.:\d]+\s*(.*)', re.IGNORECASE)
    option_pattern = re.compile(r'^[a-dA-D][\)\.]\s*(.*)')
    correct_option_pattern = re.compile(r'^Ans[\.:]\s*([a-dA-D])', re.IGNORECASE)
    
    # Process the text lines
    current_question = None
    current_options = []
    current_correct = None
    
    for line in text_lines:
        line = line.strip()
        if not line:
            continue
        
        # Check if line is a question
        question_match = question_pattern.match(line)
        if question_match:
            # Save the previous question if it exists
            if current_question and current_options:
                # Generate ID
                question_id = f"{id_prefix}{imported_count + 1}"
                
                # Determine correct answer index
                correct_index = 0  # Default to first option if not specified
                if current_correct:
                    try:
                        correct_index = ord(current_correct.upper()) - ord('A')
                    except:
                        pass
                
                # Create question data
                question_data = {
                    "question": current_question,
                    "options": current_options,
                    "correct_answer": correct_index,
                    "category": "PDF Import"
                }
                
                # Save the question
                add_question_data(question_id, question_data)
                imported_count += 1
            
            # Start a new question
            current_question = question_match.group(1)
            current_options = []
            current_correct = None
            continue
        
        # Check if line is an option
        option_match = option_pattern.match(line)
        if option_match and current_question:
            option_text = option_match.group(1)
            current_options.append(option_text)
            continue
        
        # Check if line specifies the correct answer
        correct_match = correct_option_pattern.match(line)
        if correct_match and current_question:
            current_correct = correct_match.group(1)
            continue
        
        # If it's not a question, option, or correct answer, and we have a question,
        # assume it's part of the question text
        if current_question:
            current_question += " " + line
    
    # Save the last question if it exists
    if current_question and current_options:
        question_id = f"{id_prefix}{imported_count + 1}"
        
        # Determine correct answer index
        correct_index = 0  # Default to first option if not specified
        if current_correct:
            try:
                correct_index = ord(current_correct.upper()) - ord('A')
            except:
                pass
        
        # Create question data
        question_data = {
            "question": current_question,
            "options": current_options,
            "correct_answer": correct_index,
            "category": "PDF Import"
        }
        
        # Save the question
        add_question_data(question_id, question_data)
        imported_count += 1
    
    # Clean up temp file
    try:
        file_path = context.user_data.get("pdf_file_path")
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logger.error(f"Error cleaning up temp file: {e}")
    
    # Update import message
    await import_message.edit_text(
        f"Import completed! Imported {imported_count} questions from the PDF."
    )
    
    # Clear user data
    context.user_data.clear()
    
    return ConversationHandler.END

# TXT Import functionality
async def import_txt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the TXT import process."""
    # Reset user data
    context.user_data.clear()
    
    # Ask if they want to use a custom ID or auto-generate
    keyboard = [
        [InlineKeyboardButton("Auto-generate ID", callback_data="txt_auto_id")],
        [InlineKeyboardButton("Enter custom ID", callback_data="txt_custom_id")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Do you want to use a custom ID for the imported questions or auto-generate IDs?",
        reply_markup=reply_markup
    )
    
    return TXT_UPLOAD

async def handle_txt_id_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the selection of ID generation method for TXT import."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "txt_auto_id":
        # Auto-generate ID
        context.user_data["txt_auto_id"] = True
        await query.edit_message_text(text="Please upload the TXT file:")
        return TXT_UPLOAD
    elif query.data == "txt_custom_id":
        # Ask for custom ID prefix
        await query.edit_message_text(text="Enter a custom ID prefix for the imported questions:")
        context.user_data["txt_auto_id"] = False
        return TXT_CUSTOM_ID
    
    return ConversationHandler.END

async def handle_txt_custom_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the custom ID prefix for TXT import."""
    custom_id_prefix = update.message.text.strip()
    
    # Validate custom ID prefix (only allow alphanumeric characters and some special ones)
    if not re.match(r'^[a-zA-Z0-9_-]+$', custom_id_prefix):
        await update.message.reply_text(
            "Invalid ID format. Please use only letters, numbers, underscores, and hyphens."
        )
        return TXT_CUSTOM_ID
    
    # Save the custom ID prefix
    context.user_data["txt_id_prefix"] = custom_id_prefix
    
    # Ask for TXT upload
    await update.message.reply_text("Please upload the TXT file:")
    
    return TXT_UPLOAD

async def process_txt_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the uploaded TXT file."""
    if not update.message.document:
        await update.message.reply_text("Please upload a text file.")
        return TXT_UPLOAD
    
    # Check file format
    file = update.message.document
    if not file.file_name.lower().endswith(('.txt', '.text')):
        await update.message.reply_text("Please upload a text file (*.txt, *.text).")
        return TXT_UPLOAD
    
    # Download the file
    file_id = file.file_id
    new_file = await context.bot.get_file(file_id)
    
    # Create temp directory if it doesn't exist
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    # Save the file
    file_path = os.path.join(TEMP_DIR, f"{file_id}.txt")
    await new_file.download_to_drive(file_path)
    
    # Send processing message
    processing_message = await update.message.reply_text("Processing text file, please wait...")
    
    # Process the file
    context.user_data["txt_file_path"] = file_path
    
    try:
        # Read the file
        with open(file_path, 'r', encoding='utf-8') as f:
            text_lines = f.readlines()
        
        # Apply deduplication and grouping
        if text_lines:
            text_lines = group_and_deduplicate_questions(text_lines)
        
        # Get question count
        question_count = 0
        for line in text_lines:
            if re.match(r'^Q[\.:\d]', line.strip(), re.IGNORECASE):
                question_count += 1
        
        # Store the extracted text
        context.user_data["txt_text_lines"] = text_lines
        
        # Update processing message
        await processing_message.edit_text(
            f"Text file processed! Found approximately {question_count} potential questions.\n\n"
            "How do you want to proceed?\n\n"
            "1. Send /txt_review to see the extracted text\n"
            "2. Send /txt_import to import all questions\n"
            "3. Send /cancel to abort the import"
        )
        
        return TXT_PROCESSING
    
    except Exception as e:
        logger.error(f"Error processing text file: {e}")
        await processing_message.edit_text(f"Error processing text file: {e}")
        return ConversationHandler.END

async def review_txt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the extracted text from TXT file."""
    if "txt_text_lines" not in context.user_data:
        await update.message.reply_text("No text data to review. Please start over.")
        return
    
    text_lines = context.user_data["txt_text_lines"]
    
    if not text_lines:
        await update.message.reply_text("No text extracted from the file.")
        return
    
    # Create chunks of text to avoid message too long errors
    chunk_size = 4000
    text_chunks = []
    current_chunk = ""
    
    for line in text_lines:
        if len(current_chunk) + len(line) + 1 > chunk_size:
            text_chunks.append(current_chunk)
            current_chunk = line
        else:
            if current_chunk:
                current_chunk += "\n" + line
            else:
                current_chunk = line
    
    if current_chunk:
        text_chunks.append(current_chunk)
    
    # Send chunks
    for i, chunk in enumerate(text_chunks):
        await update.message.reply_text(
            f"[Chunk {i+1}/{len(text_chunks)}]\n\n{chunk}"
        )
    
    # Remind about import options
    await update.message.reply_text(
        "You can now:\n\n"
        "1. Send /txt_import to import all questions\n"
        "2. Send /cancel to abort the import"
    )

async def import_txt_questions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Import questions from the processed TXT file."""
    if "txt_text_lines" not in context.user_data:
        await update.message.reply_text("No text data to import. Please start over.")
        return ConversationHandler.END
    
    text_lines = context.user_data["txt_text_lines"]
    
    if not text_lines:
        await update.message.reply_text("No text extracted from the file.")
        return ConversationHandler.END
    
    # Process the text and extract questions
    import_message = await update.message.reply_text("Importing questions, please wait...")
    
    # Initialize counter
    imported_count = 0
    
    # Get the ID prefix or generate random ones
    if context.user_data.get("txt_auto_id", True):
        # Auto-generate IDs
        id_prefix = f"txt_{random.randint(100, 999)}_"
    else:
        # Use custom ID prefix
        id_prefix = context.user_data.get("txt_id_prefix", "txt_") + "_"
    
    # Regex patterns for question extraction
    question_pattern = re.compile(r'^Q[\.:\d]+\s*(.*)', re.IGNORECASE)
    option_pattern = re.compile(r'^[a-dA-D][\)\.]\s*(.*)')
    correct_option_pattern = re.compile(r'^Ans[\.:]\s*([a-dA-D])', re.IGNORECASE)
    
    # Process the text lines
    current_question = None
    current_options = []
    current_correct = None
    
    for line in text_lines:
        line = line.strip()
        if not line:
            continue
        
        # Check if line is a question
        question_match = question_pattern.match(line)
        if question_match:
            # Save the previous question if it exists
            if current_question and current_options:
                # Generate ID
                question_id = f"{id_prefix}{imported_count + 1}"
                
                # Determine correct answer index
                correct_index = 0  # Default to first option if not specified
                if current_correct:
                    try:
                        correct_index = ord(current_correct.upper()) - ord('A')
                    except:
                        pass
                
                # Create question data
                question_data = {
                    "question": current_question,
                    "options": current_options,
                    "correct_answer": correct_index,
                    "category": "TXT Import"
                }
                
                # Save the question
                add_question_data(question_id, question_data)
                imported_count += 1
            
            # Start a new question
            current_question = question_match.group(1)
            current_options = []
            current_correct = None
            continue
        
        # Check if line is an option
        option_match = option_pattern.match(line)
        if option_match and current_question:
            option_text = option_match.group(1)
            current_options.append(option_text)
            continue
        
        # Check if line specifies the correct answer
        correct_match = correct_option_pattern.match(line)
        if correct_match and current_question:
            current_correct = correct_match.group(1)
            continue
        
        # If it's not a question, option, or correct answer, and we have a question,
        # assume it's part of the question text
        if current_question:
            current_question += " " + line
    
    # Save the last question if it exists
    if current_question and current_options:
        question_id = f"{id_prefix}{imported_count + 1}"
        
        # Determine correct answer index
        correct_index = 0  # Default to first option if not specified
        if current_correct:
            try:
                correct_index = ord(current_correct.upper()) - ord('A')
            except:
                pass
        
        # Create question data
        question_data = {
            "question": current_question,
            "options": current_options,
            "correct_answer": correct_index,
            "category": "TXT Import"
        }
        
        # Save the question
        add_question_data(question_id, question_data)
        imported_count += 1
    
    # Clean up temp file
    try:
        file_path = context.user_data.get("txt_file_path")
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logger.error(f"Error cleaning up temp file: {e}")
    
    # Update import message
    await import_message.edit_text(
        f"Import completed! Imported {imported_count} questions from the text file."
    )
    
    # Clear user data
    context.user_data.clear()
    
    return ConversationHandler.END

async def clone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the clone process."""
    # Reset user data
    context.user_data.clear()
    
    # Ask the user to choose cloning method
    keyboard = [
        [InlineKeyboardButton("Clone from URL", callback_data="clone_url")],
        [InlineKeyboardButton("Manual Entry", callback_data="clone_manual")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Choose how you want to clone questions:",
        reply_markup=reply_markup
    )
    
    return CLONE_URL

async def handle_clone_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the selection of cloning method."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "clone_url":
        await query.edit_message_text(
            text="Enter the URL of the quiz instance to clone from:"
        )
        return CLONE_URL
    elif query.data == "clone_manual":
        await query.edit_message_text(
            text="Enter the questions JSON data to clone:"
        )
        return CLONE_MANUAL
    
    return ConversationHandler.END

async def clone_from_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Clone questions from a URL."""
    url = update.message.text.strip()
    
    clone_message = await update.message.reply_text("Cloning questions, please wait...")
    
    try:
        import requests
        response = requests.get(f"{url}/questions.json", timeout=10)
        
        if response.status_code != 200:
            await clone_message.edit_text(f"Error: Failed to fetch questions (Status {response.status_code})")
            return ConversationHandler.END
        
        new_questions = response.json()
        
        # Get existing questions
        existing_questions = load_questions()
        
        # Count added and updated questions
        added = 0
        updated = 0
        
        # Merge questions
        for q_id, q_data in new_questions.items():
            if q_id in existing_questions:
                # Update existing question
                existing_questions[q_id] = q_data
                updated += 1
            else:
                # Add new question
                existing_questions[q_id] = q_data
                added += 1
        
        # Save the merged questions
        save_questions(existing_questions)
        
        await clone_message.edit_text(
            f"Cloning completed!\n"
            f"Added {added} new questions.\n"
            f"Updated {updated} existing questions."
        )
        
    except Exception as e:
        logger.error(f"Error cloning from URL: {e}")
        await clone_message.edit_text(f"Error cloning questions: {e}")
    
    return ConversationHandler.END

async def clone_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Clone questions from manual JSON input."""
    json_text = update.message.text.strip()
    
    clone_message = await update.message.reply_text("Processing questions, please wait...")
    
    try:
        new_questions = json.loads(json_text)
        
        if not isinstance(new_questions, dict):
            await clone_message.edit_text("Error: Invalid JSON format. Expected a dictionary.")
            return ConversationHandler.END
        
        # Get existing questions
        existing_questions = load_questions()
        
        # Count added and updated questions
        added = 0
        updated = 0
        
        # Merge questions
        for q_id, q_data in new_questions.items():
            if q_id in existing_questions:
                # Update existing question
                existing_questions[q_id] = q_data
                updated += 1
            else:
                # Add new question
                existing_questions[q_id] = q_data
                added += 1
        
        # Save the merged questions
        save_questions(existing_questions)
        
        await clone_message.edit_text(
            f"Import completed!\n"
            f"Added {added} new questions.\n"
            f"Updated {updated} existing questions."
        )
        
    except json.JSONDecodeError:
        await clone_message.edit_text("Error: Invalid JSON format.")
    except Exception as e:
        logger.error(f"Error importing manual questions: {e}")
        await clone_message.edit_text(f"Error importing questions: {e}")
    
    return ConversationHandler.END

async def poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle responses to polls."""
    answer = update.poll_answer
    poll_id = answer.poll_id
    user_id = answer.user.id
    user_name = answer.user.username or answer.user.first_name
    selected_option = answer.option_ids[0] if answer.option_ids else None
    
    # Load quiz results and participant data
    results = load_quiz_results()
    participants = load_participants()
    
    # Check if the poll is tracked
    if poll_id not in results:
        logger.info(f"Answer for untracked poll: {poll_id}")
        return
    
    # Get question data
    question_id = results[poll_id]["question_id"]
    question_data = get_question_data(question_id)
    
    if not question_data:
        logger.error(f"Question data not found for ID: {question_id}")
        return
    
    # Get correct answer
    correct_answer = question_data["correct_answer"]
    category = question_data.get("category")
    
    # Record answer for user
    if poll_id not in participants:
        participants[poll_id] = {}
    
    # Record the answer and timestamp
    participants[poll_id][str(user_id)] = {
        "user_name": user_name,
        "selected_option": selected_option,
        "timestamp": datetime.datetime.now().isoformat(),
        "is_correct": selected_option == correct_answer
    }
    
    # Save updated participants data
    save_participants(participants)
    
    # Update user statistics
    is_correct = selected_option == correct_answer
    update_user_data(user_id, is_correct, category)
    
    # Apply penalties for incorrect answers if enabled
    if not is_correct and NEGATIVE_MARKING_ENABLED:
        apply_penalty(user_id, question_id, category)

async def poll2q(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Convert a poll to a question with /poll2q command."""
    if update.message.reply_to_message and update.message.reply_to_message.poll:
        # We have a reply to a poll
        poll = update.message.reply_to_message.poll
        
        # Extract the question and options
        question_text = poll.question
        options = [option.text for option in poll.options]
        
        # Ask if they want to use a custom ID or auto-generate
        keyboard = [
            [InlineKeyboardButton("Auto-generate ID", callback_data="poll2q_auto_id")],
            [InlineKeyboardButton("Enter custom ID", callback_data="poll2q_custom_id")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Store poll data in context
        context.user_data["poll2q_question"] = question_text
        context.user_data["poll2q_options"] = options
        
        await update.message.reply_text(
            "Do you want to use a custom ID for this question or auto-generate one?",
            reply_markup=reply_markup
        )
        
        return CUSTOM_ID
    else:
        await update.message.reply_text(
            "Please reply to a poll message with the /poll2q command."
        )
        return ConversationHandler.END

async def handle_poll2q_id_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle ID selection for poll2q conversion."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "poll2q_auto_id":
        # Auto-generate ID
        question_id = str(random.randint(10000, 99999))
        context.user_data["poll2q_id"] = question_id
        
        # Ask for correct answer
        await query.edit_message_text(
            text=f"Question: {context.user_data['poll2q_question']}\n\n"
                "Options:\n" + 
                "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(context.user_data['poll2q_options'])]) +
                "\n\nEnter the number of the correct answer (1, 2, 3, etc.):"
        )
        return ANSWER
    elif query.data == "poll2q_custom_id":
        # Ask for custom ID
        await query.edit_message_text(text="Enter a custom ID for this question:")
        context.user_data["awaiting_poll2q_custom_id"] = True
        return CUSTOM_ID
    
    return ConversationHandler.END

async def handle_poll2q_custom_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom ID input for poll2q conversion."""
    custom_id = update.message.text.strip()
    
    # Validate custom ID (only allow alphanumeric characters and some special ones)
    if not re.match(r'^[a-zA-Z0-9_-]+$', custom_id):
        await update.message.reply_text(
            "Invalid ID format. Please use only letters, numbers, underscores, and hyphens."
        )
        return CUSTOM_ID
    
    # Check if ID already exists
    questions = load_questions()
    if custom_id in questions:
        await update.message.reply_text(
            "This ID already exists. Please choose a different one:"
        )
        return CUSTOM_ID
    
    # Save the custom ID
    context.user_data["poll2q_id"] = custom_id
    context.user_data["awaiting_poll2q_custom_id"] = False
    
    # Ask for correct answer
    await update.message.reply_text(
        f"Question: {context.user_data['poll2q_question']}\n\n"
        "Options:\n" + 
        "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(context.user_data['poll2q_options'])]) +
        "\n\nEnter the number of the correct answer (1, 2, 3, etc.):"
    )
    
    return ANSWER

async def poll2q_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the correct answer for poll2q."""
    try:
        answer_num = int(update.message.text.strip())
        if answer_num < 1 or answer_num > len(context.user_data["poll2q_options"]):
            await update.message.reply_text(
                f"Please enter a valid number between 1 and {len(context.user_data['poll2q_options'])}."
            )
            return ANSWER
        
        # Adjust for 0-indexing
        correct_answer = answer_num - 1
        
        # Get the question data
        question_id = context.user_data["poll2q_id"]
        question_text = context.user_data["poll2q_question"]
        options = context.user_data["poll2q_options"]
        
        # Create question data
        question_data = {
            "question": question_text,
            "options": options,
            "correct_answer": correct_answer,
            "category": "Poll Conversion"
        }
        
        # Save the question
        add_question_data(question_id, question_data)
        
        # Create response message
        response = f"Poll converted to question with ID: {question_id}\n\n"
        response += f"Question: {question_text}\n\n"
        response += "Options:\n"
        
        for i, option in enumerate(options):
            if i == correct_answer:
                response += f"{i+1}. {option} ✓\n"
            else:
                response += f"{i+1}. {option}\n"
        
        await update.message.reply_text(response)
        
        # Clear user data
        context.user_data.clear()
        
        return ConversationHandler.END
    
    except ValueError:
        await update.message.reply_text("Please enter a valid number.")
        return ANSWER

def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).build()

    # Add the handlers for various commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("quiz", quiz))
    application.add_handler(CommandHandler("quiz_id", quiz_id))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("delete", delete))
    application.add_handler(CommandHandler("questions", list_questions))

    # Handler for PollAnswers
    application.add_handler(PollAnswerHandler(poll_answer))

    # ConversationHandler for adding questions
    add_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_question)],
        states={
            QUESTION: [
                CallbackQueryHandler(handle_id_selection, pattern=r'^(auto_id|custom_id)$'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, question)
            ],
            CUSTOM_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_id)],
            OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, options)],
            CATEGORY: [
                CallbackQueryHandler(category, pattern=r'^cat:'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, category_text)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(add_conv_handler)

    # ConversationHandler for editing questions
    edit_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("edit", edit)],
        states={
            EDIT_SELECT: [CallbackQueryHandler(handle_edit_selection)],
            EDIT_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_question_text)],
            EDIT_OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_options)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(edit_conv_handler)

    # ConversationHandler for cloning questions
    clone_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("clone", clone)],
        states={
            CLONE_URL: [
                CallbackQueryHandler(handle_clone_selection, pattern=r'^clone_'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, clone_from_url)
            ],
            CLONE_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, clone_manual)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(clone_conv_handler)

    # ConversationHandler for PDF import
    pdf_import_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("import_pdf", import_pdf)],
        states={
            PDF_UPLOAD: [
                CallbackQueryHandler(handle_pdf_id_selection, pattern=r'^pdf_'),
                MessageHandler(filters.Document.ALL, process_pdf_upload)
            ],
            PDF_CUSTOM_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pdf_custom_id)],
            PDF_PROCESSING: [
                CommandHandler("pdf_review", review_pdf),
                CommandHandler("pdf_import", import_pdf_questions)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(pdf_import_conv_handler)

    # ConversationHandler for TXT import
    txt_import_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("import_txt", import_txt)],
        states={
            TXT_UPLOAD: [
                CallbackQueryHandler(handle_txt_id_selection, pattern=r'^txt_'),
                MessageHandler(filters.Document.ALL, process_txt_upload)
            ],
            TXT_CUSTOM_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_txt_custom_id)],
            TXT_PROCESSING: [
                CommandHandler("txt_review", review_txt),
                CommandHandler("txt_import", import_txt_questions)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(txt_import_conv_handler)

    # ConversationHandler for poll to question
    poll2q_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("poll2q", poll2q)],
        states={
            CUSTOM_ID: [
                CallbackQueryHandler(handle_poll2q_id_selection, pattern=r'^poll2q_'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_poll2q_custom_id)
            ],
            ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, poll2q_answer)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False
    )
    application.add_handler(poll2q_conv_handler)

    # Run the bot until the user presses Ctrl-C
    application.run_polling()

if __name__ == "__main__":
    main()
