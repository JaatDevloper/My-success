#!/usr/bin/env python3
"""
Complete Telegram Quiz Bot with multi-question ID support and advanced cloning:
1. Add multiple questions with same ID
2. Poll to question conversion with multi-ID support
3. Show all participants in final results
4. Auto-sequencing questions
5. Clone quizzes from other Telegram channels and bots (via URL, username, or channel ID)
"""

import json
import logging
import os
import random
import asyncio
import re
from typing import Dict, List, Tuple, Union, Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, Poll
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler, PollAnswerHandler

from telethon import TelegramClient
from telethon.errors import ChannelPrivateError, InviteHashInvalidError
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.types import Channel, Message, MessageMediaPoll, PeerChannel, User

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment variable
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Telethon API credentials from environment variables
API_ID = int(os.environ.get("API_ID", "0"))  # Convert to int for Telethon
API_HASH = os.environ.get("API_HASH", "")
SESSION_NAME = "quiz_user_session"  # Session for user account

# Conversation states
QUESTION, OPTIONS, ANSWER, CATEGORY = range(4)
EDIT_SELECT, EDIT_QUESTION, EDIT_OPTIONS = range(4, 7)
CLONE_URL, CLONE_MANUAL = range(7, 9)
CUSTOM_ID = range(9, 10)
# Additional states for user cloning
CLONE_PHONE, CLONE_SOURCE_TYPE, CLONE_SOURCE, CLONE_LIMIT = range(10, 14)

# Data files
QUESTIONS_FILE = "questions.json"
USERS_FILE = "users.json"

# Regular expressions for quiz formats
QUIZ_PATTERN = re.compile(r'(?:Question|Q):\s*(.*?)(?:\n|$)', re.IGNORECASE)
OPTION_PATTERN = re.compile(r'(?:[A-Z]|[0-9]+)\s*[\)\.]\s*(.*?)(?:\n|$)')
ANSWER_PATTERN = re.compile(r'(?:Answer|A):\s*([A-Z]|[0-9]+)', re.IGNORECASE)

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
    """Send a premium-style welcome message without borders."""
    user = update.effective_user

    welcome_text = (
        f"✨ 𝙒𝙚𝙡𝙘𝙤𝙢𝙚, [{user.first_name}](tg://user?id={user.id})! ✨\n\n"
        "🧠 *𝗤𝘂𝗶𝘇 𝗠𝗮𝘀𝘁𝗲𝗿 𝗕𝗼𝘁* 𝗂𝗌 𝗁𝖾𝗋𝖾 𝗍𝗈 𝖼𝗁𝖺𝗅𝗅𝖾𝗇𝗀𝖾 𝗒𝗈𝗎𝗋 𝖻𝗋𝖺𝗂𝗇 𝖺𝗇𝖽 𝗍𝖾𝗌𝗍 𝗒𝗈𝗎𝗋 𝗌𝗄𝗂𝗅𝗅𝗌!\n\n"
        "𝗁𝖾𝗋𝖾'𝗌 𝗐𝗁𝖺𝗍 𝗒𝗈𝗎 𝖼𝖺𝗇 𝖽𝗈:\n\n"
        "• ⚡ *Start a Quiz:* `/quiz`\n"
        "• 📊 *Check Stats:* `/stats`\n"
        "• ➕ *Add Question:* `/add`\n"
        "• ✏️ *Edit Question:* `/edit`\n"
        "• ❌ *Delete Question:* `/delete`\n"
        "• 🔄 *Poll to Quiz:* `/poll2q`\n"
        "• 📱 *Clone Quizzes:* `/clone_user`\n"
        "• ℹ️ *Help & Commands:* `/help`\n\n"
        "🔥 *Let's go — become the legend of the leaderboard!* 🏆\n\n"
        "👨‍💻 *Developed by* [@JaatCoderX](https://t.me/JaatCoderX)"
    )

    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help message."""
    await start(update, context)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display user statistics."""
    user = update.effective_user
    user_data = get_user_data(user.id)
    
    total = user_data.get("total_answers", 0)
    correct = user_data.get("correct_answers", 0)
    percentage = (correct / total * 100) if total > 0 else 0
    
    stats_text = (
        f"📊 Statistics for {user.first_name}\n\n"
        f"Total questions answered: {total}\n"
        f"Correct answers: {correct}\n"
        f"Success rate: {percentage:.1f}%\n\n"
    )
    
    await update.message.reply_text(stats_text)

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

async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Edit a question by ID."""
    # Check if ID was provided with command
    args = context.args
    if args and len(args) > 0:
        try:
            question_id = int(args[0])
            question = get_question_by_id(question_id)
            if not question:
                await update.message.reply_text(f"No question found with ID {question_id}.")
                return
            
            # Store the question ID for editing
            context.user_data["editing_id"] = question_id
            context.user_data["editing_question"] = question
            
            await update.message.reply_text(
                f"Editing question ID {question_id}:\n\n"
                f"Current text: {question['question']}\n\n"
                "Send me the new question text:"
            )
            
            # Start the edit conversation
            return EDIT_QUESTION
        except ValueError:
            await update.message.reply_text("Please provide a valid numeric ID.")
    else:
        # If no ID provided, show list of questions
        questions = load_questions()
        if not questions:
            await update.message.reply_text("No questions available to edit.")
            return
        
        message = "To edit a question, use /edit <id>. Available questions:\n\n"
        for qid, question_list in questions.items():
            if isinstance(question_list, list):
                message += f"ID: {qid} - {len(question_list)} questions\n"
            else:
                message += f"ID: {qid} - {question_list.get('question', 'Untitled')[:30]}...\n"
        
        await update.message.reply_text(message)

async def edit_question_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the edited question text and ask for options."""
    question_id = context.user_data.get("editing_id")
    question = context.user_data.get("editing_question", {})
    
    # Update the question text
    question["question"] = update.message.text
    
    # Show current options
    options = question.get("options", [])
    options_text = "\n".join([f"{i}. {opt}" for i, opt in enumerate(options)])
    
    await update.message.reply_text(
        "Question text updated! Now send me the new options, one per line:\n\n"
        f"Current options:\n{options_text}"
    )
    
    return EDIT_OPTIONS

async def edit_question_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the edited options and ask for the correct answer."""
    question_id = context.user_data.get("editing_id")
    question = context.user_data.get("editing_question", {})
    
    # Update the options
    options = update.message.text.split('\n')
    question["options"] = options
    
    # Show options for selecting correct answer
    options_text = "\n".join([f"{i}. {opt}" for i, opt in enumerate(options)])
    
    await update.message.reply_text(
        f"Options updated! Now tell me which one is correct (0-{len(options)-1}):\n\n{options_text}"
    )
    
    return ANSWER

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
    
    await update.message.reply_text(
        f"Starting a quiz with {num_questions} questions! Questions will automatically proceed after 30 seconds.\n\n"
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
    
    # Send the poll
    message = await context.bot.send_poll(
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
    sent_polls[str(poll_id)] = {
        "question_index": question_index,
        "message_id": message.message_id,
        "answers": {}
    }
    quiz["sent_polls"] = sent_polls
    
    # Schedule next question
    quiz["current_index"] = question_index + 1
    
    # Schedule next question or end
    if question_index + 1 < len(questions):
        context.job_queue.run_once(
            poll_timeout, 30, chat_id=chat_id, name=f"quiz_{chat_id}_{question_index}"
        )

async def poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle poll answers and track user responses."""
    answer = update.poll_answer
    poll_id = answer.poll_id
    user_id = answer.user.id
    
    # Check if this poll belongs to an active quiz
    active_quizzes = {}
    for chat_id, chat_data in context.bot_data.items():
        if isinstance(chat_data, dict) and "quiz" in chat_data:
            quiz = chat_data.get("quiz", {})
            if quiz.get("active", False) and poll_id in quiz.get("sent_polls", {}):
                active_quizzes[chat_id] = quiz
    
    if not active_quizzes:
        return
    
    # Update user answers for each active quiz containing this poll
    for chat_id, quiz in active_quizzes.items():
        poll_data = quiz["sent_polls"].get(poll_id, {})
        question_index = poll_data.get("question_index")
        
        if question_index is not None:
            # Store user answer
            poll_data["answers"][str(user_id)] = {
                "user": answer.user.to_dict(),
                "option": answer.option_ids[0] if answer.option_ids else None,
                "timestamp": asyncio.get_event_loop().time()
            }
            
            # Update participant info
            if str(user_id) not in quiz.get("participants", {}):
                quiz["participants"][str(user_id)] = {
                    "user": answer.user.to_dict(),
                    "correct": 0,
                    "total": 0
                }

async def poll_timeout(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle poll timeout and send results."""
    job = context.job
    chat_id = job.chat_id
    
    quiz = context.chat_data.get("quiz", {})
    if not quiz.get("active", False):
        return
    
    current_index = quiz.get("current_index", 0)
    
    # Send next question
    await send_question(context, chat_id, current_index)

async def end_quiz(context, chat_id):
    """End the quiz and show results."""
    quiz = context.chat_data.get("quiz", {})
    
    if not quiz:
        return
    
    quiz["active"] = False
    
    # Collect results
    participants = quiz.get("participants", {})
    sent_polls = quiz.get("sent_polls", {})
    questions = quiz.get("questions", [])
    
    # Calculate scores for each participant
    for poll_id, poll_data in sent_polls.items():
        question_index = poll_data.get("question_index")
        if question_index is None or question_index >= len(questions):
            continue
        
        question = questions[question_index]
        correct_answer = question.get("answer")
        
        for user_id, answer_data in poll_data.get("answers", {}).items():
            if user_id not in participants:
                continue
            
            option = answer_data.get("option")
            participants[user_id]["total"] += 1
            
            if option == correct_answer:
                participants[user_id]["correct"] += 1
                
                # Update user's statistics in database
                user_data = get_user_data(user_id)
                user_data["total_answers"] = user_data.get("total_answers", 0) + 1
                user_data["correct_answers"] = user_data.get("correct_answers", 0) + 1
                save_user_data(user_id, user_data)
            else:
                # Update user's statistics in database (incorrect)
                user_data = get_user_data(user_id)
                user_data["total_answers"] = user_data.get("total_answers", 0) + 1
                save_user_data(user_id, user_data)
    
    # Sort participants by score
    sorted_participants = sorted(
        participants.items(),
        key=lambda x: (x[1].get("correct", 0), -x[1].get("total", 0)),
        reverse=True
    )
    
    # Generate results message
    results_text = "📋 Quiz Results:\n\n"
    
    if sorted_participants:
        for i, (user_id, data) in enumerate(sorted_participants):
            user = data.get("user", {})
            name = user.get("first_name", f"User {user_id}")
            correct = data.get("correct", 0)
            total = data.get("total", 0)
            percentage = (correct / total * 100) if total > 0 else 0
            
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
            
            results_text += f"{medal} *{name}*: {correct}/{total} correct ({percentage:.1f}%)\n"
    else:
        results_text += "No participants in this quiz!\n"
    
    # Send results
    await context.bot.send_message(
        chat_id=chat_id,
        text=results_text,
        parse_mode='Markdown'
    )
    
    # Cleanup
    if "quiz" in context.chat_data:
        del context.chat_data["quiz"]

async def poll2q_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Convert a reply-to poll to a quiz question."""
    # Check if the command is a reply to a poll message
    if not update.message.reply_to_message or not update.message.reply_to_message.poll:
        await update.message.reply_text(
            "Please use this command as a reply to a poll message."
        )
        return
    
    poll = update.message.reply_to_message.poll
    
    # Check if it's a quiz poll (has correct answers)
    if not poll.correct_option_id:
        await update.message.reply_text(
            "This poll is not a quiz! Only quizzes with correct answers can be converted."
        )
        return
    
    # Extract poll data
    question_text = poll.question
    options = [opt.text for opt in poll.options]
    correct_answer = poll.correct_option_id
    
    # Create question data
    question_data = {
        "question": question_text,
        "options": options,
        "answer": correct_answer,
        "category": "Imported"
    }
    
    # Get next ID
    question_id = get_next_question_id()
    
    # Add question
    add_question_with_id(question_id, question_data)
    
    await update.message.reply_text(
        f"✅ Quiz question added with ID: {question_id}\n\n"
        f"Question: {question_text}\n"
        f"Options: {len(options)}\n"
        f"Category: Imported"
    )

# ----------------- NEW USER ACCOUNT CLONING FUNCTIONS -----------------

class UserCloner:
    def __init__(self):
        """Initialize the user cloner with Telethon client"""
        if not API_ID or not API_HASH:
            logger.error("API_ID and API_HASH environment variables must be set for Telethon")
            raise ValueError("API_ID and API_HASH must be set")
        
        self.client = None
        self.is_connected = False
        self.phone = None
    
    async def connect(self, phone=None) -> bool:
        """Connect to Telegram using Telethon with a user account"""
        try:
            self.phone = phone
            self.client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
            
            # This will prompt for phone number and verification code if not provided
            if phone:
                await self.client.start(phone=phone)
            else:
                await self.client.start()
                
            self.is_connected = True
            logger.info("Connected to Telegram with Telethon using a user account")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Telegram: {e}")
            self.is_connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from Telegram"""
        if self.client and self.is_connected:
            await self.client.disconnect()
            self.is_connected = False
            logger.info("Disconnected from Telegram")
    
    async def ensure_connection(self) -> bool:
        """Ensure the client is connected before operations"""
        if not self.is_connected or not self.client:
            return await self.connect(self.phone)
        return True
    
    async def get_entity_from_url(self, url: str) -> Optional[Union[Channel, User]]:
        """Get Telegram entity from a URL"""
        if not await self.ensure_connection():
            return None
        
        try:
            entity = await self.client.get_entity(url)
            return entity
        except Exception as e:
            logger.error(f"Failed to get entity from URL {url}: {e}")
            return None
    
    async def get_entity_from_username(self, username: str) -> Optional[Union[Channel, User]]:
        """Get Telegram entity from a username"""
        if not await self.ensure_connection():
            return None
        
        try:
            # Add @ if not present
            if not username.startswith('@'):
                username = f"@{username}"
            
            entity = await self.client.get_entity(username)
            return entity
        except Exception as e:
            logger.error(f"Failed to get entity from username {username}: {e}")
            return None
    
    async def get_entity_from_id(self, channel_id: int) -> Optional[Union[Channel, User]]:
        """Get Telegram entity from a channel ID"""
        if not await self.ensure_connection():
            return None
        
        try:
            entity = await self.client.get_entity(PeerChannel(channel_id))
            return entity
        except Exception as e:
            logger.error(f"Failed to get entity from ID {channel_id}: {e}")
            return None
    
    async def join_channel(self, entity: Union[Channel, User]) -> bool:
        """Join a channel if needed"""
        if not await self.ensure_connection():
            return False
        
        try:
            # Try to join the channel
            await self.client(JoinChannelRequest(entity))
            logger.info(f"Successfully joined channel: {entity.title if hasattr(entity, 'title') else entity.username}")
            return True
        except (ChannelPrivateError, InviteHashInvalidError):
            logger.error(f"Cannot join channel: it's private or the invite link is invalid")
            return False
        except Exception as e:
            logger.error(f"Failed to join channel: {e}")
            return False
    
    async def get_messages(self, entity: Union[Channel, User], limit: int = 100) -> List[Message]:
        """Get messages from a channel or user"""
        if not await self.ensure_connection():
            return []
        
        try:
            messages = await self.client.get_messages(entity, limit=limit)
            return messages
        except Exception as e:
            logger.error(f"Failed to get messages: {e}")
            return []
    
    def extract_quiz_from_poll(self, message: Message) -> Optional[Dict]:
        """Extract quiz data from a poll message"""
        if not message.media or not isinstance(message.media, MessageMediaPoll):
            return None
        
        poll = message.media.poll
        
        # Check if it's a quiz (has correct answers)
        if not poll.quiz:
            return None
        
        options = [answer.text for answer in poll.answers]
        correct_answer = None
        
        # Find correct answer if available in results
        if message.media.results and message.media.results.results:
            for i, result in enumerate(message.media.results.results):
                if result.correct:
                    correct_answer = i
                    break
        
        # If we couldn't find the correct answer, skip this poll
        if correct_answer is None:
            return None
        
        return {
            "question": poll.question,
            "options": options,
            "answer": correct_answer,
            "category": "Imported"  # Default category for imported quizzes
        }
    
    def extract_quiz_from_text(self, message: Message) -> Optional[Dict]:
        """Extract quiz data from a text message"""
        if not message.text:
            return None
        
        # Try to find question
        question_match = QUIZ_PATTERN.search(message.text)
        if not question_match:
            return None
        
        question = question_match.group(1).strip()
        
        # Extract options
        options = []
        for match in OPTION_PATTERN.finditer(message.text):
            options.append(match.group(1).strip())
        
        if not options:
            return None
        
        # Try to find answer
        answer_match = ANSWER_PATTERN.search(message.text)
        if not answer_match:
            return None
        
        answer_text = answer_match.group(1).strip()
        
        # Convert letter (A, B, C) to index (0, 1, 2)
        try:
            if answer_text.isalpha():
                correct_answer = ord(answer_text.upper()) - ord('A')
            else:
                correct_answer = int(answer_text) - 1
                
            # Validate answer index
            if correct_answer < 0 or correct_answer >= len(options):
                return None
        except:
            return None
        
        return {
            "question": question,
            "options": options,
            "answer": correct_answer,
            "category": "Imported"  # Default category for imported quizzes
        }
    
    async def extract_quizzes(self, entity: Union[Channel, User], limit: int = 100) -> List[Dict]:
        """Extract all quizzes from a channel's messages"""
        quizzes = []
        
        messages = await self.get_messages(entity, limit=limit)
        for message in messages:
            # Try to extract from poll
            quiz = self.extract_quiz_from_poll(message)
            if quiz:
                quizzes.append(quiz)
                continue
                
            # Try to extract from text
            quiz = self.extract_quiz_from_text(message)
            if quiz:
                quizzes.append(quiz)
        
        logger.info(f"Extracted {len(quizzes)} quizzes from channel")
        return quizzes
    
    async def clone_quizzes_by_url(self, url: str, limit: int = 100) -> List[Dict]:
        """Clone quizzes from a channel by URL"""
        entity = await self.get_entity_from_url(url)
        if not entity:
            return []
        
        await self.join_channel(entity)
        quizzes = await self.extract_quizzes(entity, limit)
        return quizzes
    
    async def clone_quizzes_by_username(self, username: str, limit: int = 100) -> List[Dict]:
        """Clone quizzes from a channel by username"""
        entity = await self.get_entity_from_username(username)
        if not entity:
            return []
        
        await self.join_channel(entity)
        quizzes = await self.extract_quizzes(entity, limit)
        return quizzes
    
    async def clone_quizzes_by_id(self, channel_id: int, limit: int = 100) -> List[Dict]:
        """Clone quizzes from a channel by ID"""
        entity = await self.get_entity_from_id(channel_id)
        if not entity:
            return []
        
        await self.join_channel(entity)
        quizzes = await self.extract_quizzes(entity, limit)
        return quizzes

async def clone_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clone quizzes using a user account to bypass API limitations"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    await context.bot.send_message(
        chat_id=chat_id,
        text="🔄 Starting quiz cloning with user account method...\n"
             "This will allow us to bypass the bot API limitations.\n\n"
             "Please enter your phone number with country code (e.g., +12123456789):",
    )
    
    # Store state to wait for phone number
    context.user_data['waiting_for'] = 'clone_phone'
    context.user_data['clone_chat_id'] = chat_id
    return CLONE_PHONE

async def process_clone_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process input for clone command"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = update.message.text
    
    # Check if we're expecting input for clone
    if 'waiting_for' not in context.user_data:
        return
    
    waiting_for = context.user_data['waiting_for']
    
    if waiting_for == 'clone_phone':
        # Got phone number, now ask for source type
        phone = text.strip()
        context.user_data['clone_phone'] = phone
        
        # Ask for source type
        keyboard = [
            [InlineKeyboardButton("URL", callback_data="clone_source_url")],
            [InlineKeyboardButton("Username", callback_data="clone_source_username")],
            [InlineKeyboardButton("Channel ID", callback_data="clone_source_id")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Please select the source type:",
            reply_markup=reply_markup
        )
        
        # Clear waiting status
        del context.user_data['waiting_for']
        return CLONE_SOURCE_TYPE
    
    elif waiting_for == 'clone_source':
        # Got source input, now ask for limit
        source = text.strip()
        context.user_data['clone_source'] = source
        
        await update.message.reply_text(
            "How many recent messages should I scan for quizzes? (Enter a number, max 100):"
        )
        
        # Update waiting status
        context.user_data['waiting_for'] = 'clone_limit'
        return CLONE_LIMIT
    
    elif waiting_for == 'clone_limit':
        # Got limit, now start cloning
        try:
            limit = int(text.strip())
            limit = min(max(1, limit), 100)  # Ensure between 1 and 100
        except ValueError:
            limit = 10  # Default if not a valid number
        
        source_type = context.user_data.get('clone_source_type', 'username')
        source = context.user_data.get('clone_source', '')
        phone = context.user_data.get('clone_phone', '')
        
        # Start cloning process
        await start_user_cloning(context, chat_id, source_type, source, limit, phone)
        
        # Clear waiting status
        del context.user_data['waiting_for']
        return ConversationHandler.END

async def clone_source_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle source type selection for cloning."""
    query = update.callback_query
    await query.answer()
    
    # Extract source type from callback data
    callback_data = query.data
    source_type = callback_data.replace('clone_source_', '')
    
    # Store source type in user data
    context.user_data['clone_source_type'] = source_type
    
    # Ask for source input
    source_type_names = {
        'url': 'URL',
        'username': 'Username',
        'id': 'Channel ID'
    }
    
    await query.edit_message_text(
        text=f"Please enter the {source_type_names.get(source_type, 'Source')}:"
    )
    
    # Set waiting status
    context.user_data['waiting_for'] = 'clone_source'
    return CLONE_SOURCE

async def start_user_cloning(context, chat_id, source_type, source, limit, phone):
    """Start the actual cloning process with user account"""
    # Send progress message
    progress_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"🔄 Starting quiz cloning from {source_type}: {source}\n"
             f"Scanning up to {limit} recent messages...\n\n"
             "This might take a few moments. Please wait."
    )
    
    try:
        # Initialize UserCloner
        cloner = UserCloner()
        
        # Connect to Telegram
        connected = await cloner.connect(phone)
        
        if not connected:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_msg.message_id,
                text="❌ Failed to connect to Telegram. Please check your credentials and try again."
            )
            return
        
        # Clone quizzes based on source type
        quizzes = []
        try:
            if source_type == 'url':
                quizzes = await cloner.clone_quizzes_by_url(source, limit)
            elif source_type == 'username':
                quizzes = await cloner.clone_quizzes_by_username(source, limit)
            elif source_type == 'id':
                channel_id = int(source)
                quizzes = await cloner.clone_quizzes_by_id(channel_id, limit)
        except Exception as e:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_msg.message_id,
                text=f"❌ Error during cloning: {str(e)}"
            )
            await cloner.disconnect()
            return
        
        # Disconnect from Telegram
        await cloner.disconnect()
        
        if not quizzes:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_msg.message_id,
                text="❌ No quizzes found. Try a different source or increase the limit."
            )
            return
        
        # Save quizzes
        saved_count = 0
        for quiz in quizzes:
            question_id = get_next_question_id()
            if add_question_with_id(question_id, quiz):
                saved_count += 1
        
        # Send success message
        result_text = f"✅ Successfully cloned {saved_count} quizzes!\n\n"
        
        # Show sample of quizzes
        if quizzes:
            result_text += "📋 Sample of cloned quizzes:\n"
            for i, quiz in enumerate(quizzes[:2]):  # Show first 2 quizzes
                result_text += f"\n[Quiz {i+1}]\n"
                result_text += f"Question: {quiz['question'][:50]}...\n"
                result_text += f"Options: {len(quiz['options'])}\n"
                result_text += f"Category: {quiz.get('category', 'Imported')}\n"
        
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_msg.message_id,
            text=result_text
        )
        
    except Exception as e:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_msg.message_id,
            text=f"❌ An error occurred: {str(e)}"
        )

# Create conversation handler for cloning
clone_user_handler = ConversationHandler(
    entry_points=[CommandHandler("clone_user", clone_user_command)],
    states={
        CLONE_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_clone_input)],
        CLONE_SOURCE_TYPE: [CallbackQueryHandler(clone_source_callback, pattern="^clone_source_")],
        CLONE_SOURCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_clone_input)],
        CLONE_LIMIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_clone_input)]
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

def extract_quiz_from_text_standalone(text):
    """Standalone function to extract quiz data from text format"""
    # Try to find question
    question_match = QUIZ_PATTERN.search(text)
    if not question_match:
        return None
    
    question = question_match.group(1).strip()
    
    # Extract options
    options = []
    for match in OPTION_PATTERN.finditer(text):
        options.append(match.group(1).strip())
    
    if not options:
        return None
    
    # Try to find answer
    answer_match = ANSWER_PATTERN.search(text)
    if not answer_match:
        return None
    
    answer_text = answer_match.group(1).strip()
    
    # Convert letter (A, B, C) to index (0, 1, 2)
    try:
        if answer_text.isalpha():
            correct_answer = ord(answer_text.upper()) - ord('A')
        else:
            correct_answer = int(answer_text) - 1
            
        # Validate answer index
        if correct_answer < 0 or correct_answer >= len(options):
            return None
    except:
        return None
    
    return {
        "question": question,
        "options": options,
        "answer": correct_answer,
        "category": "Imported"
    }

async def clone_manual_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the process of manually cloning a quiz"""
    await update.message.reply_text(
        "📝 *Manual Quiz Clone*\n\n"
        "Paste the quiz text in this format:\n\n"
        "Question: What is the capital of France?\n"
        "A) Paris\n"
        "B) London\n"
        "C) Berlin\n"
        "D) Rome\n"
        "Answer: A\n\n"
        "You can also paste multiple quizzes separated by '---'",
        parse_mode='Markdown'
    )
    
    return CLONE_MANUAL

async def clone_manual_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process manually input quiz text"""
    text = update.message.text
    
    # Check if it contains multiple quizzes
    if '---' in text:
        quiz_texts = text.split('---')
    else:
        quiz_texts = [text]
    
    # Process each quiz
    added_quizzes = []
    for quiz_text in quiz_texts:
        quiz_data = extract_quiz_from_text_standalone(quiz_text.strip())
        if quiz_data:
            question_id = get_next_question_id()
            add_question_with_id(question_id, quiz_data)
            added_quizzes.append((question_id, quiz_data))
    
    # Send summary
    if added_quizzes:
        summary = f"✅ Successfully added {len(added_quizzes)} quizzes:\n\n"
        for i, (qid, quiz) in enumerate(added_quizzes[:3]):  # Show first 3
            summary += f"{i+1}. ID: {qid} - {quiz['question'][:40]}...\n"
        
        if len(added_quizzes) > 3:
            summary += f"...and {len(added_quizzes) - 3} more\n"
        
        await update.message.reply_text(summary)
    else:
        await update.message.reply_text(
            "❌ No valid quizzes found in your input. Please make sure you're using the correct format."
        )
    
    return ConversationHandler.END

# Create conversation handler for manual cloning
clone_manual_handler = ConversationHandler(
    entry_points=[CommandHandler("clone_manual", clone_manual_command)],
    states={
        CLONE_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, clone_manual_text)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add conversation handler for adding questions
    add_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_question_start)],
        states={
            QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_text)],
            OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_options)],
            ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_answer)],
            CUSTOM_ID: [
                CallbackQueryHandler(custom_id_callback, pattern="^(auto_id|custom_id)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Update.CALLBACK_QUERY, custom_id_input)
            ],
            CATEGORY: [CallbackQueryHandler(category_callback, pattern="^category_")]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(add_handler)
    
    # Add conversation handler for editing questions
    edit_handler = ConversationHandler(
        entry_points=[CommandHandler("edit", edit_command)],
        states={
            EDIT_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_question_text)],
            EDIT_OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_question_options)],
            ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_answer)],
            CUSTOM_ID: [
                CallbackQueryHandler(custom_id_callback, pattern="^(auto_id|custom_id)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_id_input)
            ],
            CATEGORY: [CallbackQueryHandler(category_callback, pattern="^category_")]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(edit_handler)
    
    # Add conversation handler for user cloning
    application.add_handler(clone_user_handler)
    
    # Add conversation handler for manual cloning
    application.add_handler(clone_manual_handler)
    
    # Register other handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("poll2q", poll2q_command))
    
    # Register poll answer handler
    application.add_handler(PollAnswerHandler(poll_answer))
    
    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main()
