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
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8063036514:AAFJzt2HgR13_bT_zCZKLJs73S7uneZcx8o")

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
        "<b>𝗛𝗲𝗿𝗲’𝘀 𝘄𝗵𝗮𝘁 𝘆𝗼𝘂 𝗰𝗮𝗻 𝗱𝗼:</b>\n"
        "• ⚡ <b>Start a Quiz:</b> /quiz\n"
        "• 📊 <b>Check Stats:</b> /stats\n"
        "• ➕ <b>Add Question:</b> /add\n"
        "• ✏️ <b>Edit Question:</b> /edit\n"
        "• ❌ <b>Delete Question:</b> /delete\n"
        "• 🔄 <b>Poll to Quiz:</b> /poll2q\n"
        "• ℹ️ <b>Help & Commands:</b> /help\n\n"
        
        "📄 <b>𝗙𝗶𝗹𝗲 𝗜𝗺𝗽𝗼𝗿𝘁 & Custom ID:</b>\n"
        "• 📥 <b>Import from PDF:</b> /pdfimport\n"
        "• 📝 <b>Import from TXT:</b> /txtimport\n"
        "• 🆔 <b>Start Quiz by ID:</b> /quizid\n"
        "• ℹ️ <b>PDF Info:</b> /pdfinfo\n\n"
        
        "⚙️ <b>𝗔𝗱𝘃𝗮𝗻𝗰𝗲𝗱 𝗤𝘂𝗶𝘇 𝗦𝗲𝘁𝘁𝗶𝗻𝗴𝘀:</b>\n"
        "• ⚙️ <b>Negative Marking:</b> /negmark\n"
        "• 🧹 <b>Reset Penalties:</b> /resetpenalty\n"
        "• ✋ <b>Stop Quiz Anytime:</b> /stop\n\n"
        
        "🔥 <b>Let’s go — become the legend of the leaderboard!</b> 🏆\n\n"
        "👨‍💻 <b>Developed by</b> <a href='https://t.me/JaatCoderX'>@JaatCoderX</a>\n"  
    )
    await update.message.reply_html(welcome_text)
    
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
    
    # Validate the question before processing
    if not question.get("question") or not question["question"].strip():
        logger.error(f"Empty question text for question {question_index}")
        error_msg = (
            f"❌ Could not display question #{question_index+1}.\n"
            f"Reason: Text must be non-empty\n\n"
            "Moving to next question..."
        )
        await context.bot.send_message(chat_id=chat_id, text=error_msg)
        # Skip to next question
        await schedule_next_question(context, chat_id, question_index + 1)
        return
    
    # Make sure we have at least 2 options (Telegram requirement)
    if not question.get("options") or len(question["options"]) < 2:
        logger.error(f"Not enough options for question {question_index}")
        error_msg = (
            f"❌ Could not display question #{question_index+1}.\n"
            f"Reason: At least 2 options required\n\n"
            "Moving to next question..."
        )
        await context.bot.send_message(chat_id=chat_id, text=error_msg)
        # Skip to next question
        await schedule_next_question(context, chat_id, question_index + 1)
        return
    
    # Check for empty options
    empty_options = [i for i, opt in enumerate(question["options"]) if not opt or not opt.strip()]
    if empty_options:
        logger.error(f"Empty options found for question {question_index}: {empty_options}")
        # Fix by replacing empty options with placeholder text
        for i in empty_options:
            question["options"][i] = "(No option provided)"
        logger.info(f"Replaced empty options with placeholder text")
    
    # Telegram limits for polls:
    # - Question text: 300 characters
    # - Option text: 100 characters
    # Truncate if necessary
    question_text = question["question"]
    if len(question_text) > 290:  # Leave some margin
        question_text = question_text[:287] + "..."
        logger.info(f"Truncated question text from {len(question['question'])} to 290 characters")
    
    # Prepare and truncate options if needed, and limit to 10 options (Telegram limit)
    options = []
    for i, option in enumerate(question["options"]):
        # Only process the first 10 options (Telegram limit)
        if i >= 10:
            logger.warning(f"Question has more than 10 options, truncating to 10 (Telegram limit)")
            break
        
        if len(option) > 97:  # Leave some margin
            option = option[:94] + "..."
            logger.info(f"Truncated option from {len(option)} to 97 characters")
        options.append(option)
    
    # If we had to truncate options, make sure the correct answer is still valid
    correct_answer = question["answer"]
    if len(question["options"]) > 10 and correct_answer >= 10:
        logger.warning(f"Correct answer index {correct_answer} is out of range after truncation, defaulting to 0")
        correct_answer = 0
    elif correct_answer >= len(options):
        logger.warning(f"Correct answer index {correct_answer} is out of range of options list, defaulting to 0")
        correct_answer = 0
    else:
        correct_answer = question["answer"]
    
    try:
        # Send the poll with our validated correct_answer
        message = await context.bot.send_poll(
            chat_id=chat_id,
            question=question_text,
            options=options,
            type="quiz",
            correct_option_id=correct_answer,
            is_anonymous=False,
            open_period=25  # Close poll after 25 seconds
        )
    except Exception as e:
        logger.error(f"Error sending poll: {str(e)}")
        # Send a message instead if poll fails
        error_msg = (
            f"❌ Could not display question #{question_index+1}.\n"
            f"Reason: {str(e)}\n\n"
            "Moving to next question..."
        )
        await context.bot.send_message(chat_id=chat_id, text=error_msg)
        
        # Skip to next question
        await schedule_next_question(context, chat_id, question_index + 1)
        return
    
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
    await asyncio.sleep(15)  # Wait 30 seconds
    
    # Check if quiz is still active
    quiz = context.chat_data.get("quiz", {})
    if quiz.get("active", False):
        await send_question(context, chat_id, next_index)

async def schedule_end_quiz(context, chat_id):
    """Schedule end of quiz with delay."""
    await asyncio.sleep(15)  # Wait 30 seconds after last question
    
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
                # Using the proper way to update chat_data
                chat_data["quiz"] = quiz
                
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

# ---------- PDF IMPORT FUNCTIONS ----------
def extract_text_from_pdf(pdf_file_path):
    """
    Extract text from a PDF file using PyPDF2
    Returns a list of extracted text content from each page
    """
    try:
        logger.info(f"Extracting text from PDF: {pdf_file_path}")
        
        if not PDF_SUPPORT:
            logger.warning("PyPDF2 not installed, cannot extract text from PDF.")
            return ["PyPDF2 module not available. Please install PyPDF2 to enable PDF text extraction."]
        
        extracted_text = []
        with open(pdf_file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text = page.extract_text()
                # Check for Hindi text
                if text:
                    lang = detect_language(text)
                    if lang == 'hi':
                        logger.info("Detected Hindi text in PDF")
                
                extracted_text.append(text if text else "")
        return extracted_text
    except Exception as e:
        logger.error(f"Error in direct text extraction: {e}")
        return []




def parse_questions_from_text(text_list, custom_id=None):
    """Improved parser with correct answer text and answer letter (A/B/C/D)"""
    import re
    questions = []
    question_block = []

    for page_text in text_list:
        if not page_text:
            continue
        lines = page_text.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if re.match(r'^(Q\.|\d+[:.)])', line, re.IGNORECASE):
                if question_block:
                    questions.append('\n'.join(question_block))
                    question_block = []
            question_block.append(line)

        if question_block:
            questions.append('\n'.join(question_block))
            question_block = []

    parsed_questions = []
    for block in questions:
        lines = block.split('\n')
        question_text = ""
        options = []
        answer = 0
        
        # Track if an option is marked with a checkmark or asterisk
        option_with_mark = None

        for line in lines:
            if re.match(r'^(Q\.|\d+[:.)])', line, re.IGNORECASE):
                question_text = re.sub(r'^(Q\.|\d+[:.)])\s*', '', line).strip()
            elif re.match(r'^[A-D1-4][).]', line.strip()):
                # Check if this option has a checkmark or asterisk
                option_index = len(options)
                option_text = re.sub(r'^[A-D1-4][).]\s*', '', line).strip()
                
                # Check for various marks
                if any(mark in option_text for mark in ['*', '✓', '✔', '✅']):
                    option_with_mark = option_index
                    # Clean the option text by removing the mark
                    option_text = re.sub(r'[\*✓✔✅]', '', option_text).strip()
                
                options.append(option_text)
            elif re.match(r'^(Ans|Answer|उत्तर|सही उत्तर|जवाब)[:\-\s]+', line, re.IGNORECASE):
                match = re.search(r'[ABCDabcd1-4]', line)
                if match:
                    answer_char = match.group().upper()
                    answer = {'A': 0, '1': 0, 'B': 1, '2': 1, 'C': 2, '3': 2, 'D': 3, '4': 3}.get(answer_char, 0)

        if question_text and len(options) >= 2:
            # Use option_with_mark if it was detected
            if option_with_mark is not None:
                answer = option_with_mark
                
            parsed_questions.append({
                'question': question_text,
                'options': options,
                'answer': answer,
                'answer_option': ['A', 'B', 'C', 'D'][answer] if answer < 4 else "A",
                'correct_answer': options[answer] if answer < len(options) else "",
                'category': 'General Knowledge'
            })

    return parsed_questions
    for page_text in text_list:
        if not page_text:
            continue
        lines = page_text.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if re.match(r'^(Q\.|\d+[:.)])', line, re.IGNORECASE):
                if question_block:
                    questions.append('\n'.join(question_block))
                    question_block = []
            question_block.append(line)

        if question_block:
            questions.append('\n'.join(question_block))
            question_block = []

    parsed_questions = []
    for block in questions:
        lines = block.split('\n')
        question_text = ""
        options = []
        answer = 0

        for line in lines:
            if re.match(r'^(Q\.|\d+[:.)])', line, re.IGNORECASE):
                question_text = re.sub(r'^(Q\.|\d+[:.)])\s*', '', line).strip()
            elif re.match(r'^[A-D1-4][).]', line.strip()):
                options.append(re.sub(r'^[A-D1-4][).]\s*', '', line).strip())
            elif re.match(r'^(Ans|Answer|उत्तर)[:\-\s]+', line, re.IGNORECASE):
                match = re.search(r'[ABCDabcd1-4]', line)
                if match:
                    answer_char = match.group().upper()
                    answer = {'A': 0, '1': 0, 'B': 1, '2': 1, 'C': 2, '3': 2, 'D': 3, '4': 3}.get(answer_char, 0)

        if question_text and len(options) >= 2:
            parsed_questions.append({
                'question': question_text,
                'options': options,
                'answer': answer,
                'correct_answer': options[answer] if answer < len(options) else "",
                'category': 'General Knowledge'
            })

    return parsed_questions
    for page_text in text_list:
        if not page_text:
            continue
        lines = page_text.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if re.match(r'^(Q\.|\d+[:.)])', line, re.IGNORECASE):
                if question_block:
                    questions.append('\n'.join(question_block))
                    question_block = []
            question_block.append(line)

        if question_block:
            questions.append('\n'.join(question_block))
            question_block = []

    parsed_questions = []
    for block in questions:
        lines = block.split('\n')
        question_text = ""
        options = []
        answer = 0

        for line in lines:
            if re.match(r'^(Q\.|\d+[:.)])', line, re.IGNORECASE):
                question_text = re.sub(r'^(Q\.|\d+[:.)])\s*', '', line).strip()
            elif re.match(r'^[A-D1-4][).]', line.strip()):
                options.append(re.sub(r'^[A-D1-4][).]\s*', '', line).strip())
            elif re.match(r'^(Ans|Answer|उत्तर)[:\-\s]+', line, re.IGNORECASE):
                match = re.search(r'[ABCDabcd1-4]', line)
                if match:
                    answer_char = match.group().upper()
                    answer = {'A': 0, '1': 0, 'B': 1, '2': 1, 'C': 2, '3': 2, 'D': 3, '4': 3}.get(answer_char, 0)

        if question_text and len(options) >= 2:
            parsed_questions.append({
                'question': question_text,
                'options': options,
                'answer': answer,
                'category': 'General Knowledge'
            })

    return parsed_questions
    # Simple question pattern detection:
    # - Question starts with a number or "Q." or "Question"
    # - Options start with A), B), C), D) or similar
    # - Answer might be marked with "Ans:" or "Answer:"
    
    for page_text in text_list:
        if not page_text or not page_text.strip():
            continue
            
        lines = page_text.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Check if line starts a new question
            if (line.startswith('Q.') or 
                (line and line[0].isdigit() and len(line) > 2 and line[1:3] in ['. ', ') ', '- ']) or
                line.lower().startswith('question')):
                
                # Save previous question if exists
                if current_question and 'question' in current_question and 'options' in current_question:
                    if len(current_question['options']) >= 2:  # Must have at least 2 options
                        questions.append(current_question)
                
                # Start a new question
                current_question = {
                    'question': line,
                    'options': [],
                    'answer': None,
                    'category': 'General Knowledge'  # Default category
                }
                
                # Collect question text that may span multiple lines
                j = i + 1
                option_detected = False
                while j < len(lines) and not option_detected:
                    next_line = lines[j].strip()
                    # Check if this line starts an option
                    if (next_line.startswith('A)') or next_line.startswith('A.') or
                        next_line.startswith('a)') or next_line.startswith('1)') or
                        next_line.startswith('B)') or next_line.startswith('B.')):
                        option_detected = True
                    else:
                        current_question['question'] += ' ' + next_line
                        j += 1
                
                i = j - 1 if option_detected else j  # Adjust index to continue from option lines or next line
            
            # Check for options
            
            elif current_question and re.match(r"^(ans|answer|correct answer)[:\- ]", line.strip(), re.IGNORECASE):
                # Extract option letter from the answer line using regex
                match = re.search(r"[ABCDabcd1-4]", line)
                if match:
                    char = match.group().upper()
                    current_question['answer'] = {
                        'A': 0, '1': 0,
                        'B': 1, '2': 1,
                        'C': 2, '3': 2,
                        'D': 3, '4': 3
                    }.get(char, 0)
    
            i += 1
    
    # Add the last question if it exists
    if current_question and 'question' in current_question and 'options' in current_question:
        if len(current_question['options']) >= 2:
            questions.append(current_question)
    
    # Post-process questions
    processed_questions = []
    for q in questions:
        # If no correct answer is identified, default to first option
        if q['answer'] is None:
            q['answer'] = 0
        
        # Clean up the question text
        q['question'] = q['question'].replace('Q.', '').replace('Question:', '').strip()
        
        # Clean up option texts
        cleaned_options = []
        for opt in q['options']:
            # Remove option identifiers (A), B), etc.)
            if opt and opt[0].isalpha() and len(opt) > 2 and opt[1] in [')', '.', '-']:
                opt = opt[2:].strip()
            elif opt and opt[0].isdigit() and len(opt) > 2 and opt[1] in [')', '.', '-']:
                opt = opt[2:].strip()
            cleaned_options.append(opt)
        
        q['options'] = cleaned_options
        
        # Only include questions with adequate options
        if len(q['options']) >= 2:
            processed_questions.append(q)
            
    # Log how many questions were extracted
    logger.info(f"Extracted {len(processed_questions)} questions from PDF")
    
    return processed_questions

async def pdf_import_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the PDF import process."""
    await update.message.reply_text(
        "📚 Let's import questions from a PDF file!\n\n"
        "Send me the PDF file you want to import questions from."
    )
    return PDF_UPLOAD

async def pdf_file_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the PDF file upload."""
    # Check if a document was received
    if not update.message.document:
        await update.message.reply_text("Please send a PDF file.")
        return PDF_UPLOAD
    
    # Check if it's a PDF file
    file = update.message.document
    if not file.file_name.lower().endswith('.pdf'):
        await update.message.reply_text("Please send a PDF file (with .pdf extension).")
        return PDF_UPLOAD
    
    # Ask for a custom ID
    await update.message.reply_text(
        "Please provide a custom ID for these questions.\n"
        "All questions from this PDF will be saved under this ID.\n"
        "Enter a number or a short text ID (e.g., 'science_quiz' or '42'):"
    )
    
    # Store the file ID for later download
    context.user_data['pdf_file_id'] = file.file_id
    return PDF_CUSTOM_ID

async def pdf_custom_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the custom ID input for PDF questions."""
    custom_id = update.message.text.strip()
    
    # Validate the custom ID
    if not custom_id:
        await update.message.reply_text("Please provide a valid ID.")
        return PDF_CUSTOM_ID
    
    # Store the custom ID
    context.user_data['pdf_custom_id'] = custom_id
    
    # Let user know we're processing the PDF
    status_message = await update.message.reply_text(
        "⏳ Processing the PDF file. This may take a moment..."
    )
    
    # Store the status message ID for updating
    context.user_data['status_message_id'] = status_message.message_id
    
    # Download and process the PDF file
    return await process_pdf_file(update, context)

async def process_pdf_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the PDF file and extract questions."""
    try:
        # Get file ID and custom ID from user data
        file_id = context.user_data.get('pdf_file_id')
        custom_id = context.user_data.get('pdf_custom_id')
        
        if not file_id or not custom_id:
            await update.message.reply_text("Error: Missing file or custom ID information.")
            return ConversationHandler.END
        
        # Check if PDF support is available
        if not PDF_SUPPORT:
            await update.message.reply_text(
                "❌ PDF support is not available. Please install PyPDF2 module.\n"
                "You can run: pip install PyPDF2"
            )
            return ConversationHandler.END
        
        # Download the file
        file = await context.bot.get_file(file_id)
        pdf_file_path = os.path.join(TEMP_DIR, f"{custom_id}_import.pdf")
        await file.download_to_drive(pdf_file_path)
        
        # Update status message
        status_message_id = context.user_data.get('status_message_id')
        if status_message_id:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_message_id,
                text="⏳ PDF downloaded. Extracting text and questions..."
            )
        
        # Extract text from PDF
        extracted_text_list = group_and_deduplicate_questions(extract_text_from_pdf(pdf_file_path))
        
        # Update status message
        if status_message_id:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_message_id,
                text="⏳ Text extracted. Parsing questions..."
            )
        
        # Parse questions from the extracted text
        questions = parse_questions_from_text(extracted_text_list, custom_id)
        
        # Clean up temporary files
        if os.path.exists(pdf_file_path):
            os.remove(pdf_file_path)
        
        # Check if we found any questions
        if not questions:
            await update.message.reply_text(
                "❌ No questions could be extracted from the PDF.\n"
                "Please make sure the PDF contains properly formatted questions and options."
            )
            return ConversationHandler.END
        
        # Update status message
        if status_message_id:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_message_id,
                text=f"✅ Found {len(questions)} questions! Saving to the database..."
            )
        
        # Save the questions under the custom ID
        all_questions = load_questions()
        
        # Prepare the questions data structure
        if custom_id not in all_questions:
            all_questions[custom_id] = []
        
        # Check if all_questions[custom_id] is a list
        if not isinstance(all_questions[custom_id], list):
            all_questions[custom_id] = [all_questions[custom_id]]
            
        # Add all extracted questions to the custom ID
        all_questions[custom_id].extend(questions)
        
        # Save the updated questions
        save_questions(all_questions)
        
        # Send completion message
        await update.message.reply_text(
            f"✅ Successfully imported {len(questions)} questions from the PDF!\n\n"
            f"They have been saved under the custom ID: '{custom_id}'\n\n"
            f"You can start a quiz with these questions using:\n"
            f"/quizid {custom_id}"
        )
        
        # End the conversation
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        await update.message.reply_text(
            f"❌ An error occurred while processing the PDF: {str(e)}\n"
            "Please try again or use a different PDF file."
        )
        return ConversationHandler.END

async def quiz_with_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a quiz with questions from a specific ID."""
    # Check if an ID was provided
    if not context.args or not context.args[0]:
        await update.message.reply_text(
            "Please provide an ID to start a quiz with.\n"
            "Example: /quizid science_quiz"
        )
        return
    
    # Convert quiz_id to string to handle numeric IDs properly
    quiz_id = str(context.args[0])
    logger.info(f"Starting quiz with ID: {quiz_id}")
    
    # Load all questions
    all_questions = load_questions()
    
    # Check if the ID exists
    if quiz_id not in all_questions:
        await update.message.reply_text(
            f"❌ No questions found with ID: '{quiz_id}'\n"
            "Please check the ID and try again."
        )
        return
    
    # Get questions for the given ID
    questions = all_questions[quiz_id]
    
    # If it's not a list, convert it to a list
    if not isinstance(questions, list):
        questions = [questions]
    
    # Check if there are any questions
    if not questions:
        await update.message.reply_text(
            f"❌ No questions found with ID: '{quiz_id}'\n"
            "Please check the ID and try again."
        )
        return
    
    # Initialize quiz state similar to the regular quiz command
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    # Initialize quiz state
    context.chat_data["quiz"] = {
        "active": True,
        "current_index": 0,
        "questions": questions,
        "sent_polls": {},
        "participants": {},
        "chat_id": chat_id,
        "creator": {
            "id": user.id,
            "name": user.first_name,
            "username": user.username
        }
    }
    
    # Send info about quiz
    await update.message.reply_text(
        f"Starting quiz with ID: {quiz_id}\n"
        f"Total questions: {len(questions)}\n\n"
        f"First question coming up..."
    )
    
    # Send first question with slight delay
    await asyncio.sleep(2)
    await send_question(context, chat_id, 0)

async def pdf_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show information about PDF import feature."""
    pdf_support_status = "✅ AVAILABLE" if PDF_SUPPORT else "❌ NOT AVAILABLE"
    image_support_status = "✅ AVAILABLE" if IMAGE_SUPPORT else "❌ NOT AVAILABLE"
    
    info_text = (
        "📄 PDF Import Feature Guide\n\n"
        f"PDF Support: {pdf_support_status}\n"
        f"Image Processing: {image_support_status}\n\n"
        "Use the /pdfimport command to import questions from a PDF file.\n\n"
        "How it works:\n"
        "1. The bot will ask you to upload a PDF file.\n"
        "2. Send a PDF file containing questions and options.\n"
        "3. Provide a custom ID to save all questions from this PDF.\n"
        "4. The bot will extract questions and detect Hindi text if present.\n"
        "5. All extracted questions will be saved under your custom ID.\n\n"
        "PDF Format Tips:\n"
        "- Questions should start with 'Q.', a number, or 'Question:'\n"
        "- Options should be labeled as A), B), C), D) or 1), 2), 3), 4)\n"
        "- Answers can be indicated with 'Ans:' or 'Answer:'\n"
        "- Hindi text is fully supported\n\n"
        "To start a quiz with imported questions, use:\n"
        "/quizid YOUR_CUSTOM_ID"
    )
    await update.message.reply_text(info_text)

# ====== /stop command ======
async def stop_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    quiz = context.chat_data.get("quiz", {})

    if quiz.get("active", False):
        quiz["active"] = False
        context.chat_data["quiz"] = quiz
        await update.message.reply_text("✅ Quiz has been stopped.")
    else:
        await update.message.reply_text("ℹ️ No quiz is currently running.")

# ---------- TXT IMPORT COMMAND HANDLERS ----------
async def txtimport_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the text import process"""
    await update.message.reply_text(
        "📄 <b>Text File Import Wizard</b>\n\n"
        "Please upload a <b>.txt file</b> containing quiz questions.\n\n"
        "<b>File Format:</b>\n"
        "• Questions MUST end with a question mark (?) to be detected\n"
        "• Questions should start with 'Q1.' or '1.' format (e.g., 'Q1. What is...?')\n"
        "• Options should be labeled as A), B), C), D) with one option per line\n"
        "• Correct answer can be indicated with:\n"
        "  - Asterisk after option: B) Paris*\n"
        "  - Check marks after option: C) Berlin✓ or C) Berlin✔ or C) Berlin✅\n"
        "  - Answer line: Ans: B or Answer: B\n"
        "  - Hindi format: उत्तर: B or सही उत्तर: B\n\n"
        "<b>English Example:</b>\n"
        "Q1. What is the capital of France?\n"
        "A) London\n"
        "B) Paris*\n"
        "C) Berlin\n"
        "D) Rome\n\n"
        "<b>Hindi Example:</b>\n"
        "Q1. भारत की राजधानी कौन सी है?\n"
        "A) मुंबई\n"
        "B) दिल्ली\n"
        "C) कोलकाता\n"
        "D) चेन्नई\n"
        "उत्तर: B\n\n"
        "Send /cancel to abort the import process.",
        parse_mode='HTML'
    )
    return TXT_UPLOAD

async def receive_txt_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle text file upload - more robust implementation"""
    try:
        # Check if the message contains a document
        if not update.message.document:
            await update.message.reply_text(
                "❌ Please upload a text file (.txt)\n"
                "Try again or /cancel to abort."
            )
            return TXT_UPLOAD
    
        # Check if it's a text file
        file = update.message.document
        if not file.file_name.lower().endswith('.txt'):
            await update.message.reply_text(
                "❌ Only .txt files are supported.\n"
                "Please upload a text file or /cancel to abort."
            )
            return TXT_UPLOAD
    
        # Download the file
        status_message = await update.message.reply_text("⏳ Downloading file...")
        
        # Ensure temp directory exists
        os.makedirs(TEMP_DIR, exist_ok=True)
        logger.info(f"Temporary directory: {os.path.abspath(TEMP_DIR)}")
        
        try:
            # Get the file from Telegram
            new_file = await context.bot.get_file(file.file_id)
            
            # Create a unique filename with timestamp to avoid collisions
            import time
            timestamp = int(time.time())
            file_path = os.path.join(TEMP_DIR, f"{timestamp}_{file.file_id}_{file.file_name}")
            logger.info(f"Saving file to: {file_path}")
            
            # Download the file
            await new_file.download_to_drive(file_path)
            logger.info(f"File downloaded successfully to {file_path}")
            
            # Verify file exists and has content
            if not os.path.exists(file_path):
                logger.error(f"File download failed - file does not exist at {file_path}")
                await update.message.reply_text("❌ File download failed. Please try again.")
                return TXT_UPLOAD
                
            if os.path.getsize(file_path) == 0:
                logger.error(f"Downloaded file is empty: {file_path}")
                await update.message.reply_text("❌ The uploaded file is empty. Please provide a file with content.")
                os.remove(file_path)
                return TXT_UPLOAD
                
            # Update status message
            await status_message.edit_text("✅ File downloaded successfully!")
            
            # Store the file path in context
            context.user_data['txt_file_path'] = file_path
            context.user_data['txt_file_name'] = file.file_name
            
            # Generate automatic ID based on filename and timestamp
            base_filename = os.path.splitext(file.file_name)[0]
            auto_id = f"txt_{timestamp}_{base_filename.replace(' ', '_')}"
            logger.info(f"Generated automatic ID: {auto_id}")
            
            # Store the auto ID in context
            context.user_data['txt_custom_id'] = auto_id
            
            # Notify user that processing has begun
            await update.message.reply_text(
                f"⏳ Processing text file with auto-generated ID: <b>{auto_id}</b>...\n"
                "This may take a moment depending on the file size.",
                parse_mode='HTML'
            )
            
            # Process file directly instead of asking for custom ID, but must return END
            await process_txt_file(update, context)
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            await update.message.reply_text(f"❌ Download failed: {str(e)}. Please try again.")
            return TXT_UPLOAD
            
    except Exception as e:
        logger.error(f"Unexpected error in receive_txt_file: {e}")
        await update.message.reply_text(
            "❌ An unexpected error occurred while processing your upload.\n"
            "Please try again or contact the administrator."
        )
        return TXT_UPLOAD

async def set_custom_id_txt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Set custom ID for the imported questions from text file and process the file immediately"""
    custom_id = update.message.text.strip()
    
    # Log the received custom ID for debugging
    logger.info(f"Received custom ID: {custom_id}, Type: {type(custom_id)}")
    
    # Basic validation for the custom ID
    if not custom_id or ' ' in custom_id:
        await update.message.reply_text(
            "❌ Invalid ID. Please provide a single word without spaces.\n"
            "Try again or /cancel to abort."
        )
        return TXT_CUSTOM_ID
    
    # Convert the custom_id to a string to handle numeric IDs properly
    custom_id = str(custom_id)
    logger.info(f"After conversion: ID={custom_id}, Type={type(custom_id)}")
    
    # Store the custom ID
    context.user_data['txt_custom_id'] = custom_id
    
    # Get file path from context
    file_path = context.user_data.get('txt_file_path')
    logger.info(f"File path from context: {file_path}")
    
    try:
        # Send processing message
        await update.message.reply_text(
            f"⏳ Processing text file with ID: <b>{custom_id}</b>...\n"
            "This may take a moment depending on the file size.",
            parse_mode='HTML'
        )
        
        # Validate file path
        if not file_path or not os.path.exists(file_path):
            logger.error(f"File not found at path: {file_path}")
            await update.message.reply_text("❌ File not found or download failed. Please try uploading again.")
            return ConversationHandler.END
        
        # Read the text file with proper error handling
        try:
            logger.info(f"Attempting to read file: {file_path}")
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                logger.info(f"Successfully read file with UTF-8 encoding, content length: {len(content)}")
        except UnicodeDecodeError:
            # Try with another encoding if UTF-8 fails
            try:
                logger.info("UTF-8 failed, trying UTF-16")
                with open(file_path, 'r', encoding='utf-16') as f:
                    content = f.read()
                    logger.info(f"Successfully read file with UTF-16 encoding, content length: {len(content)}")
            except UnicodeDecodeError:
                # If both fail, try latin-1 which should accept any bytes
                logger.info("UTF-16 failed, trying latin-1")
                with open(file_path, 'r', encoding='latin-1') as f:
                    content = f.read()
                    logger.info(f"Successfully read file with latin-1 encoding, content length: {len(content)}")
        
        # Detect if text contains Hindi
        lang = detect_language(content)
        logger.info(f"Language detected: {lang}")
        
        # Split file into lines and count them
        lines = content.splitlines()
        logger.info(f"Split content into {len(lines)} lines")
        
        # Extract questions
        logger.info("Starting question extraction...")
        questions = extract_questions_from_txt(lines)
        logger.info(f"Extracted {len(questions)} questions")
        
        if not questions:
            logger.warning("No valid questions found in the text file")
            await update.message.reply_text(
                "❌ No valid questions found in the text file.\n"
                "Please check the file format and try again."
            )
            # Clean up
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Removed file: {file_path}")
            return ConversationHandler.END
        
        # Save questions with the custom ID
        logger.info(f"Adding {len(questions)} questions with ID: {custom_id}")
        added = add_questions_with_id(custom_id, questions)
        logger.info(f"Added {added} questions with ID: {custom_id}")
        
        # Clean up
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Removed file: {file_path}")
        
        # Send completion message
        logger.info("Sending completion message")
        await update.message.reply_text(
            f"✅ Successfully imported <b>{len(questions)}</b> questions with ID: <b>{custom_id}</b>\n\n"
            f"Language detected: <b>{lang}</b>\n\n"
            f"To start a quiz with these questions, use:\n"
            f"<code>/quizid {custom_id}</code>",
            parse_mode='HTML'
        )
        
        logger.info("Text import process completed successfully")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}", exc_info=True)
        try:
            await update.message.reply_text(
                f"❌ An error occurred during import: {str(e)}\n"
                "Please try again or contact the administrator."
            )
        except Exception as msg_error:
            logger.error(f"Error sending error message: {str(msg_error)}")
            
        # Clean up any temporary files on error
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Removed file: {file_path}")
            except Exception as cleanup_error:
                logger.error(f"Error removing file: {str(cleanup_error)}")
                
        return ConversationHandler.END

async def process_txt_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the uploaded text file and extract questions"""
    # Retrieve file path and custom ID from context
    file_path = context.user_data.get('txt_file_path')
    custom_id = context.user_data.get('txt_custom_id')
    
    # Ensure custom_id is treated as a string
    if custom_id is not None:
        custom_id = str(custom_id)
    
    logger.info(f"Processing txt file. Path: {file_path}, ID: {custom_id}")
    
    # Early validation
    if not file_path:
        logger.error("No file path found in context")
        if update.message:
            await update.message.reply_text("❌ File path not found. Please try uploading again.")
        return ConversationHandler.END
    
    if not os.path.exists(file_path):
        logger.error(f"File does not exist at path: {file_path}")
        if update.message:
            await update.message.reply_text("❌ File not found on disk. Please try uploading again.")
        return ConversationHandler.END
    
    # Use the original message that started the conversation if the current update doesn't have a message
    message_obj = update.message if update.message else update.effective_chat
    
    # Read the text file
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        # Try with another encoding if UTF-8 fails
        try:
            with open(file_path, 'r', encoding='utf-16') as f:
                content = f.read()
        except UnicodeDecodeError:
            # If both fail, try latin-1 which should accept any bytes
            with open(file_path, 'r', encoding='latin-1') as f:
                content = f.read()
    
    # Detect if text contains Hindi
    lang = detect_language(content)
    
    # Split file into lines
    lines = content.splitlines()
    
    # Extract questions
    questions = extract_questions_from_txt(lines)
    
    if not questions:
        error_msg = "❌ No valid questions found in the text file.\nPlease check the file format and try again."
        if hasattr(message_obj, "reply_text"):
            await message_obj.reply_text(error_msg)
        else:
            await context.bot.send_message(chat_id=message_obj.id, text=error_msg)
        
        # Clean up
        if os.path.exists(file_path):
            os.remove(file_path)
        return ConversationHandler.END
    
    # Save questions with the custom ID
    added = add_questions_with_id(custom_id, questions)
    logger.info(f"Added {added} questions with ID: {custom_id}")
    
    # Clean up
    if os.path.exists(file_path):
        os.remove(file_path)
    
    # Send completion message
    success_msg = (
        f"✅ Successfully imported <b>{len(questions)}</b> questions with ID: <b>{custom_id}</b>\n\n"
        f"Language detected: <b>{lang}</b>\n\n"
        f"To start a quiz with these questions, use:\n"
        f"<code>/quizid {custom_id}</code>"
    )
    
    try:
        if hasattr(message_obj, "reply_text"):
            await message_obj.reply_text(success_msg, parse_mode='HTML')
        else:
            await context.bot.send_message(
                chat_id=message_obj.id, 
                text=success_msg,
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"Failed to send completion message: {e}")
        # Try one more time without parse_mode as fallback
        try:
            plain_msg = f"✅ Successfully imported {len(questions)} questions with ID: {custom_id}. Use /quizid {custom_id} to start a quiz."
            await context.bot.send_message(chat_id=update.effective_chat.id, text=plain_msg)
        except Exception as e2:
            logger.error(f"Final attempt to send message failed: {e2}")
    
    return ConversationHandler.END

async def txtimport_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the import process"""
    # Clean up any temporary files
    file_path = context.user_data.get('txt_file_path')
    if file_path and os.path.exists(file_path):
        os.remove(file_path)
    
    await update.message.reply_text(
        "❌ Text import process cancelled.\n"
        "You can start over with /txtimport"
    )
    return ConversationHandler.END

def extract_questions_from_txt(lines):
    """
    Extract questions, options, and answers from text file lines
    Returns a list of question dictionaries with text truncated to fit Telegram limits
    Specially optimized for Hindi/Rajasthani quiz formats with numbered options and checkmarks
    """
    questions = []
    
    # Telegram character limits
    MAX_QUESTION_LENGTH = 290  # Telegram limit for poll questions is 300, leaving 10 for safety
    MAX_OPTION_LENGTH = 97     # Telegram limit for poll options is 100, leaving 3 for safety
    MAX_OPTIONS_COUNT = 10     # Telegram limit for number of poll options
    
    # Define patterns for specific quiz format: numbered options with checkmarks (✓, ✅)
    # This pattern matches lines like "(1) Option text" or "1. Option text" or "1 Option text"
    numbered_option_pattern = re.compile(r'^\s*\(?(\d+)\)?[\.\s]\s*(.*?)\s*$', re.UNICODE)
    
    # This pattern specifically detects options with checkmarks
    option_with_checkmark = re.compile(r'.*[✓✅].*$', re.UNICODE)
    
    # Patterns to filter out metadata/promotional lines
    skip_patterns = [
        r'^\s*RT:.*',    # Retweet marker
        r'.*<ggn>.*',    # HTML-like tags
        r'.*Ex:.*',      # Example marker
        r'.*@\w+.*',     # Twitter/Telegram handles
        r'.*\bBy\b.*',   # Credit line
        r'.*https?://.*', # URLs
        r'.*t\.me/.*'    # Telegram links
    ]
    
    # Process the file by blocks (each block is a question with its options)
    # Each block typically starts with a question and is followed by options
    current_block = []
    blocks = []
    
    # Group the content into blocks separated by empty lines
    for line in lines:
        line = line.strip()
        
        # Skip empty lines, use them as block separators
        if not line:
            if current_block:
                blocks.append(current_block)
                current_block = []
            continue
            
        # Skip metadata/promotional lines
        should_skip = False
        for pattern in skip_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                should_skip = True
                break
                
        if should_skip:
            continue
            
        # Add the line to the current block
        current_block.append(line)
    
    # Add the last block if it exists
    if current_block:
        blocks.append(current_block)
    
    # Process each block to extract questions and options
    for block in blocks:
        if not block:
            continue
        
        # The first line is almost always the question
        question_text = block[0]
        
        # Clean the question text
        # Remove any option-like patterns that may have been included
        question_text = re.sub(r'\(\d+\).*$', '', question_text).strip()
        question_text = re.sub(r'\d+\..*$', '', question_text).strip()
        
        # If the question is too long, truncate it
        if len(question_text) > MAX_QUESTION_LENGTH:
            question_text = question_text[:MAX_QUESTION_LENGTH-3] + "..."
        
        # Process the remaining lines as options
        options = []
        correct_answer = 0  # Default to first option
        has_correct_marked = False
        
        for i, line in enumerate(block[1:]):
            # Skip any promotional/metadata lines within the block
            should_skip = False
            for pattern in skip_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    should_skip = True
                    break
                    
            if should_skip:
                continue
            
            # Check if this is a numbered option
            option_match = numbered_option_pattern.match(line)
            
            if option_match:
                # Extract the option number and text
                option_num = int(option_match.group(1))
                option_text = option_match.group(2).strip()
                
                # Check if this option has a checkmark (✓, ✅)
                has_checkmark = option_with_checkmark.match(line) is not None
                
                # Remove the checkmark from the option text
                option_text = re.sub(r'[✓✅]', '', option_text).strip()
                
                # If the option is too long, truncate it
                if len(option_text) > MAX_OPTION_LENGTH:
                    option_text = option_text[:MAX_OPTION_LENGTH-3] + "..."
                
                # Ensure the options list has enough slots
                while len(options) < option_num:
                    options.append("")
                
                # Add the option text (using 1-based indexing)
                options[option_num-1] = option_text
                
                # If this option has a checkmark, mark it as the correct answer
                if has_checkmark:
                    correct_answer = option_num - 1  # Convert to 0-based for internal use
                    has_correct_marked = True
            else:
                # This might be an unnumbered option or part of the question
                # Check if it has a checkmark
                has_checkmark = option_with_checkmark.match(line) is not None
                
                # Clean the text
                option_text = re.sub(r'[✓✅]', '', line).strip()
                
                if i == 0 and not options:
                    # If this is the first line after the question and we have no options yet,
                    # it might be part of the question text
                    if len(question_text) + len(option_text) + 1 <= MAX_QUESTION_LENGTH:
                        question_text += " " + option_text
                else:
                    # Otherwise, treat it as an option
                    if len(option_text) > MAX_OPTION_LENGTH:
                        option_text = option_text[:MAX_OPTION_LENGTH-3] + "..."
                    
                    options.append(option_text)
                    
                    # If it has a checkmark, mark it as correct
                    if has_checkmark:
                        correct_answer = len(options) - 1
                        has_correct_marked = True
        
        # Only add the question if we have a question text and at least 2 options
        if question_text and len(options) >= 2:
            # Clean up options list - remove any empty options
            options = [opt for opt in options if opt]
            
            # Ensure we don't exceed Telegram's limit of 10 options
            if len(options) > MAX_OPTIONS_COUNT:
                options = options[:MAX_OPTIONS_COUNT]
            
            # Make sure the correct_answer is still valid after cleaning
            if correct_answer >= len(options):
                correct_answer = 0
            
            # Add the question to our list
            questions.append({
                "question": question_text,
                "options": options,
                "answer": correct_answer,
                "category": "Imported"
            })
    
    # If the block-based approach didn't work (no questions found),
    # fall back to line-by-line processing
    if not questions:
        # Variables for line-by-line processing
        current_question = None
        current_options = []
        correct_answer = 0
        processing_options = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Only check for patterns with question marks (?)
        question_match1 = question_pattern1.match(line)
        question_match2 = question_pattern2.match(line)
        question_emoji_match = question_pattern_emoji.match(line) if '?' in line else None
        question_match3 = question_pattern3.match(line) if '?' in line else None
        hindi_match = hindi_question_pattern.match(line) if '?' in line else None
        
        # Check for option with checkmark - this directly indicates correct answer
        checkmark_match = option_with_checkmark.match(line)
        if checkmark_match and current_question and processing_options:
            # Get the correct letter (from any of the capture groups)
            option_letter = checkmark_match.group(1) or checkmark_match.group(2) or checkmark_match.group(3) or checkmark_match.group(4)
            if option_letter:
                # Normalize fancy Unicode letters if needed
                if option_letter in "𝗔𝗕𝗖𝗗":
                    option_letter = chr(ord('A') + "𝗔𝗕𝗖𝗗".index(option_letter))
                
                try:
                    correct_answer = "ABCD".index(option_letter.upper())
                    logger.info(f"Found option with checkmark: {option_letter} (index {correct_answer})")
                except ValueError:
                    logger.warning(f"Invalid checkmark option letter {option_letter}, defaulting to A")
                    correct_answer = 0
        
        # Check for question matches - must have a question mark to be considered
        if question_match1 or question_match2 or question_emoji_match or question_match3 or hindi_match:
            # Save the previous question if it exists
            if current_question and current_options:
                if correct_answer is not None:
                    # Make sure options list has at least 2 items (Telegram requirement)
                    while len(current_options) < 2:
                        current_options.append("(No option provided)")
                    
                    # Validate correct_answer is within range of options
                    if correct_answer is not None and (correct_answer < 0 or correct_answer >= len(current_options)):
                        logger.warning(f"Invalid answer index {correct_answer}, defaulting to 0")
                        correct_answer = 0
                    
                    questions.append({
                        "question": current_question[:MAX_QUESTION_LENGTH] if len(current_question) > MAX_QUESTION_LENGTH else current_question,
                        "options": current_options.copy(),
                        "answer": correct_answer,
                        "category": "Imported"
                    })
            
            # Start a new question, truncating if needed
            if question_match1:
                logger.info("Found question with format 'Q1?' (preferred format)")
                question_text = question_match1.group(2)
            elif question_match2:
                logger.info("Found question with format '1?' (numbered question)")
                question_text = question_match2.group(2)
            elif question_emoji_match:
                logger.info("Found question with emoji prefix (special format)")
                # Extract only the part of the text up to the question mark
                question_end = line.find('?') + 1
                question_text = line[:question_end].strip()
                
                # IMPORTANT: Skip any text after the question mark completely
                # This ensures only the question itself is used
                # We don't add any remaining text as an option or question
                remaining_text = line[question_end:].strip()
                if remaining_text:
                    logger.info(f"Completely ignoring text after emoji-prefixed question mark: '{remaining_text}'")
            elif question_match3:
                logger.info("Found question with format ending with ?")
                # Extract only the part of the text up to the question mark
                question_end = line.find('?') + 1
                question_text = line[:question_end].strip()
                
                # IMPORTANT: Skip any text after the question mark completely
                # This ensures only the question itself is used
                # We don't add any remaining text as an option or question
                remaining_text = line[question_end:].strip()
                if remaining_text:
                    logger.info(f"Completely ignoring text after question mark: '{remaining_text}'")
            elif hindi_match:
                logger.info("Found Hindi question with question mark")
                # For Hindi, also try to extract just the question portion
                if '?' in line:
                    question_end = line.find('?') + 1
                    question_text = line[:question_end].strip()
                    
                    # IMPORTANT: Skip any text after the question mark completely
                    # This ensures only the question itself is used in Hindi questions too
                    remaining_text = line[question_end:].strip()
                    if remaining_text:
                        logger.info(f"Completely ignoring text after Hindi question mark: '{remaining_text}'")
                else:
                    question_text = line
            else:
                # This shouldn't happen based on the if condition, but just in case
                question_text = line
            
            # Ensure it has a question mark at the end if it doesn't already
            if not question_text.endswith('?'):
                if '?' not in question_text:
                    question_text += '?'
            
            if len(question_text) > MAX_QUESTION_LENGTH:
                question_text = question_text[:MAX_QUESTION_LENGTH-3] + "..."
                logger.info(f"Truncated question text to {MAX_QUESTION_LENGTH} characters")
            
            current_question = question_text
            current_options = []
            correct_answer = None
            processing_options = True  # Now we expect options to follow
            continue
        
        # Check if line is an option in standard format (A), B., etc.
        option_match = option_pattern.match(line)
        hindi_option_match = hindi_option_pattern.match(line) if any(char in line for char in "कखगघ१२३४") else None
        
        if option_match or hindi_option_match:
            if processing_options:  # Only process options if we're expecting them after a question
                if option_match:
                    # Handle both standard format and fancy Unicode format (【𝗔】)
                    # Get the first non-None group from groups 1-4, which represent different option formats
                    option_letter = option_match.group(1) or option_match.group(2) or option_match.group(3) or option_match.group(4)
                    if option_letter in "𝗔𝗕𝗖𝗗":
                        # Convert fancy Unicode to standard letter
                        option_letter = chr(ord('A') + "𝗔𝗕𝗖𝗗".index(option_letter))
                    
                    option_letter = option_letter.upper()
                    # The last group will always be the option text (after the option letter)
                    option_text = option_match.group(5).strip() if option_match.group(5) else ""
                    
                    logger.info(f"Found option {option_letter}: {option_text[:30]}...")
                    
                    # Clean up any emojis or special characters from the beginning and end
                    option_text = re.sub(r'^[👉✨✳️☑️◼︎▪️♦️🔮🔺🔹🔸◽️🔘◆▫️🔳🟥🟩🟦🟪🟨⬛️◾️✴️🔱🧡❤️✅🥀]|[👉✨✳️☑️◼︎▪️♦️🔮🔺🔹🔸◽️🔘◆▫️🔳🟥🟩🟦🟪🟨⬛️◾️✴️🔱🧡❤️✅🥀]$', '', option_text).strip()
                    
                    # Remove promotional text patterns - expanded with more patterns
                    promo_patterns = [
                        r'Ex:.*$',  # Explanation text
                        r'★★.*★★',  # Decorative stars
                        r'^\s*https?://\S+\s*$',  # URLs at start of line
                        r'\s*BY\s+VIPIN\s+SHARMA\s+GAUR.*',  # Credit text
                        r'\s*𝐁𝐘\s+𝐕𝐈𝐏𝐈𝐍\s+𝐒𝐇𝐀𝐑𝐌𝐀\s+𝐆𝐀𝐔𝐑.*',  # Fancy credit text
                        r'.*CREATE\s+BY.*GROUP\s+OWNER.*',  # Group credits
                        r'\s*JOIN\s*:.*$',  # Join group text
                        r'.*@[A-Za-z0-9_]+.*',  # Telegram usernames
                        r'.*t\.me/[A-Za-z0-9_]+.*',  # Telegram links
                        r'.*IMPORTANT\s+QUESTION.*BY\s+SHARMA.*',  # Credit titles
                        r'.*QUESTION\s+RAJ\s+GK\s+BY.*',  # Credit titles
                        r'.*♦|👉.*𝐁𝐘.*',  # BY with emoji prefixes
                        r'^\s*[0-9\-]+\s*$',  # Remove lines with just numbers
                        r'.*पढ़ें\s+वही\s+जो\s+परीक्षा\s+में\s+आए.*',  # Hindi text about exams
                        r'.*#[a-zA-Z0-9_]+.*',  # Hashtags
                        r'.*\<ggn>.*\</ggn>.*',  # HTML-like tags
                        r'.*\.me/.*',  # Any domain links with .me/
                        r'RT:.*',  # Retweet-style text
                        r'.*join\s+everyone.*',  # Join group invitations
                        r'.*शिक्षक\s+भर्ती\s+चैनल.*',  # Teacher recruitment channel (Hindi)
                        r'.*GK_RAJASTHA_N.*',  # Specific channel name
                        r'.*\b(?:WHATSAPP|TELEGRAM)\b.*',  # Social media references 
                        r'.*👍.*',  # Thumbs up emoji
                        r'.*(?:SUBSCRIBE|LIKE|SHARE).*',  # Social media actions
                        r'^\d+\.\s*\d+\.\s*\d+\s*$',  # Date patterns like 18.04.2025
                        r'.*𝐈𝐌𝐏𝐎𝐑𝐓𝐀𝐍𝐓\s+𝐐𝐔𝐄𝐒𝐓𝐈𝐎𝐍.*',  # Important question banners
                        r'.*\[\s*[A-Za-z0-9_\s\-]+\s*\].*',  # Text in square brackets like [EXAM NAME]
                        r'.*𝐁𝐞𝐬𝐭\s+𝐄𝐝𝐮𝐜𝐚𝐭𝐢𝐨𝐧\s+𝐂𝐡𝐚𝐧𝐧𝐞𝐥.*',  # Educational channel banners
                        r'.*▋.*',  # Lines with decorative block characters
                        r'.*𝐏𝐀𝐓𝐖𝐀𝐑\s+𝐇𝐈𝐆𝐇\s+𝐂𝐎𝐔𝐑𝐓.*',  # Specific exam related text
                        r'.*राजस्थान\s+का\s+सबसे\s+भरोसेमंद\s+चैनल.*',  # Hindi channel promotional text
                        r'.*(?:नाम\s+ही\s+काफी\s+है|Enquiry|Promotion|Advertising|Contact).*',  # Marketing text
                        r'.*Admin\s*:.*',  # Admin contact information
                        r'.*(?:🔱|🔥|✍️).*',  # Posts with decorative emojis
                        r'.*𝐕𝐤_𝐯𝐞𝐫𝐦𝐚\d+.*'  # Specific username pattern
                    ]
                    for pattern in promo_patterns:
                        option_text = re.sub(pattern, '', option_text, flags=re.IGNORECASE).strip()
                                            
                elif hindi_option_match:
                    # Get the Hindi letter from either group 1 or 2
                    hindi_letter = hindi_option_match.group(1) or hindi_option_match.group(2)
                    option_letter = hindi_to_english.get(hindi_letter, 'A')
                    # The last group is always the option text
                    option_text = hindi_option_match.group(3).strip()
                    logger.info(f"Detected Hindi option {hindi_letter} (mapped to {option_letter})")
                else:
                    # This shouldn't happen but just in case
                    continue
                
                # Check if this option is marked as correct with an asterisk or check mark
                if option_text.endswith('*') or option_text.endswith('✓') or option_text.endswith('✔') or option_text.endswith('✅'):
                    option_text = re.sub(r'[\*✓✔✅]$', '', option_text).strip()
                    correct_answer = "ABCD".index(option_letter)
                    logger.info(f"Found marked correct answer: {option_letter}")
                
                # Truncate option if too long
                if len(option_text) > MAX_OPTION_LENGTH:
                    option_text = option_text[:MAX_OPTION_LENGTH-3] + "..."
                    logger.info(f"Truncated option {option_letter} to {MAX_OPTION_LENGTH} characters")
                
                # Don't add "Answer:" lines as options - include Hindi answer patterns
                if not any(option_text.lower().startswith(ans) for ans in ("ans:", "answer:", "ans", "answer", "उत्तर", "सही उत्तर", "जवाब", "उत्तर:", "जवाब:")):
                    # Check if we've already hit the maximum number of options
                    if len(current_options) >= MAX_OPTIONS_COUNT:
                        logger.warning(f"Maximum number of options ({MAX_OPTIONS_COUNT}) reached, ignoring option {option_letter}")
                        continue
                        
                    # Get index for this option letter
                    try:
                        option_index = "ABCD".index(option_letter)
                        
                        # Ensure we don't exceed maximum number of options
                        if option_index >= MAX_OPTIONS_COUNT:
                            logger.warning(f"Option index {option_index} exceeds maximum allowed ({MAX_OPTIONS_COUNT}), ignoring")
                            continue
                            
                        # Ensure options list has enough slots
                        while len(current_options) <= option_index:
                            current_options.append("")
                        
                        current_options[option_index] = option_text
                        logger.info(f"Added option {option_letter}: {option_text}")
                    except ValueError:
                        # Invalid option letter, just append to list if we haven't reached the limit
                        if len(current_options) < MAX_OPTIONS_COUNT:
                            current_options.append(option_text)
                            logger.info(f"Added fallback option: {option_text}")
                        else:
                            logger.warning(f"Maximum number of options ({MAX_OPTIONS_COUNT}) reached, ignoring additional option")
            continue
        
        # Check if line indicates the correct answer (multiple patterns for Hindi and English)
        answer_match1 = answer_pattern1.match(line)
        answer_match2 = answer_pattern2.match(line)  # Asterisk pattern (A) option*
        answer_match3 = answer_pattern3.match(line)
        answer_match4 = answer_pattern4.match(line)  # Hindi pattern उत्तर (A)
        answer_match5 = answer_pattern5.match(line)  # Hindi pattern उत्तर A
        
        if answer_match1 or answer_match2 or answer_match3 or answer_match4 or answer_match5:
            # Find the first matching pattern
            match_to_use = None
            for match in [answer_match1, answer_match2, answer_match3, answer_match4, answer_match5]:
                if match:
                    match_to_use = match
                    break
                    
            if match_to_use:
                answer_letter = match_to_use.group(1).upper()
                logger.info(f"Found answer indicator with letter: {answer_letter}")
                
                try:
                    correct_answer = "ABCD".index(answer_letter)
                    logger.info(f"Found correct answer: {answer_letter} (index {correct_answer})")
                except ValueError:
                    logger.warning(f"Invalid answer letter {answer_letter}, defaulting to A")
                    correct_answer = 0
            
            continue
        
        # If not a new question or option, append to current question, but respect max length
        if current_question:
            if len(current_question) < MAX_QUESTION_LENGTH:
                # Only append if we're not already at max length
                new_text = current_question + " " + line
                if len(new_text) > MAX_QUESTION_LENGTH:
                    # If appending would make it too long, truncate
                    current_question = new_text[:MAX_QUESTION_LENGTH-3] + "..."
                    logger.info("Truncated question text after appending line")
                else:
                    current_question = new_text
    
    # Add the last question if it exists
    if current_question and current_options:
        if correct_answer is not None:
            # Make sure options list has at least 2 items (Telegram requirement)
            while len(current_options) < 2:
                current_options.append("(No option provided)")
            
            # Validate correct_answer is within range of options
            if correct_answer is not None and (correct_answer < 0 or correct_answer >= len(current_options)):
                logger.warning(f"Invalid answer index {correct_answer}, defaulting to 0")
                correct_answer = 0
            
            questions.append({
                "question": current_question[:MAX_QUESTION_LENGTH] if len(current_question) > MAX_QUESTION_LENGTH else current_question,
                "options": current_options.copy(),
                "answer": correct_answer,
                "category": "Imported"
            })
    
    return questions

def add_questions_with_id(custom_id, questions_list):
    """
    Add questions with a custom ID
    Returns the number of questions added
    """
    try:
        # Ensure custom_id is treated as a string to avoid dictionary key issues
        custom_id = str(custom_id)
        logger.info(f"Adding questions with ID (after conversion): {custom_id}, Type: {type(custom_id)}")
        
        # Additional data validation to catch any issues
        if not questions_list:
            logger.error("Empty questions list passed to add_questions_with_id")
            return 0
        
        # Validate questions before adding them - filter out invalid ones
        valid_questions = []
        for q in questions_list:
            # Check if question text is not empty and has at least 2 options
            if q.get('question') and len(q.get('options', [])) >= 2:
                # Make sure all required fields are present and non-empty
                if all(key in q and q[key] is not None for key in ['question', 'options', 'answer']):
                    # Make sure the question text is not empty
                    if q['question'].strip() != '':
                        # Make sure all options have text
                        if all(opt.strip() != '' for opt in q['options']):
                            valid_questions.append(q)
                            continue
            logger.warning(f"Skipped invalid question: {q}")
        
        if not valid_questions:
            logger.error("No valid questions found after validation!")
            return 0
            
        logger.info(f"Validated questions: {len(valid_questions)} of {len(questions_list)} are valid")
            
        # Load existing questions
        questions = load_questions()
        logger.info(f"Loaded existing questions dictionary, keys: {list(questions.keys())}")
        
        # Check if custom ID already exists
        if custom_id in questions:
            logger.info(f"ID {custom_id} exists in questions dict")
            # If the ID exists but isn't a list, convert it to a list
            if not isinstance(questions[custom_id], list):
                questions[custom_id] = [questions[custom_id]]
                logger.info(f"Converted existing entry to list for ID {custom_id}")
            # Add the new questions to the list
            original_len = len(questions[custom_id])
            questions[custom_id].extend(valid_questions)
            logger.info(f"Extended question list from {original_len} to {len(questions[custom_id])} items")
        else:
            # Create a new list with these questions
            questions[custom_id] = valid_questions
            logger.info(f"Created new entry for ID {custom_id} with {len(valid_questions)} questions")
        
        # Save the updated questions
        logger.info(f"Saving updated questions dict with {len(questions)} IDs")
        save_questions(questions)
        
        return len(valid_questions)
    except Exception as e:
        logger.error(f"Error in add_questions_with_id: {str(e)}", exc_info=True)
        return 0

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Basic command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("stop", stop_quiz_command))
    application.add_handler(CommandHandler("stats", stats_command))  # This calls extended_stats_command
    application.add_handler(CommandHandler("delete", delete_command))
    
    # NEGATIVE MARKING ADDITION: Add new command handlers
    application.add_handler(CommandHandler("negmark", negative_marking_settings))
    application.add_handler(CommandHandler("resetpenalty", reset_user_penalty_command))
    application.add_handler(CallbackQueryHandler(negative_settings_callback, pattern=r"^neg_mark_"))
    
    # PDF IMPORT ADDITION: Add new command handlers
    application.add_handler(CommandHandler("pdfinfo", pdf_info_command))
    application.add_handler(CommandHandler("quizid", quiz_with_id_command))
    
    # PDF import conversation handler
    pdf_import_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("pdfimport", pdf_import_command)],
        states={
            PDF_UPLOAD: [MessageHandler(filters.Document.ALL, pdf_file_received)],
            PDF_CUSTOM_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, pdf_custom_id_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(pdf_import_conv_handler)
    
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
    
    # TXT Import Command Handler
    # Use the same TXT import states defined at the top level
    # No need to redefine them here
    
    # Text Import conversation handler - simplified without custom ID step
    txtimport_handler = ConversationHandler(
        entry_points=[CommandHandler("txtimport", txtimport_start)],
        states={
            TXT_UPLOAD: [
                MessageHandler(filters.Document.ALL, receive_txt_file),
                CommandHandler("cancel", txtimport_cancel),
            ],
            # No TXT_CUSTOM_ID state - we'll automatically generate an ID instead
        },
        fallbacks=[CommandHandler("cancel", txtimport_cancel)],
    )
    application.add_handler(txtimport_handler)
    
    # Start the Bot
    application.run_polling()

if __name__ == "__main__":
    main()
