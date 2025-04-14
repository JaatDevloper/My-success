#!/usr/bin/env python3
"""
Enhanced Telegram Quiz Bot with PDF Import & Hindi Support
Based on the original simple_bot.py but with added PDF import features.
Supports various PDF formats and Hindi language content.

Key Features:
- PDF import with intelligent text extraction
- Hindi language support
- Negative marking
- Customizable question IDs
"""

import json
import logging
import os
import random
import tempfile
import asyncio

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler, CallbackQueryHandler, PollAnswerHandler

# Check for PyPDF2 support
try:
    import PyPDF2
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    print("PyPDF2 not installed. PDF import functionality will be limited.")
    
# Check for Pillow support
try:
    from PIL import Image, ImageEnhance
    IMAGE_SUPPORT = True
except ImportError:
    IMAGE_SUPPORT = False
    print("PIL/Pillow not installed. Image processing will be disabled.")

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
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

# Data files
QUESTIONS_FILE = "questions.json"
USERS_FILE = "users.json"
PENALTIES_FILE = "penalties.json"
TEMP_DIR = "temp_files"

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
    Enhanced language detection to identify if text contains Hindi
    Returns 'hi' if Hindi characters are detected, 'en' otherwise
    """
    if not text:
        return 'en'
        
    # Unicode ranges for Hindi (Devanagari script)
    hindi_range = range(0x0900, 0x097F + 1)
    
    # Count Hindi characters
    hindi_char_count = 0
    total_char_count = 0
    
    for char in text:
        if char.isalpha():
            total_char_count += 1
            if ord(char) in hindi_range:
                hindi_char_count += 1
    
    # If at least 10% of characters are Hindi, consider it Hindi content
    if total_char_count > 0 and (hindi_char_count / total_char_count) > 0.1:
        return 'hi'
    
    return 'en'

def start(update: Update, context: CallbackContext) -> None:
    """Send a welcome message when the command /start is issued."""
    user = update.effective_user
    welcome_text = (
        f"👋 Hello, {user.first_name}!\n\n"
        "Welcome to the Enhanced Quiz Bot with PDF Import & Hindi Support.\n\n"
        "📝 Core Features:\n"
        "💡 /quiz - Start a new quiz (auto-sequence)\n"
        "📊 /stats - View your quiz statistics with penalties\n"
        "➕ /add - Add a new question to the quiz bank\n"
        "❌ /delete - Delete a question\n\n"
        
        "📄 PDF Import Features:\n"
        "📥 /pdfimport - Import questions from a PDF file\n"
        "🆔 /quizid - Start a quiz with a specific custom ID\n"
        "ℹ️ /pdfinfo - Information about PDF import features\n\n"
        
        "🔄 Additional Features:\n"
        "⚙️ /negmark - Configure negative marking settings\n"
        "🧹 /resetpenalty - Reset your penalties\n"
        "ℹ️ /help - Show this help message\n\n"
        "Let's test your knowledge with some fun quizzes!"
    )
    update.message.reply_text(welcome_text)

def help_command(update: Update, context: CallbackContext) -> None:
    """Show help message."""
    start(update, context)

# ---------- NEGATIVE MARKING COMMAND ADDITIONS ----------
def extended_stats_command(update: Update, context: CallbackContext) -> None:
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
    
    update.message.reply_text(stats_text)

def negative_marking_settings(update: Update, context: CallbackContext) -> None:
    """Show and manage negative marking settings."""
    keyboard = [
        [InlineKeyboardButton("Enable Negative Marking", callback_data="neg_mark_enable")],
        [InlineKeyboardButton("Disable Negative Marking", callback_data="neg_mark_disable")],
        [InlineKeyboardButton("Reset All Penalties", callback_data="neg_mark_reset")],
        [InlineKeyboardButton("Back", callback_data="neg_mark_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        "🔧 Negative Marking Settings\n\n"
        "You can enable/disable negative marking or reset penalties.",
        reply_markup=reply_markup
    )

def negative_settings_callback(update: Update, context: CallbackContext) -> None:
    """Handle callback queries from negative marking settings."""
    query = update.callback_query
    query.answer()
    
    global NEGATIVE_MARKING_ENABLED
    
    if query.data == "neg_mark_enable":
        NEGATIVE_MARKING_ENABLED = True
        query.edit_message_text("✅ Negative marking has been enabled.")
    
    elif query.data == "neg_mark_disable":
        NEGATIVE_MARKING_ENABLED = False
        query.edit_message_text("✅ Negative marking has been disabled.")
    
    elif query.data == "neg_mark_reset":
        reset_user_penalties()
        query.edit_message_text("✅ All user penalties have been reset.")
    
    elif query.data == "neg_mark_back":
        # Exit settings
        query.edit_message_text("Settings closed. Use /negmark to access settings again.")

def reset_user_penalty_command(update: Update, context: CallbackContext) -> None:
    """Reset penalties for a specific user."""
    args = context.args
    
    if args and len(args) > 0:
        try:
            user_id = int(args[0])
            reset_user_penalties(user_id)
            update.message.reply_text(f"✅ Penalties for user ID {user_id} have been reset.")
        except ValueError:
            update.message.reply_text("❌ Please provide a valid numeric user ID.")
    else:
        # Reset current user's penalties
        user_id = update.effective_user.id
        reset_user_penalties(user_id)
        update.message.reply_text("✅ Your penalties have been reset.")
# ---------- END NEGATIVE MARKING COMMAND ADDITIONS ----------

# Original function (unchanged)
def stats_command(update: Update, context: CallbackContext) -> None:
    """Display user statistics."""
    # Call the extended stats command instead to show penalties
    extended_stats_command(update, context)

def add_question_start(update: Update, context: CallbackContext) -> int:
    """Start the process of adding a new question."""
    update.message.reply_text(
        "Let's add a new quiz question! First, send me the question text."
    )
    return QUESTION

def add_question_text(update: Update, context: CallbackContext) -> int:
    """Save the question text and ask for options."""
    context.user_data["new_question"] = {"question": update.message.text}
    update.message.reply_text(
        "Great! Now send me the answer options, one per line. For example:\n\n"
        "Paris\n"
        "London\n"
        "Berlin\n"
        "Rome"
    )
    return OPTIONS

def add_question_options(update: Update, context: CallbackContext) -> int:
    """Save the options and ask for the correct answer."""
    options = update.message.text.split('\n')
    context.user_data["new_question"]["options"] = options
    
    options_text = "\n".join([f"{i}. {opt}" for i, opt in enumerate(options)])
    update.message.reply_text(
        f"Options saved! Now tell me which one is correct (0-{len(options)-1}):\n\n{options_text}"
    )
    return ANSWER

def add_question_answer(update: Update, context: CallbackContext) -> int:
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
            
            update.message.reply_text(
                "How would you like to assign an ID to this question?",
                reply_markup=reply_markup
            )
            return CUSTOM_ID
        else:
            update.message.reply_text(
                f"Please enter a valid option number between 0 and {len(options)-1}."
            )
            return ANSWER
    except ValueError:
        update.message.reply_text(
            "Please enter a valid number."
        )
        return ANSWER

def custom_id_callback(update: Update, context: CallbackContext) -> int:
    """Handle ID selection method."""
    query = update.callback_query
    query.answer()
    
    if query.data == "auto_id":
        # Auto-generate ID and continue to category
        categories = ["General Knowledge", "Science", "History", "Geography", "Entertainment", "Sports"]
        keyboard = [[InlineKeyboardButton(cat, callback_data=f"category_{cat}")] for cat in categories]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
            "Select a category for this question:",
            reply_markup=reply_markup
        )
        return CATEGORY
    else:
        # Ask user to input a custom ID
        query.edit_message_text(
            "Please enter a numeric ID for this question. If the ID already exists, your question will be added to that ID without overwriting existing questions."
        )
        context.user_data["awaiting_custom_id"] = True
        return CUSTOM_ID

def custom_id_input(update: Update, context: CallbackContext) -> int:
    """Handle custom ID input."""
    try:
        custom_id = int(update.message.text)
        context.user_data["custom_id"] = custom_id
        
        # Show category selection
        categories = ["General Knowledge", "Science", "History", "Geography", "Entertainment", "Sports"]
        keyboard = [[InlineKeyboardButton(cat, callback_data=f"category_{cat}")] for cat in categories]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(
            "Select a category for this question:",
            reply_markup=reply_markup
        )
        return CATEGORY
    except ValueError:
        update.message.reply_text(
            "Please enter a valid numeric ID."
        )
        return CUSTOM_ID

def category_callback(update: Update, context: CallbackContext) -> int:
    """Handle category selection."""
    query = update.callback_query
    query.answer()
    
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
    
    query.edit_message_text(
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

def cancel(update: Update, context: CallbackContext) -> int:
    """Cancel the current operation."""
    update.message.reply_text(
        "Operation cancelled."
    )
    # Clean up any custom ID related data
    if "custom_id" in context.user_data:
        del context.user_data["custom_id"]
    if "awaiting_custom_id" in context.user_data:
        del context.user_data["awaiting_custom_id"]
    
    return ConversationHandler.END

def delete_command(update: Update, context: CallbackContext) -> None:
    """Delete a question by ID."""
    # Check if ID was provided with command
    args = context.args
    if args and len(args) > 0:
        try:
            question_id = int(args[0])
            if delete_question_by_id(question_id):
                update.message.reply_text(f"Question with ID {question_id} has been deleted.")
            else:
                update.message.reply_text(f"No question found with ID {question_id}.")
        except ValueError:
            update.message.reply_text("Please provide a valid numeric ID.")
    else:
        # If no ID provided, show list of questions
        questions = load_questions()
        if not questions:
            update.message.reply_text("No questions available to delete.")
            return
        
        message = "To delete a question, use /delete <id>. Available questions:\n\n"
        for qid, question_list in questions.items():
            if isinstance(question_list, list):
                message += f"ID: {qid} - {len(question_list)} questions\n"
            else:
                message += f"ID: {qid} - {question_list.get('question', 'Untitled')[:30]}...\n"
        
        update.message.reply_text(message)

def quiz_command(update: Update, context: CallbackContext) -> None:
    """Start a quiz session with random questions."""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    # Load all questions
    all_questions = load_questions()
    if not questions:
        update.message.reply_text("No questions available. Add some with /add first!")
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
    
    update.message.reply_text(
        f"Starting a quiz with {num_questions} questions! Questions will automatically proceed after 30 seconds.\n\n"
        f"❗ Negative marking is {negative_status} - incorrect answers will deduct points!\n\n"
        f"First question coming up..."
    )
    
    # Send first question
    send_question(context, chat_id, 0)

def send_question(context, chat_id, question_index):
    """Send a quiz question."""
    quiz = context.chat_data.get("quiz", {})
    
    if not quiz.get("active", False):
        return
    
    questions = quiz.get("questions", [])
    
    if question_index >= len(questions):
        # End of quiz
        end_quiz(context, chat_id)
        return
    
    # Get current question
    question = questions[question_index]
    
    # Send the poll
    message = context.bot.send_poll(
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
    sent_polls[poll_id] = {
        "question_index": question_index,
        "message_id": message.message_id,
        "answers": {}
    }
    quiz["sent_polls"] = sent_polls
    quiz["current_index"] = question_index
    context.chat_data["quiz"] = quiz
    
    # Schedule next question or end of quiz
    if question_index + 1 < len(questions):
        # We use job queue for v13.15
        context.job_queue.run_once(
            lambda ctx: send_question(ctx.job.context, chat_id, question_index + 1),
            30,  # 30 seconds delay
        )
    else:
        # Schedule end of quiz
        context.job_queue.run_once(
            lambda ctx: end_quiz(ctx.job.context, chat_id),
            30,  # 30 seconds delay
        )

def poll_answer(update: Update, context: CallbackContext) -> None:
    """Handle poll answers from users with negative marking."""
    # Get the answer
    poll_answer = update.poll_answer
    poll_id = poll_answer.poll_id
    user_id = poll_answer.user.id
    selected_option = poll_answer.option_ids[0] if poll_answer.option_ids else None
    
    # Get quiz state
    quiz = context.chat_data.get("quiz", {})
    sent_polls = quiz.get("sent_polls", {})
    
    # Check if this poll is part of our quiz
    if poll_id not in sent_polls:
        return
    
    # Get poll information
    poll_info = sent_polls[poll_id]
    question_index = poll_info.get("question_index")
    
    if question_index is None:
        return
    
    # Get the question
    questions = quiz.get("questions", [])
    if question_index >= len(questions):
        return
    
    question = questions[question_index]
    
    # Check if answer is correct
    correct_option = question.get("answer")
    is_correct = (selected_option == correct_option)
    
    # Update user's answers (for this specific poll)
    answers = poll_info.get("answers", {})
    answers[str(user_id)] = {
        "selected_option": selected_option,
        "is_correct": is_correct
    }
    poll_info["answers"] = answers
    
    # Update sent_polls
    sent_polls[poll_id] = poll_info
    quiz["sent_polls"] = sent_polls
    
    # Get participant info
    participants = quiz.get("participants", {})
    user_data = participants.get(str(user_id), {"correct": 0, "total": 0})
    
    # Update stats
    if is_correct:
        user_data["correct"] += 1
    else:
        # If incorrect, apply penalty if negative marking is enabled
        category = question.get("category", "General Knowledge")
        apply_penalty(user_id, category)
    
    user_data["total"] += 1
    
    # Update participants
    participants[str(user_id)] = user_data
    quiz["participants"] = participants
    
    # Save quiz state
    context.chat_data["quiz"] = quiz
    
    # Also update user's global stats
    user_global_data = get_user_data(user_id)
    user_global_data["total_answers"] += 1
    if is_correct:
        user_global_data["correct_answers"] += 1
    save_user_data(user_id, user_global_data)

def end_quiz(context, chat_id):
    """End the quiz and display results with all participants and penalties."""
    # Get quiz state
    quiz = context.chat_data.get("quiz", {})
    
    if not quiz.get("active", False):
        return
    
    # Deactivate quiz
    quiz["active"] = False
    context.chat_data["quiz"] = quiz
    
    # Get participants
    participants = quiz.get("participants", {})
    if not participants:
        context.bot.send_message(
            chat_id=chat_id,
            text="Quiz ended. No participants."
        )
        return
    
    # Build results message
    results_text = "📊 Quiz Results 📊\n\n"
    
    # Sort participants by correct answers
    sorted_participants = []
    for user_id, stats in participants.items():
        # Get user's name
        try:
            user_info = context.bot.get_chat_member(chat_id, int(user_id)).user
            user_name = user_info.first_name
            if user_info.username:
                user_name += f" (@{user_info.username})"
        except:
            user_name = f"User {user_id}"
        
        # Get penalties
        penalty = get_user_penalties(user_id)
        
        # Calculate adjusted score
        raw_score = stats.get("correct", 0)
        adjusted_score = max(0, raw_score - penalty)
        
        sorted_participants.append({
            "name": user_name,
            "id": user_id,
            "raw_score": raw_score,
            "penalty": penalty,
            "adjusted_score": adjusted_score,
            "total": stats.get("total", 0)
        })
    
    # Sort by adjusted score (highest first)
    sorted_participants.sort(key=lambda x: x["adjusted_score"], reverse=True)
    
    # Add each participant to results
    for i, participant in enumerate(sorted_participants):
        position = i + 1
        position_emoji = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{position}."
        
        results_text += (
            f"{position_emoji} {participant['name']}\n"
            f"   Raw Score: {participant['raw_score']}/{participant['total']}\n"
        )
        
        # Include penalty information if negative marking is enabled
        if NEGATIVE_MARKING_ENABLED:
            results_text += (
                f"   Penalties: -{participant['penalty']:.2f}\n"
                f"   Adjusted Score: {participant['adjusted_score']:.2f}/{participant['total']}\n"
            )
        
        results_text += "\n"
    
    # Send results message
    context.bot.send_message(
        chat_id=chat_id,
        text=results_text
    )

# ---------- PDF IMPORT FUNCTIONS ----------
def extract_text_from_pdf(pdf_file_path):
    """
    Enhanced extraction of text from PDF files with improved support for 
    various formats and Hindi content
    Returns a list of extracted text content from each page
    """
    try:
        logger.info(f"Extracting text from PDF: {pdf_file_path}")
        
        if not PDF_SUPPORT:
            logger.warning("PyPDF2 not installed, cannot extract text from PDF.")
            return ["PyPDF2 module not available. Please install PyPDF2 to enable PDF text extraction."]
        
        extracted_text = []
        
        try:
            # First try using PyPDF2
            with open(pdf_file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page in reader.pages:
                    text = page.extract_text()
                    
                    # Special handling for Hindi content
                    if text:
                        lang = detect_language(text)
                        if lang == 'hi':
                            logger.info("Detected Hindi text in PDF")
                            # For Hindi text: preserve whitespace and formatting
                            text = text.replace('\n\n', ' <PARAGRAPH> ')
                            text = text.replace('\n', ' ')
                            text = text.replace(' <PARAGRAPH> ', '\n\n')
                    
                    # Extra processing to handle poor layout PDFs
                    if text:
                        # Handle cases where question and options are improperly separated
                        text = text.replace('?', '?\n')  # Add line break after question marks
                        
                        # Fix common option format issues
                        for prefix in ['A)', 'B)', 'C)', 'D)', 'a)', 'b)', 'c)', 'd)',
                                      'A.', 'B.', 'C.', 'D.', 'a.', 'b.', 'c.', 'd.',
                                      '1)', '2)', '3)', '4)', '1.', '2.', '3.', '4.']:
                            # Ensure options start on a new line
                            text = text.replace(' ' + prefix, '\n' + prefix)
                            
                        # Fix answer indication
                        for ans in ['Ans:', 'Answer:', 'Correct:', 'Correct Answer:']:
                            text = text.replace(' ' + ans, '\n' + ans)
                    
                    extracted_text.append(text if text else "")
        except Exception as pdf_error:
            logger.error(f"PyPDF2 extraction failed: {pdf_error}")
            # Fall back to simple extraction if PyPDF2 fails
            extracted_text = ["Failed to extract text: PDF might be encrypted or damaged."]
        
        return extracted_text
    except Exception as e:
        logger.error(f"Critical error in PDF extraction: {e}")
        return ["Error processing PDF. Please check the file format."]

def parse_questions_from_text(text_list, custom_id=None):
    """
    Enhanced parsing of questions from extracted text with better support for 
    various PDF formats and improved Hindi answer detection
    Returns a list of question dictionaries
    """
    questions = []
    current_question = None
    
    # Enhanced pattern detection:
    # - Supports more question formats (numbered, Q., Question, etc.)
    # - Better handling of options in various formats (A), B), a., 1., etc.)
    # - Improved answer detection, especially for Hindi content
    # - Handling of questions that span multiple lines
    
    for page_text in text_list:
        if not page_text or not page_text.strip():
            continue
            
        # Pre-process the text for better parsing
        page_text = page_text.replace('।', '.\n')  # Hindi sentence ends with ।
        
        lines = page_text.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines
            if not line:
                i += 1
                continue
                
            # More comprehensive pattern for question detection
            is_question_start = (
                line.startswith('Q.') or 
                line.startswith('Q ') or
                line.startswith('Q:') or
                (line and line[0].isdigit() and len(line) > 2 and line[1:3] in ['. ', ') ', '- ', ':', ' ']) or
                line.lower().startswith('question') or
                # Typical Hindi question patterns
                ('प्रश्न' in line and len(line) < 100)  # प्रश्न = "question" in Hindi
            )
            
            # Check if line starts a new question
            if is_question_start:
                # Save previous question if exists
                if current_question and 'question' in current_question and 'options' in current_question:
                    if len(current_question['options']) >= 2:  # Must have at least 2 options
                        questions.append(current_question)
                
                # Start a new question
                current_question = {
                    'question': line,
                    'options': [],
                    'answer': None,
                    'category': 'General Knowledge',  # Default category
                    'option_prefixes': {}  # To store option prefixes for answer matching
                }
                
                # Collect question text that may span multiple lines
                j = i + 1
                option_detected = False
                end_of_text = False
                
                while j < len(lines) and not option_detected and not end_of_text:
                    next_line = lines[j].strip()
                    
                    # Handle empty lines
                    if not next_line:
                        j += 1
                        continue
                    
                    # More comprehensive detection of option patterns
                    if (next_line.startswith(('A)', 'A.', 'A ', 'a)', 'a.', 'a ', '1)', '1.', '1 ', '(a)', '(A)')) or
                        next_line.startswith(('B)', 'B.', 'B ', 'b)', 'b.', 'b ', '2)', '2.', '2 ', '(b)', '(B)'))):
                        option_detected = True
                    # Check for Hindi option patterns
                    elif ('क)' in next_line[:4] or 'ख)' in next_line[:4] or 
                          'क.' in next_line[:4] or 'ख.' in next_line[:4] or
                          'क ' in next_line[:4] or 'ख ' in next_line[:4]):
                        option_detected = True
                    # Check if we've hit another question
                    elif (next_line.startswith('Q.') or 
                          (next_line and next_line[0].isdigit() and len(next_line) > 2 and next_line[1:3] in ['. ', ') ', '- ']) or
                          next_line.lower().startswith('question') or
                          'प्रश्न' in next_line[:10]):
                        end_of_text = True
                    else:
                        # Continue collecting the question text
                        current_question['question'] += ' ' + next_line
                        j += 1
                
                i = j - 1 if option_detected else j  # Adjust index to continue from option lines or next line
            
            # Comprehensive pattern for options detection
            # - Supports A), B), a., b., 1), 2), etc.
            # - Supports Hindi options क), ख), etc.
            is_option = False
            option_prefix = ''
            
            if current_question:
                # Check for Latin alphabet options
                if (line.startswith(('A)', 'A.', 'A ', 'a)', 'a.', 'a ', '1)', '1.', '1 ', '(a)', '(A)'))):
                    is_option = True
                    option_prefix = 'A'
                elif (line.startswith(('B)', 'B.', 'B ', 'b)', 'b.', 'b ', '2)', '2.', '2 ', '(b)', '(B)'))):
                    is_option = True
                    option_prefix = 'B'
                elif (line.startswith(('C)', 'C.', 'C ', 'c)', 'c.', 'c ', '3)', '3.', '3 ', '(c)', '(C)'))):
                    is_option = True
                    option_prefix = 'C'
                elif (line.startswith(('D)', 'D.', 'D ', 'd)', 'd.', 'd ', '4)', '4.', '4 ', '(d)', '(D)'))):
                    is_option = True
                    option_prefix = 'D'
                # Check for Hindi options 
                elif 'क)' in line[:4] or 'क.' in line[:4] or 'क ' in line[:4]:
                    is_option = True
                    option_prefix = 'क'  # Hindi "ka" = A
                elif 'ख)' in line[:4] or 'ख.' in line[:4] or 'ख ' in line[:4]:
                    is_option = True
                    option_prefix = 'ख'  # Hindi "kha" = B
                elif 'ग)' in line[:4] or 'ग.' in line[:4] or 'ग ' in line[:4]:
                    is_option = True 
                    option_prefix = 'ग'  # Hindi "ga" = C
                elif 'घ)' in line[:4] or 'घ.' in line[:4] or 'घ ' in line[:4]:
                    is_option = True
                    option_prefix = 'घ'  # Hindi "gha" = D
            
            # Process the option if detected
            if is_option:
                option_text = line
                
                # Store the option prefix for answer matching
                if option_prefix and current_question is not None:
                    # Map option prefixes to their indices
                    if option_prefix in ['A', 'a', '1', 'क']:
                        current_question['option_prefixes']['A'] = 0
                    elif option_prefix in ['B', 'b', '2', 'ख']:
                        current_question['option_prefixes']['B'] = 1
                    elif option_prefix in ['C', 'c', '3', 'ग']:
                        current_question['option_prefixes']['C'] = 2
                    elif option_prefix in ['D', 'd', '4', 'घ']:
                        current_question['option_prefixes']['D'] = 3
                
                if current_question is not None:
                    current_question['options'].append(option_text)
            
            # Enhanced answer detection with Hindi support
            # For answer indications like "Ans:", "Answer:", "Correct:", etc. in both English and Hindi
            elif current_question and (
                line.lower().startswith(('ans:', 'answer:', 'correct answer:', 'correct:', 'solution:', 'sol:')) or
                'उत्तर:' in line[:10] or 'उत्तर ' in line[:10] or  # Hindi for "answer"
                'सही उत्तर:' in line[:15] or 'सही उत्तर ' in line[:15] or  # Hindi for "correct answer"
                'समाधान:' in line[:15] or 'समाधान ' in line[:15]  # Hindi for "solution"
            ):
                # Extract the answer from the line
                answer_text = line.lower()
                
                # First check for directly mentioned option prefixes
                if 'a' in answer_text or '(a)' in answer_text or '1' in answer_text or 'option a' in answer_text or 'क' in answer_text:
                    current_question['answer'] = 0
                elif 'b' in answer_text or '(b)' in answer_text or '2' in answer_text or 'option b' in answer_text or 'ख' in answer_text:
                    current_question['answer'] = 1
                elif 'c' in answer_text or '(c)' in answer_text or '3' in answer_text or 'option c' in answer_text or 'ग' in answer_text:
                    current_question['answer'] = 2
                elif 'd' in answer_text or '(d)' in answer_text or '4' in answer_text or 'option d' in answer_text or 'घ' in answer_text:
                    current_question['answer'] = 3
                
                # If we have option prefixes stored, use them to match the answer
                elif 'option_prefixes' in current_question:
                    prefixes = current_question['option_prefixes']
                    for prefix, index in prefixes.items():
                        if prefix.lower() in answer_text.lower():
                            current_question['answer'] = index
                            break
            
            i += 1
    
    # Add the last question if it exists
    if current_question and 'question' in current_question and 'options' in current_question:
        if len(current_question['options']) >= 2:
            questions.append(current_question)
    
    # Post-process questions
    processed_questions = []
    for q in questions:
        # Clean up the question text
        q['question'] = q['question'].replace('Q.', '').replace('Question:', '').strip()
        if q['question'].startswith(tuple(str(i) for i in range(10))):
            # Remove leading numbers (1., 2., etc.)
            parts = q['question'].split('. ', 1)
            if len(parts) > 1:
                q['question'] = parts[1]
        
        # Clean up option texts
        cleaned_options = []
        for opt in q['options']:
            # Handle Latin alphabet options
            if opt and len(opt) > 2:
                if opt[0].isalpha() and opt[1] in [')', '.', '-', ':']:
                    opt = opt[2:].strip()
                elif opt.startswith('(') and opt[2] == ')':  # (a), (A), etc.
                    opt = opt[3:].strip()
                elif opt[0].isdigit() and opt[1] in [')', '.', '-', ':']:
                    opt = opt[2:].strip()
                # Handle Hindi options like क), ख), etc.
                elif opt[0] in ['क', 'ख', 'ग', 'घ'] and opt[1] in [')', '.', '-', ':']:
                    opt = opt[2:].strip()
            
            cleaned_options.append(opt)
        
        q['options'] = cleaned_options
        
        # If no correct answer is identified, use smarter detection:
        if q['answer'] is None:
            # Look for "correct" or similar words in options
            for i, opt in enumerate(q['options']):
                opt_lower = opt.lower()
                if 'correct' in opt_lower or 'right' in opt_lower or 'true' in opt_lower or 'सही' in opt_lower:
                    q['answer'] = i
                    break
            
            # If still no answer, default to first option
            if q['answer'] is None:
                q['answer'] = 0
        
        # Remove the option_prefixes field which was only used for processing
        if 'option_prefixes' in q:
            del q['option_prefixes']
            
        # Only include questions with adequate options
        if len(q['options']) >= 2:
            processed_questions.append(q)
    
    # Log how many questions were extracted
    logger.info(f"Extracted {len(processed_questions)} questions from PDF")
    
    return processed_questions

def pdf_import_command(update: Update, context: CallbackContext) -> int:
    """Start the PDF import process."""
    update.message.reply_text(
        "📚 Let's import questions from a PDF file!\n\n"
        "Send me the PDF file you want to import questions from."
    )
    return PDF_UPLOAD

def pdf_file_received(update: Update, context: CallbackContext) -> int:
    """Handle the PDF file upload."""
    # Check if a document was received
    if not update.message.document:
        update.message.reply_text("Please send a PDF file.")
        return PDF_UPLOAD
    
    # Check if it's a PDF file
    file = update.message.document
    if not file.file_name.lower().endswith('.pdf'):
        update.message.reply_text("Please send a PDF file (with .pdf extension).")
        return PDF_UPLOAD
    
    # Ask for a custom ID
    update.message.reply_text(
        "Please provide a custom ID for these questions.\n"
        "All questions from this PDF will be saved under this ID.\n"
        "Enter a number or a short text ID (e.g., 'science_quiz' or '42'):"
    )
    
    # Store the file ID for later download
    context.user_data['pdf_file_id'] = file.file_id
    return PDF_CUSTOM_ID

def pdf_custom_id_received(update: Update, context: CallbackContext) -> int:
    """Handle the custom ID input for PDF questions."""
    custom_id = update.message.text.strip()
    
    # Validate the custom ID
    if not custom_id:
        update.message.reply_text("Please provide a valid ID.")
        return PDF_CUSTOM_ID
    
    # Store the custom ID
    context.user_data['pdf_custom_id'] = custom_id
    
    # Let user know we're processing the PDF
    status_message = update.message.reply_text(
        "⏳ Processing the PDF file. This may take a moment..."
    )
    
    # Store the status message ID for updating
    context.user_data['status_message_id'] = status_message.message_id
    
    try:
        # Get file ID and custom ID from user data
        file_id = context.user_data.get('pdf_file_id')
        custom_id = context.user_data.get('pdf_custom_id')
        
        if not file_id or not custom_id:
            update.message.reply_text("Error: Missing file or custom ID information.")
            return ConversationHandler.END
        
        # Check if PDF support is available
        if not PDF_SUPPORT:
            update.message.reply_text(
                "❌ PDF support is not available. Please install PyPDF2 module.\n"
                "You can run: pip install PyPDF2"
            )
            return ConversationHandler.END
        
        # Download the file
        file = context.bot.get_file(file_id)
        pdf_file_path = os.path.join(TEMP_DIR, f"{custom_id}_import.pdf")
        file.download(pdf_file_path)
        
        # Update status message
        status_message_id = context.user_data.get('status_message_id')
        if status_message_id:
            context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_message_id,
                text="⏳ PDF downloaded. Extracting text and questions..."
            )
        
        # Extract text from PDF
        extracted_text_list = extract_text_from_pdf(pdf_file_path)
        
        # Update status message
        if status_message_id:
            context.bot.edit_message_text(
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
            update.message.reply_text(
                "❌ No questions could be extracted from the PDF.\n"
                "Please make sure the PDF contains properly formatted questions and options."
            )
            return ConversationHandler.END
        
        # Update status message
        if status_message_id:
            context.bot.edit_message_text(
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
        update.message.reply_text(
            f"✅ Successfully imported {len(questions)} questions from the PDF!\n\n"
            f"They have been saved under the custom ID: '{custom_id}'\n\n"
            f"You can start a quiz with these questions using:\n"
            f"/quizid {custom_id}"
        )
        
    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        update.message.reply_text(
            f"❌ An error occurred while processing the PDF: {str(e)}\n"
            "Please try again or use a different PDF file."
        )
    
    return ConversationHandler.END

def quiz_with_id_command(update: Update, context: CallbackContext) -> None:
    """Start a quiz with questions from a specific ID."""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    # Check if an ID was provided
    if not context.args or not context.args[0]:
        update.message.reply_text(
            "Please provide an ID to start a quiz with.\n"
            "Example: /quizid science_quiz"
        )
        return
    
    quiz_id = context.args[0]
    
    # Load all questions
    all_questions = load_questions()
    
    # Check if the ID exists
    if quiz_id not in all_questions:
        update.message.reply_text(
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
        update.message.reply_text(
            f"❌ No questions found with ID: '{quiz_id}'\n"
            "Please check the ID and try again."
        )
        return
    
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
    update.message.reply_text(
        f"Starting quiz with ID: {quiz_id}\n"
        f"Total questions: {len(questions)}\n\n"
        f"First question coming up..."
    )
    
    # Send first question
    send_question(context, chat_id, 0)

def pdf_info_command(update: Update, context: CallbackContext) -> None:
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
    update.message.reply_text(info_text)

def main() -> None:
    """Start the bot."""
    # Create the Updater (v13.15 style)
    updater = Updater(BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # Basic command handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("quiz", quiz_command))
    dispatcher.add_handler(CommandHandler("stats", stats_command))
    dispatcher.add_handler(CommandHandler("delete", delete_command))
    
    # NEGATIVE MARKING ADDITION: Add new command handlers
    dispatcher.add_handler(CommandHandler("negmark", negative_marking_settings))
    dispatcher.add_handler(CommandHandler("resetpenalty", reset_user_penalty_command))
    dispatcher.add_handler(CallbackQueryHandler(negative_settings_callback, pattern=r"^neg_mark_"))
    
    # PDF IMPORT ADDITION: Add new command handlers
    dispatcher.add_handler(CommandHandler("pdfinfo", pdf_info_command))
    dispatcher.add_handler(CommandHandler("quizid", quiz_with_id_command))
    
    # PDF import conversation handler - simplified for compatibility
    pdf_import_handler = ConversationHandler(
        entry_points=[CommandHandler("pdfimport", pdf_import_command)],
        states={
            PDF_UPLOAD: [MessageHandler(Filters.document & Filters.document.pdf, pdf_file_received)],
            PDF_CUSTOM_ID: [MessageHandler(Filters.text & ~Filters.command, pdf_custom_id_received)],
            PDF_PROCESSING: [],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    dispatcher.add_handler(pdf_import_handler)
    
    # Add question conversation handler
    add_question_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_question_start)],
        states={
            QUESTION: [MessageHandler(Filters.text & ~Filters.command, add_question_text)],
            OPTIONS: [MessageHandler(Filters.text & ~Filters.command, add_question_options)],
            ANSWER: [MessageHandler(Filters.text & ~Filters.command, add_question_answer)],
            CUSTOM_ID: [
                CallbackQueryHandler(custom_id_callback, pattern=r"^(auto_id|custom_id)$"),
                MessageHandler(Filters.text & ~Filters.command & (lambda update, context: context.user_data.get("awaiting_custom_id", False)), custom_id_input)
            ],
            CATEGORY: [CallbackQueryHandler(category_callback, pattern=r"^category_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    dispatcher.add_handler(add_question_handler)
    
    # Poll Answer Handler - CRITICAL for tracking all participants
    dispatcher.add_handler(PollAnswerHandler(poll_answer))
    
    # Start the Bot
    updater.start_polling()
    logger.info("Bot started successfully!")
    
    # Run the bot until the user presses Ctrl-C
    updater.idle()

if __name__ == "__main__":
    main()