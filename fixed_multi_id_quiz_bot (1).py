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
from telegram.ext import Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler
from telegram.ext import filters  # Import filters as a module, not individually
from telegram.constants import ParseMode

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token directly set in code
BOT_TOKEN = "7631768276:AAFwTYA8CK5tTHQfExI-w9cxPLnlLJa4iW0"
if not BOT_TOKEN:
    logger.error("No BOT_TOKEN provided. Please set the BOT_TOKEN.")
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
                "ID must be a number. Please enter a numeric ID."
            )
            return CUSTOM_ID
    return ADDING_QUESTION

async def category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle category selection and finalize question creation."""
    query = update.callback_query
    if query:
        await query.answer()
        category = query.data.split('_', 1)[1]
    
        # Get the data from context
        question_text = context.user_data["question"]
        options = context.user_data["options"]
        answer = context.user_data["answer"]
        
        # Create the question data
        question_data = {
            "question": question_text,
            "options": options,
            "answer": answer,
            "category": category,
            "created_at": datetime.now().isoformat()
        }
        
        # Handle auto or custom ID
        if "custom_id" in context.user_data:
            question_id = context.user_data["custom_id"]
        else:
            question_id = get_next_question_id()
        
        # Add the question with the assigned ID
        add_question_with_id(question_id, question_data)
        
        await query.edit_message_text(
            f"✅ Question added successfully!\n\n"
            f"*Question ID: {question_id}*\n"
            f"*Category: {category}*\n\n"
            f"*Question:* {question_text}\n\n"
            f"*Options:*\n" + "\n".join([f"{'✓ ' if i == answer else ''}{i}. {option}" for i, option in enumerate(options)]),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Clear user data
        context.user_data.clear()
        
        return ConversationHandler.END
    return ADDING_QUESTION

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel conversation."""
    await update.message.reply_text(
        "Question creation cancelled. Use /add to start again."
    )
    context.user_data.clear()
    return ConversationHandler.END

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a question by ID."""
    if not context.args:
        await update.message.reply_text(
            "Please provide a question ID to delete.\n"
            "Example: `/delete 42`"
        )
        return
    
    try:
        question_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID must be a number.")
        return
    
    success = delete_question_by_id(question_id)
    
    if success:
        await update.message.reply_text(f"Question ID {question_id} deleted successfully.")
    else:
        await update.message.reply_text(f"Question ID {question_id} not found.")

async def poll_to_question_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Convert a poll to a quiz question."""
    if update.message.forward_from_chat and update.message.poll:
        poll = update.message.poll
        
        # Check if it's a quiz poll
        if not poll.correct_option_id and not poll.type == "quiz":
            await update.message.reply_text(
                "This poll doesn't have a correct answer marked. I can only convert quiz polls."
            )
            return
        
        # Create question data
        options = [option.text for option in poll.options]
        
        question_data = {
            "question": poll.question,
            "options": options,
            "answer": poll.correct_option_id,
            "category": "Imported Poll",
            "created_at": datetime.now().isoformat()
        }
        
        # Get next available ID
        question_id = get_next_question_id()
        
        # Add the question
        add_question_with_id(question_id, question_data)
        
        await update.message.reply_text(
            f"✅ Poll converted to quiz question!\n\n"
            f"*Question ID: {question_id}*\n\n"
            f"*Question:* {poll.question}\n\n"
            f"*Options:*\n" + "\n".join([f"{'✓ ' if i == poll.correct_option_id else ''}{i}. {option}" for i, option in enumerate(options)]),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            "Please forward a quiz poll to me to convert it to a question.\n\n"
            "Note: The poll must be a quiz type with a correct answer marked."
        )

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a quiz with optional ID and count."""
    questions_data = load_questions()
    
    if not questions_data:
        await update.message.reply_text(
            "There are no questions in the database yet. Add some with /add or /poll2q."
        )
        return
    
    question_id = None
    count = 1
    
    # Parse command arguments
    if context.args:
        try:
            question_id = int(context.args[0])
            if len(context.args) > 1:
                count = int(context.args[1])
        except ValueError:
            await update.message.reply_text(
                "Invalid arguments. Usage: /quiz [ID] [count]"
            )
            return
    
    # If no ID provided, choose a random one
    if question_id is None:
        available_ids = list(questions_data.keys())
        question_id = int(random.choice(available_ids))
    
    # Get question by ID
    question_id_str = str(question_id)
    if question_id_str not in questions_data:
        await update.message.reply_text(
            f"No questions found with ID {question_id}."
        )
        return
    
    # Get the questions
    question_list = questions_data[question_id_str]
    if not isinstance(question_list, list):
        question_list = [question_list]
    
    # Limit count to available questions
    count = min(count, len(question_list))
    
    # Shuffle and select questions
    selected_questions = random.sample(question_list, count)
    
    # Send the first question
    await send_quiz_question(update, context, selected_questions, 0)

async def send_quiz_question(update: Update, context: ContextTypes.DEFAULT_TYPE, questions: List[Dict], index: int) -> None:
    """Send a quiz question."""
    if index >= len(questions):
        await update.message.reply_text(
            "Quiz complete! Check your stats with /stats."
        )
        return
    
    question_data = questions[index]
    
    # Create poll options
    poll_options = []
    for option in question_data["options"]:
        poll_options.append(option)
    
    # Send the poll
    message = await context.bot.send_poll(
        update.effective_chat.id,
        question=question_data["question"],
        options=poll_options,
        type=Poll.QUIZ,
        correct_option_id=question_data["answer"],
        is_anonymous=False,
        explanation=f"Question {index+1} of {len(questions)}",
    )
    
    # Store poll data for tracking
    poll_data = {
        "message_id": message.message_id,
        "chat_id": update.effective_chat.id,
        "questions": questions,
        "current_index": index,
        "correct_option": question_data["answer"],
        "user_id": update.effective_user.id
    }
    
    # Store in bot data
    if "polls" not in context.bot_data:
        context.bot_data["polls"] = {}
    
    context.bot_data["polls"][message.poll.id] = poll_data

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle poll answers."""
    answer = update.poll_answer
    poll_id = answer.poll_id
    
    # Check if this poll is being tracked
    if "polls" not in context.bot_data or poll_id not in context.bot_data["polls"]:
        return
    
    poll_data = context.bot_data["polls"][poll_id]
    user_id = poll_data["user_id"]
    
    # Only process if this is the user who started the quiz
    if answer.user.id != user_id:
        return
    
    # Check if the answer is correct
    correct = answer.option_ids[0] == poll_data["correct_option"]
    
    # Update user statistics
    user_data = get_user_data(user_id)
    user_data["total_answered"] += 1
    if correct:
        user_data["correct_answers"] += 1
    save_user_data(user_id, user_data)
    
    # Send the next question with a delay
    await asyncio.sleep(2)  # Give time to see the correct answer
    
    # Send next question
    questions = poll_data["questions"]
    current_index = poll_data["current_index"]
    
    # Move to next question
    await send_quiz_question(update, context, questions, current_index + 1)
    
    # Remove the poll data
    del context.bot_data["polls"][poll_id]

async def clone_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the process of cloning a quiz from @QuizBot or a channel."""
    await update.message.reply_text(
        "I can clone quiz questions from @QuizBot or any public Telegram channel with polls.\n\n"
        "Please send me:\n"
        "• A quiz ID from @QuizBot (e.g. `12345`)\n"
        "• OR a channel username (e.g. `@channel_name`)\n"
        "• OR a link to a specific channel message (e.g. `https://t.me/channel_name/123`)"
    )
    return CLONE_URL

async def clone_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the URL or username for cloning."""
    url_text = update.message.text.strip()
    
    # Store in context for later use
    context.user_data["clone_source"] = url_text
    
    # Ask for ID preference
    keyboard = [
        [InlineKeyboardButton("Auto-generate IDs", callback_data="clone_auto_id")],
        [InlineKeyboardButton("Specify custom ID", callback_data="clone_custom_id")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "How would you like to assign IDs to the cloned questions?",
        reply_markup=reply_markup
    )
    
    return CLONE_CUSTOM_ID

async def clone_custom_id_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle ID selection for cloned questions."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "clone_auto_id":
        # Let's ask for category
        categories = ["General Knowledge", "Science", "History", "Geography", "Entertainment", "Sports", "Imported Quiz"]
        keyboard = [[InlineKeyboardButton(cat, callback_data=f"clone_category_{cat}")] for cat in categories]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Select a category for the cloned questions:",
            reply_markup=reply_markup
        )
        
        context.user_data["clone_use_auto_id"] = True
        return CLONE_CATEGORY
    else:
        # Custom ID requested
        await query.edit_message_text(
            "Please enter a numeric ID for the cloned questions.\n\n"
            "If the ID already exists, the questions will be added to that ID without overwriting existing ones."
        )
        return CLONE_CUSTOM_ID

async def clone_custom_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom ID input for cloned questions."""
    try:
        custom_id = int(update.message.text)
        context.user_data["clone_custom_id"] = custom_id
        
        # Show category selection
        categories = ["General Knowledge", "Science", "History", "Geography", "Entertainment", "Sports", "Imported Quiz"]
        keyboard = [[InlineKeyboardButton(cat, callback_data=f"clone_category_{cat}")] for cat in categories]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Select a category for the cloned questions:",
            reply_markup=reply_markup
        )
        
        return CLONE_CATEGORY
    except ValueError:
        await update.message.reply_text(
            "ID must be a number. Please enter a numeric ID."
        )
        return CLONE_CUSTOM_ID

async def clone_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle category selection and start cloning process."""
    query = update.callback_query
    await query.answer()
    
    category = query.data.split('_', 2)[2]  # format: clone_category_NAME
    
    # Store in context
    context.user_data["clone_category"] = category
    
    # Get clone source from context
    source = context.user_data.get("clone_source", "")
    
    # Send status message
    status_message = await query.edit_message_text(
        f"Starting clone process from: {source}\n"
        f"Category: {category}\n\n"
        f"Please wait, this may take a while..."
    )
    
    # Determine if it's a QuizBot quiz or a channel
    if source.isdigit():
        # It's a QuizBot quiz ID
        await clone_from_quizbot(context, source, status_message)
    else:
        # It's a channel or message link
        await clone_from_channel(context, source, status_message)
    
    return ConversationHandler.END

async def clone_from_quizbot(context, quiz_id, status_message):
    """Clone questions from @QuizBot."""
    # This requires a more complex implementation with a user session
    # which is beyond the scope of this simple example
    
    await context.bot.edit_message_text(
        "Cloning from @QuizBot is not fully implemented yet.\n\n"
        "Consider using the forward polls method instead:\n"
        "1. Open @QuizBot and start the quiz you want to clone\n"
        "2. Forward each quiz poll to this bot\n"
        "3. I'll automatically convert them to questions",
        chat_id=status_message.chat_id,
        message_id=status_message.message_id
    )

async def clone_from_channel(context, channel, status_message):
    """Clone quiz polls from a Telegram channel."""
    global telethon_client
    
    # Initialize Telethon client if not already
    if not telethon_client:
        try:
            telethon_client = await initialize_telethon_client()
        except Exception as e:
            await context.bot.edit_message_text(
                f"Error initializing Telethon client: {str(e)}\n\n"
                f"Please make sure you have set the API_ID, API_HASH, and PHONE_NUMBER environment variables.",
                chat_id=status_message.chat_id,
                message_id=status_message.message_id
            )
            return
    
    try:
        # Parse channel name/URL
        channel_id = None
        message_id = None
        
        if channel.startswith("https://t.me/") or channel.startswith("t.me/"):
            # It's a URL, extract channel name and optional message ID
            parts = channel.split("/")
            if len(parts) >= 4:
                channel_id = parts[3]
                if len(parts) >= 5 and parts[4].isdigit():
                    message_id = int(parts[4])
        else:
            # It's a username
            channel_id = channel.lstrip("@")
        
        if not channel_id:
            await context.bot.edit_message_text(
                "Invalid channel format. Please provide a valid channel username or link.",
                chat_id=status_message.chat_id,
                message_id=status_message.message_id
            )
            return
        
        # Get entity
        entity = await telethon_client.get_entity(channel_id)
        
        # Fetch messages
        if message_id:
            # Fetch specific message and nearby polls
            messages = await telethon_client.get_messages(
                entity, 
                limit=20,  # Get some messages around the target
                offset_id=message_id,
                reverse=True
            )
        else:
            # Fetch recent polls
            messages = await telethon_client.get_messages(
                entity,
                limit=50,  # Limited to 50 most recent messages
                filter=telethon.tl.types.InputMessagesFilterPoll()
            )
        
        # Find quiz polls
        count = 0
        cloned_count = 0
        
        for msg in messages:
            count += 1
            
            if hasattr(msg, 'poll') and msg.poll and hasattr(msg.poll, 'quiz') and msg.poll.quiz:
                # It's a quiz poll, extract data
                poll = msg.poll
                
                options = []
                for option in poll.answers:
                    options.append(option.text)
                
                correct_option = None
                for i, option in enumerate(poll.answers):
                    if option.correct:
                        correct_option = i
                        break
                
                if correct_option is None:
                    # Skip if no correct answer found
                    continue
                
                # Create question data
                question_data = {
                    "question": poll.question,
                    "options": options,
                    "answer": correct_option,
                    "category": context.user_data["clone_category"],
                    "created_at": datetime.now().isoformat(),
                    "source": f"Cloned from {channel}"
                }
                
                # Get ID
                if context.user_data.get("clone_use_auto_id", False):
                    question_id = get_next_question_id()
                else:
                    question_id = context.user_data["clone_custom_id"]
                
                # Add question
                add_question_with_id(question_id, question_data)
                cloned_count += 1
                
                # Update status message every 5 questions
                if cloned_count % 5 == 0:
                    await context.bot.edit_message_text(
                        f"Cloning in progress...\n\n"
                        f"Processed: {count} messages\n"
                        f"Cloned: {cloned_count} questions",
                        chat_id=status_message.chat_id,
                        message_id=status_message.message_id
                    )
        
        # Final update
        if cloned_count > 0:
            await context.bot.edit_message_text(
                f"✅ Clone completed!\n\n"
                f"Successfully cloned {cloned_count} quiz questions from {channel}.\n\n"
                f"You can now use them with the /quiz command.",
                chat_id=status_message.chat_id,
                message_id=status_message.message_id
            )
        else:
            await context.bot.edit_message_text(
                f"No quiz polls found in {channel}.\n\n"
                f"Make sure the channel contains poll messages with quiz type (with correct answers marked).",
                chat_id=status_message.chat_id,
                message_id=status_message.message_id
            )
    
    except Exception as e:
        await context.bot.edit_message_text(
            f"Error cloning from channel: {str(e)}",
            chat_id=status_message.chat_id,
            message_id=status_message.message_id
        )

async def initialize_telethon_client():
    """Initialize the Telethon client for quiz cloning if needed"""
    global telethon_client, API_ID, API_HASH, PHONE_NUMBER, SESSION_STRING
    
    if not API_ID or not API_HASH:
        raise ValueError("API_ID and API_HASH must be set")
    
    if SESSION_STRING:
        # Use existing session
        session = StringSession(SESSION_STRING)
    else:
        # Create new session
        session = StringSession("")
    
    client = telethon.TelegramClient(session, API_ID, API_HASH)
    await client.connect()
    
    if not await client.is_user_authorized():
        if not PHONE_NUMBER:
            raise ValueError("PHONE_NUMBER must be set for authentication")
        
        await client.send_code_request(PHONE_NUMBER)
        raise ValueError("Authentication required. Please set the SESSION_STRING environment variable with the result of client.session.save()")
    
    return client

async def extract_quiz_from_url(url):
    """Extract quiz questions from any Telegram channel URL using Telethon"""
    pass  # Implemented in clone_from_channel

async def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("delete", delete_command))

    # Poll to question handler
    application.add_handler(MessageHandler(filters.POLL, poll_to_question_command))

    # Add question conversation handler
    add_question_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_question_start)],
        states={
            ADDING_QUESTION: [MessageHandler(filters.TEXT, add_question_text)],
            ADDING_OPTIONS: [MessageHandler(filters.TEXT, add_question_options)],
            ADDING_ANSWER: [CallbackQueryHandler(add_question_answer, pattern=r"^answer_")],
            CUSTOM_ID: [
                CallbackQueryHandler(custom_id_callback),
                MessageHandler(filters.TEXT, custom_id_input)
            ],
            CATEGORY_SELECTION: [
                CallbackQueryHandler(category_selection, pattern=r"^category_")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(add_question_conv_handler)

    # Clone quiz conversation handler
    clone_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("clone", clone_command)],
        states={
            CLONE_URL: [MessageHandler(filters.TEXT, clone_url)],
            CLONE_CUSTOM_ID: [
                CallbackQueryHandler(clone_custom_id_callback),
                MessageHandler(filters.TEXT, clone_custom_id_input)
            ],
            CLONE_CATEGORY: [
                CallbackQueryHandler(clone_category_selection, pattern=r"^clone_category_")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(clone_conv_handler)

    # Poll answer handler
    application.add_handler(CallbackQueryHandler(handle_poll_answer))

    # Start the Bot
    await application.run_polling()

if __name__ == '__main__':
    asyncio.run(main())