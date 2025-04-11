"""
Telegram Quiz Bot with improved participant tracking and ranking system
"""
import os
import json
import random
import asyncio
import logging
import re
import requests
from urllib.parse import urlparse
from telegram import Update, Poll, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, PollHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Define conversation states
QUESTION, OPTIONS, ANSWER = range(3)
EDIT_SELECT, EDIT_QUESTION, EDIT_OPTIONS, EDIT_ANSWER = range(3, 7)
CLONE_URL, CLONE_MANUAL = range(7, 9)

# Get bot token from environment
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Create data directory if it doesn't exist
os.makedirs('data', exist_ok=True)

# File paths
QUESTIONS_FILE = 'data/questions.json'
USERS_FILE = 'data/users.json'

def load_questions():
    """Load questions from the JSON file"""
    try:
        if os.path.exists(QUESTIONS_FILE):
            with open(QUESTIONS_FILE, 'r', encoding='utf-8') as file:
                questions = json.load(file)
            logger.info(f"Loaded {len(questions)} questions")
            return questions
        else:
            # Create sample questions if file doesn't exist
            questions = [
                {
                    "id": 1,
                    "question": "What is the capital of France?",
                    "options": ["Berlin", "Madrid", "Paris", "Rome"],
                    "answer": 2,  # Paris (0-based index)
                    "category": "Geography"
                },
                {
                    "id": 2,
                    "question": "Which planet is known as the Red Planet?",
                    "options": ["Venus", "Mars", "Jupiter", "Saturn"],
                    "answer": 1,  # Mars (0-based index)
                    "category": "Science"
                }
            ]
            save_questions(questions)
            return questions
    except Exception as e:
        logger.error(f"Error loading questions: {e}")
        return []

def save_questions(questions):
    """Save questions to the JSON file"""
    try:
        with open(QUESTIONS_FILE, 'w', encoding='utf-8') as file:
            json.dump(questions, file, ensure_ascii=False, indent=4)
        logger.info(f"Saved {len(questions)} questions")
        return True
    except Exception as e:
        logger.error(f"Error saving questions: {e}")
        return False

def get_next_question_id():
    """Get the next available question ID"""
    questions = load_questions()
    if not questions:
        return 1
    return max(q.get("id", 0) for q in questions) + 1

def get_question_by_id(question_id):
    """Get a question by its ID"""
    questions = load_questions()
    for question in questions:
        if question.get("id") == question_id:
            return question
    return None

def delete_question_by_id(question_id):
    """Delete a question by its ID"""
    questions = load_questions()
    updated_questions = [q for q in questions if q.get("id") != question_id]
    if len(updated_questions) < len(questions):
        save_questions(updated_questions)
        return True
    return False

def parse_telegram_quiz_url(url):
    """Parse a Telegram quiz URL to extract question and options"""
    try:
        # Basic URL validation
        if not url or "t.me" not in url:
            logger.error(f"Not a valid Telegram URL: {url}")
            return None
        
        # Try different methods to extract quiz content
        logger.info(f"Attempting to extract quiz from URL: {url}")
        
        # Method 1: Try to use Telegram API (Pyrogram) if credentials are available
        api_id = os.getenv('API_ID')
        api_hash = os.getenv('API_HASH')
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        
        if api_id and api_hash and bot_token:
            try:
                from pyrogram import Client
                import asyncio
                
                # Extract channel username and message ID from URL
                channel_pattern = r't\.me/([^/]+)/(\d+)'
                channel_match = re.search(channel_pattern, url)
                
                if channel_match:
                    channel_name = channel_match.group(1)
                    message_id = int(channel_match.group(2))
                    
                    # Function to get message using Pyrogram
                    async def get_quiz_message():
                        logger.info(f"Trying to fetch message from {channel_name}, ID: {message_id}")
                        async with Client(
                            "quiz_bot_client",
                            api_id=api_id,
                            api_hash=api_hash,
                            bot_token=bot_token,
                            in_memory=True
                        ) as app:
                            try:
                                message = await app.get_messages(channel_name, message_id)
                                if message:
                                    # If it's a poll message
                                    if message.poll:
                                        return {
                                            "question": message.poll.question,
                                            "options": [opt.text for opt in message.poll.options],
                                            "answer": 0  # Default, user will select correct answer
                                        }
                                    # If it's a text message that might contain quiz info
                                    elif message.text:
                                        # Try to parse text as quiz (question + options format)
                                        lines = message.text.strip().split('\n')
                                        if len(lines) >= 3:  # At least 1 question and 2 options
                                            question = lines[0]
                                            options = []
                                            
                                            # Extract options (look for numbered/lettered options)
                                            for line in lines[1:]:
                                                line = line.strip()
                                                # Remove common option prefixes
                                                line = re.sub(r'^[a-z][\.\)]\s*', '', line)
                                                line = re.sub(r'^\d+[\.\)]\s*', '', line)
                                                if line:
                                                    options.append(line)
                                            
                                            if len(options) >= 2:
                                                return {
                                                    "question": question,
                                                    "options": options,
                                                    "answer": 0
                                                }
                            except Exception as e:
                                logger.error(f"Error getting message with Pyrogram: {e}")
                                return None
                        return None
                    
                    # Run the async function
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    result = loop.run_until_complete(get_quiz_message())
                    loop.close()
                    
                    if result:
                        logger.info(f"Successfully extracted quiz via Pyrogram: {result['question']}")
                        return result
            except Exception as e:
                logger.error(f"Pyrogram method failed: {e}")
        
        # Method 2: Enhanced web scraping with multiple patterns
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
        
        # Try to get both the regular URL and the embedded version
        try:
            response = requests.get(url, headers=headers)
            content = response.text
            
            # First, look for standard poll format
            poll_q_match = re.search(r'<div class="tgme_widget_message_poll_question">([^<]+)</div>', content)
            poll_options = re.findall(r'<div class="tgme_widget_message_poll_option_text">([^<]+)</div>', content)
            
            if poll_q_match and poll_options and len(poll_options) >= 2:
                question = poll_q_match.group(1).strip()
                return {
                    "question": question,
                    "options": poll_options,
                    "answer": 0
                }
            
            # If not a direct poll, try embedded view
            if "rajsthangk" in url or "gk" in url.lower() or "quiz" in url.lower():
                # Try to extract channel and message_id
                channel_pattern = r't\.me/([^/]+)/(\d+)'
                channel_match = re.search(channel_pattern, url)
                
                if channel_match:
                    channel_name = channel_match.group(1)
                    message_id = channel_match.group(2)
                    
                    # Try embedded view
                    embed_url = f"https://t.me/{channel_name}/{message_id}?embed=1"
                    try:
                        embed_response = requests.get(embed_url, headers=headers)
                        embed_content = embed_response.text
                        
                        # Try to find quiz in embedded view
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(embed_content, 'html.parser')
                        
                        # Look for message text that might contain quiz
                        message_text = soup.select_one('.tgme_widget_message_text')
                        if message_text:
                            text = message_text.get_text().strip()
                            lines = [line.strip() for line in text.split('\n') if line.strip()]
                            
                            if lines and len(lines) >= 3:  # At least question + 2 options
                                question = lines[0]
                                
                                # Check if this looks like a quiz (has options with A), B), 1., 2., etc.)
                                option_pattern = re.compile(r'^[A-Za-z0-9][\.\)]')
                                options = []
                                for line in lines[1:]:
                                    # Remove option markers
                                    clean_line = re.sub(r'^[A-Za-z0-9][\.\)]\s*', '', line)
                                    if clean_line:
                                        options.append(clean_line)
                                
                                if len(options) >= 2:
                                    logger.info(f"Extracted quiz from message text with {len(options)} options")
                                    return {
                                        "question": question,
                                        "options": options,
                                        "answer": 0
                                    }
                        
                        # For RAJ GK QUIZ HOUSE format, look for quiz title
                        page_title = soup.select_one('meta[property="og:title"]')
                        if page_title and "quiz" in page_title.get('content', '').lower():
                            title = page_title.get('content', '').strip()
                            
                            # Try to extract options from the page
                            lines = []
                            for p in soup.select('.tgme_widget_message_text p'):
                                lines.append(p.get_text().strip())
                            
                            # If we have potential options
                            if lines and len(lines) >= 2:
                                return {
                                    "question": title,
                                    "options": lines,
                                    "answer": 0
                                }
                    except Exception as embed_err:
                        logger.error(f"Error with embedded view: {embed_err}")
                        pass
        except Exception as request_err:
            logger.error(f"Error with request: {request_err}")
            pass
            
        # If all methods fail, return None
        logger.error("All extraction methods failed for URL")
        return None
    except Exception as e:
        logger.error(f"Error parsing quiz URL: {e}")
        return None

def load_quiz_from_url(url):
    """Load quiz from Telegram URL"""
    quiz_data = parse_telegram_quiz_url(url)
    if quiz_data:
        question_id = get_next_question_id()
        question = {
            "id": question_id,
            "question": quiz_data["question"],
            "options": quiz_data["options"],
            "answer": quiz_data["answer"],
            "category": "Imported"
        }
        questions = load_questions()
        questions.append(question)
        save_questions(questions)
        return question
    return None

def get_user_data(user_id):
    """Get user data from the JSON file"""
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as file:
                users = json.load(file)
                return users.get(str(user_id), {})
        return {}
    except Exception as e:
        logger.error(f"Error loading user data: {e}")
        return {}

def save_user_data(user_id, data):
    """Save user data to the JSON file"""
    try:
        users = {}
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as file:
                users = json.load(file)
        
        users[str(user_id)] = data
        
        with open(USERS_FILE, 'w', encoding='utf-8') as file:
            json.dump(users, file, ensure_ascii=False, indent=4)
        
        return True
    except Exception as e:
        logger.error(f"Error saving user data: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the command /start is issued."""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    # Track user
    user_data = {
        "user_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "chats": [chat_id]
    }
    save_user_data(user.id, user_data)
    
    # Prepare the welcome message
    welcome_text = (
        f"👋 Welcome to the Quiz Bot, {user.first_name}!\n\n"
        "This bot allows you to create and play quizzes.\n\n"
        "📝 Main commands:\n"
        "/quiz - Start a quiz session\n"
        "/create - Create a new quiz question\n"
        "/clone - Clone a quiz from a Telegram URL\n"
        "/edit - Edit existing questions\n"
        "/help - Show this help message\n\n"
        "Let's get started!"
    )
    
    await context.bot.send_message(
        chat_id=chat_id, 
        text=welcome_text
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display the help message."""
    help_text = (
        "📚 Quiz Bot Commands:\n\n"
        "/start - Start the bot\n"
        "/quiz - Start a quiz session\n"
        "/create - Create a new quiz question\n"
        "/clone - Clone a quiz from a Telegram URL\n"
        "/edit - Edit existing questions\n"
        "/help - Show this help message\n\n"
        "During a quiz session:\n"
        "/nextq - Go to the next question\n"
        "/end - End the quiz session\n\n"
        "During question creation:\n"
        "/cancel - Cancel the current operation\n\n"
        "Enjoy your quiz experience! 🎓"
    )
    
    await update.message.reply_text(help_text)

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a quiz session."""
    chat_id = update.effective_chat.id
    
    # Check if a quiz is already running
    if context.chat_data.get("quiz_running", False):
        await update.message.reply_text(
            "A quiz is already running in this chat. Use /end to finish it first."
        )
        return
    
    questions = load_questions()
    if not questions:
        await update.message.reply_text(
            "No questions available. Please use /create to add some questions first."
        )
        return
    
    # Initialize quiz data
    context.chat_data["quiz_running"] = True
    context.chat_data["quiz_questions"] = questions.copy()
    random.shuffle(context.chat_data["quiz_questions"])
    context.chat_data["current_question_index"] = 0
    context.chat_data["participant_scores"] = {}  # Initialize empty scores dict
    context.chat_data["participant_names"] = {}   # Initialize empty names dict
    context.chat_data["active_polls"] = {}        # Keep track of active polls
    
    await update.message.reply_text(
        "Starting a new quiz session! I'll send the first question shortly.\n"
        "Use /nextq to move to the next question and /end to finish the quiz."
    )
    
    # Send the first question
    await send_quiz_question(context, chat_id)

async def send_quiz_question(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """Send a quiz question to the chat."""
    if not context.chat_data.get("quiz_running", False):
        await context.bot.send_message(
            chat_id=chat_id,
            text="No quiz is currently running. Use /quiz to start one."
        )
        return
    
    quiz_questions = context.chat_data.get("quiz_questions", [])
    current_index = context.chat_data.get("current_question_index", 0)
    
    if current_index >= len(quiz_questions):
        await context.bot.send_message(
            chat_id=chat_id,
            text="No more questions available. The quiz is over!"
        )
        await end_quiz_command(None, context)
        return
    
    question = quiz_questions[current_index]
    question_text = question.get("question", "Unknown question")
    options = question.get("options", [])
    correct_option = question.get("answer", 0)
    
    # Create and send the poll
    message = await context.bot.send_poll(
        chat_id=chat_id,
        question=f"Q{current_index+1}: {question_text}",
        options=options,
        type=Poll.QUIZ,
        correct_option_id=correct_option,
        is_anonymous=True  # Note: Telegram quiz polls are always anonymous in the UI
    )
    
    # Save the poll ID to match answers later
    context.chat_data["active_polls"][message.poll.id] = {
        "message_id": message.message_id,
        "question_index": current_index,
        "correct_answer": correct_option
    }

async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Move to the next question in the quiz."""
    chat_id = update.effective_chat.id
    
    if not context.chat_data.get("quiz_running", False):
        await update.message.reply_text(
            "No quiz is currently running. Use /quiz to start one."
        )
        return
    
    # Increase question index
    context.chat_data["current_question_index"] += 1
    
    # Send the next question
    await send_quiz_question(context, chat_id)

async def poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle answers to quiz polls."""
    if not context.chat_data.get("quiz_running", False):
        return
    
    poll_id = update.poll_answer.poll_id
    user_id = update.poll_answer.user.id
    user_name = update.poll_answer.user.full_name
    selected_option = update.poll_answer.option_ids[0] if update.poll_answer.option_ids else None
    
    # Store user's name for later use in results
    context.chat_data["participant_names"][user_id] = user_name
    
    poll_info = context.chat_data["active_polls"].get(poll_id)
    if not poll_info:
        return
    
    correct_answer = poll_info["correct_answer"]
    
    # Initialize user's score if not already present
    if user_id not in context.chat_data["participant_scores"]:
        context.chat_data["participant_scores"][user_id] = 0
    
    # Check if answer is correct
    if selected_option == correct_answer:
        context.chat_data["participant_scores"][user_id] += 1
        logger.info(f"User {user_name} ({user_id}) answered correctly")
    else:
        logger.info(f"User {user_name} ({user_id}) answered incorrectly")

async def end_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """End the current quiz session and display final scores."""
    chat_id = update.effective_chat.id if update else context.chat_data.get("chat_id")
    
    if not context.chat_data.get("quiz_running", False):
        if update:
            await update.message.reply_text(
                "No quiz is currently running. Use /quiz to start one."
            )
        return
    
    # Get participant scores and names
    scores = context.chat_data.get("participant_scores", {})
    names = context.chat_data.get("participant_names", {})
    
    # Make sure we include the quiz creator in the participants list if they're not there
    quiz_creator_id = context.chat_data.get("quiz_creator_id")
    quiz_creator_name = context.chat_data.get("quiz_creator_name")
    
    if quiz_creator_id and quiz_creator_id not in names and quiz_creator_name:
        names[quiz_creator_id] = quiz_creator_name
        # If the creator has no score yet, add a default score
        if quiz_creator_id not in scores:
            scores[quiz_creator_id] = 0
    
    # Generate rankings - even if scores dict is empty, we'll show all participants
    # Create a list of (user_id, score) tuples for all participants
    score_list = [(user_id, scores.get(user_id, 0)) for user_id in names.keys()]
    
    # Sort by score in descending order
    score_list.sort(key=lambda x: x[1], reverse=True)
    
    # Build the results message
    total_questions = len(context.chat_data.get("quiz_questions", []))
    results_message = "📊 Quiz Results 📊\n\n"
    results_message += f"Total Questions: {total_questions}\n\n"
    
    # Always show all participants in the results, even if score_list is empty
    # Create a placeholder if needed
    if not score_list:
        # Use the quiz starter as a placeholder
        starter_name = "Unknown User"
        if update and update.effective_user:
            starter_name = update.effective_user.first_name
        elif context.chat_data.get("quiz_creator_name"):
            starter_name = context.chat_data.get("quiz_creator_name")
            
        # Add the starter as a participant
        results_message += f"Quiz completed by: {starter_name}!\n\n"
        results_message += f"🥇 {starter_name}: 0/{total_questions} correct (0.0%)\n"
    else:
        # We have participants to show
        if len(score_list) > 0:
            winner_id, winner_score = score_list[0]
            winner_name = names.get(winner_id, f"User {winner_id}")
            results_message += f"🏆 Congratulations to the winner: {winner_name}!\n\n"
        
        results_message += "📝 All Participants Ranking 📝\n"
        
        # Add each participant to the rankings with appropriate emoji for top 3
        for rank, (user_id, score) in enumerate(score_list, 1):
            user_name = names.get(user_id, f"User {user_id}")
            
            # Add medals for top 3
            if rank == 1:
                rank_prefix = "🥇"
            elif rank == 2:
                rank_prefix = "🥈"
            elif rank == 3:
                rank_prefix = "🥉"
            else:
                rank_prefix = f"{rank}."
                
            # Calculate percentage
            percentage = (score / total_questions * 100) if total_questions > 0 else 0
            results_message += f"{rank_prefix} {user_name}: {score}/{total_questions} correct ({percentage:.1f}%)\n"
    
    # Send the results
    await context.bot.send_message(
        chat_id=chat_id,
        text=results_message
    )
    
    # Reset quiz data
    context.chat_data["quiz_running"] = False
    context.chat_data["participant_scores"] = {}
    context.chat_data["participant_names"] = {}
    context.chat_data["active_polls"] = {}

async def create_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the question creation process."""
    await update.message.reply_text(
        "Let's create a new quiz question!\n"
        "First, please enter the question text, or use /cancel to abort."
    )
    return QUESTION

async def question_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the question text and ask for options."""
    context.user_data["question"] = update.message.text
    
    await update.message.reply_text(
        "Good! Now enter the options for your question, one per message.\n"
        "Send /done when you've entered all options (minimum 2)."
    )
    context.user_data["options"] = []
    return OPTIONS

async def option_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save each option and continue collecting."""
    if update.message.text == "/done":
        if len(context.user_data["options"]) < 2:
            await update.message.reply_text(
                "You need at least 2 options for a quiz question. Please add more options."
            )
            return OPTIONS
        
        # Display options for selection of correct answer
        options = context.user_data["options"]
        option_text = "Please select the correct answer by typing the number:\n\n"
        for i, option in enumerate(options):
            option_text += f"{i+1}. {option}\n"
        
        await update.message.reply_text(option_text)
        return ANSWER
    
    context.user_data["options"].append(update.message.text)
    
    await update.message.reply_text(
        f"Option added! You now have {len(context.user_data['options'])} options.\n"
        "Add another option or send /done when finished."
    )
    return OPTIONS

async def correct_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the correct answer and create the question."""
    try:
        answer_num = int(update.message.text)
        if 1 <= answer_num <= len(context.user_data["options"]):
            # Convert to 0-based index
            context.user_data["answer"] = answer_num - 1
            
            # Create the question
            question_id = get_next_question_id()
            question = {
                "id": question_id,
                "question": context.user_data["question"],
                "options": context.user_data["options"],
                "answer": context.user_data["answer"],
                "category": "Custom"
            }
            
            # Add to questions list
            questions = load_questions()
            questions.append(question)
            save_questions(questions)
            
            await update.message.reply_text(
                "✅ Question created successfully!\n\n"
                f"Question: {question['question']}\n"
                f"Correct answer: {question['options'][question['answer']]}\n\n"
                "Use /quiz to start a quiz with this question."
            )
            
            # Clear user data
            context.user_data.clear()
            return ConversationHandler.END
        else:
            await update.message.reply_text(
                f"Please enter a valid option number between 1 and {len(context.user_data['options'])}."
            )
            return ANSWER
    except ValueError:
        await update.message.reply_text(
            "Please enter a valid number for the correct answer."
        )
        return ANSWER

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current operation."""
    context.user_data.clear()
    await update.message.reply_text(
        "Operation cancelled. Use /help to see available commands."
    )
    return ConversationHandler.END

async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the question editing process."""
    questions = load_questions()
    
    if not questions:
        await update.message.reply_text(
            "No questions available to edit. Use /create to add some questions first."
        )
        return ConversationHandler.END
    
    # Show list of questions
    question_list = "Select a question to edit by typing its number:\n\n"
    for i, q in enumerate(questions):
        question_text = q.get("question", "Unknown")
        # Truncate long questions
        if len(question_text) > 50:
            question_text = question_text[:47] + "..."
        
        question_list += f"{i+1}. {question_text}\n"
    
    context.user_data["edit_questions"] = questions
    
    await update.message.reply_text(question_list)
    return EDIT_SELECT

async def edit_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle question selection for editing."""
    try:
        selection = int(update.message.text)
        questions = context.user_data.get("edit_questions", [])
        
        if 1 <= selection <= len(questions):
            # Convert to 0-based index
            selected_index = selection - 1
            context.user_data["edit_index"] = selected_index
            
            question = questions[selected_index]
            
            # Display question details and edit options
            details = f"Editing Question: {question['question']}\n\n"
            details += "Options:\n"
            for i, option in enumerate(question['options']):
                correct = "✓" if i == question['answer'] else " "
                details += f"{i+1}. [{correct}] {option}\n"
            
            details += "\nWhat would you like to edit?\n"
            details += "1. Question text\n"
            details += "2. Options\n"
            details += "3. Correct answer\n"
            details += "4. Delete this question\n"
            details += "5. Cancel editing"
            
            await update.message.reply_text(details)
            return EDIT_QUESTION
        else:
            await update.message.reply_text(
                f"Please enter a valid question number between 1 and {len(questions)}."
            )
            return EDIT_SELECT
    except ValueError:
        await update.message.reply_text(
            "Please enter a valid number for question selection."
        )
        return EDIT_SELECT

async def edit_question_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle edit choice selection."""
    try:
        choice = int(update.message.text)
        
        if choice == 1:  # Edit question text
            await update.message.reply_text(
                "Please enter the new question text:"
            )
            return EDIT_QUESTION
        elif choice == 2:  # Edit options
            question = context.user_data["edit_questions"][context.user_data["edit_index"]]
            options_text = "Current options:\n"
            for i, option in enumerate(question['options']):
                options_text += f"{i+1}. {option}\n"
            
            options_text += "\nSend the number of the option to edit, or 'new' to add a new option:"
            
            await update.message.reply_text(options_text)
            return EDIT_OPTIONS
        elif choice == 3:  # Edit correct answer
            question = context.user_data["edit_questions"][context.user_data["edit_index"]]
            options_text = "Select the correct answer by typing its number:\n\n"
            for i, option in enumerate(question['options']):
                current = "← Current" if i == question['answer'] else ""
                options_text += f"{i+1}. {option} {current}\n"
            
            await update.message.reply_text(options_text)
            return EDIT_ANSWER
        elif choice == 4:  # Delete question
            question = context.user_data["edit_questions"][context.user_data["edit_index"]]
            question_id = question.get("id")
            
            if delete_question_by_id(question_id):
                await update.message.reply_text(
                    "✅ Question deleted successfully!"
                )
            else:
                await update.message.reply_text(
                    "❌ Failed to delete the question."
                )
            
            context.user_data.clear()
            return ConversationHandler.END
        elif choice == 5:  # Cancel editing
            await update.message.reply_text(
                "Question editing cancelled."
            )
            context.user_data.clear()
            return ConversationHandler.END
        else:
            await update.message.reply_text(
                "Please enter a valid choice between 1 and 5."
            )
            return EDIT_QUESTION
    except ValueError:
        if update.message.text.lower() == "new":
            await update.message.reply_text(
                "Please enter the new option text:"
            )
            context.user_data["adding_new_option"] = True
            return EDIT_OPTIONS
            
        await update.message.reply_text(
            "Please enter a valid number for your choice."
        )
        return EDIT_QUESTION

async def edit_question_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle updating the question text."""
    if update.message.text.isdigit():
        # User is probably trying to select an edit option
        return await edit_question_choice(update, context)
    
    # Update the question text
    new_text = update.message.text
    questions = context.user_data["edit_questions"]
    index = context.user_data["edit_index"]
    
    questions[index]["question"] = new_text
    
    # Save the updated questions
    if save_questions(questions):
        await update.message.reply_text(
            "✅ Question text updated successfully!"
        )
    else:
        await update.message.reply_text(
            "❌ Failed to update the question."
        )
    
    context.user_data.clear()
    return ConversationHandler.END

async def edit_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle updating question options."""
    questions = context.user_data["edit_questions"]
    index = context.user_data["edit_index"]
    question = questions[index]
    
    # Check if we're adding a new option
    if context.user_data.get("adding_new_option"):
        new_option = update.message.text
        question["options"].append(new_option)
        
        # Save the updated questions
        if save_questions(questions):
            await update.message.reply_text(
                f"✅ New option '{new_option}' added successfully!"
            )
        else:
            await update.message.reply_text(
                "❌ Failed to add the new option."
            )
        
        context.user_data.clear()
        return ConversationHandler.END
    
    # Check if we're in option selection mode
    if "editing_option" not in context.user_data:
        try:
            option_index = int(update.message.text) - 1
            
            if 0 <= option_index < len(question["options"]):
                context.user_data["editing_option"] = option_index
                
                await update.message.reply_text(
                    f"Current option: {question['options'][option_index]}\n"
                    "Please enter the new text for this option:"
                )
                return EDIT_OPTIONS
            else:
                await update.message.reply_text(
                    f"Please enter a valid option number between 1 and {len(question['options'])}."
                )
                return EDIT_OPTIONS
        except ValueError:
            await update.message.reply_text(
                "Please enter a valid number for the option."
            )
            return EDIT_OPTIONS
    else:
        # We're updating an option
        option_index = context.user_data["editing_option"]
        new_text = update.message.text
        
        # Update the option
        question["options"][option_index] = new_text
        
        # If this was the correct answer, update the answer indicator
        if option_index == question["answer"]:
            pass  # No need to change the answer index
        
        # Save the updated questions
        if save_questions(questions):
            await update.message.reply_text(
                "✅ Option updated successfully!"
            )
        else:
            await update.message.reply_text(
                "❌ Failed to update the option."
            )
        
        context.user_data.clear()
        return ConversationHandler.END

async def edit_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle updating the correct answer."""
    try:
        answer_num = int(update.message.text)
        questions = context.user_data["edit_questions"]
        index = context.user_data["edit_index"]
        question = questions[index]
        
        if 1 <= answer_num <= len(question["options"]):
            # Convert to 0-based index
            question["answer"] = answer_num - 1
            
            # Save the updated questions
            if save_questions(questions):
                await update.message.reply_text(
                    f"✅ Correct answer updated to: {question['options'][question['answer']]}"
                )
            else:
                await update.message.reply_text(
                    "❌ Failed to update the correct answer."
                )
            
            context.user_data.clear()
            return ConversationHandler.END
        else:
            await update.message.reply_text(
                f"Please enter a valid option number between 1 and {len(question['options'])}."
            )
            return EDIT_ANSWER
    except ValueError:
        await update.message.reply_text(
            "Please enter a valid number for the correct answer."
        )
        return EDIT_ANSWER

async def clone_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the process to clone a quiz from a Telegram URL."""
    keyboard = [
        [InlineKeyboardButton("URL Import", callback_data="clone_url")],
        [InlineKeyboardButton("Manual Entry", callback_data="clone_manual")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "How would you like to clone a quiz?\n\n"
        "• URL Import: Clone from a Telegram quiz URL\n"
        "• Manual Entry: Enter quiz details manually",
        reply_markup=reply_markup
    )
    
    return ConversationHandler.END  # We'll use callback queries instead

async def clone_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle button clicks for clone options."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "clone_url":
        await query.edit_message_text(
            "Please send the URL of the Telegram quiz message you want to clone:"
        )
        return CLONE_URL
    elif query.data == "clone_manual":
        await query.edit_message_text(
            "Let's create a new quiz question manually!\n"
            "Please enter the question text:"
        )
        return CLONE_MANUAL
    
    return ConversationHandler.END

async def clone_url_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle URL input for cloning."""
    url = update.message.text
    
    await update.message.reply_text(
        "Attempting to clone quiz from URL... This may take a moment."
    )
    
    result = load_quiz_from_url(url)
    
    if result:
        await update.message.reply_text(
            f"✅ Quiz cloned successfully!\n\n"
            f"Question: {result['question']}\n"
            f"Options: {', '.join(result['options'])}\n\n"
            "You can now use /quiz to include this question in quizzes."
        )
    else:
        await update.message.reply_text(
            "❌ Failed to clone quiz from the URL. Please check if the URL is valid and contains a quiz."
        )
    
    return ConversationHandler.END

async def clone_manual_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle manual entry for cloning (redirects to create flow)."""
    # Save the question text
    context.user_data["question"] = update.message.text
    
    await update.message.reply_text(
        "Good! Now enter the options for your question, one per message.\n"
        "Send /done when you've entered all options (minimum 2)."
    )
    context.user_data["options"] = []
    return OPTIONS

def main() -> None:
    """Start the bot."""
    # Create the Application with the bot token
    application = Application.builder().token(BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("nextq", next_question))
    application.add_handler(CommandHandler("end", end_quiz_command))
    
    # Poll answer handler
    application.add_handler(PollHandler(poll_answer))
    
    # Callback query handler for clone options
    application.add_handler(CallbackQueryHandler(clone_button, pattern=r"^clone_"))
    
    # Conversation handler for creating questions
    create_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("create", create_command)],
        states={
            QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, question_text)],
            OPTIONS: [MessageHandler(filters.TEXT, option_text)],
            ANSWER: [MessageHandler(filters.TEXT, correct_answer)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(create_conv_handler)
    
    # Conversation handler for editing questions
    edit_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("edit", edit_command)],
        states={
            EDIT_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_select)],
            EDIT_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_question_text)],
            EDIT_OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_options)],
            EDIT_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_answer)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(edit_conv_handler)
    
    # Conversation handler for cloning questions
    clone_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("clone", clone_command)],
        states={
            CLONE_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, clone_url_handler)],
            CLONE_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, clone_manual_handler)],
            OPTIONS: [MessageHandler(filters.TEXT, option_text)],
            ANSWER: [MessageHandler(filters.TEXT, correct_answer)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(clone_conv_handler)
    
    # Start the Bot
    application.run_polling()

if __name__ == "__main__":
    main()
