#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Multi ID Quiz Bot with Cloning feature
This bot supports cloning quizzes from the official @QuizBot as well as any Telegram channel with polls
"""

import os
import re
import json
import logging
import random
import asyncio
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Union, Any

# Telethon imports (for quiz cloning)
import telethon
from telethon.tl.types import PeerUser, PeerChannel
from telethon.sessions import StringSession
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Poll, PollOption
from telegram.ext import Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.constants import ParseMode

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment variables or fallback to hardcoded token
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7631768276:AAFwTYA8CK5tTHQfExI-w9cxPLnlLJa4iW0")

if not BOT_TOKEN:
    logger.error("No BOT_TOKEN provided. Please set the BOT_TOKEN environment variable.")
    exit(1)

# Telethon API credentials from environment variables
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
PHONE_NUMBER = os.environ.get("PHONE_NUMBER")
SESSION_STRING = os.environ.get("SESSION_STRING")

# If API credentials are missing, warn but don't exit
if not API_ID or not API_HASH or not PHONE_NUMBER:
    logger.warning("Telethon API credentials are incomplete. Quiz cloning feature will be limited.")

# Global Telethon client for quiz cloning
telethon_client = None

# Path to JSON file for storing questions
QUESTIONS_FILE = "questions.json"

# Conversation states
ADDING_QUESTION, ADDING_OPTIONS, ADDING_ANSWER, CUSTOM_ID, CATEGORY_SELECTION = range(5)
CLONE_URL, CLONE_CUSTOM_ID, CLONE_CATEGORY = range(5, 8)

# Make sure questions file exists
if not os.path.exists(QUESTIONS_FILE):
    with open(QUESTIONS_FILE, "w") as f:
        json.dump({}, f)

def load_questions():
    """Load questions from the JSON file"""
    try:
        with open(QUESTIONS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        logger.warning("Questions file not found or corrupted. Creating new file.")
        with open(QUESTIONS_FILE, "w") as f:
            json.dump({}, f)
        return {}

def save_questions(questions):
    """Save questions to the JSON file"""
    with open(QUESTIONS_FILE, "w") as f:
        json.dump(questions, f, indent=2)

def get_next_question_id():
    """Get the next available question ID"""
    questions = load_questions()
    if not questions:
        return 1
    
    # Convert all keys to integers and find the maximum
    max_id = max(map(int, questions.keys())) if questions else 0
    return max_id + 1

def get_question_by_id(question_id):
    """Get a question by its ID"""
    questions = load_questions()
    question_id_str = str(question_id)
    
    if question_id_str not in questions:
        return None
    
    # Handle both single question and list of questions
    result = questions[question_id_str]
    if isinstance(result, list):
        # Multiple questions with same ID, return a random one
        return random.choice(result)
    else:
        # Single question, return it
        return result

def delete_question_by_id(question_id):
    """Delete a question by its ID"""
    questions = load_questions()
    question_id_str = str(question_id)
    
    if question_id_str not in questions:
        return False
    
    del questions[question_id_str]
    save_questions(questions)
    return True

def add_question_with_id(question_id, question_data):
    """Add a question with a specific ID, preserving existing questions with the same ID"""
    questions = load_questions()
    question_id_str = str(question_id)
    
    if question_id_str in questions:
        # If there are already questions with this ID
        existing = questions[question_id_str]
        
        if isinstance(existing, list):
            # If it's already a list, append the new question
            existing.append(question_data)
        else:
            # If it's a single question, convert to list and append
            questions[question_id_str] = [existing, question_data]
    else:
        # No existing questions with this ID, create new entry
        questions[question_id_str] = question_data
    
    save_questions(questions)

def get_user_data(user_id):
    """Get user data from file"""
    try:
        with open(f"user_{user_id}.json", "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"total_answered": 0, "correct_answers": 0}

def save_user_data(user_id, data):
    """Save user data to file"""
    with open(f"user_{user_id}.json", "w") as f:
        json.dump(data, f)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        f"Hello {user.mention_html()}! 👋\n\n"
        f"I'm a Quiz Bot with multi-question ID support. This means several questions can share the same ID, allowing for more varied quizzes.\n\n"
        f"Here's what I can do:\n"
        f"• Run quizzes with /quiz [ID] [count]\n"
        f"• Add questions with /add\n"
        f"• Convert polls to questions with /poll2q\n"
        f"• Clone quizzes directly from @QuizBot with /clone\n"
        f"• View your stats with /stats\n"
        f"• Delete questions with /delete [ID]\n\n"
        f"For more information, use the /help command."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help message."""
    help_text = (
        "🔍 *Bot Commands* 🔍\n\n"
        
        "*Quiz Commands*\n"
        "/quiz [ID] [count] - Start a quiz with the specified ID and question count\n"
        "  • Example: `/quiz 5 10` - Quiz with ID 5, 10 questions\n"
        "  • If count is omitted, I'll use all available questions\n"
        "  • If both ID and count are omitted, I'll choose a random ID\n\n"
        
        "*Question Management*\n"
        "/add - Add a new question (interactive)\n"
        "/delete [ID] - Delete a question by ID\n"
        "/poll2q - Convert a forwarded Telegram poll to a quiz question\n"
        "/clone - Clone quiz questions directly from @QuizBot or any channel\n\n"
        
        "*Information*\n"
        "/stats - View your quiz performance statistics\n"
        "/help - Show this help message\n\n"
        
        "*Advanced Features*\n"
        "• *Multi-ID Support*: Multiple questions can share the same ID\n"
        "• *Quiz Cloning*: Clone quizzes directly from @QuizBot or any Telegram channel\n"
        "• *Poll Conversion*: Convert any Telegram poll to a quiz question\n"
    )
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display user statistics."""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    total_answered = user_data.get("total_answered", 0)
    correct_answers = user_data.get("correct_answers", 0)
    
    if total_answered == 0:
        accuracy = 0
    else:
        accuracy = (correct_answers / total_answered) * 100
    
    stats_text = (
        "📊 *Your Quiz Statistics* 📊\n\n"
        f"Questions Answered: {total_answered}\n"
        f"Correct Answers: {correct_answers}\n"
        f"Accuracy: {accuracy:.1f}%\n\n"
    )
    
    # Add accuracy emoji
    if accuracy >= 90:
        stats_text += "🏆 Outstanding! You're a quiz master!"
    elif accuracy >= 75:
        stats_text += "🥇 Great job! You're doing very well!"
    elif accuracy >= 60:
        stats_text += "🥈 Good work! Keep practicing!"
    elif accuracy >= 40:
        stats_text += "🥉 You're making progress! Keep going!"
    else:
        stats_text += "💪 Practice makes perfect! Don't give up!"
    
    await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)

async def add_question_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the process of adding a new question."""
    await update.message.reply_text(
        "Let's add a new quiz question! 📝\n\n"
        "Please send me the question text."
    )
    return ADDING_QUESTION

async def add_question_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the question text and ask for options."""
    question_text = update.message.text
    context.user_data["question"] = question_text
    
    await update.message.reply_text(
        f"Got it! Question: '{question_text}'\n\n"
        f"Now send me the answer options, one per line.\n"
        f"Example:\n"
        f"Option 1\n"
        f"Option 2\n"
        f"Option 3\n"
        f"Option 4"
    )
    return ADDING_OPTIONS

async def add_question_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the options and ask for the correct answer."""
    options_text = update.message.text
    options = [option.strip() for option in options_text.split('\n') if option.strip()]
    
    if len(options) < 2:
        await update.message.reply_text(
            "I need at least 2 options for a valid quiz question. Please send the options again, one per line."
        )
        return ADDING_OPTIONS
    
    context.user_data["options"] = options
    
    # Create keyboard for selecting the correct answer
    keyboard = []
    for i, option in enumerate(options):
        keyboard.append([InlineKeyboardButton(f"{i}. {option}", callback_data=f"answer_{i}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Great! I've recorded {len(options)} options.\n\n"
        f"Now please select the correct answer:",
        reply_markup=reply_markup
    )
    
    return ADDING_ANSWER

async def add_question_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the correct answer and create the question."""
    query = update.callback_query
    await query.answer()
    
    # Extract answer index from callback data
    answer_index = int(query.data.split('_')[1])
    context.user_data["answer"] = answer_index
    
    # Ask for ID preference
    keyboard = [
        [InlineKeyboardButton("Auto-generate ID", callback_data="auto_id")],
        [InlineKeyboardButton("Specify custom ID", callback_data="custom_id")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Selected answer: {answer_index}. {context.user_data['options'][answer_index]}\n\n"
        f"How would you like to assign an ID to this question?",
        reply_markup=reply_markup
    )
    
    return CUSTOM_ID

async def custom_id_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle ID selection method."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "auto_id":
        # Show category selection
        categories = ["General Knowledge", "Science", "History", "Geography", "Entertainment", "Sports"]
        keyboard = [[InlineKeyboardButton(cat, callback_data=f"category_{cat}")] for cat in categories]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Select a category for this question:",
            reply_markup=reply_markup
        )
        return CATEGORY_SELECTION
    else:
        # Custom ID requested
        await query.edit_message_text(
            "Please enter a numeric ID for this question.\n\n"
            "If the ID already exists, your question will be added to that ID without overwriting existing questions."
        )
        context.user_data["awaiting_custom_id"] = True
        return CUSTOM_ID

async def custom_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom ID input."""
    if context.user_data.get("awaiting_custom_id", False):
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
            return CATEGORY_SELECTION
        except ValueError:
            await update.message.reply_text(
                "Please enter a valid numeric ID."
            )
            return CUSTOM_ID
    
    return CUSTOM_ID

async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle category selection."""
    query = update.callback_query
    await query.answer()
    
    category = query.data.replace("category_", "")
    
    # Prepare the question data
    question_data = {
        "question": context.user_data["question"],
        "options": context.user_data["options"],
        "answer": context.user_data["answer"],
        "category": category
    }
    
    # Determine question ID
    if context.user_data.get("custom_id"):
        question_id = context.user_data["custom_id"]
    else:
        question_id = get_next_question_id()
    
    # Add the question with the ID (preserving existing questions)
    add_question_with_id(question_id, question_data)
    
    # Get how many questions are now at this ID
    questions = load_questions()
    question_count = len(questions[str(question_id)]) if isinstance(questions[str(question_id)], list) else 1
    
    await query.edit_message_text(
        f"✅ Question added successfully!\n\n"
        f"ID: {question_id} (This ID now has {question_count} question(s))\n"
        f"Question: {question_data['question']}\n"
        f"Category: {category}\n"
        f"Options: {len(question_data['options'])}\n"
        f"Correct answer: {question_data['answer']}. {question_data['options'][question_data['answer']]}"
    )
    
    # Clean up user data
    if "question" in context.user_data:
        del context.user_data["question"]
    if "options" in context.user_data:
        del context.user_data["options"]
    if "answer" in context.user_data:
        del context.user_data["answer"]
    if "custom_id" in context.user_data:
        del context.user_data["custom_id"]
    if "awaiting_custom_id" in context.user_data:
        del context.user_data["awaiting_custom_id"]
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current operation."""
    # Clean up user data
    keys_to_delete = [
        "question", "options", "answer", "custom_id", "awaiting_custom_id",
        "poll2q", "awaiting_poll_id", "poll_custom_id",
        "clone_url", "clone_questions", "clone_custom_id", "awaiting_clone_custom_id"
    ]
    
    for key in keys_to_delete:
        if key in context.user_data:
            del context.user_data[key]
    
    await update.message.reply_text(
        "Operation cancelled. What would you like to do next?"
    )
    return ConversationHandler.END

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a question by ID."""
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "Please provide a question ID to delete.\n"
            "Usage: /delete [question_id]"
        )
        return
    
    try:
        question_id = int(args[0])
        success = delete_question_by_id(question_id)
        
        if success:
            await update.message.reply_text(
                f"✅ Successfully deleted question with ID {question_id}."
            )
        else:
            await update.message.reply_text(
                f"❌ No question found with ID {question_id}."
            )
    except ValueError:
        await update.message.reply_text(
            "Invalid question ID. Please provide a numeric ID."
        )

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a quiz session with random questions."""
    args = context.args
    chat_id = update.effective_chat.id
    
    # Load all questions
    all_questions = load_questions()
    if not all_questions:
        await update.message.reply_text(
            "No questions available. Add some questions first using the /add command."
        )
        return
    
    question_id = None
    question_count = 5  # Default count
    
    if args:
        try:
            question_id = int(args[0])
            if str(question_id) not in all_questions:
                await update.message.reply_text(
                    f"No questions found with ID {question_id}. Please try another ID."
                )
                return
            
            # If second argument is provided, use it as question count
            if len(args) > 1:
                question_count = min(int(args[1]), 20)  # Limit to 20 questions
        except ValueError:
            await update.message.reply_text(
                "Invalid arguments. Usage: /quiz [question_id] [count]"
            )
            return
    else:
        # Random question ID if none provided
        question_id = int(random.choice(list(all_questions.keys())))
    
    # Get questions for the quiz
    selected_questions = []
    question_id_str = str(question_id)
    
    if question_id_str in all_questions:
        questions_at_id = all_questions[question_id_str]
        
        if isinstance(questions_at_id, list):
            # Multiple questions at this ID
            if len(questions_at_id) <= question_count:
                # Use all available questions if fewer than requested
                selected_questions = questions_at_id.copy()
                random.shuffle(selected_questions)
            else:
                # Select random subset
                selected_questions = random.sample(questions_at_id, question_count)
        else:
            # Single question at this ID
            selected_questions = [questions_at_id]
    
    if not selected_questions:
        await update.message.reply_text(
            f"No questions found with ID {question_id}."
        )
        return
    
    # Store quiz data in chat context
    context.chat_data["quiz"] = {
        "active": True,
        "questions": selected_questions,
        "current_index": 0,
        "sent_polls": {},
        "participants": {},
        "creator": {
            "id": update.effective_user.id,
            "name": update.effective_user.name,
            "username": update.effective_user.username
        }
    }
    
    # Announce quiz start
    await update.message.reply_text(
        f"🎮 Starting quiz with {len(selected_questions)} question(s)!\n\n"
        f"Category: {selected_questions[0].get('category', 'General Knowledge')}\n"
        f"ID: {question_id}\n\n"
        f"First question coming up in 3 seconds..."
    )
    
    # Schedule first question
    asyncio.create_task(
        send_question(context, chat_id, 0)
    )

async def send_question(context, chat_id, question_index):
    """Send a quiz question and schedule next one."""
    quiz = context.chat_data.get("quiz", {})
    
    if not quiz.get("active", False):
        return
    
    questions = quiz.get("questions", [])
    
    if question_index >= len(questions):
        # No more questions, end the quiz
        asyncio.create_task(
            schedule_end_quiz(context, chat_id)
        )
        return
    
    # Get the current question
    question_data = questions[question_index]
    
    question_text = question_data.get("question", "")
    options = question_data.get("options", [])
    answer_index = question_data.get("answer", 0)
    
    # Send the poll/quiz
    message = await context.bot.send_poll(
        chat_id=chat_id,
        question=f"Q{question_index+1}: {question_text}",
        options=options,
        type=Poll.QUIZ,
        correct_option_id=answer_index,
        is_anonymous=False,
        explanation=None
    )
    
    # Store poll id for tracking answers
    poll_id = message.poll.id
    quiz["sent_polls"][poll_id] = {
        "question_index": question_index,
        "correct_answer": answer_index,
        "answers": {}
    }
    
    # Update current index
    quiz["current_index"] = question_index + 1
    context.chat_data["quiz"] = quiz
    
    # Schedule next question if there are more
    if question_index + 1 < len(questions):
        asyncio.create_task(
            schedule_next_question(context, chat_id, question_index + 1)
        )
    else:
        # Schedule end of quiz after last question
        asyncio.create_task(
            schedule_end_quiz(context, chat_id)
        )

async def schedule_next_question(context, chat_id, next_index):
    """Schedule the next question with delay."""
    await asyncio.sleep(15)  # Wait 15 seconds between questions
    await send_question(context, chat_id, next_index)

async def schedule_end_quiz(context, chat_id):
    """Schedule end of quiz with delay."""
    await asyncio.sleep(15)  # Wait 15 seconds after last question
    await end_quiz(context, chat_id)

async def poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle poll answers from users."""
    answer_update = update.poll_answer
    user = answer_update.user
    poll_id = answer_update.poll_id
    selected_option = answer_update.option_ids[0] if answer_update.option_ids else None
    
    # Check if this poll is part of an active quiz
    quiz = context.chat_data.get("quiz", {})
    if not quiz.get("active", False):
        return
    
    sent_polls = quiz.get("sent_polls", {})
    if poll_id not in sent_polls:
        return
    
    poll_data = sent_polls[poll_id]
    correct_answer = poll_data.get("correct_answer")
    
    # Record user's answer
    user_id = str(user.id)
    poll_data["answers"][user_id] = {
        "user_name": user.full_name,
        "username": user.username,
        "answer": selected_option,
        "is_correct": selected_option == correct_answer
    }
    
    # Update participants stats
    participants = quiz.get("participants", {})
    if user_id not in participants:
        participants[user_id] = {
            "name": user.full_name,
            "username": user.username,
            "correct": 0,
            "answered": 0
        }
    
    participants[user_id]["answered"] += 1
    if selected_option == correct_answer:
        participants[user_id]["correct"] += 1
    
    # Update quiz data
    quiz["sent_polls"] = sent_polls
    quiz["participants"] = participants
    context.chat_data["quiz"] = quiz
    
    # Update user stats
    user_data = get_user_data(user.id)
    user_data["total_answered"] = user_data.get("total_answered", 0) + 1
    if selected_option == correct_answer:
        user_data["correct_answers"] = user_data.get("correct_answers", 0) + 1
    save_user_data(user.id, user_data)

async def initialize_telethon_client():
    """Initialize the Telethon client for quiz cloning if needed"""
    global telethon_client
    
    if not API_ID or not API_HASH or not PHONE_NUMBER:
        logger.warning("Telethon API credentials not set. Quiz cloning will not work.")
        return False
    
    if telethon_client and telethon_client.is_connected():
        return True
    
    try:
        # Create and connect the client
        if SESSION_STRING:
            telethon_client = telethon.TelegramClient(
                StringSession(SESSION_STRING),
                api_id=int(API_ID),
                api_hash=API_HASH
            )
        else:
            telethon_client = telethon.TelegramClient(
                "quiz_bot_session",
                api_id=int(API_ID),
                api_hash=API_HASH
            )
        
        await telethon_client.connect()
        
        # Check authorization
        if not await telethon_client.is_user_authorized():
            await telethon_client.send_code_request(PHONE_NUMBER)
            logger.warning("Telethon client not authorized. You need to sign in.")
            return False
        
        return True
    
    except Exception as e:
        logger.error(f"Error initializing Telethon client: {e}")
        return False

async def extract_quiz_from_url(url):
    """Extract quiz questions from any Telegram channel URL using Telethon"""
    global telethon_client
    
    # Initialize Telethon client if needed
    if not await initialize_telethon_client():
        return None, "Failed to initialize Telethon client. Please check your API credentials."
    
    try:
        # Parse URL to get message ID and chat name - case insensitive
        match = re.search(r't\.me/([a-zA-Z0-9_]+)/(\d+)', url, re.IGNORECASE)
        if not match:
            return None, "Invalid Telegram URL. Please provide a valid URL in the format t.me/channel_name/12345"
        
        channel_name = match.group(1)
        message_id = int(match.group(2))
        
        try:
            # Get the channel entity
            channel_entity = await telethon_client.get_entity(channel_name)
            
            # Get the message
            messages = await telethon_client.get_messages(channel_entity, ids=message_id)
            if not messages or len(messages) == 0:
                return None, "Could not find the message. It may be deleted or inaccessible."
            
            quiz_message = messages[0]
            
            # Check if it's a quiz message (has a poll)
            quiz_questions = []
            
            if hasattr(quiz_message, 'poll') and quiz_message.poll:
                # Direct poll message
                poll = quiz_message.poll
                correct_option = next((i for i, opt in enumerate(poll.results.results) if opt.correct), 0)
                
                question_data = {
                    "question": poll.question,
                    "options": [opt.text for opt in poll.answers],
                    "answer": correct_option,
                    "category": "Cloned Quiz",
                    "sourceUrl": url
                }
                quiz_questions.append(question_data)
            else:
                # Try to find polls in replies
                related_messages = await telethon_client.get_messages(
                    channel_entity, 
                    limit=20,
                    reply_to=quiz_message.id
                )
                
                for msg in related_messages:
                    if hasattr(msg, 'poll') and msg.poll:
                        poll = msg.poll
                        correct_option = next((i for i, opt in enumerate(poll.results.results) if opt.correct), 0)
                        
                        question_data = {
                            "question": poll.question,
                            "options": [opt.text for opt in poll.answers],
                            "answer": correct_option,
                            "category": "Cloned Quiz",
                            "sourceUrl": url
                        }
                        quiz_questions.append(question_data)
            
            if not quiz_questions:
                return None, "Could not find any quiz questions in this message or its replies."
            
            return quiz_questions, None
            
        except Exception as e:
            logger.error(f"Error processing message from {channel_name}: {e}")
            return None, f"Error processing quiz: {str(e)}"
            
    except Exception as e:
        logger.error(f"Error extracting quiz from URL: {e}")
        return None, f"Error extracting quiz: {str(e)}"

async def clone_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Command handler to start the quiz cloning process"""
    # Check if user has proper permissions (optional)
    # user = update.effective_user
    # if user.id not in ADMIN_IDS:
    #     await update.message.reply_text("You don't have permission to use this command.")
    #     return ConversationHandler.END
    
    await update.message.reply_text(
        "🔄 Quiz Cloning\n\n"
        "Send me the URL of a Telegram quiz that you want to clone.\n"
        "The URL can be in any format like:\n"
        "- https://t.me/quizbot/12345 (QuizBot quiz)\n"
        "- https://t.me/rajasthan_gk_study_quizz/5624 (Any channel quiz)\n\n"
        "Type /cancel to cancel the operation."
    )
    return CLONE_URL

async def clone_url_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the quiz URL for cloning"""
    url = update.message.text.strip()
    
    # Check if it's a valid Telegram URL with message ID - case insensitive
    if not re.search(r't\.me/([a-zA-Z0-9_]+)/(\d+)', url, re.IGNORECASE):
        await update.message.reply_text(
            "That doesn't look like a valid Telegram URL.\n"
            "The URL should look like:\n"
            "- https://t.me/quizbot/12345 (QuizBot quiz)\n"
            "- https://t.me/rajasthan_gk_study_quizz/5624 (Any channel quiz)\n\n"
            "Please try again or type /cancel to abort."
        )
        return CLONE_URL
    
    # Store the URL in user data
    context.user_data["clone_url"] = url
    
    # Tell user we're processing
    processing_message = await update.message.reply_text(
        "⏳ Processing quiz URL...\n"
        "This may take a moment as I extract the questions."
    )
    
    # Extract questions from the URL
    questions, error = await extract_quiz_from_url(url)
    
    if error or not questions:
        await update.message.reply_text(
            f"❌ Failed to clone quiz: {error or 'No questions found.'}\n\n"
            f"Please check the URL and try again, or contact the administrator."
        )
        return ConversationHandler.END
    
    # Store extracted questions
    context.user_data["clone_questions"] = questions
    
    # Update processing message
    await context.bot.edit_message_text(
        f"✅ Successfully extracted {len(questions)} question(s) from quiz!\n\n"
        f"Would you like to use an auto-generated ID or specify a custom ID for these questions?",
        chat_id=processing_message.chat_id,
        message_id=processing_message.message_id
    )
    
    # Ask for ID preference
    keyboard = [
        [InlineKeyboardButton("Auto-generate ID", callback_data="clone_auto_id")],
        [InlineKeyboardButton("Specify custom ID", callback_data="clone_custom_id")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Choose an ID option:",
        reply_markup=reply_markup
    )
    
    return CLONE_CUSTOM_ID

async def clone_id_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle ID selection for cloned questions"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "clone_auto_id":
        # Show category selection
        categories = ["General Knowledge", "Science", "History", "Geography", "Entertainment", "Sports", "Cloned Quiz"]
        keyboard = [[InlineKeyboardButton(cat, callback_data=f"clone_category_{cat}")] for cat in categories]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Select a category for these questions:",
            reply_markup=reply_markup
        )
        return CLONE_CATEGORY
    else:
        # Ask for custom ID
        await query.edit_message_text(
            "Please enter a numeric ID for these questions.\n\n"
            "If the ID already exists, your questions will be added to that ID without overwriting existing questions."
        )
        context.user_data["awaiting_clone_custom_id"] = True
        return CLONE_CUSTOM_ID

async def clone_custom_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom ID input for cloned questions"""
    try:
        custom_id = int(update.message.text)
        context.user_data["clone_custom_id"] = custom_id
        
        # Show category selection
        categories = ["General Knowledge", "Science", "History", "Geography", "Entertainment", "Sports", "Cloned Quiz"]
        keyboard = [[InlineKeyboardButton(cat, callback_data=f"clone_category_{cat}")] for cat in categories]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Select a category for these questions:",
            reply_markup=reply_markup
        )
        return CLONE_CATEGORY
    except ValueError:
        await update.message.reply_text(
            "Please enter a valid numeric ID."
        )
        return CLONE_CUSTOM_ID

async def clone_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle category selection for cloned questions"""
    query = update.callback_query
    await query.answer()
    
    category = query.data.replace("clone_category_", "")
    
    # Get the questions from user data
    questions = context.user_data.get("clone_questions", [])
    
    # Set category for all questions
    for question in questions:
        question["category"] = category
    
    # Generate or use custom ID
    if context.user_data.get("clone_custom_id"):
        question_id = context.user_data["clone_custom_id"]
    else:
        question_id = get_next_question_id()
    
    # Add all questions under the same ID
    for question in questions:
        add_question_with_id(question_id, question)
    
    # Construct success message
    clone_url = context.user_data.get("clone_url", "")
    
    await query.edit_message_text(
        f"✅ Successfully cloned {len(questions)} question(s) with ID: {question_id}\n\n"
        f"Category: {category}\n"
        f"Source: {clone_url}\n\n"
        f"You can now use these questions in your quizzes!"
    )
    
    # Clean up
    if "clone_custom_id" in context.user_data:
        del context.user_data["clone_custom_id"]
    if "awaiting_clone_custom_id" in context.user_data:
        del context.user_data["awaiting_clone_custom_id"]
    if "clone_questions" in context.user_data:
        del context.user_data["clone_questions"]
    if "clone_url" in context.user_data:
        del context.user_data["clone_url"]
    
    return ConversationHandler.END

async def end_quiz(context, chat_id):
    """End the quiz and display results with all participants."""
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
                        "answered": 0
                    }
                
                participants[user_id]["answered"] += 1
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
            "answered": 0
        }
    
    # Create results message
    results_message = f"🏁 The quiz has finished!\n\n{questions_count} questions answered\n\n"
    
    # Sort participants by correct answers (desc) and answered (asc)
    sorted_participants = sorted(
        participants.items(),
        key=lambda x: (x[1].get("correct", 0), -x[1].get("answered", 0)),
        reverse=True
    )
    
    # Format results
    if sorted_participants:
        winner_id, winner_data = sorted_participants[0]
        winner_name = winner_data.get("name", "Quiz Taker")
        
        results_message += f"🏆 Congratulations to the winner: {winner_name}!\n\n"
        results_message += "📊 Final Ranking 📊\n"
        
        # Show all participants with ranks
        for i, (user_id, data) in enumerate(sorted_participants):
            rank_emoji = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
            
            name = data.get("name", f"Player {i+1}")
            username = data.get("username", "")
            username_text = f" (@{username})" if username else ""
            
            correct = data.get("correct", 0)
            percentage = (correct / questions_count * 100) if questions_count > 0 else 0
            
            results_message += f"{rank_emoji} {name}{username_text}: {correct}/{questions_count} ({percentage:.1f}%)\n"
    else:
        results_message += "No participants found for this quiz."
    
    # Send results
    await context.bot.send_message(
        chat_id=chat_id,
        text=results_message
    )

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

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Basic command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("delete", delete_command))
    
    # Quiz cloning command handler
    clone_handler = ConversationHandler(
        entry_points=[CommandHandler("clone", clone_quiz_command)],
        states={
            CLONE_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, clone_url_handler)
            ],
            CLONE_CUSTOM_ID: [
                CallbackQueryHandler(clone_id_callback, pattern=r"^clone_(auto|custom)_id$"),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, 
                    clone_custom_id_input,
                    filters=filters.TEXT
                )
            ],
            CLONE_CATEGORY: [
                CallbackQueryHandler(clone_category_callback, pattern=r"^clone_category_")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(clone_handler)
    
    # Question adding conversation handler
    add_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_question_start)],
        states={
            ADDING_QUESTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_text)
            ],
            ADDING_OPTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_options)
            ],
            ADDING_ANSWER: [
                CallbackQueryHandler(add_question_answer, pattern=r"^answer_")
            ],
            CUSTOM_ID: [
                CallbackQueryHandler(custom_id_callback, pattern=r"^(auto|custom)_id$"),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, 
                    custom_id_input,
                    filters=filters.TEXT
                )
            ],
            CATEGORY_SELECTION: [
                CallbackQueryHandler(category_callback, pattern=r"^category_")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(add_handler)
    
    # Poll to question conversion handlers
    application.add_handler(CommandHandler("poll2q", poll_to_question))
    application.add_handler(MessageHandler(
        filters.FORWARDED & filters.ChatType.PRIVATE,
        handle_forwarded_poll
    ))
    application.add_handler(CallbackQueryHandler(
        handle_poll_answer,
        pattern=r"^poll_answer_"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_poll_id_selection,
        pattern=r"^pollid_(auto|custom)$"
    ))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_poll_custom_id
    ))
    application.add_handler(CallbackQueryHandler(
        handle_poll_category,
        pattern=r"^pollcat_"
    ))
    
    # Poll answer handler
    application.add_handler(application.poll_answer_handler(poll_answer))
    
    # Run the bot until the user presses Ctrl-C
    application.run_polling()

if __name__ == "__main__":
    main()
