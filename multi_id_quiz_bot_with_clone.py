"""
Complete Telegram Quiz Bot with multi-question ID support:
1. Add multiple questions with same ID
2. Poll to question conversion with multi-ID support
3. Show all participants in final results
4. Auto-sequencing questions
5. Direct quiz cloning from @QuizBot
"""

import json
import logging
import os
import random
import asyncio
import re
import requests
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler, PollAnswerHandler

# Telethon imports for QuizBot cloning
import telethon
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import PeerUser, PeerChannel

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment variable
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7631768276:AAFwTYA8CK5tTHQfExI-w9cxPLnlLJa4iW0")

# Telethon API credentials for quiz cloning
API_ID = os.environ.get("API_ID", "28624690")  # Replace with your actual API ID
API_HASH = os.environ.get("API_HASH", "67e6593b5a9b5ab20b11ccef6700af5f")  # Replace with your actual API Hash
PHONE_NUMBER = os.environ.get("PHONE_NUMBER", "+919351504990")  # Replace with your phone number
SESSION_STRING = os.environ.get("SESSION_STRING")

# Global Telethon client for quiz cloning
telethon_client = None

# Conversation states
QUESTION, OPTIONS, ANSWER, CATEGORY = range(4)
EDIT_SELECT, EDIT_QUESTION, EDIT_OPTIONS = range(4, 7)
CLONE_URL, CLONE_MANUAL = range(7, 9)
CUSTOM_ID = range(9, 10)
CLONE_SOURCE, CLONE_ID, CLONE_CATEGORY = range(10, 13)

# Data files
QUESTIONS_FILE = "questions.json"
USERS_FILE = "users.json"

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
        "• 📩 *Clone Quiz:* `/clone`\n"
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
    await asyncio.sleep(30)  # Wait 30 seconds
    
    # Check if quiz is still active
    quiz = context.chat_data.get("quiz", {})
    if quiz.get("active", False):
        await send_question(context, chat_id, next_index)

async def schedule_end_quiz(context, chat_id):
    """Schedule end of quiz with delay."""
    await asyncio.sleep(30)  # Wait 30 seconds after last question
    
    # End the quiz
    await end_quiz(context, chat_id)

async def poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle poll answers from users."""
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
                        "answered": 0
                    }
                
                participants[str(user.id)]["answered"] += 1
                if is_correct:
                    participants[str(user.id)]["correct"] += 1
                
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

async def initialize_telethon_client():
    """Initialize the Telethon client for quiz cloning"""
    global telethon_client
    
    # Check if API credentials are set and valid
    try:
        api_id = int(API_ID) if API_ID else None
        api_hash = API_HASH
        
        if not api_id or not api_hash:
            logger.warning("Telethon API credentials are incomplete. Quiz cloning feature will be limited.")
            return None
            
        try:
            if SESSION_STRING:
                # Use existing session
                client = TelegramClient(StringSession(SESSION_STRING), api_id, api_hash)
            else:
                # Create new session
                client = TelegramClient(StringSession(), api_id, api_hash)
            
            await client.connect()
            
            # Check if already authorized
            if not await client.is_user_authorized():
                if not PHONE_NUMBER:
                    logger.warning("Phone number not provided and no session found. Cannot authenticate Telethon client.")
                    return None
                    
                # Send code request
                await client.send_code_request(PHONE_NUMBER)
                logger.info(f"Authentication code sent to {PHONE_NUMBER}")
                return None  # Will need to complete auth in another step
                
            logger.info("Telethon client initialized successfully")
            telethon_client = client
            return client
        except Exception as e:
            logger.error(f"Error initializing Telethon client: {e}")
            return None
    except (ValueError, TypeError):
        logger.warning("Invalid API_ID format. API_ID must be a number.")
        return None

async def clone_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the process of cloning a quiz from @QuizBot."""
    await update.message.reply_text(
        "🔄 *Clone Quiz Feature* 🔄\n\n"
        "I can clone entire quizzes directly from the official @QuizBot!\n\n"
        "Please send me:\n"
        "• A quiz ID from @QuizBot (e.g. `12345`)\n"
        "• OR a direct link to a quiz (e.g. `https://t.me/QuizBot?start=quizId`)\n\n"
        "You can find quiz IDs by looking at the URL when you open a quiz in @QuizBot.",
        parse_mode='Markdown'
    )
    return CLONE_SOURCE

async def clone_source_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the source input and ask for ID preferences."""
    source_text = update.message.text.strip()
    
    # Extract quiz ID if it's a URL
    if source_text.startswith("https://") or source_text.startswith("http://"):
        # Try to extract the quiz ID from the URL
        match = re.search(r'[?&]start=(\w+)', source_text)
        if match:
            source_text = match.group(1)
        else:
            await update.message.reply_text(
                "I couldn't extract a quiz ID from that URL. Please send me just the quiz ID number."
            )
            return CLONE_SOURCE
    
    # Store in context for later use
    context.user_data["clone_source"] = source_text
    
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
    
    return CLONE_ID

async def clone_id_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle ID selection for cloned questions."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "clone_auto_id":
        # Let's ask for category
        categories = ["General Knowledge", "Science", "History", "Geography", "Entertainment", "Sports", "Imported Quiz"]
        keyboard = [[InlineKeyboardButton(cat, callback_data=f"clone_cat_{cat}")] for cat in categories]
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
        context.user_data["awaiting_clone_id"] = True
        return CLONE_ID

async def clone_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom ID input for cloned questions."""
    try:
        custom_id = int(update.message.text)
        context.user_data["clone_custom_id"] = custom_id
        context.user_data["awaiting_clone_id"] = False
        
        # Show category selection
        categories = ["General Knowledge", "Science", "History", "Geography", "Entertainment", "Sports", "Imported Quiz"]
        keyboard = [[InlineKeyboardButton(cat, callback_data=f"clone_cat_{cat}")] for cat in categories]
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
        return CLONE_ID

async def clone_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle category selection and start cloning process."""
    query = update.callback_query
    await query.answer()
    
    category = query.data.split('_', 2)[2]  # format: clone_cat_NAME
    
    # Store in context
    context.user_data["clone_category"] = category
    
    # Get clone source from context
    source = context.user_data.get("clone_source", "")
    
    # Send status message
    status_message = await query.edit_message_text(
        f"Starting clone process from QuizBot ID: {source}\n"
        f"Category: {category}\n\n"
        f"Please wait, this may take a while..."
    )
    
    # Start the cloning process
    await clone_quiz_from_quizbot(update, context, source, status_message)
    
    return ConversationHandler.END

async def clone_quiz_from_quizbot(update, context, quiz_id, status_message):
    """Clone questions from @QuizBot."""
    global telethon_client
    
    # For progress updates
    await status_message.edit_text(
        f"Cloning quiz {quiz_id} from @QuizBot...\n\n"
        f"Step 1/3: Initializing connection..."
    )
    
    # Initialize Telethon client if needed
    if not telethon_client:
        await status_message.edit_text(
            f"Cloning quiz {quiz_id} from @QuizBot...\n\n"
            f"Step 1/3: Initializing connection...\n"
            f"Connecting to Telegram..."
        )
        
        client = await initialize_telethon_client()
        if not client:
            # If Telethon initialization failed, offer workaround
            await status_message.edit_text(
                f"Unable to initialize direct cloning feature.\n\n"
                f"To clone a quiz from @QuizBot manually:\n"
                f"1. Open @QuizBot and start the quiz: {quiz_id}\n"
                f"2. Forward each quiz question to me\n"
                f"3. I'll convert each one as you send them"
            )
            return
    else:
        client = telethon_client
    
    try:
        # Update progress
        await status_message.edit_text(
            f"Cloning quiz {quiz_id} from @QuizBot...\n\n"
            f"Step 2/3: Accessing quiz content...\n"
            f"Sending request to QuizBot..."
        )
        
        # Send /start command with quiz ID to QuizBot
        quizbot_entity = await client.get_entity("QuizBot")
        await client.send_message(quizbot_entity, f"/start {quiz_id}")
        
        # Wait a moment for QuizBot to respond
        await asyncio.sleep(2)
        
        # Get the welcome message and verify it's a quiz
        messages = await client.get_messages(quizbot_entity, limit=5)
        valid_quiz = False
        quiz_title = "Imported Quiz"
        
        for msg in messages:
            # Look for welcome message that confirms this is a quiz
            if hasattr(msg, 'text') and "start the quiz" in msg.text.lower():
                valid_quiz = True
                # Try to extract the quiz title
                lines = msg.text.split('\n')
                if len(lines) > 0:
                    potential_title = lines[0].strip()
                    if potential_title and len(potential_title) < 50:  # Reasonable title length
                        quiz_title = potential_title
                break
        
        if not valid_quiz:
            await status_message.edit_text(
                f"Error: The ID {quiz_id} doesn't seem to be a valid quiz in @QuizBot.\n\n"
                f"Please check the ID and try again."
            )
            return
        
        # Update progress
        await status_message.edit_text(
            f"Cloning quiz {quiz_id} from @QuizBot...\n\n"
            f"Step 2/3: Accessing quiz content...\n"
            f"Found quiz: {quiz_title}\n"
            f"Starting quiz and collecting questions..."
        )
        
        # Send "Start Quiz" button press
        async for message in client.iter_messages(quizbot_entity, limit=10):
            if hasattr(message, 'buttons') and message.buttons:
                for row in message.buttons:
                    for button in row:
                        if hasattr(button, 'text') and ("start" in button.text.lower() and "quiz" in button.text.lower()):
                            await message.click(text=button.text)
                            break
        
        # Wait for the first quiz question
        await asyncio.sleep(2)
        
        # Extract questions one by one
        cloned_count = 0
        max_questions = 50  # Safety limit
        custom_id = context.user_data.get("clone_custom_id") if not context.user_data.get("clone_use_auto_id", False) else None
        category = context.user_data.get("clone_category", "Imported Quiz")
        
        # Update progress
        await status_message.edit_text(
            f"Cloning quiz {quiz_id} from @QuizBot...\n\n"
            f"Step 3/3: Extracting questions...\n"
            f"Questions found: 0"
        )
        
        while cloned_count < max_questions:
            # Get the latest messages (looking for poll)
            messages = await client.get_messages(quizbot_entity, limit=5)
            found_question = False
            
            for msg in messages:
                # Find poll message
                if hasattr(msg, 'poll') and msg.poll:
                    found_question = True
                    poll = msg.poll
                    
                    # Extract question data
                    question_text = poll.question
                    options = [opt.text for opt in poll.options]
                    
                    # We don't know the correct answer yet, so use the first option
                    # The user can edit it later if needed
                    correct_answer = 0  
                    
                    # Create question data
                    question_data = {
                        "question": question_text,
                        "options": options,
                        "answer": correct_answer,
                        "category": category
                    }
                    
                    # Save the question
                    if custom_id:
                        add_question_with_id(custom_id, question_data)
                    else:
                        # Auto-generate ID
                        add_question_with_id(get_next_question_id(), question_data)
                    
                    cloned_count += 1
                    
                    # Update progress
                    await status_message.edit_text(
                        f"Cloning quiz {quiz_id} from @QuizBot...\n\n"
                        f"Step 3/3: Extracting questions...\n"
                        f"Questions found: {cloned_count}"
                    )
                    
                    # Click "Next" or any available button to continue
                    for message in messages:
                        if hasattr(message, 'buttons') and message.buttons:
                            # Click the first available button (usually "Next")
                            await message.click(0)
                            break
                    
                    # Wait for the next question
                    await asyncio.sleep(2)
                    break
            
            if not found_question:
                # Check if we reached the end of the quiz
                end_reached = False
                for msg in messages:
                    if hasattr(msg, 'text') and msg.text and ("result" in msg.text.lower() or "score" in msg.text.lower() or "completed" in msg.text.lower()):
                        end_reached = True
                        break
                
                if end_reached or cloned_count > 0:
                    # We've either explicitly detected the end or already found some questions before
                    break
                elif cloned_count == 0:
                    # If we haven't found any questions yet, wait a bit longer
                    await asyncio.sleep(3)
                    continue
                else:
                    # No more questions found, exit
                    break
        
        # Show success message
        if cloned_count > 0:
            if custom_id:
                # Get how many questions are now at this ID
                questions = load_questions()
                total_count = len(questions[str(custom_id)]) if isinstance(questions[str(custom_id)], list) else 1
                
                await status_message.edit_text(
                    f"✅ Successfully cloned {cloned_count} questions from QuizBot!\n\n"
                    f"Quiz ID: {quiz_id}\n"
                    f"Category: {category}\n"
                    f"Questions added with ID: {custom_id}\n"
                    f"Total questions with this ID: {total_count}\n\n"
                    f"Use /quiz to try out your new quiz!"
                )
            else:
                await status_message.edit_text(
                    f"✅ Successfully cloned {cloned_count} questions from QuizBot!\n\n"
                    f"Quiz ID: {quiz_id}\n"
                    f"Category: {category}\n"
                    f"Questions added with auto-generated IDs\n\n"
                    f"Use /quiz to try out your new quiz!"
                )
        else:
            await status_message.edit_text(
                f"⚠️ No questions could be extracted from QuizBot for ID: {quiz_id}\n\n"
                f"Please check if this is a valid quiz ID and try again."
            )
    
    except Exception as e:
        logger.error(f"Error cloning from QuizBot: {str(e)}")
        await status_message.edit_text(
            f"Error cloning from QuizBot: {str(e)}\n\n"
            f"You can still try the manual method:\n"
            f"1. Open @QuizBot and start the quiz: {quiz_id}\n"
            f"2. Forward each quiz question to me\n"
            f"3. I'll convert each one as you send them"
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
    
    # Clone quiz conversation handler
    clone_handler = ConversationHandler(
        entry_points=[CommandHandler("clone", clone_command)],
        states={
            CLONE_SOURCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, clone_source_input)],
            CLONE_ID: [
                CallbackQueryHandler(clone_id_callback, pattern=r"^clone_(auto|custom)_id$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, clone_id_input,
                    lambda update, context: context.user_data.get("awaiting_clone_id", False)
                )
            ],
            CLONE_CATEGORY: [CallbackQueryHandler(clone_category_callback, pattern=r"^clone_cat_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(clone_handler)
    
    # Poll Answer Handler - CRITICAL for tracking all participants
    application.add_handler(PollAnswerHandler(poll_answer))
    
    # Initialize Telethon client in the background
    asyncio.create_task(initialize_telethon_client())
    
    # Start the Bot
    application.run_polling()

if __name__ == "__main__":
    main()