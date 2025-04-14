"""
Telegram Quiz Bot with negative marking functionality and PDF question import capability
Based on the original multi_id_quiz_bot.py but with added features for negative marking
and support for importing questions from PDF files with multilingual support (English and Hindi)
"""

import json
import logging
import os
import random
import asyncio
import io
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler, PollAnswerHandler
import pdfplumber
import langdetect

# Configure logging
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
CUSTOM_ID = 9  # Individual values instead of range
WAITING_FOR_PDF = 10  # New state for waiting for PDF file

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
        "📄 /importpdf - Import questions from a PDF file\n"  # New command
        "⚙️ /negmark - Configure negative marking settings\n"
        "🧹 /resetpenalty - Reset your penalties\n"
        "ℹ️ /help - Show this help message\n\n"
        "Let's test your knowledge with some fun quizzes!"
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
            await update.message.reply_text("⚠️ Invalid user ID. Please provide a valid numeric ID.")
    else:
        # Reset for the current user
        user_id = update.effective_user.id
        reset_user_penalties(user_id)
        await update.message.reply_text("✅ Your penalties have been reset.")

# ---------- PDF IMPORT FUNCTIONALITY ----------
# PDF parsing patterns
QUESTION_PATTERNS = [
    r'(?:Q|q)(?:uestion)?\s*(?:\.|\:)?\s*(\d+)\s*(?:\.|\:|\))?\s*(.*?)(?=(?:Q|q)(?:uestion)?\s*(?:\.|\:)?\s*\d|$)',
    r'(\d+)\s*(?:\.|\:|\))?\s*(.*?)(?=\d+\s*(?:\.|\:|\))|$)',
    r'(?<=\n)(?:\(?[a-z0-9]\)?)?\s*(.*?)\?(?=\n)'  # Matches any line ending with ?
]

OPTION_PATTERNS = [
    r'(?:[A-D]|[a-d]|[१-४])\s*(?:\.|\:|\))\s*(.*?)(?=(?:[A-D]|[a-d]|[१-४])\s*(?:\.|\:|\))|$)',
    r'(?:\([A-D]|[a-d]|[१-४]\))\s*(.*?)(?=\([A-D]|[a-d]|[१-४]\)|$)'
]

ANSWER_PATTERNS = [
    r'(?:Answer|Ans|answer|ans|उत्तर)[\s\:\.\)]*([A-Da-d१-४])',
    r'(?:Correct option|Correct|correct)[\s\:\.\)]*([A-Da-d१-४])'
]

# Hindi numeral to English conversion
HINDI_TO_ENG_NUMERALS = {
    '१': '1', '२': '2', '३': '3', '४': '4', '५': '5',
    '६': '6', '७': '7', '८': '8', '९': '9', '०': '0'
}

def detect_pdf_language(text):
    """Detect if the text is Hindi or English"""
    try:
        if any('\u0900' <= c <= '\u097F' for c in text):
            return 'hi'
        return langdetect.detect(text)
    except:
        return 'en'  # Default to English if detection fails

def extract_text_from_pdf(pdf_file):
    """Extract text from PDF file with proper encoding for multilingual support"""
    text = ""
    try:
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                # Extract text with proper character encoding
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        
        return text
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        raise ValueError(f"Failed to extract text from PDF: {str(e)}")

def parse_pdf_questions(pdf_text):
    """Parse questions from PDF text with support for English and Hindi"""
    questions = []
    is_hindi = detect_pdf_language(pdf_text) == 'hi'
    
    # Try different patterns to find questions
    for pattern in QUESTION_PATTERNS:
        matches = re.findall(pattern, pdf_text, re.DOTALL | re.MULTILINE)
        if matches:
            # We found questions with this pattern
            for match in matches:
                if isinstance(match, tuple):
                    # If the pattern captured groups
                    question_num, question_text = match
                    question_text = question_text.strip()
                else:
                    # If the pattern captured just the question text
                    question_text = match.strip()
                    question_num = len(questions) + 1
                
                if question_text:
                    # Extract options for this question
                    options = []
                    option_text = pdf_text[pdf_text.find(question_text) + len(question_text):]
                    
                    # Try to find options using patterns
                    for opt_pattern in OPTION_PATTERNS:
                        opt_matches = re.findall(opt_pattern, option_text, re.DOTALL)
                        if opt_matches:
                            option_letters = "ABCD"
                            for i, opt_match in enumerate(opt_matches[:4]):  # Limit to 4 options
                                options.append({
                                    "letter": option_letters[i],
                                    "text": opt_match.strip()
                                })
                            break
                    
                    # Find answer
                    answer = None
                    for ans_pattern in ANSWER_PATTERNS:
                        ans_match = re.search(ans_pattern, option_text, re.DOTALL)
                        if ans_match:
                            answer = ans_match.group(1).upper()
                            # Convert Hindi numeral if needed
                            if answer in HINDI_TO_ENG_NUMERALS:
                                answer = HINDI_TO_ENG_NUMERALS[answer]
                            break
                    
                    # Only add valid questions with options and answer
                    if options and answer:
                        questions.append({
                            "question": question_text,
                            "options": options,
                            "answer": answer,
                            "language": "hi" if is_hindi else "en"
                        })
            break
    
    return questions

def format_questions_for_bot(questions):
    """Format parsed questions to match the bot's question format"""
    formatted_questions = []
    
    for question in questions:
        # Build options list
        options = []
        correct_answer_index = None
        
        for i, option in enumerate(question["options"]):
            options.append(option["text"])
            if option["letter"] == question["answer"]:
                correct_answer_index = i
        
        # If we couldn't determine the correct answer, try by letter (A=0, B=1, etc.)
        if correct_answer_index is None and question["answer"]:
            letter_to_index = {"A": 0, "B": 1, "C": 2, "D": 3}
            if question["answer"] in letter_to_index:
                correct_answer_index = letter_to_index[question["answer"]]
        
        # Skip if still no valid answer
        if correct_answer_index is None:
            continue
        
        # Determine category (default to General Knowledge)
        category = "General Knowledge"
        if "science" in question["question"].lower():
            category = "Science"
        elif "history" in question["question"].lower():
            category = "History"
        elif "geography" in question["question"].lower():
            category = "Geography"
        elif any(term in question["question"].lower() for term in ["movie", "music", "film", "actor", "celebrity"]):
            category = "Entertainment"
        elif any(term in question["question"].lower() for term in ["sports", "game", "player", "team"]):
            category = "Sports"
        
        # Format the question for the bot
        formatted_question = {
            "question": question["question"],
            "options": options,
            "answer": correct_answer_index,
            "category": category
        }
        
        formatted_questions.append(formatted_question)
    
    return formatted_questions

def extract_and_save_pdf_questions(pdf_data):
    """Extract questions from PDF and save them to the questions file"""
    try:
        # Extract text from PDF
        pdf_text = extract_text_from_pdf(pdf_data)
        
        # Parse questions from the text
        parsed_questions = parse_pdf_questions(pdf_text)
        
        if not parsed_questions:
            return {
                "success": False,
                "message": "No valid questions found in the PDF",
                "count": 0
            }
        
        # Format questions for the bot
        formatted_questions = format_questions_for_bot(parsed_questions)
        
        if not formatted_questions:
            return {
                "success": False,
                "message": "No valid questions could be formatted for the bot",
                "count": 0
            }
        
        # Add questions to the database
        questions_added = 0
        next_id = get_next_question_id()
        
        for question in formatted_questions:
            add_question_with_id(next_id, question)
            next_id += 1
            questions_added += 1
        
        return {
            "success": True, 
            "message": f"Successfully imported {questions_added} questions",
            "count": questions_added
        }
        
    except Exception as e:
        logger.error(f"Error in PDF import process: {e}")
        return {
            "success": False,
            "message": f"Error processing PDF: {str(e)}",
            "count": 0
        }

async def import_pdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for the /importpdf command - initiates PDF import flow"""
    await update.message.reply_text(
        "📄 PDF Question Import\n\n"
        "Please send me a PDF file containing quiz questions.\n\n"
        "The PDF should contain questions in a format like:\n"
        "1. What is the capital of France?\n"
        "A. London\n"
        "B. Berlin\n"
        "C. Paris\n"
        "D. Rome\n"
        "Answer: C\n\n"
        "Hindi questions are also supported.\n"
        "Type /cancel to abort."
    )
    return WAITING_FOR_PDF

async def pdf_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle PDF file reception"""
    # Show a processing message
    processing_msg = await update.message.reply_text("⏳ Processing PDF, please wait...")
    
    try:
        # Get the PDF file from the message
        pdf_file = await update.message.document.get_file()
        pdf_bytes = await pdf_file.download_as_bytearray()
        pdf_data = io.BytesIO(pdf_bytes)
        
        # Process the PDF directly (extract questions and save them)
        result = extract_and_save_pdf_questions(pdf_data)
        
        if result["success"]:
            await processing_msg.edit_text(
                f"✅ {result['message']}\n\n"
                f"Questions successfully imported from the PDF."
            )
        else:
            await processing_msg.edit_text(
                f"❌ {result['message']}\n\n"
                "Please check the PDF format and try again."
            )
    
    except Exception as e:
        logger.error(f"Error in PDF import: {e}")
        await processing_msg.edit_text(
            f"❌ Error processing the PDF: {str(e)}\n\n"
            "Please make sure you sent a valid PDF file."
        )
    
    return ConversationHandler.END

async def cancel_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the PDF import process"""
    await update.message.reply_text("PDF import cancelled.")
    return ConversationHandler.END

def main() -> None:
    """Run the bot."""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Basic command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("stats", extended_stats_command))  # Using the extended version
    application.add_handler(CommandHandler("delete", delete_command))
    
    # NEGATIVE MARKING ADDITION: Add negative marking command handlers
    application.add_handler(CommandHandler("negmark", negative_marking_settings))
    application.add_handler(CommandHandler("resetpenalty", reset_user_penalty_command))
    application.add_handler(CallbackQueryHandler(negative_settings_callback, pattern=r"^neg_mark_"))
    
    # PDF IMPORT ADDITION: Add conversation handler for PDF import
    pdf_import_handler = ConversationHandler(
        entry_points=[CommandHandler("importpdf", import_pdf_command)],
        states={
            WAITING_FOR_PDF: [
                MessageHandler(filters.Document.PDF, pdf_received),
                CommandHandler("cancel", cancel_import),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_import)]
    )
    application.add_handler(pdf_import_handler)
    
    # Poll to question command and handlers
    application.add_handler(CommandHandler("poll2q", poll_to_question))
    application.add_handler(MessageHandler(
        filters.FORWARDED & ~filters.COMMAND, 
        handle_forwarded_poll
    ))
    application.add_handler(CallbackQueryHandler(handle_poll_answer, pattern=r"^poll_answer_"))
    application.add_handler(CallbackQueryHandler(handle_poll_id_selection, pattern=r"^poll_id_"))
    application.add_handler(CallbackQueryHandler(handle_poll_category, pattern=r"^poll_cat_"))
    
    # Add question conversation handler
    add_question_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_question_start)],
        states={
            QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_text)],
            OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_options)],
            ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_answer)],
            CUSTOM_ID: [
                CallbackQueryHandler(custom_id_callback, pattern=r"^(auto_id|custom_id)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_id_input)
            ],
            CATEGORY: [CallbackQueryHandler(category_callback, pattern=r"^category_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(add_question_handler)
    
    # Poll Answer Handler - CRITICAL for tracking all participants
    application.add_handler(PollAnswerHandler(poll_answer))

    # Run the bot until the user presses Ctrl-C
    application.run_polling()

if __name__ == "__main__":
    main()
