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
- Added bulk import feature for multiple questions
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
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7631768276:AAFWUidQIXRnw-CLxaNAPvc0YGef6u1iZWQ")

# Conversation states
QUESTION, OPTIONS, ANSWER, CATEGORY = range(4)
EDIT_SELECT, EDIT_QUESTION, EDIT_OPTIONS = range(4, 7)
CLONE_URL, CLONE_MANUAL = range(7, 9)
CUSTOM_ID = range(9, 10)

# PDF import conversation states (use high numbers to avoid conflicts)
PDF_UPLOAD, PDF_CUSTOM_ID, PDF_PROCESSING = range(100, 103)

# Bulk Import conversation states
BULK_IMPORT_PASTE_QUESTIONS, BULK_IMPORT_CONFIRM, BULK_IMPORT_CATEGORY = range(300, 303)

# Example formats to show the user for bulk import
BULK_IMPORT_EXAMPLE_FORMATS = """
Examples of supported formats:

Format 1:
Q: What is the capital of France?
A) Berlin
B) Madrid
C) Paris
D) Rome
Answer: C

Format 2:
1. Which planet is known as the Red Planet?
1) Venus
2) Mars
3) Jupiter
4) Saturn
Correct: 2

Format 3:
Question: Who wrote "Romeo and Juliet"?
Options:
- Charles Dickens
- Jane Austen
- William Shakespeare
- Mark Twain
Answer: William Shakespeare
"""

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
        "• 📋 <b>Bulk Import:</b> /bulkimport\n"
        "• ℹ️ <b>Help & Commands:</b> /help\n\n"
        
        "📄 <b>𝗣𝗗𝗙 𝗜𝗺𝗽𝗼𝗿𝘁 & Custom ID:</b>\n"
        "• 📥 <b>Import from PDF:</b> /pdfimport\n"
        "• 🆔 <b>Start Quiz by ID:</b> /quizid\n"
        "• ℹ️ <b>PDF Info:</b> /pdfinfo\n\n"
        
        "⚙️ <b>𝗔𝗱𝘃𝗮𝗻𝗰𝗲𝗱 𝗤𝘂𝗶𝘇 𝗦𝗲𝘁𝘁𝗶𝗻𝗴𝘀:</b>\n"
        "• ⚙️ <b>Negative Marking:</b> /negmark\n"
        "• 🧹 <b>Reset Penalties:</b> /resetpenalty\n"
    )
    await update.message.reply_html(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "📚 <b>Quiz Bot Commands Guide</b>\n\n"
        "<b>Quiz Participation:</b>\n"
        "• /quiz - Start random quiz\n"
        "• /quizid - Start quiz with specific ID\n"
        "• /stop - Stop current quiz\n\n"
        
        "<b>Question Management:</b>\n"
        "• /add - Add a new question\n"
        "• /edit - Edit existing question\n"
        "• /delete - Delete a question\n"
        "• /pdfimport - Import questions from PDF\n"
        "• /bulkimport - Import multiple questions at once\n"
        "• /poll2q - Convert poll to question\n\n"
        
        "<b>User Stats:</b>\n"
        "• /stats - View your performance\n"
        "• /allstats - View top performers\n"
        "• /extendedstats - Includes penalties\n\n"
        
        "<b>Negative Marking:</b>\n"
        "• /negmark - Configure negative marking\n"
        "• /resetpenalty - Reset penalty points\n\n"
        
        "<b>Information:</b>\n"
        "• /start - Bot introduction\n"
        "• /help - This help message\n"
        "• /pdfinfo - PDF import instructions\n\n"
        
        "<b>Advanced:</b>\n"
        "You can forward polls to convert them into questions!"
    )
    await update.message.reply_html(help_text)

# ---------- BULK IMPORT FUNCTIONS ----------
async def bulkimport_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the bulk import conversation."""
    user = update.effective_user
    
    # Store an empty list for parsed questions
    context.user_data['parsed_questions'] = []
    
    await update.message.reply_html(
        f"Hi {user.mention_html()}! Let's import multiple questions at once.\n\n"
        f"Please paste your questions below. I can recognize several common formats.\n"
        f"{BULK_IMPORT_EXAMPLE_FORMATS}\n\n"
        f"Type /cancel to abort the import process."
    )
    
    return BULK_IMPORT_PASTE_QUESTIONS

async def parse_bulk_questions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Parse the pasted questions."""
    text = update.message.text
    
    if not text or text.strip() == "":
        await update.message.reply_text("Please paste some questions or type /cancel.")
        return BULK_IMPORT_PASTE_QUESTIONS
    
    # Placeholder for parsed questions
    parsed_questions = []
    
    # Split text into potential question blocks
    # We'll try different splitting strategies
    blocks = []
    
    # Try to split by "Q:" or "Question:" pattern
    if "Q:" in text or "Question:" in text or re.search(r"\b[0-9]+\.", text):
        # Split by question markers
        split_pattern = r"(?:^|\n)(?:Q:|Question:|[0-9]+\.)\s"
        question_blocks = re.split(split_pattern, text, flags=re.MULTILINE)
        
        # Filter out empty blocks and re-add the Q: prefix for consistency
        for block in question_blocks:
            if block.strip():
                blocks.append(block.strip())
    else:
        # If no obvious question markers, try to analyze line by line
        lines = text.split('\n')
        current_block = []
        
        for line in lines:
            line = line.strip()
            if not line:
                if current_block:
                    blocks.append('\n'.join(current_block))
                    current_block = []
            else:
                current_block.append(line)
        
        if current_block:
            blocks.append('\n'.join(current_block))
    
    # Process each block
    for block in blocks:
        question_data = parse_question_block(block)
        if question_data:
            parsed_questions.append(question_data)
    
    # Store parsed questions in context
    context.user_data['parsed_questions'] = parsed_questions
    
    if not parsed_questions:
        await update.message.reply_text(
            "I couldn't parse any questions from your text. Please check the format and try again.\n\n"
            f"{BULK_IMPORT_EXAMPLE_FORMATS}\n\n"
            "Type /cancel to abort the import process."
        )
        return BULK_IMPORT_PASTE_QUESTIONS
    
    # Show a summary of what was parsed
    summary = f"✅ Successfully parsed {len(parsed_questions)} questions:\n\n"
    
    for i, q in enumerate(parsed_questions[:5], 1):
        summary += f"{i}. {q['question'][:50]}{'...' if len(q['question']) > 50 else ''}\n"
    
    if len(parsed_questions) > 5:
        summary += f"...and {len(parsed_questions) - 5} more\n"
    
    keyboard = [
        [
            InlineKeyboardButton("✓ Confirm Import", callback_data="confirm_import"),
            InlineKeyboardButton("✗ Cancel", callback_data="cancel_import"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(summary, reply_markup=reply_markup)
    
    return BULK_IMPORT_CONFIRM

def parse_question_block(text):
    """Parse a single question block into the required format."""
    # Initialize empty question data
    question_data = {
        "question": "",
        "options": [],
        "correct_answer": None,
        "category": "General Knowledge"  # Default category
    }
    
    # Extract the question text
    question_match = re.search(r"^(?:Q:|Question:|[0-9]+\.)\s*(.*?)(?:\n|\?|$)", text, re.IGNORECASE)
    if question_match:
        question_data["question"] = question_match.group(1).strip()
        if not question_data["question"].endswith("?"):
            question_data["question"] += "?"
    else:
        return None
    
    # Extract options - try different patterns
    
    # Pattern 1: A) Option, B) Option...
    options_pattern1 = re.findall(r"(?:^|\n)([A-D])[).:]\s*(.*?)(?=\n[A-D][).:]\s*|\n(?:Answer|Correct)|$)", text, re.DOTALL)
    
    # Pattern 2: 1) Option, 2) Option...
    # Split by line to process more intelligently
    lines = text.strip().split('\n')
    options_pattern2 = []
    question_pattern = re.match(r"^\s*([0-9]+)[.]\s+(.*)", lines[0]) if lines else None
    
    # Process each line that has a numeric prefix
    for line in lines:
        # Skip lines with question number or answer
        if line == lines[0] and question_pattern:
            continue
        if re.search(r"(?:Answer|Correct)", line, re.IGNORECASE):
            continue
            
        # Look for numbered options
        option_match = re.match(r"^\s*([1-4])[).:]\s+(.*)", line)
        if option_match:
            options_pattern2.append((option_match.group(1), option_match.group(2)))
    
    # Pattern 3: - Option (bullet points)
    options_pattern3 = re.findall(r"(?:^|\n)(?:Options:)?\s*(?:[-•*])\s*(.*?)(?=\n[-•*]\s*|\n(?:Answer|Correct)|$)", text, re.DOTALL)
    
    if options_pattern1:
        for letter, option in options_pattern1:
            question_data["options"].append(option.strip())
        
        # Look for the correct answer (letter)
        answer_match = re.search(r"(?:Answer|Correct)[^A-D]*([A-D])", text, re.IGNORECASE)
        if answer_match:
            letter = answer_match.group(1).upper()
            # Convert letter to index (A=0, B=1, etc.)
            correct_index = ord(letter) - ord('A')
            if 0 <= correct_index < len(question_data["options"]):
                question_data["correct_answer"] = correct_index
            
    elif options_pattern2:
        # Check if we need to skip the first option (when the question and first option might be the same)
        question_text = question_data["question"].strip('?').lower()
        all_options = []
        
        for number, option_text in options_pattern2:
            # We need to check if the option matches the question itself
            option_clean = option_text.strip().lower()
            if option_clean != question_text:
                all_options.append(option_text.strip())
        
        question_data["options"] = all_options
        
        # Look for the correct answer (number)
        answer_match = re.search(r"(?:Answer|Correct)[^1-4]*([1-4])", text, re.IGNORECASE)
        if answer_match:
            number = answer_match.group(1)
            # Convert to index (1=0, 2=1, etc.)
            correct_index = int(number) - 1
            if 0 <= correct_index < len(all_options):
                question_data["correct_answer"] = correct_index
            
    elif options_pattern3:
        question_data["options"] = [option.strip() for option in options_pattern3]
        
        # Look for the correct answer (text)
        answer_match = re.search(r"(?:Answer|Correct)[^A-Za-z]*(.+?)$", text, re.IGNORECASE | re.MULTILINE)
        if answer_match:
            correct_text = answer_match.group(1).strip()
            # Find the matching option
            for i, option in enumerate(question_data["options"]):
                if option.lower() == correct_text.lower() or option.lower().startswith(correct_text.lower()):
                    question_data["correct_answer"] = i
                    break
    
    # If we have options but no correct answer, try one more method
    if question_data["options"] and question_data["correct_answer"] is None:
        # Look for any mention of "correct" near an option
        for i, option in enumerate(question_data["options"]):
            if re.search(r"(?:correct|right|✓|✅)", option, re.IGNORECASE):
                question_data["correct_answer"] = i
                # Remove the "correct" marker from the option text
                clean_option = re.sub(r"\s*(?:correct|right|✓|✅).*", "", option, flags=re.IGNORECASE)
                question_data["options"][i] = clean_option.strip()
                break
    
    # Validate the parsed question
    if not question_data["question"] or not question_data["options"] or question_data["correct_answer"] is None:
        return None
    
    return question_data

async def confirm_bulk_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the confirmation of import."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_import":
        await query.edit_message_text("Import canceled. No questions were added.")
        return ConversationHandler.END
    
    # Prepare to ask for category
    categories = [
        "General Knowledge", "Science", "History", 
        "Geography", "Entertainment", "Sports"
    ]
    
    keyboard = []
    for category in categories:
        keyboard.append([InlineKeyboardButton(category, callback_data=f"cat_{category}")])
    
    # Add a "Skip" option to use default category
    keyboard.append([InlineKeyboardButton("Skip (use default)", callback_data="cat_skip")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Please select a category for all {len(context.user_data['parsed_questions'])} questions:",
        reply_markup=reply_markup
    )
    
    return BULK_IMPORT_CATEGORY

async def assign_bulk_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Assign a category to all questions and save them."""
    query = update.callback_query
    await query.answer()
    
    parsed_questions = context.user_data.get('parsed_questions', [])
    
    if not parsed_questions:
        await query.edit_message_text("No questions to import. The process has been canceled.")
        return ConversationHandler.END
    
    # Extract category from callback data
    if query.data == "cat_skip":
        category = "General Knowledge"  # Default
    else:
        category = query.data[4:]  # Remove "cat_" prefix
    
    # Load existing questions
    questions = load_questions()
    
    # Track how many questions were successfully added
    added_count = 0
    
    # Get the next question ID
    next_id = get_next_question_id()
    
    # Add each parsed question
    for question_data in parsed_questions:
        # Assign the selected category
        question_data["category"] = category
        
        # Add to questions dictionary
        add_question_with_id(next_id, question_data)
        next_id += 1
        added_count += 1
    
    # Provide success feedback
    await query.edit_message_text(
        f"✅ Success! Added {added_count} new questions to the '{category}' category.\n\n"
        f"You can now use these questions in quizzes with the /quiz command."
    )
    
    # Clear user data
    context.user_data.pop('parsed_questions', None)
    
    return ConversationHandler.END

async def cancel_bulk_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the bulk import conversation."""
    await update.message.reply_text("Bulk import canceled. No questions were added.")
    
    # Clear user data
    context.user_data.pop('parsed_questions', None)
    
    return ConversationHandler.END
# ---------- END BULK IMPORT FUNCTIONS ----------

# Your existing code here (include all your other command functions)

def main() -> None:
    """Start the bot."""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add conversation handler with the states
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", start_add_question)],
        states={
            QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, question_text)],
            OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, question_options)],
            ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, question_answer)],
            CATEGORY: [CallbackQueryHandler(question_category)],
            CUSTOM_ID: [
                CallbackQueryHandler(question_id_method),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, 
                    question_custom_id,
                    lambda update, context: context.user_data.get('awaiting_id', False)
                )
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(conv_handler)
    
    # Add basic command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("delete", delete_question))
    application.add_handler(CommandHandler("stats", view_stats))
    application.add_handler(CommandHandler("extendedstats", view_extended_stats))
    application.add_handler(CommandHandler("resetpenalty", reset_penalty))
    application.add_handler(CommandHandler("negmark", negative_marking))
    application.add_handler(CallbackQueryHandler(negmark_callback, pattern=r"^negmark_"))
    
    # Add quiz command handlers
    application.add_handler(CommandHandler("quiz", start_quiz))
    application.add_handler(CommandHandler("quizid", start_quiz_by_id))
    application.add_handler(CommandHandler("stop", stop_quiz))
    
    # Add poll handlers
    application.add_handler(PollAnswerHandler(handle_poll_answer))
    application.add_handler(CommandHandler("poll2q", convert_poll_to_question))
    
    # Add quiz editing handler
    application.add_handler(CommandHandler("edit", edit_question_start))
    application.add_handler(CallbackQueryHandler(edit_question_handler, pattern=r"^edit_"))
    
    # PDF import handler
    pdf_import_handler = ConversationHandler(
        entry_points=[CommandHandler("pdfimport", pdf_import_start)],
        states={
            PDF_UPLOAD: [MessageHandler(filters.DOCUMENT, pdf_file_handler)],
            PDF_CUSTOM_ID: [
                CallbackQueryHandler(pdf_id_method, pattern=r"^pdf_id_"),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, 
                    pdf_custom_id_handler,
                    lambda update, context: context.user_data.get('awaiting_pdf_id', False)
                )
            ],
            PDF_PROCESSING: [CallbackQueryHandler(pdf_process_handler, pattern=r"^pdf_process")]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(pdf_import_handler)
    application.add_handler(CommandHandler("pdfinfo", pdf_info))
    
    # Add bulk import conversation handler
    bulk_import_handler = ConversationHandler(
        entry_points=[CommandHandler("bulkimport", bulkimport_command)],
        states={
            BULK_IMPORT_PASTE_QUESTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, parse_bulk_questions),
            ],
            BULK_IMPORT_CONFIRM: [
                CallbackQueryHandler(confirm_bulk_import, pattern=r"^(confirm|cancel)_import$"),
            ],
            BULK_IMPORT_CATEGORY: [
                CallbackQueryHandler(assign_bulk_category, pattern=r"^cat_"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_bulk_import)]
    )
    application.add_handler(bulk_import_handler)
    
    # Start the Bot
    application.run_polling()
    
if __name__ == "__main__":
    main()