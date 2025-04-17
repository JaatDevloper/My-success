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
        "<b>𝗛𝗲𝗿𝗲’𝘀 𝘄𝗵𝗮𝘁 𝘆𝗼𝘂 𝗰𝗮𝗻 𝗱𝗼:</b>\n"
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
        "• ⚡ <b>Quick Scrape Website:</b> /quickscrape\n"
        "• 📝 <b>Import Text Questions:</b> /textimport\n"
        "• 🔍 <b>Test URL Fetch:</b> /debugfetch\n"
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
        logger.warning(f"Quiz not active for chat {chat_id}, cannot send question {question_index}")
        return
    
    questions = quiz.get("questions", [])
    
    if not questions:
        logger.error(f"No questions found in quiz data for chat {chat_id}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Error: No questions found for this quiz. Please try another ID."
        )
        return
    
    if question_index >= len(questions):
        # End of quiz
        logger.info(f"Reached end of questions ({question_index} >= {len(questions)}), ending quiz")
        await end_quiz(context, chat_id)
        return
    
    # Get current question
    question = questions[question_index]
    
    # Debug log
    logger.info(f"Sending question {question_index+1}/{len(questions)} to chat {chat_id}")
    logger.info(f"Question data: {question}")
    
    try:
        # Make sure question has all required fields
        if "question" not in question or "options" not in question or "answer" not in question:
            logger.error(f"Question {question_index} is missing required fields: {question}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ Error: Question {question_index+1} has invalid format. Skipping to next question."
            )
            
            # Try to send the next question
            if question_index + 1 < len(questions):
                await send_question(context, chat_id, question_index + 1)
            else:
                await end_quiz(context, chat_id)
            return
        
        # Ensure options is a list of strings
        options = question["options"]
        if not isinstance(options, list):
            logger.error(f"Options is not a list for question {question_index}: {options}")
            
            # Try to convert if it's another format
            if isinstance(options, str):
                options = options.split('\n')
            else:
                logger.error(f"Cannot send question with invalid options: {options}")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Error: Question {question_index+1} has invalid options format. Skipping to next question."
                )
                
                # Try to send the next question
                if question_index + 1 < len(questions):
                    await send_question(context, chat_id, question_index + 1)
                else:
                    await end_quiz(context, chat_id)
                return
        
        # Make sure answer is a valid index
        if not isinstance(question["answer"], int) or question["answer"] < 0 or question["answer"] >= len(options):
            logger.error(f"Invalid answer index {question['answer']} for question {question_index}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ Error: Question {question_index+1} has invalid answer index. Skipping to next question."
            )
            
            # Try to send the next question
            if question_index + 1 < len(questions):
                await send_question(context, chat_id, question_index + 1)
            else:
                await end_quiz(context, chat_id)
            return
        
        # Send the poll
        message = await context.bot.send_poll(
            chat_id=chat_id,
            question=question["question"],
            options=options,
            type="quiz",
            correct_option_id=question["answer"],
            is_anonymous=False,
            open_period=25  # Close poll after 25 seconds
        )
        
        # Confirm poll was sent
        logger.info(f"Successfully sent poll for question {question_index+1} to chat {chat_id}")
        
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
            logger.info(f"Scheduling next question ({question_index+1}) for chat {chat_id}")
            asyncio.create_task(schedule_next_question(context, chat_id, question_index + 1))
        else:
            # Last question, schedule end of quiz
            logger.info(f"Last question sent, scheduling end of quiz for chat {chat_id}")
            asyncio.create_task(schedule_end_quiz(context, chat_id))
            
    except Exception as e:
        # Log the error
        logger.error(f"Error sending question {question_index} to chat {chat_id}: {str(e)}")
        tb_import = __import__('traceback')
        logger.error(f"Traceback: {tb_import.format_exc()}")
        
        # Notify the user
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Error sending question: {str(e)}\nTrying to continue with next question..."
        )
        
        # Try to send the next question
        if question_index + 1 < len(questions):
            await send_question(context, chat_id, question_index + 1)
        else:
            await end_quiz(context, chat_id)

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
    
    quiz_id = context.args[0]
    
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

# ====== Web Scraping Functions ======
def is_valid_url(url):
    """Check if a URL is valid"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def fetch_url_content(url):
    """Fetch content from a URL with proper headers"""
    try:
        # Log URL fetching attempt
        logger.info(f"Attempting to fetch URL: {url}")
        
        # Handle AMP URLs by attempting to get the original URL if possible
        original_url = url
        
        # Special handling for Google AMP cache URLs
        if 'google.com/amp' in url or 'ampproject.org' in url or '/amp/' in url:
            try:
                # Try to extract the original URL from Google AMP
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                # Get the AMP page first
                logger.info(f"Detected AMP URL, attempting to fetch AMP content: {url}")
                amp_response = requests.get(url, headers=headers, timeout=15)
                amp_response.raise_for_status()
                
                # Look for canonical link
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(amp_response.text, 'html.parser')
                canonical = soup.find('link', rel='canonical')
                if canonical and canonical.get('href'):
                    original_url = canonical.get('href')
                    logger.info(f"Redirecting from AMP to original URL: {original_url}")
                else:
                    # If no canonical URL found, just use the AMP content
                    logger.info("No canonical URL found, using AMP content directly")
                    return amp_response.text
            except Exception as e:
                logger.warning(f"Failed to extract original URL from AMP: {e}, continuing with AMP URL")
                # If fetching the AMP page failed, we'll still try the original URL below
        
        # Headers that mimic a real browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,hi;q=0.8',  # Added Hindi language preference
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
            'Referer': 'https://www.google.com/'  # Adding referrer to help with some sites
        }
        
        logger.info(f"Fetching content from URL: {original_url}")
        
        # Try different methods if the standard request fails
        try:
            # Standard method
            response = requests.get(original_url, headers=headers, timeout=20)
            response.raise_for_status()
            
            # Check if the response is valid HTML
            if response.text and len(response.text) > 0:
                logger.info(f"Successfully fetched content from URL using standard method: {original_url}")
                return response.text
            else:
                logger.warning(f"Empty response from {original_url}")
        except Exception as e:
            logger.warning(f"Standard method failed: {e}, trying fallback methods")
            
            # Fallback 1: Try with a different user agent
            try:
                mobile_headers = {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9,hi;q=0.8',
                }
                logger.info(f"Trying with mobile user agent: {original_url}")
                response = requests.get(original_url, headers=mobile_headers, timeout=15)
                if response.status_code == 200 and response.text:
                    logger.info(f"Mobile user agent method succeeded: {original_url}")
                    return response.text
            except Exception as mobile_e:
                logger.warning(f"Mobile user agent method failed: {mobile_e}")
                
            # Fallback 2: Try with a session to handle cookies and redirects
            try:
                logger.info(f"Trying with session method: {original_url}")
                session = requests.Session()
                session.headers.update(headers)
                response = session.get(original_url, timeout=15)
                if response.status_code == 200 and response.text:
                    logger.info(f"Session method succeeded: {original_url}")
                    return response.text
            except Exception as session_e:
                logger.warning(f"Session method failed: {session_e}")
        
        # If we got here, all methods failed
        logger.error(f"All methods failed to fetch URL: {url}")
        return None
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error fetching URL {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching URL {url}: {e}")
        return None

def extract_text_with_trafilatura(html_content):
    """Extract main text content using trafilatura"""
    try:
        text = trafilatura.extract(html_content)
        return text
    except Exception as e:
        logger.error(f"Error extracting text with trafilatura: {e}")
        return None

def extract_questions_from_text(text):
    """Extract questions, options, and answers from text content"""
    if not text:
        return []
    
    questions = []
    lines = text.split('\n')
    
    current_question = None
    current_options = []
    current_answer = None
    in_hindi = False
    
    # Check if text contains Hindi
    hindi_range = range(0x0900, 0x097F + 1)
    for char in text:
        if ord(char) in hindi_range:
            in_hindi = True
            break
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        
        # Check for question pattern (Q1, 1., Question 1, etc. and Hindi patterns प्रश्न 1)
        if in_hindi:
            # Hindi question patterns (प्र. 1, प्रश्न 1, etc.)
            q_match = re.search(r'(?:^|\s*)((?:प्र|प्रश्न)?\s*\d+\.?\s*)(.*?)(?:\?|\.|$)', line)
        else:
            # English question patterns
            q_match = re.search(r'(?:^|\s*)((?:Q|Question)?\s*\d+\.?\s*)(.*?)(?:\?|\.|$)', line, re.IGNORECASE)
        
        if q_match:
            # Save previous question if exists
            if current_question:
                questions.append({
                    'question': current_question,
                    'options': current_options,
                    'answer': current_answer
                })
            
            # Start new question
            current_question = q_match.group(2).strip()
            if not current_question.endswith('?') and not current_question.endswith('.'):
                current_question += '?'
            current_options = []
            current_answer = None
            continue
        
        # Check for numbered questions without prefix (1. What is...)
        if not q_match and current_question is None:
            numbered_q = re.search(r'^\s*(\d+\.?\s*)(.*?)(?:\?|\.|$)', line)
            if numbered_q:
                current_question = numbered_q.group(2).strip()
                if not current_question.endswith('?') and not current_question.endswith('.'):
                    current_question += '?'
                current_options = []
                current_answer = None
                continue
        
        # Check for options (A) Option, B. Option, etc.) - including Hindi options (क, ख, ग, घ)
        opt_match = None
        
        if in_hindi:
            # Hindi options: क, ख, ग, घ with various separators
            opt_match = re.search(r'^\s*([क-घ])[\.)\s]+(.*)', line)
            if opt_match and current_question:
                # Convert Hindi option letters to English A-D
                hindi_to_eng = {'क': 'A', 'ख': 'B', 'ग': 'C', 'घ': 'D'}
                option_letter = hindi_to_eng.get(opt_match.group(1), 'A')
                option_text = opt_match.group(2).strip()
                current_options.append((option_letter, option_text))
                continue
        
        # Try English options if Hindi didn't match or not in Hindi
        opt_match = re.search(r'^\s*([A-D])[\.)\s]+(.*)', line, re.IGNORECASE)
        if opt_match and current_question:
            option_letter = opt_match.group(1).upper()
            option_text = opt_match.group(2).strip()
            current_options.append((option_letter, option_text))
            continue
            
        # Check for numbered options (1. Option, 2. Option)
        if current_question and len(current_options) < 4:
            num_opt_match = re.search(r'^\s*(\d+)[\.)\s]+(.*)', line)
            if num_opt_match:
                num = int(num_opt_match.group(1))
                if 1 <= num <= 4:  # Only accept options 1-4
                    # Convert to A-D format
                    option_letter = chr(64 + num)  # 1->A, 2->B, etc.
                    option_text = num_opt_match.group(2).strip()
                    current_options.append((option_letter, option_text))
                    continue
        
        # Check for answer indicator - various patterns in English and Hindi
        if in_hindi:
            # Hindi answer patterns (उत्तर: क, सही उत्तर: ख, etc.)
            ans_match = re.search(r'(?:उत्तर|सही|उत्त)[:\s]+([क-घ])', line)
            if ans_match and current_question:
                hindi_to_eng = {'क': 'A', 'ख': 'B', 'ग': 'C', 'घ': 'D'}
                current_answer = hindi_to_eng.get(ans_match.group(1), 'A')
                continue
                
        # English answer patterns
        ans_match = re.search(r'(?:answer|correct|ans)[:\s]+([A-D])', line, re.IGNORECASE)
        if ans_match and current_question:
            current_answer = ans_match.group(1).upper()
            continue
            
        # Try to find the answer pattern in format "Answer: Option text"
        if current_question and current_options and not current_answer:
            for ans_pattern in ["answer is ", "correct answer is ", "answer: ", "correct: "]:
                if ans_pattern in line.lower():
                    # Try to match option text with the line
                    for idx, (opt_letter, opt_text) in enumerate(current_options):
                        # Safely compare by checking if the option text appears in the line
                        if opt_text and opt_text.lower() in line.lower():
                            current_answer = opt_letter
                            break
                    if current_answer:
                        break
    
    # Add the last question
    if current_question:
        questions.append({
            'question': current_question,
            'options': current_options,
            'answer': current_answer
        })
    
    return questions

def scrape_quiz_content(url):
    """Main function to scrape quiz content from a URL"""
    if not WEB_SCRAPING_SUPPORT:
        return [], "Web scraping support is not available. Please install requests, beautifulsoup4, and trafilatura."
    
    if not is_valid_url(url):
        return [], "Invalid URL format."
    
    # Special handling for AMP pages
    is_amp_page = 'amp' in url.lower() or '/amp/' in url.lower()
    
    html_content = fetch_url_content(url)
    if not html_content:
        return [], "Failed to fetch content from URL."
    
    # Extract text content from HTML
    text_content = extract_text_with_trafilatura(html_content)
    if not text_content:
        return [], "Failed to extract text content from URL."
    
    # Extract questions from text
    questions = extract_questions_from_text(text_content)
    
    # If no questions found or it's an AMP page, try alternate methods
    if not questions or is_amp_page:
        # Try using BeautifulSoup for specific website patterns
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Special handling for AMP pages
            if is_amp_page:
                # Look for content in AMP-specific elements
                amp_content = []
                for tag in soup.select('p, li, h2, h3, h4, div.question, div.mcq'):
                    text = tag.get_text(strip=True)
                    if text:
                        amp_content.append(text)
                
                # Join all content and try to extract questions again
                if amp_content:
                    amp_text = "\n".join(amp_content)
                    amp_questions = extract_questions_from_text(amp_text)
                    if amp_questions:
                        questions.extend(amp_questions)
            
            # Look for common question patterns if still no questions
            if not questions:
                question_elements = soup.select('.question, .quiz-question, .mcq, .question-text, .wp-block-query, li.question, div.que')
                
                if question_elements:
                    for q_elem in question_elements:
                        question_text = q_elem.get_text(strip=True)
                        
                        # Look for options near the question
                        option_elements = q_elem.find_next_siblings('div', class_=lambda c: c and ('option' in c.lower() or 'answer' in c.lower()))
                        
                        options = []
                        for i, opt in enumerate(option_elements[:4]):  # Limit to 4 options (A-D)
                            opt_text = opt.get_text(strip=True)
                            if opt_text:
                                options.append((chr(65 + i), opt_text))  # A, B, C, D
                        
                        if options:
                            questions.append({
                                'question': question_text,
                                'options': options,
                                'answer': None  # We can't reliably determine correct answer
                            })
            
            # If still no questions, look for numbered lists that might be questions
            if not questions:
                # Find paragraphs with numbers at the beginning
                potential_questions = []
                paragraphs = soup.find_all(['p', 'li', 'div'])
                
                for p in paragraphs:
                    text = p.get_text(strip=True)
                    # Look for numbered items that might be questions
                    if re.match(r'^\d+[\.\)]', text) or text.startswith('Q') or text.startswith('प्रश्न'):
                        potential_questions.append(text)
                
                if potential_questions:
                    combined_text = "\n".join(potential_questions)
                    numbered_questions = extract_questions_from_text(combined_text)
                    if numbered_questions:
                        questions.extend(numbered_questions)
                        
        except Exception as e:
            logger.error(f"Error using BeautifulSoup parser: {e}")
    
    if questions:
        return questions, None
    else:
        return [], "No questions found in the content."

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
    option_letters = []
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
        r'^([A-D])\.?\s+(.+)',  # A. Option text
        r'^\(([A-D])\)\s+(.+)',  # (A) Option text
        r'^([a-d])\.?\s+(.+)',  # a. Option text
        r'^\(([a-d])\)\s+(.+)',  # (a) Option text
        r'^(\d+)\.?\s+(.+)',  # 1. Option text
        r'^\((\d+)\)\s+(.+)',  # (1) Option text
        # Hindi specific patterns
        r'^(पहला)\s*विकल्प\s*:?\s+(.+)',  # पहला विकल्प: Option text
        r'^(दूसरा)\s*विकल्प\s*:?\s+(.+)',  # दूसरा विकल्प: Option text
        r'^(तीसरा)\s*विकल्प\s*:?\s+(.+)',  # तीसरा विकल्प: Option text
        r'^(चौथा)\s*विकल्प\s*:?\s+(.+)',  # चौथा विकल्प: Option text
        # Universal option markers for Hindi
        r'^विकल्प\s+([क-घ])\s*:?\s+(.+)',  # विकल्प क: Option text
        r'^([क-घ])\.?\s+(.+)',  # क. Option text
        r'^\(([क-घ])\)\s+(.+)',  # (क) Option text
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
                # Map the correct answer letter to index
                correct_index = 0  # Default to first option
                if correct_answer:
                    # Try to find the correct answer in our options
                    for idx, (letter, _) in enumerate(current_options):
                        if letter.lower() == correct_answer.lower():
                            correct_index = idx
                            break
                
                # Create question data structure
                q_data = {
                    'question': current_question,
                    'options': current_options.copy(),
                    'correct_answer': correct_index
                }
                questions.append(q_data)
            
            # Reset for new question
            current_options = []
            option_letters = []
            correct_answer = None
            in_options_section = False
            option_count = 0
        
        # If this is a question line, set it as current question
        if is_question:
            current_question = line
            in_options_section = True  # Options likely follow the question
        elif current_question:
            # Check if this line contains an option
            for pattern in option_patterns:
                match = re.match(pattern, line)
                if match:
                    letter = match.group(1)
                    option_text = match.group(2).strip()
                    
                    # Prevent duplicate options (keep first occurrence)
                    if letter not in option_letters and option_text:
                        current_options.append((letter, option_text))
                        option_letters.append(letter)
                        option_count += 1
                    break
            
            # Check if this line indicates the correct answer
            for pattern in answer_patterns:
                match = re.match(pattern, line)
                if match:
                    correct_answer = match.group(2)
                    break
        
        i += 1
    
    # Don't forget to save the last question if any
    if current_question and current_options:
        # Map the correct answer letter to index
        correct_index = 0  # Default to first option
        if correct_answer:
            # Try to find the correct answer in our options
            for idx, (letter, _) in enumerate(current_options):
                if letter.lower() == correct_answer.lower():
                    correct_index = idx
                    break
        
        # Create question data structure
        q_data = {
            'question': current_question,
            'options': current_options.copy(),
            'correct_answer': correct_index
        }
        questions.append(q_data)
    
    return questions
    # ====== Web Scraping Commands ======
# Define conversation states for web scraping
WEB_URL, WEB_CATEGORY, WEB_CUSTOM_ID, WEB_CONFIRM = range(200, 204)

# Quick scrape command to directly scrape and save question

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
    
    # Get category (optional)
    category = "Web Scraped"
    if len(context.args) >= 2:
        category = context.args[1]
    
    # Get custom ID (optional)
    custom_id = None
    if len(context.args) >= 3:
        try:
            custom_id = int(context.args[2])
        except ValueError:
            await update.message.reply_text(
                "⚠️ Custom ID must be a number. Using auto-generated ID instead."
            )
    
    # Acknowledge receipt of command
    status_message = await update.message.reply_text(
        f"⏳ Quick scraping started for: {url}\n"
        f"Category: {category}\n"
        f"Custom ID: {custom_id if custom_id is not None else 'Auto-generated'}\n\n"
        "This may take a moment..."
    )
    
    try:
        # Log the URL being processed
        logger.info(f"Quick scraping URL: {url}")
        
        # First test URL accessibility
        try:
            test_content = fetch_url_content(url)
            if test_content:
                await status_message.edit_text(
                    f"⏳ Quick scraping: {url}\n"
                    f"✅ URL is accessible\n"
                    f"Now extracting questions..."
                )
            else:
                await status_message.edit_text(
                    f"⏳ Quick scraping: {url}\n"
                    f"⚠️ URL not directly accessible, trying alternative methods..."
                )
        except Exception as e:
            logger.error(f"URL test failed in quickscrape: {str(e)}")
            await status_message.edit_text(
                f"⏳ Quick scraping: {url}\n"
                f"⚠️ URL test failed, trying alternative methods..."
            )
        
        # Try to scrape content
        questions, error = scrape_quiz_content(url)
        
        if error:
            logger.error(f"Error in quickscrape for URL {url}: {error}")
            await status_message.edit_text(
                f"❌ Error scraping URL: {error}\n\n"
                "Please check the URL or try /debugfetch to diagnose the issue."
            )
            return
        
        if not questions:
            await status_message.edit_text(
                "❌ No questions found on the website.\n\n"
                "The URL was accessible but no quiz questions could be identified."
            )
            return
        
        # Format the questions
        formatted_questions = format_questions_for_bot(questions, category)
        
        if not formatted_questions:
            await status_message.edit_text(
                "❌ Failed to format questions.\n\n"
                "Questions were found but could not be properly formatted."
            )
            return
        
        # Get question ID to use
        question_id = custom_id if custom_id is not None else get_next_question_id()
        
        # Save questions
        for question in formatted_questions:
            add_question_with_id(question_id, question)
        
        # Success message
        await status_message.edit_text(
            f"✅ Success! Quick scrape completed.\n\n"
            f"• URL: {url}\n"
            f"• Category: {category}\n"
            f"• Questions imported: {len(formatted_questions)}\n"
            f"• ID: {question_id}\n\n"
            f"You can use these questions in a quiz with:\n"
            f"/quizid {question_id}"
        )
        
    except Exception as e:
        # Log and report any errors
        logger.error(f"Unexpected error in quickscrape for URL {url}: {str(e)}")
        tb_import = __import__('traceback')
        logger.error(f"Traceback: {tb_import.format_exc()}")
        
        await status_message.edit_text(
            f"❌ An unexpected error occurred during quick scrape: {str(e)}\n\n"
            "Please try the /webscrape command for a more interactive approach."
        )

# Debugging function to test URL fetching
async def debug_fetch_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Debug command to test URL fetching directly"""
    # Check if URL is provided as argument
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "Please provide a URL to test, e.g., /debugfetch https://example.com"
        )
        return
    
    url = context.args[0]
    
    # If URL doesn't start with http:// or https://, add https://
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
        await update.message.reply_text(
            f"🔄 Added 'https://' to your URL. Using: {url}"
        )
    
    status_message = await update.message.reply_text(
        f"⏳ Testing URL fetch for: {url}"
    )
    
    try:
        # Fetch the content
        html_content = fetch_url_content(url)
        
        if html_content:
            # Get length and preview
            content_length = len(html_content)
            preview = html_content[:500] + "..." if content_length > 500 else html_content
            
            await status_message.edit_text(
                f"✅ Successfully fetched URL!\n"
                f"Content length: {content_length} characters\n\n"
                f"Preview of first 500 characters:\n```\n{preview}\n```",
                parse_mode='Markdown'
            )
            
            # Try extracting text
            text_content = extract_text_with_trafilatura(html_content)
            if text_content:
                text_preview = text_content[:500] + "..." if len(text_content) > 500 else text_content
                await update.message.reply_text(
                    f"✅ Text extraction successful!\n"
                    f"Extracted text length: {len(text_content)} characters\n\n"
                    f"Preview:\n```\n{text_preview}\n```",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    "⚠️ Failed to extract text with trafilatura."
                )
        else:
            await status_message.edit_text(
                f"❌ Failed to fetch URL: {url}\n"
                "Check logs for more details."
            )
    except Exception as e:
        await status_message.edit_text(
            f"❌ Error testing URL: {str(e)}"
        )

# Define states for text import
TEXT_INPUT, TEXT_CATEGORY, TEXT_CUSTOM_ID, TEXT_CONFIRM = range(300, 304)

async def text_import_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the text import process to manually add formatted questions"""
    await update.message.reply_text(
        "📝 <b>Text Import for Quiz Questions</b>\n\n"
        "Please paste your questions in the following format:\n\n"
        "<code>Question text?\n"
        "(A) Option A\n"
        "(B) Option B\n"
        "(C) Option C\n"
        "(D) Option D\n"
        "उत्तर (B)</code>\n\n"
        "You can add multiple questions at once. Make sure to separate them with empty lines.\n\n"
        "<i>Send /cancel to abort this operation.</i>",
        parse_mode='HTML'
    )
    
    # Start conversation for text import
    context.application.add_handler(ConversationHandler(
        entry_points=[],  # Empty because we're starting it manually
        states={
            TEXT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, text_import_received)],
            TEXT_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, text_category_received)],
            TEXT_CUSTOM_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, text_custom_id_received)],
            TEXT_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, text_confirm_import)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="text_import_conversation"
    ))
    
    return TEXT_INPUT

async def text_import_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the received text with questions"""
    text = update.message.text.strip()
    
    if not text:
        await update.message.reply_text(
            "⚠️ Empty text received. Please paste your questions in the required format."
        )
        return TEXT_INPUT
    
    # Parse questions from text
    questions = parse_formatted_questions(text)
    
    if not questions:
        await update.message.reply_text(
            "❌ No valid questions found in the text.\n\n"
            "Please make sure your questions follow the required format:\n\n"
            "Question text?\n"
            "(A) Option A\n"
            "(B) Option B\n"
            "(C) Option C\n"
            "(D) Option D\n"
            "उत्तर (B)"
        )
        return TEXT_INPUT
    
    # Store questions in context
    context.user_data['text_questions'] = questions
    
    # Show a preview of parsed questions
    preview_text = f"✅ Successfully parsed {len(questions)} questions!\n\n"
    
    # Show a preview of the first 3 questions
    for i, q in enumerate(questions[:3]):
        preview_text += f"Q{i+1}: {q['question']}\n"
        for j, opt in enumerate(q['options']):
            option_letter = chr(65 + j)  # A, B, C, D
            preview_text += f"  ({option_letter}) {opt}\n"
        
        if q['answer'] is not None:
            answer_letter = chr(65 + q['answer'])
            preview_text += f"  Answer: ({answer_letter})\n"
        
        preview_text += "\n"
    
    if len(questions) > 3:
        preview_text += f"...and {len(questions) - 3} more questions.\n\n"
    
    preview_text += "Now, please enter a category for these questions (e.g., Science, History, General):"
    
    await update.message.reply_text(preview_text)
    
    return TEXT_CATEGORY

async def text_category_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save category and ask for custom ID"""
    category = update.message.text.strip()
    
    # Store category in context
    context.user_data['text_category'] = category
    
    # Ask for custom ID
    await update.message.reply_text(
        "🆔 Optional: Enter a custom ID number for these questions.\n"
        "This helps you organize questions into groups. Leave empty for auto-assignment."
    )
    
    return TEXT_CUSTOM_ID

async def text_custom_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom ID input"""
    custom_id_text = update.message.text.strip()
    
    # Check if custom ID is valid or empty
    if custom_id_text:
        if not custom_id_text.isdigit():
            await update.message.reply_text(
                "⚠️ Custom ID must be a number. Please enter a numeric ID or leave empty for auto-assignment."
            )
            return TEXT_CUSTOM_ID
        
        custom_id = int(custom_id_text)
        context.user_data['text_custom_id'] = custom_id
    else:
        context.user_data['text_custom_id'] = None
    
    # Format questions and ask for confirmation
    questions = context.user_data['text_questions']
    category = context.user_data['text_category']
    
    # Format the questions for the bot
    formatted_questions = []
    for q in questions:
        formatted_question = {
            "question": q['question'],
            "options": q['options'],
            "answer": q['answer'],
            "category": category
        }
        formatted_questions.append(formatted_question)
    
    # Store formatted questions in context
    context.user_data['formatted_questions'] = formatted_questions
    
    # Ask for confirmation
    custom_id_info = f"Custom ID: {context.user_data['text_custom_id']}" if context.user_data['text_custom_id'] else "Auto-assigned ID"
    
    await update.message.reply_text(
        f"📝 <b>Summary:</b>\n"
        f"• {len(formatted_questions)} questions ready to import\n"
        f"• Category: {category}\n"
        f"• {custom_id_info}\n\n"
        f"Type 'yes' to confirm and save these questions to your quiz bot database.",
        parse_mode='HTML'
    )
    
    return TEXT_CONFIRM

async def text_confirm_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save imported questions to the database"""
    response = update.message.text.strip().lower()
    
    if response != 'yes':
        await update.message.reply_text(
            "❌ Import cancelled. No questions were saved.\n"
            "You can start over with /textimport or use /help to see all commands."
        )
        # Remove the conversation handler
        for handler in context.application.handlers[0]:
            if isinstance(handler, ConversationHandler) and handler.name == "text_import_conversation":
                context.application.handlers[0].remove(handler)
                break
        return ConversationHandler.END
    
    # Extract data from context
    formatted_questions = context.user_data['formatted_questions']
    custom_id = context.user_data.get('text_custom_id')
    
    # Add questions to database
    question_id = custom_id if custom_id else get_next_question_id()
    
    for question in formatted_questions:
        add_question_with_id(question_id, question)
    
    # Confirm success
    await update.message.reply_text(
        f"✅ Successfully imported {len(formatted_questions)} questions with ID: {question_id}\n\n"
        f"You can use these questions in a quiz with:\n"
        f"/quizid {question_id}"
    )
    
    # Clear context data
    context.user_data.clear()
    
    # Remove the conversation handler
    for handler in context.application.handlers[0]:
        if isinstance(handler, ConversationHandler) and handler.name == "text_import_conversation":
            context.application.handlers[0].remove(handler)
            break
    
    return ConversationHandler.END

def parse_formatted_questions(text):
    """Parse questions in the format provided by the user"""
    questions = []
    
    # Split text into separate questions
    question_blocks = re.split(r'\n\s*\n', text)
    
    for block in question_blocks:
        if not block.strip():
            continue
        
        # Try to extract question, options, and answer
        lines = block.strip().split('\n')
        if len(lines) < 2:
            continue
        
        question_text = lines[0].strip()
        
        # Extract options and answer
        options = []
        answer_index = None
        
        # Find options marked with (A), (B), etc. or A), B), etc.
        option_pattern = r'^\s*[\(]?([A-Da-d])[\)\.:]?\s+(.+)$'
        answer_pattern = r'^\s*(?:उत्तर|Answer|Ans)[:\s]*[\(]?([A-Da-d])[\)\.:]?'
        
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            
            # Check if this is an option
            option_match = re.match(option_pattern, line)
            if option_match:
                option_letter = option_match.group(1).upper()
                option_text = option_match.group(2).strip()
                
                # Calculate option index (A=0, B=1, etc.)
                option_index = ord(option_letter) - ord('A')
                
                # Fill in any missing options
                while len(options) < option_index:
                    options.append(f"Option {len(options)+1}")
                
                options.append(option_text)
                continue
            
            # Check if this is the answer
            answer_match = re.match(answer_pattern, line)
            if answer_match:
                answer_letter = answer_match.group(1).upper()
                answer_index = ord(answer_letter) - ord('A')
        
        # Only add if we have a question, options, and answer
        if question_text and options:
            if answer_index is None or answer_index < 0 or answer_index >= len(options):
                answer_index = 0  # Default to first option if answer is invalid
            
            questions.append({
                'question': question_text,
                'options': options,
                'answer': answer_index
            })
    
    return questions

async def web_scrape_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start web scraping import process"""
    if not WEB_SCRAPING_SUPPORT:
        await update.message.reply_text(
            "⚠️ Web scraping support is not available.\n"
            "Please install required packages: requests, beautifulsoup4, and trafilatura."
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "🔍 <b>Web Scraping for Quiz Questions</b>\n\n"
        "Please send me the URL of a website containing quiz questions.\n"
        "I'll try to extract questions, options, and answers automatically.\n\n"
        "Example URLs:\n"
        "• Quiz websites\n"
        "• Educational sites with quizzes\n"
        "• Blog posts containing Q&A\n\n"
        "<i>Send /cancel to abort this operation.</i>",
        parse_mode='HTML'
    )
    
    return WEB_URL

async def web_url_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the received URL"""
    url = update.message.text.strip()
    
    # If URL doesn't start with http:// or https://, add https://
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
        await update.message.reply_text(
            f"🔄 Added 'https://' to your URL. Using: {url}"
        )
    
    # Store URL in context
    context.user_data['scrape_url'] = url
    
    if not is_valid_url(url):
        await update.message.reply_text(
            "⚠️ Invalid URL format. Please enter a valid URL like example.com or https://example.com\n"
            "Try again or send /cancel to abort."
        )
        return WEB_URL
    
    # Acknowledge receipt of URL and that processing will start
    status_message = await update.message.reply_text(
        "⏳ Scraping questions from the website... This may take a moment."
    )
    
    # First, try to get a simple fetch response to confirm the URL is accessible
    try:
        test_content = fetch_url_content(url)
        if test_content:
            await status_message.edit_text(
                "✅ Successfully connected to the URL. Now extracting questions..."
            )
        else:
            await status_message.edit_text(
                "⚠️ Could not fetch content from the URL. Trying alternative methods..."
            )
    except Exception as e:
        logger.error(f"Initial fetch test failed: {str(e)}")
        await status_message.edit_text(
            "⚠️ Initial connection test failed. Trying alternative methods..."
        )
    
    try:
        # Log the URL being processed (for debugging)
        logger.info(f"Scraping URL: {url}")
        
        # Use direct non-async approach first for reliability
        try:
            # Try direct approach first (more reliable in some cases)
            logger.info("Trying direct scraping approach")
            questions, error = scrape_quiz_content(url)
            
            if questions:
                logger.info(f"Direct scraping successful, found {len(questions)} questions")
            else:
                logger.warning("Direct scraping found no questions, will try async approach")
        except Exception as direct_error:
            logger.error(f"Direct scraping failed: {str(direct_error)}")
            questions, error = [], f"Direct approach failed: {str(direct_error)}"
                
        # If direct approach fails, try async approach
        if not questions:
            try:
                logger.info("Trying async scraping approach")
                # Scrape content with a timeout to prevent hanging
                import asyncio
                
                # Use a separate thread for the blocking scrape operation
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor() as pool:
                    questions, error = await asyncio.get_event_loop().run_in_executor(
                        pool, lambda: scrape_quiz_content(url)
                    )
                
                if questions:
                    logger.info(f"Async scraping successful, found {len(questions)} questions")
                else:
                    logger.warning("Async scraping found no questions")
            except Exception as async_error:
                logger.error(f"Async scraping failed: {str(async_error)}")
                if not error:
                    error = f"Async approach failed: {str(async_error)}"
        
        # Update status message to confirm scraping results
        if questions:
            await status_message.edit_text("✅ Website scraped successfully. Processing extracted questions...")
        else:
            await status_message.edit_text("⚠️ Scraping complete but no questions were found.")
        
        if error and not questions:
            logger.error(f"Error scraping URL {url}: {error}")
            await update.message.reply_text(
                f"❌ Error: {error}\n\n"
                "Please try a different URL or try the /debugfetch command to test URL accessibility.\n"
                "Send /cancel to abort."
            )
            return WEB_URL
        
        if not questions:
            await update.message.reply_text(
                "❌ No questions found on the website.\n\n"
                "The URL was accessible but no quiz questions could be identified.\n"
                "Try a different URL or send /cancel to abort."
            )
            return WEB_URL
        
        # Store questions in context
        context.user_data['scraped_questions'] = questions
        
        # Show a preview of scraped questions
        preview_text = f"✅ Successfully scraped {len(questions)} questions!\n\n"
        
        # Show a preview of the first 3 questions
        for i, q in enumerate(questions[:3]):
            preview_text += f"Q{i+1}: {q['question']}\n"
            for j, (opt_letter, opt_text) in enumerate(q['options']):
                preview_text += f"  {opt_letter}) {opt_text}\n"
            
            if q['answer']:
                preview_text += f"  Answer: {q['answer']}\n"
            
            preview_text += "\n"
        
        if len(questions) > 3:
            preview_text += f"...and {len(questions) - 3} more questions.\n\n"
        
        preview_text += "Now, please enter a category for these questions (e.g., Science, History, General):"
        
        await update.message.reply_text(preview_text)
        
        return WEB_CATEGORY
        
    except Exception as e:
        # Catch any unexpected errors to prevent the bot from crashing
        logger.error(f"Unexpected error scraping URL {url}: {str(e)}")
        tb_import = __import__('traceback')
        logger.error(f"Traceback: {tb_import.format_exc()}")
        
        await update.message.reply_text(
            f"❌ An unexpected error occurred while scraping: {str(e)}\n\n"
            "If you've been waiting a long time, the process might have timed out.\n"
            "Please try a different URL or use /debugfetch first to test URL accessibility.\n"
            "Send /cancel to abort."
        )
        return WEB_URL

async def web_category_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save category and ask for custom ID"""
    category = update.message.text.strip()
    
    # Store category in context
    context.user_data['scrape_category'] = category
    
    # Ask for custom ID
    await update.message.reply_text(
        "🆔 Optional: Enter a custom ID number for these questions.\n"
        "This helps you organize questions into groups. Leave empty for auto-assignment."
    )
    
    return WEB_CUSTOM_ID

async def web_custom_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom ID input"""
    custom_id_text = update.message.text.strip()
    
    # Check if custom ID is valid or empty
    if custom_id_text:
        if not custom_id_text.isdigit():
            await update.message.reply_text(
                "⚠️ Custom ID must be a number. Please enter a numeric ID or leave empty for auto-assignment."
            )
            return WEB_CUSTOM_ID
        
        custom_id = int(custom_id_text)
        context.user_data['scrape_custom_id'] = custom_id
    else:
        context.user_data['scrape_custom_id'] = None
    
    # Format questions and ask for confirmation
    questions = context.user_data['scraped_questions']
    category = context.user_data['scrape_category']
    
    formatted_questions = format_questions_for_bot(questions, category)
    
    # Store formatted questions in context
    context.user_data['formatted_questions'] = formatted_questions
    
    # Ask for confirmation
    custom_id_info = f"Custom ID: {context.user_data['scrape_custom_id']}" if context.user_data['scrape_custom_id'] else "Auto-assigned ID"
    
    await update.message.reply_text(
        f"📝 <b>Summary:</b>\n"
        f"• {len(formatted_questions)} questions ready to import\n"
        f"• Category: {category}\n"
        f"• {custom_id_info}\n\n"
        f"Type 'yes' to confirm and save these questions to your quiz bot database.",
        parse_mode='HTML'
    )
    
    return WEB_CONFIRM

async def web_confirm_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save imported questions to the database"""
    response = update.message.text.strip().lower()
    
    if response != 'yes':
        await update.message.reply_text(
            "❌ Import cancelled. No questions were saved.\n"
            "You can start over with /webscrape or use /help to see all commands."
        )
        return ConversationHandler.END
    
    # Extract data from context
    formatted_questions = context.user_data['formatted_questions']
    custom_id = context.user_data.get('scrape_custom_id')
    
    # Add questions to database
    question_id = custom_id if custom_id else get_next_question_id()
    
    for question in formatted_questions:
        add_question_with_id(question_id, question)
    
    # Confirm success
    await update.message.reply_text(
        f"✅ Successfully imported {len(formatted_questions)} questions with ID: {question_id}\n\n"
        f"You can use these questions in a quiz with:\n"
        f"/quizid {question_id}"
    )
    
    # Clear context data
    context.user_data.clear()
    
    return ConversationHandler.END

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
    
    # Debugging commands
    application.add_handler(CommandHandler("debugfetch", debug_fetch_url))
    application.add_handler(CommandHandler("quickscrape", quick_scrape_command))
    
    # NEGATIVE MARKING ADDITION: Add new command handlers
    application.add_handler(CommandHandler("negmark", negative_marking_settings))
    application.add_handler(CommandHandler("resetpenalty", reset_user_penalty_command))
    application.add_handler(CallbackQueryHandler(negative_settings_callback, pattern=r"^neg_mark_"))
    
    # PDF IMPORT ADDITION: Add new command handlers
    application.add_handler(CommandHandler("pdfinfo", pdf_info_command))
    application.add_handler(CommandHandler("quizid", quiz_with_id_command))
    application.add_handler(CommandHandler("textimport", text_import_command))
    
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
    
    # Web scraping conversation handler
    web_scrape_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("webscrape", web_scrape_command)],
        states={
            WEB_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, web_url_received)],
            WEB_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, web_category_received)],
            WEB_CUSTOM_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, web_custom_id_received)],
            WEB_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, web_confirm_import)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(web_scrape_conv_handler)
    
    # Poll Answer Handler - CRITICAL for tracking all participants
    application.add_handler(PollAnswerHandler(poll_answer))
    
    # Start the Bot
    application.run_polling()

if __name__ == "__main__":
    main()
