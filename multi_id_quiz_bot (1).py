"""
Complete Telegram Quiz Bot with multi-question ID support:
1. Add multiple questions with same ID
2. Poll to question conversion with multi-ID support
3. Show all participants in final results
4. Auto-sequencing questions
5. Direct QuizBot quiz cloning without forwarding polls
"""

import json
import logging
import os
import random
import asyncio
import re
from telethon import TelegramClient, events
from telethon.tl.types import User, PeerUser, MessageMediaPoll
from telethon.sessions import StringSession
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler, PollAnswerHandler

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment variable
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")

# Telethon client credentials (for quiz cloning)
API_ID = os.environ.get("API_ID", "")
API_HASH = os.environ.get("API_HASH", "")
PHONE_NUMBER = os.environ.get("PHONE_NUMBER", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")

# Initialize Telethon client (used for quiz cloning)
telethon_client = None

# Conversation states
QUESTION, OPTIONS, ANSWER, CATEGORY = range(4)
EDIT_SELECT, EDIT_QUESTION, EDIT_OPTIONS = range(4, 7)
CLONE_URL, CLONE_CUSTOM_ID, CLONE_CATEGORY = range(7, 10)
CUSTOM_ID = 10

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
    """Send a welcome message when the command /start is issued."""
    user = update.effective_user
    welcome_text = (
        f"👋 Hello, {user.first_name}!\n\n"
        "Welcome to the Quiz Bot. Here's what you can do:\n\n"
        "💡 /quiz - Start a new quiz (auto-sequence)\n"
        "📊 /stats - View your quiz statistics\n"
        "➕ /add - Add a new question to the quiz bank\n"
        "✏️ /edit - Edit an existing question\n"
        "❌ /delete - Delete a question\n"
        "🔄 /poll2q - Convert a Telegram poll to a quiz question\n"
        "🔄 /clone - Clone quiz directly from @QuizBot\n"
        "ℹ️ /help - Show this help message\n\n"
        "Let's test your knowledge with some fun quizzes!"
    )
    await update.message.reply_text(welcome_text)

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

# Functions for QuizBot cloning feature
async def initialize_telethon_client():
    """Initialize the Telethon client for quiz cloning if needed"""
    global telethon_client
    
    if not API_ID or not API_HASH or not PHONE_NUMBER:
        logger.error("Telethon client credentials not set. Please set API_ID, API_HASH, and PHONE_NUMBER env variables.")
        return False
    
    try:
        if telethon_client is None:
            # Create session name from phone number (removing special chars)
            session_name = ''.join(c for c in PHONE_NUMBER if c.isalnum())
            telethon_client = TelegramClient(session_name, API_ID, API_HASH)
            await telethon_client.connect()
            
            # Check if authorization is needed
            if not await telethon_client.is_user_authorized():
                # If SESSION_STRING is provided, try to use it
                if SESSION_STRING:
                    try:
                        telethon_client = TelegramClient(
                            StringSession(SESSION_STRING), 
                            API_ID, 
                            API_HASH
                        )
                        await telethon_client.connect()
                        if not await telethon_client.is_user_authorized():
                            logger.error("Session string invalid or expired.")
                            return False
                    except Exception as e:
                        logger.error(f"Error using session string: {e}")
                        return False
                else:
                    logger.error("User not authorized and no session string provided.")
                    return False
        return True
    except Exception as e:
        logger.error(f"Error initializing Telethon client: {e}")
        return False

async def extract_quiz_from_url(url):
    """Extract quiz questions from a QuizBot URL using Telethon"""
    global telethon_client
    
    # Initialize Telethon client if needed
    if not await initialize_telethon_client():
        return None, "Failed to initialize Telethon client. Please check your API credentials."
    
    try:
        # Parse URL to get message ID and chat
        match = re.search(r't\.me/quizbot/(\d+)', url)
        if not match:
            return None, "Invalid QuizBot URL. Please provide a valid URL in the format t.me/quizbot/123"
        
        message_id = int(match.group(1))
        
        # Get the QuizBot entity
        quiz_bot = await telethon_client.get_entity('quizbot')
        
        # Get the quiz message
        messages = await telethon_client.get_messages(quiz_bot, ids=message_id)
        if not messages or len(messages) == 0:
            return None, "Could not find the quiz message. The message may be deleted or inaccessible."
        
        quiz_message = messages[0]
        
        # Check if it's a quiz message (has a poll)
        if not hasattr(quiz_message, 'poll') or not quiz_message.poll:
            # Try to find the quiz in replies or forwards
            related_messages = await telethon_client.get_messages(
                quiz_bot, 
                limit=20,
                reply_to=quiz_message.id
            )
            
            quiz_questions = []
            for msg in related_messages:
                if hasattr(msg, 'poll') and msg.poll:
                    # This is a poll/quiz message
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
                return None, "Could not find any quiz questions related to this URL."
            
            return quiz_questions, None
        else:
            # This is a poll/quiz message
            poll = quiz_message.poll
            correct_option = next((i for i, opt in enumerate(poll.results.results) if opt.correct), 0)
            
            question_data = {
                "question": poll.question,
                "options": [opt.text for opt in poll.answers],
                "answer": correct_option,
                "category": "Cloned Quiz",
                "sourceUrl": url
            }
            
            return [question_data], None
            
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
        "Send me the URL of a @QuizBot quiz that you want to clone.\n"
        "The URL should look like: https://t.me/quizbot/12345\n\n"
        "Type /cancel to cancel the operation."
    )
    return CLONE_URL

async def clone_url_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the quiz URL for cloning"""
    url = update.message.text.strip()
    
    # Check if it's a valid QuizBot URL
    if not re.search(r't\.me/quizbot/\d+', url):
        await update.message.reply_text(
            "That doesn't look like a valid QuizBot URL.\n"
            "The URL should look like: https://t.me/quizbot/12345\n\n"
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
                    lambda update, context: context.user_data.get("awaiting_clone_custom_id", False)
                )
            ],
            CLONE_CATEGORY: [
                CallbackQueryHandler(clone_category_callback, pattern=r"^clone_category_")
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(clone_handler)
    
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
    
    # Start the Bot
    application.run_polling()

if __name__ == "__main__":
    main()