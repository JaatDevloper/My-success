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
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7631768276:AAE3FdUFsrk9gRvcHkiCOknZ-YzDY1uHYNU")

# Conversation states
QUESTION, OPTIONS, ANSWER, CATEGORY = range(4)
EDIT_SELECT, EDIT_QUESTION, EDIT_OPTIONS = range(4, 7)
CLONE_URL, CLONE_MANUAL = range(7, 9)
CUSTOM_ID = 9  # This should be a single integer, not a range

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
        
        # Calculate penalty-adjusted score
        adjusted_score = correct - penalty
        
        # Format data for display
        stats = {}
        stats["total"] = total
        stats["correct"] = correct
        stats["incorrect"] = incorrect
        stats["penalties"] = round(penalty, 2)
        stats["adjusted_score"] = round(adjusted_score, 2)
        stats["accuracy"] = round((correct / total * 100) if total > 0 else 0, 2)
        
        return stats
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        return {
            "total": 0,
            "correct": 0,
            "incorrect": 0,
            "penalties": 0,
            "adjusted_score": 0,
            "accuracy": 0
        }
    
def format_extended_user_stats(user_id, username=None):
    """Format extended user statistics into a readable string"""
    stats = get_extended_user_stats(user_id)
    
    # Format for display
    display_name = username or f"User {user_id}"
    
    # Colorful stats display with emojis
    return (
        f"📊 Statistics for {display_name}:\n\n"
        f"📝 Total answers: {stats['total']}\n"
        f"✅ Correct answers: {stats['correct']}\n"
        f"❌ Incorrect answers: {stats['incorrect']}\n"
        f"⛔ Penalty points: {stats['penalties']}\n"
        f"🏆 Adjusted score: {stats['adjusted_score']}\n"
        f"🎯 Accuracy: {stats['accuracy']}%"
    )

def save_questions(questions):
    with open(QUESTIONS_FILE, 'w') as f:
        json.dump(questions, f, indent=4)

def load_questions():
    try:
        if os.path.exists(QUESTIONS_FILE):
            with open(QUESTIONS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except:
        return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)

def load_users():
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except:
        return {}

def save_quiz_results(results):
    try:
        with open(QUIZ_RESULTS_FILE, 'w') as f:
            json.dump(results, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving quiz results: {e}")
        return False

def load_quiz_results():
    try:
        if os.path.exists(QUIZ_RESULTS_FILE):
            with open(QUIZ_RESULTS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading quiz results: {e}")
        return {}

def save_participants(participants):
    try:
        with open(PARTICIPANTS_FILE, 'w') as f:
            json.dump(participants, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving participants: {e}")
        return False

def load_participants():
    try:
        if os.path.exists(PARTICIPANTS_FILE):
            with open(PARTICIPANTS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading participants: {e}")
        return {}

def get_user_data(user_id):
    users = load_users()
    user_id_str = str(user_id)
    if user_id_str in users:
        return users[user_id_str]
    else:
        # Initialize new user data
        users[user_id_str] = {
            "total_answers": 0,
            "correct_answers": 0,
            "quizzes_taken": []
        }
        save_users(users)
        return users[user_id_str]

def update_user_stats(user_id, is_correct, quiz_id=None):
    users = load_users()
    user_id_str = str(user_id)
    
    if user_id_str not in users:
        # Initialize new user
        users[user_id_str] = {
            "total_answers": 0,
            "correct_answers": 0,
            "quizzes_taken": []
        }
    
    # Update statistics
    users[user_id_str]["total_answers"] += 1
    if is_correct:
        users[user_id_str]["correct_answers"] += 1
    
    # Track quizzes taken
    if quiz_id and quiz_id not in users[user_id_str]["quizzes_taken"]:
        users[user_id_str]["quizzes_taken"].append(quiz_id)
    
    save_users(users)
    return users[user_id_str]

def generate_quiz_id():
    """Generate a unique quiz ID"""
    questions = load_questions()
    existing_ids = list(questions.keys())
    
    # Start with a random 5-digit number
    while True:
        new_id = str(random.randint(10000, 99999))
        if new_id not in existing_ids:
            return new_id

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    
    # Get or create user data
    user_data = get_user_data(user.id)
    
    # Create a keyboard with custom buttons
    keyboard = [
        [
            InlineKeyboardButton("❓ Create Quiz", callback_data="create_quiz"),
            InlineKeyboardButton("🎮 Take Quiz", callback_data="take_quiz")
        ],
        [
            InlineKeyboardButton("📊 My Stats", callback_data="my_stats"),
            InlineKeyboardButton("📄 Import PDF", callback_data="import_pdf")
        ],
        [
            InlineKeyboardButton("📁 Import TXT", callback_data="import_txt"),
            InlineKeyboardButton("⚙️ Settings", callback_data="settings")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send welcome message with buttons
    await update.message.reply_text(
        f"👋 Welcome to the Quiz Bot, {user.first_name}!\n\n"
        "This bot allows you to create and share quizzes with your friends. "
        "Each quiz gets a unique ID that others can use to take your quiz.\n\n"
        "What would you like to do?",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button presses"""
    query = update.callback_query
    await query.answer()
    
    # Get the callback data (button identifier)
    data = query.data
    
    if data == "create_quiz":
        await query.edit_message_text(
            "🔨 Creating a new quiz...\n\n"
            "Let's start with your first question.\n"
            "Send me the question text."
        )
        # Generate a new quiz ID
        context.user_data["quiz_id"] = generate_quiz_id()
        context.user_data["questions"] = []
        context.user_data["current_question"] = {}
        return QUESTION
    
    elif data == "take_quiz":
        await query.edit_message_text(
            "🎮 Enter the quiz ID number to take a quiz:"
        )
        return CUSTOM_ID
    
    elif data == "my_stats":
        # Display user statistics
        user_id = query.from_user.id
        stats = format_extended_user_stats(user_id, query.from_user.first_name)
        await query.edit_message_text(stats)
    
    elif data == "import_pdf":
        # Start PDF import process
        await query.edit_message_text(
            "📄 Please send me the PDF file containing your quiz questions."
        )
        return PDF_UPLOAD
    
    elif data == "import_txt":
        # Start TXT import process
        await query.edit_message_text(
            "📁 Please send me a TXT file with your quiz questions."
        )
        return TXT_UPLOAD
    
    elif data == "settings":
        # Show settings menu
        keyboard = [
            [
                InlineKeyboardButton("🔄 Reset Stats", callback_data="reset_stats"),
                InlineKeyboardButton("🔙 Back", callback_data="back_to_main")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "⚙️ Settings\n\n"
            "Choose an option:",
            reply_markup=reply_markup
        )
    
    elif data == "reset_stats":
        # Reset user statistics
        user_id = query.from_user.id
        reset_user_stats(user_id)
        reset_user_penalties(user_id)
        
        await query.edit_message_text(
            "✅ Your statistics have been reset."
        )
    
    elif data == "back_to_main":
        # Go back to main menu
        await start(update, context)
    
    return ConversationHandler.END

def reset_user_stats(user_id):
    """Reset statistics for a user"""
    users = load_users()
    user_id_str = str(user_id)
    
    if user_id_str in users:
        users[user_id_str] = {
            "total_answers": 0,
            "correct_answers": 0,
            "quizzes_taken": []
        }
        save_users(users)

async def create_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Store the question
    context.user_data["current_question"]["question"] = update.message.text
    
    await update.message.reply_text(
        "Great! Now send me the options for this question, one per line.\n"
        "Example:\n"
        "Option 1\n"
        "Option 2\n"
        "Option 3\n"
        "Option 4"
    )
    return OPTIONS

async def create_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Store the options
    options = update.message.text.splitlines()
    
    if len(options) < 2:
        await update.message.reply_text(
            "You need to provide at least 2 options. Please send the options again, one per line."
        )
        return OPTIONS
    
    context.user_data["current_question"]["options"] = options
    
    # Create inline keyboard for choosing correct answer
    keyboard = []
    for i, option in enumerate(options):
        text = f"{i+1}. {option}"
        if len(text) > 40:  # Truncate long options
            text = text[:37] + "..."
        keyboard.append([InlineKeyboardButton(text, callback_data=str(i))])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Which option is the correct answer? Choose one:",
        reply_markup=reply_markup
    )
    return ANSWER

async def create_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    # Store the correct answer
    correct_option = int(query.data)
    context.user_data["current_question"]["answer"] = correct_option
    
    # List of preset categories
    categories = ["General Knowledge", "Science", "History", "Geography", "Entertainment", "Sports", "Other"]
    
    # Create inline keyboard for choosing category
    keyboard = [[InlineKeyboardButton(cat, callback_data=cat)] for cat in categories]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Choose a category for this question:",
        reply_markup=reply_markup
    )
    return CATEGORY

async def create_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    # Store the category
    context.user_data["current_question"]["category"] = query.data
    
    # Add the completed question to the list
    context.user_data["questions"].append(context.user_data["current_question"])
    
    # Ask if want to add another question
    keyboard = [
        [
            InlineKeyboardButton("➕ Add Another Question", callback_data="add_another"),
            InlineKeyboardButton("✅ Finish Quiz", callback_data="finish_quiz")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Question added! You now have {len(context.user_data['questions'])} questions in this quiz.",
        reply_markup=reply_markup
    )
    
    # Return to QUESTION state if user wants to add another question
    return ConversationHandler.END

async def add_another_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "Let's add another question. Send me the question text."
    )
    context.user_data["current_question"] = {}
    return QUESTION

async def finish_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    quiz_id = context.user_data["quiz_id"]
    questions = context.user_data["questions"]
    
    # Save the quiz
    all_quizzes = load_questions()
    all_quizzes[quiz_id] = {
        "questions": questions,
        "created_by": query.from_user.id,
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "times_taken": 0
    }
    save_questions(all_quizzes)
    
    # Offer negative marking options
    keyboard = []
    for label, value in ADVANCED_NEGATIVE_MARKING_OPTIONS:
        if value == "custom":
            callback_data = f"penalty_custom_{quiz_id}"
        else:
            callback_data = f"penalty_{value}_{quiz_id}"
        keyboard.append([InlineKeyboardButton(label, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"✅ Quiz created successfully with ID: {quiz_id}\n\n"
        f"Do you want to enable negative marking for this quiz?\n"
        f"Select a penalty value for incorrect answers:",
        reply_markup=reply_markup
    )
    
    return ConversationHandler.END

async def set_penalty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set the negative marking penalty for a quiz"""
    query = update.callback_query
    await query.answer()
    
    # Extract penalty value and quiz ID from callback data
    # Format: penalty_VALUE_QUIZID or penalty_custom_QUIZID
    parts = query.data.split('_')
    quiz_id = parts[-1]
    
    if parts[1] == "custom":
        # Allow custom penalty value
        await query.edit_message_text(
            f"Please enter a custom penalty value for quiz {quiz_id}.\n"
            f"This should be a number between 0 and 2.0:"
        )
        context.user_data["pending_quiz_id"] = quiz_id
        return
    
    penalty = float(parts[1])
    
    # Save the penalty for this quiz
    success = set_quiz_penalty(quiz_id, penalty)
    
    if success:
        # Format the final message
        if penalty == 0:
            message = f"✅ No negative marking will be applied to quiz {quiz_id}."
        else:
            message = (
                f"✅ Negative marking set for quiz {quiz_id}.\n"
                f"Incorrect answers will be penalized by {penalty} points."
            )
        
        # Share quiz
        share_text = (
            f"📢 New Quiz Available!\n"
            f"Quiz ID: {quiz_id}\n"
            f"To take this quiz, use the /take {quiz_id} command or simply chat with the bot."
        )
        
        await query.edit_message_text(
            f"{message}\n\n"
            f"Your quiz is ready to share:\n\n"
            f"{share_text}"
        )
    else:
        await query.edit_message_text(
            f"❌ Failed to set negative marking. Please try again."
        )

async def handle_custom_penalty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle custom penalty value input"""
    try:
        # Try to convert the input to a float
        penalty = float(update.message.text)
        
        # Ensure penalty is within valid range
        if penalty < 0 or penalty > 2.0:
            await update.message.reply_text(
                "⚠️ Invalid penalty value. Please enter a number between 0 and 2.0:"
            )
            return
        
        # Get the quiz ID stored in user data
        quiz_id = context.user_data.get("pending_quiz_id")
        if not quiz_id:
            await update.message.reply_text(
                "❌ An error occurred. Please try creating your quiz again."
            )
            return
        
        # Save the penalty for this quiz
        success = set_quiz_penalty(quiz_id, penalty)
        
        if success:
            # Format the final message
            if penalty == 0:
                message = f"✅ No negative marking will be applied to quiz {quiz_id}."
            else:
                message = (
                    f"✅ Negative marking set for quiz {quiz_id}.\n"
                    f"Incorrect answers will be penalized by {penalty} points."
                )
            
            # Share quiz
            share_text = (
                f"📢 New Quiz Available!\n"
                f"Quiz ID: {quiz_id}\n"
                f"To take this quiz, use the /take {quiz_id} command or simply chat with the bot."
            )
            
            await update.message.reply_text(
                f"{message}\n\n"
                f"Your quiz is ready to share:\n\n"
                f"{share_text}"
            )
        else:
            await update.message.reply_text(
                f"❌ Failed to set negative marking. Please try again."
            )
        
        # Clear the pending quiz ID
        if "pending_quiz_id" in context.user_data:
            del context.user_data["pending_quiz_id"]
    
    except ValueError:
        await update.message.reply_text(
            "⚠️ Invalid input. Please enter a numeric value between 0 and 2.0:"
        )

async def command_take_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /take command"""
    if not context.args:
        await update.message.reply_text(
            "Please provide a quiz ID. Example: /take 12345"
        )
        return
    
    quiz_id = context.args[0]
    await take_quiz_with_id(update, context, quiz_id)

async def take_quiz_with_id(update: Update, context: ContextTypes.DEFAULT_TYPE, quiz_id: str) -> None:
    """Start a quiz with the given ID"""
    # Load all quizzes
    all_quizzes = load_questions()
    
    # Check if quiz exists
    if quiz_id not in all_quizzes:
        await update.message.reply_text(
            f"❌ Quiz with ID {quiz_id} not found. Please check the ID and try again."
        )
        return
    
    # Get quiz questions
    quiz = all_quizzes[quiz_id]
    questions = quiz["questions"]
    
    if not questions:
        await update.message.reply_text(
            f"⚠️ Quiz with ID {quiz_id} has no questions."
        )
        return
    
    # Update times taken
    quiz["times_taken"] = quiz.get("times_taken", 0) + 1
    save_questions(all_quizzes)
    
    # Get quiz creator info
    creator_id = quiz.get("created_by", "Unknown")
    creator_info = f"Created by User ID: {creator_id}"
    
    # Store the penalty value for this quiz
    penalty = get_quiz_penalty(quiz_id)
    penalty_info = f"Negative marking: {penalty} points per wrong answer" if penalty > 0 else "No negative marking"
    
    # Store quiz information in user data
    context.user_data["active_quiz"] = {
        "id": quiz_id,
        "questions": questions,
        "current_question": 0,
        "score": 0,
        "penalty": penalty,
        "start_time": datetime.datetime.now(),
        "answers": []
    }
    
    # Send quiz introduction
    await update.message.reply_text(
        f"🎮 Starting Quiz (ID: {quiz_id})\n"
        f"{creator_info}\n"
        f"{penalty_info}\n\n"
        f"This quiz has {len(questions)} questions. Let's begin!"
    )
    
    # Send the first question
    await send_quiz_question(update, context)
    
    # Add participant to the list
    participants = load_participants()
    quiz_id_str = str(quiz_id)
    user_id_str = str(update.effective_user.id)
    
    if quiz_id_str not in participants:
        participants[quiz_id_str] = []
    
    if user_id_str not in participants[quiz_id_str]:
        participants[quiz_id_str].append(user_id_str)
    
    save_participants(participants)

async def custom_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the quiz ID entry when taking a quiz"""
    quiz_id = update.message.text.strip()
    
    # Basic validation for quiz ID format
    if not re.match(r'^\d+$', quiz_id):
        await update.message.reply_text(
            "⚠️ Invalid quiz ID format. Please enter a numeric ID:"
        )
        return CUSTOM_ID
    
    await take_quiz_with_id(update, context, quiz_id)
    return ConversationHandler.END

async def send_quiz_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the current quiz question as a poll"""
    quiz_data = context.user_data.get("active_quiz", {})
    
    if not quiz_data:
        await update.message.reply_text(
            "❌ No active quiz found. Please start a new quiz with /take command."
        )
        return
    
    questions = quiz_data.get("questions", [])
    current_idx = quiz_data.get("current_question", 0)
    
    if current_idx >= len(questions):
        # Quiz is complete
        await finish_active_quiz(update, context)
        return
    
    # Get the current question
    question_data = questions[current_idx]
    question_text = question_data.get("question", "No question text")
    options = question_data.get("options", [])
    correct_option = question_data.get("answer", 0)
    
    # Create a poll with the question
    message = await context.bot.send_poll(
        chat_id=update.effective_chat.id,
        question=f"Question {current_idx + 1}/{len(questions)}: {question_text}",
        options=options,
        type="quiz",
        correct_option_id=correct_option,
        is_anonymous=False,
        explanation=None
    )
    
    # Store the poll's message_id for later reference
    context.user_data["active_quiz"]["current_poll_id"] = message.message_id
    
    # If this is the first question, explain how to answer
    if current_idx == 0:
        await update.message.reply_text(
            "👆 Select your answer above. Your responses will be tracked automatically."
        )

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a poll answer"""
    answer = update.poll_answer
    user_id = answer.user.id
    poll_id = answer.poll_id
    
    # Check if user has an active quiz
    if "active_quiz" not in context.user_data:
        return
    
    quiz_data = context.user_data["active_quiz"]
    questions = quiz_data.get("questions", [])
    current_idx = quiz_data.get("current_question", 0)
    
    if current_idx >= len(questions):
        return
    
    # Get the current question
    question_data = questions[current_idx]
    correct_option = question_data.get("answer", 0)
    
    # Check if answer is correct
    selected_option = answer.option_ids[0] if answer.option_ids else -1
    is_correct = selected_option == correct_option
    
    # Store the user's answer
    quiz_data["answers"].append({
        "question_idx": current_idx,
        "selected_option": selected_option,
        "is_correct": is_correct
    })
    
    # Update score
    if is_correct:
        quiz_data["score"] += 1
        update_user_stats(user_id, True, quiz_data["id"])
    else:
        update_user_stats(user_id, False, quiz_data["id"])
        # Apply penalty for incorrect answer
        if quiz_data.get("penalty", 0) > 0:
            category = question_data.get("category")
            apply_penalty(user_id, quiz_data["id"], category)
    
    # Move to the next question
    quiz_data["current_question"] += 1
    context.user_data["active_quiz"] = quiz_data
    
    # After a short delay, send the next question
    await asyncio.sleep(2)
    await send_quiz_question(update, context)

async def finish_active_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Complete the active quiz and show results"""
    quiz_data = context.user_data.get("active_quiz", {})
    
    if not quiz_data:
        await update.message.reply_text(
            "❌ No active quiz found."
        )
        return
    
    # Calculate quiz statistics
    questions = quiz_data.get("questions", [])
    total_questions = len(questions)
    correct_answers = quiz_data.get("score", 0)
    incorrect_answers = total_questions - correct_answers
    percentage = (correct_answers / total_questions * 100) if total_questions > 0 else 0
    
    # Get quiz completion time
    start_time = quiz_data.get("start_time", datetime.datetime.now())
    end_time = datetime.datetime.now()
    duration = end_time - start_time
    duration_str = str(duration).split('.')[0]  # Format as HH:MM:SS
    
    # Get penalty information
    penalty = quiz_data.get("penalty", 0)
    penalty_applied = 0
    
    # If negative marking was enabled, get the actual penalty applied
    if penalty > 0:
        user_id = update.effective_user.id
        user_id_str = str(user_id)
        penalties = load_penalties()
        penalty_applied = penalties.get(user_id_str, 0)
    
    # Calculate final score with penalty
    final_score = max(0, correct_answers - (penalty * incorrect_answers))
    
    # Store quiz result
    quiz_id = quiz_data.get("id")
    user_id = update.effective_user.id
    username = update.effective_user.username or f"User_{user_id}"
    
    # Determine grade based on percentage
    if percentage >= 90:
        grade = "🏆 Outstanding"
    elif percentage >= 80:
        grade = "🥇 Excellent"
    elif percentage >= 70:
        grade = "🥈 Very Good"
    elif percentage >= 60:
        grade = "🥉 Good"
    elif percentage >= 50:
        grade = "👍 Satisfactory"
    else:
        grade = "📚 Needs Improvement"
    
    # Create detailed result message
    result_message = (
        f"📋 Quiz Results (ID: {quiz_id})\n\n"
        f"📊 Score: {correct_answers}/{total_questions} ({percentage:.1f}%)\n"
        f"✅ Correct: {correct_answers}\n"
        f"❌ Incorrect: {incorrect_answers}\n"
    )
    
    # Add penalty information if applicable
    if penalty > 0:
        adjusted_percentage = (final_score / total_questions * 100) if total_questions > 0 else 0
        result_message += (
            f"⛔ Negative Marking: {penalty} per wrong answer\n"
            f"📉 Penalty Points: {incorrect_answers * penalty:.2f}\n"
            f"🏆 Final Score: {final_score:.2f}/{total_questions} ({adjusted_percentage:.1f}%)\n"
        )
    
    # Add time and grade
    result_message += (
        f"⏱️ Time Taken: {duration_str}\n"
        f"🎓 Grade: {grade}\n"
    )
    
    # Save the result
    results = load_quiz_results()
    result_id = f"{quiz_id}_{user_id}_{int(datetime.datetime.now().timestamp())}"
    
    results[result_id] = {
        "quiz_id": quiz_id,
        "user_id": user_id,
        "username": username,
        "total_questions": total_questions,
        "correct_answers": correct_answers,
        "incorrect_answers": incorrect_answers,
        "percentage": percentage,
        "penalty": penalty,
        "penalty_applied": penalty * incorrect_answers,
        "final_score": final_score,
        "duration": duration_str,
        "grade": grade,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "answers": quiz_data.get("answers", [])
    }
    
    save_quiz_results(results)
    
    # Send the results message
    await update.message.reply_text(result_message)
    
    # Offer to generate PDF result (removed HTML report option)
    keyboard = [
        [
            InlineKeyboardButton("📊 Generate PDF Report", callback_data=f"pdf_{result_id}"),
            InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Would you like to get a PDF report of your quiz results?",
        reply_markup=reply_markup
    )
    
    # Clear the active quiz
    if "active_quiz" in context.user_data:
        del context.user_data["active_quiz"]

def generate_watermark(text):
    """Generate a diagonal watermark with text"""
    if not REPORTLAB_AVAILABLE:
        return None
    
    try:
        # Create a temporary file for the watermark
        watermark_file = os.path.join(TEMP_DIR, "watermark.pdf")
        c = canvas.Canvas(watermark_file, pagesize=letter)
        
        # Set up the canvas
        width, height = letter
        c.setFont("Helvetica", 60)
        c.setFillColor(colors.Color(0, 0, 0, alpha=0.1))  # Light gray, partially transparent
        
        # Rotate and position the watermark
        c.saveState()
        c.translate(width/2, height/2)
        c.rotate(45)
        c.drawCentredString(0, 0, text)
        c.restoreState()
        
        # Repeat the watermark in a grid pattern
        c.saveState()
        c.translate(width/4, height/4)
        c.rotate(45)
        c.drawCentredString(0, 0, text)
        c.restoreState()
        
        c.saveState()
        c.translate(3*width/4, height/4)
        c.rotate(45)
        c.drawCentredString(0, 0, text)
        c.restoreState()
        
        c.saveState()
        c.translate(width/4, 3*height/4)
        c.rotate(45)
        c.drawCentredString(0, 0, text)
        c.restoreState()
        
        c.saveState()
        c.translate(3*width/4, 3*height/4)
        c.rotate(45)
        c.drawCentredString(0, 0, text)
        c.restoreState()
        
        c.save()
        return watermark_file
    
    except Exception as e:
        logger.error(f"Error generating watermark: {e}")
        return None

async def generate_pdf_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate a PDF report of quiz results"""
    query = update.callback_query
    await query.answer()
    
    # Extract result ID from callback data
    result_id = query.data.split('_', 1)[1]
    
    await query.edit_message_text(
        "⏳ Generating PDF report... Please wait."
    )
    
    # Load results
    results = load_quiz_results()
    if result_id not in results:
        await query.edit_message_text(
            "❌ Result not found. Please try taking the quiz again."
        )
        return
    
    result = results[result_id]
    
    # Ensure PDF directory exists
    ensure_pdf_directory()
    
    # Generate PDF using one of the available libraries
    if REPORTLAB_AVAILABLE:
        # Use ReportLab
        try:
            # Create unique filename with timestamp
            filename = f"quiz_{result['quiz_id']}_{result['user_id']}_{int(datetime.datetime.now().timestamp())}.pdf"
            filepath = os.path.join(PDF_RESULTS_DIR, filename)
            
            # Create watermark
            watermark_path = generate_watermark("QUIZ RESULT")
            
            # Generate PDF
            c = canvas.Canvas(filepath, pagesize=letter)
            width, height = letter
            
            # Add header
            c.setFont("Helvetica-Bold", 18)
            c.drawCentredString(width/2, height - 1*inch, "QUIZ RESULT REPORT")
            
            # Add quiz info
            c.setFont("Helvetica", 12)
            y = height - 1.5*inch
            c.drawString(1*inch, y, f"Quiz ID: {result['quiz_id']}")
            y -= 0.3*inch
            c.drawString(1*inch, y, f"User: {result['username']}")
            y -= 0.3*inch
            c.drawString(1*inch, y, f"Date: {result['timestamp']}")
            y -= 0.3*inch
            c.drawString(1*inch, y, f"Duration: {result['duration']}")
            
            # Add score info
            y -= 0.5*inch
            c.setFont("Helvetica-Bold", 14)
            c.drawString(1*inch, y, "Score Summary")
            c.setFont("Helvetica", 12)
            y -= 0.3*inch
            c.drawString(1*inch, y, f"Total Questions: {result['total_questions']}")
            y -= 0.3*inch
            c.drawString(1*inch, y, f"Correct Answers: {result['correct_answers']}")
            y -= 0.3*inch
            c.drawString(1*inch, y, f"Incorrect Answers: {result['incorrect_answers']}")
            y -= 0.3*inch
            percentage = result.get('percentage', 0)
            c.drawString(1*inch, y, f"Score Percentage: {percentage:.1f}%")
            
            # Add penalty info if applicable
            if result.get('penalty', 0) > 0:
                y -= 0.3*inch
                c.drawString(1*inch, y, f"Negative Marking: {result['penalty']} points per wrong answer")
                y -= 0.3*inch
                c.drawString(1*inch, y, f"Penalty Applied: {result['penalty_applied']:.2f} points")
                y -= 0.3*inch
                c.drawString(1*inch, y, f"Final Score: {result['final_score']:.2f}/{result['total_questions']}")
            
            # Add grade
            y -= 0.5*inch
            c.setFont("Helvetica-Bold", 16)
            c.drawString(1*inch, y, f"Grade: {result['grade']}")
            
            # Add footer
            c.setFont("Helvetica-Italic", 8)
            c.drawString(1*inch, 0.5*inch, "This report was generated automatically by Quiz Bot.")
            c.drawRightString(width - 1*inch, 0.5*inch, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            
            # Save the first page
            c.save()
            
            # Add watermark if available
            if watermark_path:
                try:
                    # Use PyPDF2 to add watermark
                    output_pdf = PyPDF2.PdfWriter()
                    
                    # Open the created PDF
                    with open(filepath, "rb") as report_file:
                        report_pdf = PyPDF2.PdfReader(report_file)
                        
                        # Get the watermark page
                        with open(watermark_path, "rb") as watermark_file:
                            watermark_pdf = PyPDF2.PdfReader(watermark_file)
                            watermark_page = watermark_pdf.pages[0]
                            
                            # Add watermark to each page
                            for page_num in range(len(report_pdf.pages)):
                                page = report_pdf.pages[page_num]
                                page.merge_page(watermark_page)
                                output_pdf.add_page(page)
                            
                            # Save the output file
                            with open(filepath, "wb") as output_file:
                                output_pdf.write(output_file)
                except Exception as e:
                    logger.error(f"Error adding watermark: {e}")
            
            # Send the PDF file
            try:
                with open(filepath, "rb") as pdf_file:
                    await context.bot.send_document(
                        chat_id=query.message.chat_id,
                        document=pdf_file,
                        filename=f"Quiz_Result_{result['quiz_id']}.pdf",
                        caption="📊 Here is your quiz result report!"
                    )
                
                # Send success message
                await query.message.reply_text(
                    "✅ PDF report generated successfully!"
                )
            except Exception as e:
                logger.error(f"Error sending PDF: {e}")
                await query.message.reply_text(
                    f"❌ Error sending PDF: {str(e)}"
                )
        
        except Exception as e:
            logger.error(f"Error generating PDF with ReportLab: {e}")
            await query.message.reply_text(
                f"❌ Error generating PDF: {str(e)}"
            )
    
    elif FPDF_AVAILABLE:
        # Use FPDF as fallback
        try:
            # Create PDF
            pdf = FPDF()
            pdf.add_page()
            
            # Set fonts
            pdf.set_font("Arial", "B", 16)
            
            # Title
            pdf.cell(190, 10, "QUIZ RESULT REPORT", 0, 1, "C")
            pdf.ln(5)
            
            # Quiz info
            pdf.set_font("Arial", "", 12)
            pdf.cell(190, 8, f"Quiz ID: {result['quiz_id']}", 0, 1)
            pdf.cell(190, 8, f"User: {result['username']}", 0, 1)
            pdf.cell(190, 8, f"Date: {result['timestamp']}", 0, 1)
            pdf.cell(190, 8, f"Duration: {result['duration']}", 0, 1)
            pdf.ln(5)
            
            # Score info
            pdf.set_font("Arial", "B", 14)
            pdf.cell(190, 10, "Score Summary", 0, 1)
            pdf.set_font("Arial", "", 12)
            pdf.cell(190, 8, f"Total Questions: {result['total_questions']}", 0, 1)
            pdf.cell(190, 8, f"Correct Answers: {result['correct_answers']}", 0, 1)
            pdf.cell(190, 8, f"Incorrect Answers: {result['incorrect_answers']}", 0, 1)
            percentage = result.get('percentage', 0)
            pdf.cell(190, 8, f"Score Percentage: {percentage:.1f}%", 0, 1)
            
            # Add penalty info if applicable
            if result.get('penalty', 0) > 0:
                pdf.cell(190, 8, f"Negative Marking: {result['penalty']} points per wrong answer", 0, 1)
                pdf.cell(190, 8, f"Penalty Applied: {result['penalty_applied']:.2f} points", 0, 1)
                pdf.cell(190, 8, f"Final Score: {result['final_score']:.2f}/{result['total_questions']}", 0, 1)
            
            # Grade
            pdf.ln(5)
            pdf.set_font("Arial", "B", 14)
            pdf.cell(190, 10, f"Grade: {result['grade']}", 0, 1)
            
            # Footer
            pdf.set_y(-15)
            pdf.set_font("Arial", "I", 8)
            pdf.cell(0, 10, "This report was generated automatically by Quiz Bot.", 0, 0, "L")
            pdf.cell(0, 10, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0, 0, "R")
            
            # Create unique filename with timestamp
            filename = f"quiz_{result['quiz_id']}_{result['user_id']}_{int(datetime.datetime.now().timestamp())}.pdf"
            filepath = os.path.join(PDF_RESULTS_DIR, filename)
            
            # Save the PDF
            pdf.output(filepath)
            
            # Send the PDF file
            try:
                with open(filepath, "rb") as pdf_file:
                    await context.bot.send_document(
                        chat_id=query.message.chat_id,
                        document=pdf_file,
                        filename=f"Quiz_Result_{result['quiz_id']}.pdf",
                        caption="📊 Here is your quiz result report!"
                    )
                
                # Send success message
                await query.message.reply_text(
                    "✅ PDF report generated successfully!"
                )
            except Exception as e:
                logger.error(f"Error sending PDF: {e}")
                await query.message.reply_text(
                    f"❌ Error sending PDF: {str(e)}"
                )
        
        except Exception as e:
            logger.error(f"Error generating PDF with FPDF: {e}")
            await query.message.reply_text(
                f"❌ Error generating PDF: {str(e)}"
            )
    
    else:
        # No PDF libraries available
        await query.message.reply_text(
            "❌ PDF generation is not available. Required libraries are not installed."
        )

async def handle_pdf_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle PDF file upload for importing questions"""
    # Check if a file was actually sent
    if not update.message.document:
        await update.message.reply_text(
            "⚠️ Please send a PDF file containing your quiz questions."
        )
        return PDF_UPLOAD
    
    document = update.message.document
    file_name = document.file_name
    
    # Check file type
    if not file_name.lower().endswith('.pdf'):
        await update.message.reply_text(
            "⚠️ Please send a PDF file (with .pdf extension)."
        )
        return PDF_UPLOAD
    
    # Get file ID and download the file
    file_id = document.file_id
    new_file = await context.bot.get_file(file_id)
    
    # Create local path for the file
    local_path = os.path.join(TEMP_DIR, f"import_{update.effective_user.id}_{int(datetime.datetime.now().timestamp())}.pdf")
    
    # Download the file
    await new_file.download_to_drive(local_path)
    
    # Store the path in user data
    context.user_data["pdf_path"] = local_path
    
    # Ask for custom ID or generate one
    keyboard = [
        [
            InlineKeyboardButton("Generate Random ID", callback_data="generate_id"),
            InlineKeyboardButton("Provide Custom ID", callback_data="custom_id")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "PDF received! Would you like to generate a random quiz ID or provide a custom one?",
        reply_markup=reply_markup
    )
    
    return PDF_CUSTOM_ID

async def handle_pdf_custom_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle quiz ID choice for PDF import"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "generate_id":
        # Generate a new quiz ID
        context.user_data["quiz_id"] = generate_quiz_id()
        
        await query.edit_message_text(
            f"Generated Quiz ID: {context.user_data['quiz_id']}\n\n"
            "⏳ Processing PDF... Please wait."
        )
        
        # Process the PDF
        return await process_pdf(update, context)
    
    elif query.data == "custom_id":
        await query.edit_message_text(
            "Please enter a custom quiz ID (numbers only):"
        )
        return PDF_CUSTOM_ID
    
    return ConversationHandler.END

async def handle_pdf_custom_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom quiz ID input for PDF import"""
    custom_id = update.message.text.strip()
    
    # Basic validation for custom ID
    if not re.match(r'^\d+$', custom_id):
        await update.message.reply_text(
            "⚠️ Invalid quiz ID format. Please enter a numeric ID:"
        )
        return PDF_CUSTOM_ID
    
    # Check if ID already exists
    questions = load_questions()
    if custom_id in questions:
        await update.message.reply_text(
            f"⚠️ Quiz ID {custom_id} already exists. Please choose a different ID:"
        )
        return PDF_CUSTOM_ID
    
    # Store the custom ID
    context.user_data["quiz_id"] = custom_id
    
    await update.message.reply_text(
        f"Using Custom Quiz ID: {custom_id}\n\n"
        "⏳ Processing PDF... Please wait."
    )
    
    # Process the PDF
    return await process_pdf(update, context)

async def process_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the uploaded PDF file to extract questions"""
    # Get the PDF path from user data
    pdf_path = context.user_data.get("pdf_path")
    
    if not pdf_path or not os.path.exists(pdf_path):
        # Send error message
        if isinstance(update.callback_query, object):
            await update.callback_query.edit_message_text(
                "❌ PDF file not found or error in upload. Please try again."
            )
        else:
            await update.message.reply_text(
                "❌ PDF file not found or error in upload. Please try again."
            )
        return ConversationHandler.END
    
    # Extract text from PDF
    pdf_text = extract_text_from_pdf(pdf_path)
    
    if not pdf_text:
        # Send error message if extraction failed
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(
                "❌ Failed to extract text from PDF. The file might be encrypted, "
                "image-based, or in an unsupported format."
            )
        else:
            await update.message.reply_text(
                "❌ Failed to extract text from PDF. The file might be encrypted, "
                "image-based, or in an unsupported format."
            )
        return ConversationHandler.END
    
    # Process the extracted text to identify questions and answers
    # This is a simple approach that assumes a specific format
    # You may need to adjust this based on your PDF format
    
    # Group and deduplicate questions
    deduplicated_lines = group_and_deduplicate_questions(pdf_text)
    
    # Parse questions and answers
    questions = []
    current_question = None
    current_options = []
    correct_answer = None
    
    for line in deduplicated_lines:
        line = line.strip()
        if not line:
            # Empty line - if we have a complete question, add it
            if current_question and current_options and correct_answer is not None:
                questions.append({
                    "question": current_question,
                    "options": current_options,
                    "answer": correct_answer,
                    "category": "Imported"
                })
                current_question = None
                current_options = []
                correct_answer = None
            continue
        
        # Check if line is a question
        if re.match(r'^Q[\.:\d]', line, re.IGNORECASE) or (not current_question and len(line) > 10):
            # If we already have a question, save it first
            if current_question and current_options and correct_answer is not None:
                questions.append({
                    "question": current_question,
                    "options": current_options,
                    "answer": correct_answer,
                    "category": "Imported"
                })
                current_options = []
                correct_answer = None
            
            # Remove Q. or Q: prefix if present
            current_question = re.sub(r'^Q[\.:\d]\s*', '', line, flags=re.IGNORECASE)
        
        # Check if line is an option (A., B., C., etc.)
        elif re.match(r'^[A-D][\.:\)]', line, re.IGNORECASE) and current_question:
            # Extract option text
            option_text = re.sub(r'^[A-D][\.:\)]\s*', '', line, flags=re.IGNORECASE)
            current_options.append(option_text)
            
            # Check if this option is marked as correct
            if "*" in line or "correct" in line.lower() or "answer" in line.lower():
                # Get the index (0-based) of this option
                correct_answer = len(current_options) - 1
        
        # Handle "Correct Answer: X" format
        elif re.match(r'^Correct\s+Answer', line, re.IGNORECASE) and current_question:
            # Try to extract the letter
            match = re.search(r'[A-D]', line, re.IGNORECASE)
            if match:
                letter = match.group(0).upper()
                # Convert letter to index (A=0, B=1, etc.)
                correct_answer = ord(letter) - ord('A')
    
    # Add the last question if we have one
    if current_question and current_options and correct_answer is not None:
        questions.append({
            "question": current_question,
            "options": current_options,
            "answer": correct_answer,
            "category": "Imported"
        })
    
    # Check if we found any valid questions
    if not questions:
        # Send error message
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(
                "❌ No valid questions found in the PDF. Make sure your questions are formatted correctly."
            )
        else:
            await update.message.reply_text(
                "❌ No valid questions found in the PDF. Make sure your questions are formatted correctly."
            )
        return ConversationHandler.END
    
    # Save the questions to the database
    quiz_id = context.user_data["quiz_id"]
    all_quizzes = load_questions()
    all_quizzes[quiz_id] = {
        "questions": questions,
        "created_by": update.effective_user.id,
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "times_taken": 0,
        "source": "pdf_import"
    }
    save_questions(all_quizzes)
    
    # Cleanup - remove the temp file
    try:
        os.remove(pdf_path)
    except:
        pass
    
    # Offer negative marking options
    keyboard = []
    for label, value in ADVANCED_NEGATIVE_MARKING_OPTIONS:
        if value == "custom":
            callback_data = f"penalty_custom_{quiz_id}"
        else:
            callback_data = f"penalty_{value}_{quiz_id}"
        keyboard.append([InlineKeyboardButton(label, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send success message
    success_message = (
        f"✅ PDF import successful!\n\n"
        f"Quiz ID: {quiz_id}\n"
        f"Questions imported: {len(questions)}\n\n"
        f"Do you want to enable negative marking for this quiz?\n"
        f"Select a penalty value for incorrect answers:"
    )
    
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text(
            success_message,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            success_message,
            reply_markup=reply_markup
        )
    
    return ConversationHandler.END

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to access advanced features"""
    user_id = update.effective_user.id
    
    # Add admin check if needed
    # if user_id != ADMIN_USER_ID:
    #     await update.message.reply_text("⛔ Admin access required.")
    #     return
    
    keyboard = [
        [
            InlineKeyboardButton("📊 User Statistics", callback_data="admin_stats"),
            InlineKeyboardButton("🧹 Clean Database", callback_data="admin_clean")
        ],
        [
            InlineKeyboardButton("🔍 View All Quizzes", callback_data="admin_quizzes"),
            InlineKeyboardButton("❌ Delete Quiz", callback_data="admin_delete")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👑 Admin Panel\n\n"
        "Select an option:",
        reply_markup=reply_markup
    )

async def handle_admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin action buttons"""
    query = update.callback_query
    await query.answer()
    
    action = query.data.split('_')[1]
    
    if action == "stats":
        # Show overall statistics
        users = load_users()
        total_users = len(users)
        
        questions = load_questions()
        total_quizzes = len(questions)
        
        total_questions = sum(len(q.get("questions", [])) for q in questions.values())
        
        # Calculate overall stats
        total_answers = sum(u.get("total_answers", 0) for u in users.values())
        correct_answers = sum(u.get("correct_answers", 0) for u in users.values())
        accuracy = (correct_answers / total_answers * 100) if total_answers > 0 else 0
        
        stats_message = (
            "📊 Overall Statistics\n\n"
            f"👥 Total Users: {total_users}\n"
            f"🧩 Total Quizzes: {total_quizzes}\n"
            f"❓ Total Questions: {total_questions}\n"
            f"📝 Total Answers: {total_answers}\n"
            f"✅ Correct Answers: {correct_answers}\n"
            f"🎯 Accuracy: {accuracy:.2f}%\n"
        )
        
        await query.edit_message_text(stats_message)
    
    elif action == "clean":
        # Clean database option
        keyboard = [
            [
                InlineKeyboardButton("🗑️ Clean Temporary Files", callback_data="clean_temp"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel_clean")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🧹 Database Cleaning Options\n\n"
            "This will remove temporary files and optimize the database.",
            reply_markup=reply_markup
        )
    
    elif action == "quizzes":
        # Show all quizzes
        questions = load_questions()
        
        if not questions:
            await query.edit_message_text(
                "No quizzes found in the database."
            )
            return
        
        # Create a summary of all quizzes
        quiz_list = "🧩 All Quizzes\n\n"
        
        for quiz_id, quiz_data in questions.items():
            quiz_questions = quiz_data.get("questions", [])
            created_by = quiz_data.get("created_by", "Unknown")
            created_at = quiz_data.get("created_at", "Unknown")
            times_taken = quiz_data.get("times_taken", 0)
            
            quiz_list += (
                f"ID: {quiz_id}\n"
                f"Questions: {len(quiz_questions)}\n"
                f"Created by: User {created_by}\n"
                f"Created on: {created_at}\n"
                f"Times taken: {times_taken}\n"
                f"-------------------\n"
            )
        
        # Send the list (may need to paginate for large lists)
        if len(quiz_list) <= 4096:
            await query.edit_message_text(quiz_list)
        else:
            # Split into smaller messages if too long
            chunks = [quiz_list[i:i+4096] for i in range(0, len(quiz_list), 4096)]
            await query.edit_message_text(chunks[0])
            
            for chunk in chunks[1:]:
                await query.message.reply_text(chunk)
    
    elif action == "delete":
        # Delete quiz option
        await query.edit_message_text(
            "❌ Delete Quiz\n\n"
            "Please enter the quiz ID you want to delete:"
        )
        # Set conversation state to handle the response
        return

async def clean_temp_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clean temporary files"""
    query = update.callback_query
    await query.answer()
    
    files_removed = 0
    
    try:
        # Clean temp directory
        for filename in os.listdir(TEMP_DIR):
            file_path = os.path.join(TEMP_DIR, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
                files_removed += 1
    except Exception as e:
        await query.edit_message_text(
            f"❌ Error cleaning temporary files: {str(e)}"
        )
        return
    
    await query.edit_message_text(
        f"✅ Cleanup completed!\n"
        f"{files_removed} temporary files removed."
    )

async def cancel_clean(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel cleanup operation"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "❌ Cleanup operation cancelled."
    )

async def delete_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a quiz by ID"""
    quiz_id = update.message.text.strip()
    
    questions = load_questions()
    
    if quiz_id not in questions:
        await update.message.reply_text(
            f"❌ Quiz with ID {quiz_id} not found."
        )
        return
    
    # Delete the quiz
    del questions[quiz_id]
    save_questions(questions)
    
    await update.message.reply_text(
        f"✅ Quiz with ID {quiz_id} has been deleted."
    )

async def handle_txt_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle TXT file upload for importing questions"""
    # Check if a file was actually sent
    if not update.message.document:
        await update.message.reply_text(
            "⚠️ Please send a TXT file containing your quiz questions."
        )
        return TXT_UPLOAD
    
    document = update.message.document
    file_name = document.file_name
    
    # Check file type
    if not file_name.lower().endswith('.txt'):
        await update.message.reply_text(
            "⚠️ Please send a TXT file (with .txt extension)."
        )
        return TXT_UPLOAD
    
    # Get file ID and download the file
    file_id = document.file_id
    new_file = await context.bot.get_file(file_id)
    
    # Create local path for the file
    local_path = os.path.join(TEMP_DIR, f"import_{update.effective_user.id}_{int(datetime.datetime.now().timestamp())}.txt")
    
    # Download the file
    await new_file.download_to_drive(local_path)
    
    # Store the path in user data
    context.user_data["txt_path"] = local_path
    
    # Ask for custom ID or generate one
    keyboard = [
        [
            InlineKeyboardButton("Generate Random ID", callback_data="txt_generate_id"),
            InlineKeyboardButton("Provide Custom ID", callback_data="txt_custom_id")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "TXT file received! Would you like to generate a random quiz ID or provide a custom one?",
        reply_markup=reply_markup
    )
    
    return TXT_CUSTOM_ID

async def handle_txt_custom_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle quiz ID choice for TXT import"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "txt_generate_id":
        # Generate a new quiz ID
        context.user_data["quiz_id"] = generate_quiz_id()
        
        await query.edit_message_text(
            f"Generated Quiz ID: {context.user_data['quiz_id']}\n\n"
            "⏳ Processing TXT file... Please wait."
        )
        
        # Process the TXT
        return await process_txt(update, context)
    
    elif query.data == "txt_custom_id":
        await query.edit_message_text(
            "Please enter a custom quiz ID (numbers only):"
        )
        return TXT_CUSTOM_ID
    
    return ConversationHandler.END

async def handle_txt_custom_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom quiz ID input for TXT import"""
    custom_id = update.message.text.strip()
    
    # Basic validation for custom ID
    if not re.match(r'^\d+$', custom_id):
        await update.message.reply_text(
            "⚠️ Invalid quiz ID format. Please enter a numeric ID:"
        )
        return TXT_CUSTOM_ID
    
    # Check if ID already exists
    questions = load_questions()
    if custom_id in questions:
        await update.message.reply_text(
            f"⚠️ Quiz ID {custom_id} already exists. Please choose a different ID:"
        )
        return TXT_CUSTOM_ID
    
    # Store the custom ID
    context.user_data["quiz_id"] = custom_id
    
    await update.message.reply_text(
        f"Using Custom Quiz ID: {custom_id}\n\n"
        "⏳ Processing TXT file... Please wait."
    )
    
    # Process the TXT
    return await process_txt(update, context)

async def process_txt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the uploaded TXT file to extract questions"""
    # Get the TXT path from user data
    txt_path = context.user_data.get("txt_path")
    
    if not txt_path or not os.path.exists(txt_path):
        # Send error message
        if isinstance(update.callback_query, object):
            await update.callback_query.edit_message_text(
                "❌ TXT file not found or error in upload. Please try again."
            )
        else:
            await update.message.reply_text(
                "❌ TXT file not found or error in upload. Please try again."
            )
        return ConversationHandler.END
    
    # Extract text from TXT
    try:
        with open(txt_path, 'r', encoding='utf-8') as file:
            txt_text = file.readlines()
    except UnicodeDecodeError:
        # Try with different encodings
        try:
            with open(txt_path, 'r', encoding='latin-1') as file:
                txt_text = file.readlines()
        except Exception as e:
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.edit_message_text(
                    f"❌ Failed to read TXT file: {str(e)}"
                )
            else:
                await update.message.reply_text(
                    f"❌ Failed to read TXT file: {str(e)}"
                )
            return ConversationHandler.END
    except Exception as e:
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(
                f"❌ Failed to read TXT file: {str(e)}"
            )
        else:
            await update.message.reply_text(
                f"❌ Failed to read TXT file: {str(e)}"
            )
        return ConversationHandler.END
    
    if not txt_text:
        # Send error message if file is empty
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(
                "❌ The TXT file is empty."
            )
        else:
            await update.message.reply_text(
                "❌ The TXT file is empty."
            )
        return ConversationHandler.END
    
    # Group and deduplicate questions
    deduplicated_lines = group_and_deduplicate_questions(txt_text)
    
    # Parse questions and answers - same logic as for PDF
    questions = []
    current_question = None
    current_options = []
    correct_answer = None
    
    for line in deduplicated_lines:
        line = line.strip()
        if not line:
            # Empty line - if we have a complete question, add it
            if current_question and current_options and correct_answer is not None:
                questions.append({
                    "question": current_question,
                    "options": current_options,
                    "answer": correct_answer,
                    "category": "Imported"
                })
                current_question = None
                current_options = []
                correct_answer = None
            continue
        
        # Check if line is a question
        if re.match(r'^Q[\.:\d]', line, re.IGNORECASE) or (not current_question and len(line) > 10):
            # If we already have a question, save it first
            if current_question and current_options and correct_answer is not None:
                questions.append({
                    "question": current_question,
                    "options": current_options,
                    "answer": correct_answer,
                    "category": "Imported"
                })
                current_options = []
                correct_answer = None
            
            # Remove Q. or Q: prefix if present
            current_question = re.sub(r'^Q[\.:\d]\s*', '', line, flags=re.IGNORECASE)
        
        # Check if line is an option (A., B., C., etc.)
        elif re.match(r'^[A-D][\.:\)]', line, re.IGNORECASE) and current_question:
            # Extract option text
            option_text = re.sub(r'^[A-D][\.:\)]\s*', '', line, flags=re.IGNORECASE)
            current_options.append(option_text)
            
            # Check if this option is marked as correct
            if "*" in line or "correct" in line.lower() or "answer" in line.lower():
                # Get the index (0-based) of this option
                correct_answer = len(current_options) - 1
        
        # Handle "Correct Answer: X" format
        elif re.match(r'^Correct\s+Answer', line, re.IGNORECASE) and current_question:
            # Try to extract the letter
            match = re.search(r'[A-D]', line, re.IGNORECASE)
            if match:
                letter = match.group(0).upper()
                # Convert letter to index (A=0, B=1, etc.)
                correct_answer = ord(letter) - ord('A')
    
    # Add the last question if we have one
    if current_question and current_options and correct_answer is not None:
        questions.append({
            "question": current_question,
            "options": current_options,
            "answer": correct_answer,
            "category": "Imported"
        })
    
    # Check if we found any valid questions
    if not questions:
        # Send error message
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(
                "❌ No valid questions found in the TXT file. Make sure your questions are formatted correctly."
            )
        else:
            await update.message.reply_text(
                "❌ No valid questions found in the TXT file. Make sure your questions are formatted correctly."
            )
        return ConversationHandler.END
    
    # Save the questions to the database
    quiz_id = context.user_data["quiz_id"]
    all_quizzes = load_questions()
    all_quizzes[quiz_id] = {
        "questions": questions,
        "created_by": update.effective_user.id,
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "times_taken": 0,
        "source": "txt_import"
    }
    save_questions(all_quizzes)
    
    # Cleanup - remove the temp file
    try:
        os.remove(txt_path)
    except:
        pass
    
    # Offer negative marking options
    keyboard = []
    for label, value in ADVANCED_NEGATIVE_MARKING_OPTIONS:
        if value == "custom":
            callback_data = f"penalty_custom_{quiz_id}"
        else:
            callback_data = f"penalty_{value}_{quiz_id}"
        keyboard.append([InlineKeyboardButton(label, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send success message
    success_message = (
        f"✅ TXT import successful!\n\n"
        f"Quiz ID: {quiz_id}\n"
        f"Questions imported: {len(questions)}\n\n"
        f"Do you want to enable negative marking for this quiz?\n"
        f"Select a penalty value for incorrect answers:"
    )
    
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text(
            success_message,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            success_message,
            reply_markup=reply_markup
        )
    
    return ConversationHandler.END

async def command_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display user statistics"""
    user_id = update.effective_user.id
    stats = format_extended_user_stats(user_id, update.effective_user.first_name)
    await update.message.reply_text(stats)

async def command_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display help information"""
    help_text = (
        "📚 Quiz Bot Help\n\n"
        "Commands:\n"
        "/start - Start the bot and show main menu\n"
        "/create - Create a new quiz\n"
        "/take [quiz_id] - Take a quiz with the given ID\n"
        "/stats - View your statistics\n"
        "/pdf [result_id] - Generate PDF for a quiz result\n"
        "/htmlreport [quiz_id] - Generate HTML report for a quiz\n"
        "/admin - Access admin features\n"
        "/help - Show this help message\n\n"
        
        "How to create a quiz:\n"
        "1. Use /create command or select 'Create Quiz' from the main menu\n"
        "2. Enter each question, options, and the correct answer\n"
        "3. Choose a category for each question\n"
        "4. Set negative marking if desired\n"
        "5. Share your quiz ID with others\n\n"
        
        "How to import questions:\n"
        "1. Select 'Import PDF' or 'Import TXT' from the main menu\n"
        "2. Upload a properly formatted document\n"
        "3. Choose a quiz ID\n"
        "4. Set negative marking if desired\n\n"
        
        "PDF/TXT format requirements:\n"
        "- Questions should start with 'Q.', 'Q:', or similar\n"
        "- Options should be labeled A., B., C., etc.\n"
        "- Correct answers should be marked with an asterisk (*) or 'Correct Answer: X'\n"
    )
    
    await update.message.reply_text(help_text)

async def generate_html_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate an HTML report for quiz results"""
    if not context.args:
        await update.message.reply_text(
            "Please provide a quiz ID. Example: /htmlreport 12345"
        )
        return
    
    quiz_id = context.args[0]
    
    # Load quiz information
    all_quizzes = load_questions()
    if quiz_id not in all_quizzes:
        await update.message.reply_text(
            f"❌ Quiz with ID {quiz_id} not found."
        )
        return
    
    # Load participants
    participants = load_participants()
    if quiz_id not in participants:
        await update.message.reply_text(
            f"❌ No participants found for quiz {quiz_id}."
        )
        return
    
    # Load quiz results
    results = load_quiz_results()
    quiz_results = {}
    
    # Filter results for this quiz
    for result_id, result_data in results.items():
        if result_data.get("quiz_id") == quiz_id:
            user_id = result_data.get("user_id")
            # Convert user_id to string to prevent issues with string assignment
            user_id_str = str(user_id)
            if user_id_str not in quiz_results or result_data.get("timestamp", "") > quiz_results[user_id_str].get("timestamp", ""):
                # Keep only the most recent result for each user
                quiz_results[user_id_str] = result_data
    
    if not quiz_results:
        await update.message.reply_text(
            f"❌ No results found for quiz {quiz_id}."
        )
        return
    
    try:
        # Create HTML report
        html_report = generate_quiz_html_report(quiz_id, all_quizzes[quiz_id], quiz_results)
        
        # Save to temporary file
        report_filename = f"quiz_{quiz_id}_report.html"
        report_path = os.path.join(TEMP_DIR, report_filename)
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html_report)
        
        # Send the HTML file
        with open(report_path, "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=f,
                filename=report_filename,
                caption=f"📊 HTML Report for Quiz {quiz_id}"
            )
        
        # Cleanup
        try:
            os.remove(report_path)
        except:
            pass
            
    except Exception as e:
        logger.error(f"Error generating HTML report: {e}")
        await update.message.reply_text(
            f"❌ An error occurred: {str(e)}"
        )

def generate_quiz_html_report(quiz_id, quiz_data, results):
    """Generate an HTML report for a quiz"""
    # Get quiz information
    questions = quiz_data.get("questions", [])
    created_by = quiz_data.get("created_by", "Unknown")
    created_at = quiz_data.get("created_at", "Unknown")
    times_taken = quiz_data.get("times_taken", 0)
    
    # Ensure all dictionary keys in results are strings to prevent assignment issues
    string_results = {}
    for key, value in results.items():
        string_results[str(key)] = value
    results = string_results
    
    # Start building the HTML - using string concatenation instead of assignment
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Quiz Report</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                line-height: 1.6;
                max-width: 1000px;
                margin: 0 auto;
                padding: 20px;
                color: #333;
            }
            h1, h2, h3 {
                color: #2c3e50;
            }
            .container {
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 20px;
                margin-bottom: 20px;
                background-color: #f9f9f9;
            }
            .quiz-info {
                display: flex;
                justify-content: space-between;
                flex-wrap: wrap;
            }
            .quiz-info div {
                margin-bottom: 10px;
                flex-basis: 48%;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
            }
            th, td {
                padding: 12px 15px;
                border: 1px solid #ddd;
                text-align: left;
            }
            th {
                background-color: #f2f2f2;
                font-weight: bold;
            }
            tr:nth-child(even) {
                background-color: #f9f9f9;
            }
            .question {
                margin-bottom: 20px;
                padding: 15px;
                border: 1px solid #ddd;
                border-radius: 5px;
                background-color: white;
            }
            .question h3 {
                margin-top: 0;
                color: #2980b9;
            }
            .options {
                margin-left: 20px;
            }
            .correct {
                color: #27ae60;
                font-weight: bold;
            }
            .stats {
                display: flex;
                justify-content: space-between;
                flex-wrap: wrap;
            }
            .stat-box {
                flex-basis: 30%;
                padding: 15px;
                margin-bottom: 15px;
                border-radius: 5px;
                background-color: #eee;
                text-align: center;
            }
            .stat-box h3 {
                margin-top: 0;
            }
            .stat-value {
                font-size: 24px;
                font-weight: bold;
            }
            .watermark {
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%) rotate(-45deg);
                font-size: 100px;
                color: rgba(200, 200, 200, 0.2);
                pointer-events: none;
                z-index: -1;
                white-space: nowrap;
            }
        </style>
    </head>
    <body>
        <div class="watermark">QUIZ REPORT</div>
        
        <h1>Quiz Report</h1>
        
        <div class="container">
            <h2>Quiz Information</h2>
            <div class="quiz-info">
                <div><strong>Quiz ID:</strong> """ + quiz_id + """</div>
                <div><strong>Created By:</strong> User """ + str(created_by) + """</div>
                <div><strong>Created On:</strong> """ + created_at + """</div>
                <div><strong>Times Taken:</strong> """ + str(times_taken) + """</div>
                <div><strong>Total Questions:</strong> """ + str(len(questions)) + """</div>
            </div>
        </div>
        
        <div class="container">
            <h2>Performance Summary</h2>
            <div class="stats">
    """
    
    # Calculate overall statistics
    total_participants = len(results)
    avg_score = sum(r.get("percentage", 0) for r in results.values()) / total_participants if total_participants > 0 else 0
    avg_time = sum([int(r.get("duration", "0:0:0").split(":")[0]) * 3600 + 
                   int(r.get("duration", "0:0:0").split(":")[1]) * 60 + 
                   int(r.get("duration", "0:0:0").split(":")[2]) 
                   for r in results.values()]) / total_participants if total_participants > 0 else 0
    
    # Format average time
    avg_time_hours = int(avg_time // 3600)
    avg_time_minutes = int((avg_time % 3600) // 60)
    avg_time_seconds = int(avg_time % 60)
    avg_time_str = f"{avg_time_hours:02d}:{avg_time_minutes:02d}:{avg_time_seconds:02d}"
    
    # Add statistics boxes
    html += f"""
            <div class="stat-box">
                <h3>Participants</h3>
                <div class="stat-value">{total_participants}</div>
            </div>
            <div class="stat-box">
                <h3>Avg. Score</h3>
                <div class="stat-value">{avg_score:.1f}%</div>
            </div>
            <div class="stat-box">
                <h3>Avg. Time</h3>
                <div class="stat-value">{avg_time_str}</div>
            </div>
    """
    
    # Close stats div
    html += """
            </div>
        </div>
        
        <div class="container">
            <h2>Participant Results</h2>
            <table>
                <tr>
                    <th>User</th>
                    <th>Score</th>
                    <th>Correct</th>
                    <th>Incorrect</th>
    """
    
    # Add penalty column if any quiz has penalties
    has_penalties = any(r.get("penalty", 0) > 0 for r in results.values())
    if has_penalties:
        html += """
                    <th>Penalties</th>
                    <th>Final Score</th>
        """
    
    html += """
                    <th>Time</th>
                    <th>Grade</th>
                </tr>
    """
    
    # Add rows for each participant
    for user_id, result in results.items():
        username = result.get("username", f"User_{user_id}")
        percentage = result.get("percentage", 0)
        correct = result.get("correct_answers", 0)
        incorrect = result.get("incorrect_answers", 0)
        duration = result.get("duration", "00:00:00")
        grade = result.get("grade", "Not Graded")
        
        # Build the row
        html += f"""
                <tr>
                    <td>{username}</td>
                    <td>{percentage:.1f}%</td>
                    <td>{correct}</td>
                    <td>{incorrect}</td>
        """
        
        # Add penalty columns if needed
        if has_penalties:
            penalty = result.get("penalty", 0)
            penalty_applied = result.get("penalty_applied", 0)
            final_score = result.get("final_score", correct)
            html += f"""
                    <td>{penalty_applied:.2f}</td>
                    <td>{final_score:.2f}</td>
            """
        
        html += f"""
                    <td>{duration}</td>
                    <td>{grade}</td>
                </tr>
        """
    
    # Close the table
    html += """
            </table>
        </div>
        
        <div class="container">
            <h2>Questions</h2>
    """
    
    # Add each question and stats
    for i, q in enumerate(questions):
        question_text = q.get("question", "No question text")
        options = q.get("options", [])
        correct_option = q.get("answer", 0)
        
        # Calculate stats for this question
        total_answers = 0
        correct_answers = 0
        
        for result in results.values():
            answers = result.get("answers", [])
            for answer in answers:
                if answer.get("question_idx") == i:
                    total_answers += 1
                    if answer.get("is_correct"):
                        correct_answers += 1
        
        # Calculate percentage correct
        percent_correct = (correct_answers / total_answers * 100) if total_answers > 0 else 0
        
        # Add question to HTML
        html += f"""
            <div class="question">
                <h3>Question {i+1}: {question_text}</h3>
                <div class="options">
        """
        
        # Add each option
        for j, option in enumerate(options):
            if j == correct_option:
                html += f'<div class="correct">✓ {option}</div>'
            else:
                html += f'<div>{option}</div>'
        
        # Add question stats
        html += f"""
                </div>
                <div><strong>Success Rate:</strong> {correct_answers}/{total_answers} ({percent_correct:.1f}%)</div>
            </div>
        """
    
    # Close container and finalize HTML
    html += """
        </div>
        
        <div class="container">
            <h2>Generated Information</h2>
            <p>This report was generated on """ + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """</p>
            <p>Report ID: """ + str(random.randint(100000, 999999)) + """</p>
        </div>
    </body>
    </html>
    """
    
    return html

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current conversation"""
    await update.message.reply_text(
        "❌ Operation cancelled."
    )
    return ConversationHandler.END

def main() -> None:
    """Set up and run the bot"""
    # Create the application and pass it your bot's token
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Register conversation handlers
    create_quiz_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_handler, pattern="^create_quiz$")
        ],
        states={
            QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_question)],
            OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_options)],
            ANSWER: [CallbackQueryHandler(create_answer)],
            CATEGORY: [CallbackQueryHandler(create_category)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # PDF import conversation handler
    pdf_import_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_handler, pattern="^import_pdf$")
        ],
        states={
            PDF_UPLOAD: [MessageHandler(filters.Document.ALL, handle_pdf_upload)],
            PDF_CUSTOM_ID: [
                CallbackQueryHandler(handle_pdf_custom_id, pattern="^(generate_id|custom_id)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pdf_custom_id_input)
            ],
            PDF_PROCESSING: [CallbackQueryHandler(process_pdf)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # TXT import conversation handler
    txt_import_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_handler, pattern="^import_txt$")
        ],
        states={
            TXT_UPLOAD: [MessageHandler(filters.Document.ALL, handle_txt_upload)],
            TXT_CUSTOM_ID: [
                CallbackQueryHandler(handle_txt_custom_id, pattern="^(txt_generate_id|txt_custom_id)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_txt_custom_id_input)
            ],
            TXT_PROCESSING: [CallbackQueryHandler(process_txt)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Take quiz conversation handler
    take_quiz_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_handler, pattern="^take_quiz$")
        ],
        states={
            CUSTOM_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_id_handler)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("create", lambda update, context: button_handler(update, context)))
    application.add_handler(CommandHandler("take", command_take_quiz))
    application.add_handler(CommandHandler("stats", command_stats))
    application.add_handler(CommandHandler("pdf", lambda update, context: generate_pdf_result(update, context)))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("help", command_help))
    application.add_handler(CommandHandler("htmlreport", generate_html_report))
    
    # Register conversation handlers
    application.add_handler(create_quiz_handler)
    application.add_handler(pdf_import_handler)
    application.add_handler(txt_import_handler)
    application.add_handler(take_quiz_handler)
    
    # Register callback query handlers
    application.add_handler(CallbackQueryHandler(add_another_question, pattern="^add_another$"))
    application.add_handler(CallbackQueryHandler(finish_quiz, pattern="^finish_quiz$"))
    application.add_handler(CallbackQueryHandler(set_penalty, pattern="^penalty_"))
    application.add_handler(CallbackQueryHandler(generate_pdf_result, pattern="^pdf_"))
    application.add_handler(CallbackQueryHandler(handle_admin_actions, pattern="^admin_"))
    application.add_handler(CallbackQueryHandler(clean_temp_files, pattern="^clean_temp$"))
    application.add_handler(CallbackQueryHandler(cancel_clean, pattern="^cancel_clean$"))
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^(my_stats|settings|reset_stats|back_to_main)$"))
    
    # Register poll answer handler
    application.add_handler(PollAnswerHandler(handle_poll_answer))
    
    # Register message handlers for custom penalty
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_penalty))
    
    # Run the bot
    application.run_polling()

if __name__ == "__main__":
    main()
