"""
Telegram Quiz Bot with accurate participant tracking and results display
"""

import json
import logging
import os
import random
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler, PollAnswerHandler

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment variable
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")

# Conversation states
QUESTION, OPTIONS, ANSWER, CATEGORY = range(4)
EDIT_SELECT, EDIT_QUESTION, EDIT_OPTIONS = range(4, 7)
CLONE_URL, CLONE_MANUAL = range(7, 9)

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
    return max([int(qid) for qid in questions.keys()]) + 1

def get_question_by_id(question_id):
    """Get a question by its ID"""
    questions = load_questions()
    return questions.get(str(question_id))

def delete_question_by_id(question_id):
    """Delete a question by its ID"""
    questions = load_questions()
    if str(question_id) in questions:
        del questions[str(question_id)]
        save_questions(questions)
        return True
    return False

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
        "💡 /quiz - Start a new quiz\n"
        "📊 /stats - View your quiz statistics\n"
        "➕ /add - Add a new question to the quiz bank\n"
        "✏️ /edit - Edit an existing question\n"
        "❌ /delete - Delete a question\n"
        "🔄 /poll2q - Convert a Telegram poll to a quiz question\n"
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
            
            # Add category
            categories = ["General Knowledge", "Science", "History", "Geography", "Entertainment", "Sports"]
            keyboard = [[InlineKeyboardButton(cat, callback_data=f"category_{cat}")] for cat in categories]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "Select a category for this question:",
                reply_markup=reply_markup
            )
            return CATEGORY
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

async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle category selection."""
    query = update.callback_query
    await query.answer()
    
    category = query.data.replace("category_", "")
    new_question = context.user_data["new_question"]
    new_question["category"] = category
    
    # Save the question
    question_id = get_next_question_id()
    questions = load_questions()
    questions[str(question_id)] = new_question
    save_questions(questions)
    
    await query.edit_message_text(
        f"✅ Question added successfully with ID: {question_id}\n\n"
        f"Question: {new_question['question']}\n"
        f"Category: {category}"
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current operation."""
    await update.message.reply_text(
        "Operation cancelled."
    )
    return ConversationHandler.END

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
    context.user_data["quiz"] = {
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
    
    # Select 5 random questions or fewer if not enough available
    question_ids = list(all_questions.keys())
    num_questions = min(5, len(question_ids))
    selected_ids = random.sample(question_ids, num_questions)
    
    # Add selected questions to the quiz
    for qid in selected_ids:
        question = all_questions[qid]
        question["id"] = int(qid)
        context.user_data["quiz"]["questions"].append(question)
    
    await update.message.reply_text(
        f"Starting a quiz with {num_questions} questions! Questions will automatically proceed after 30 seconds.\n\n"
        f"First question coming up..."
    )
    
    # Send the first question - the rest will follow automatically
    await send_next_question(update, context)

async def send_quiz_question(context, chat_id, question):
    """Send a quiz question and return its poll_id and message_id."""
    message = await context.bot.send_poll(
        chat_id=chat_id,
        question=question["question"],
        options=question["options"],
        type="quiz",  # Important: must be a quiz, not a regular poll
        correct_option_id=question["answer"],
        is_anonymous=False,  # Important: need to track individual votes
        explanation=question.get("explanation", ""),
        open_period=30  # Poll closes after 30 seconds
    )
    return message.poll.id, message.message_id

async def send_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the next question in the quiz."""
    quiz = context.user_data.get("quiz", {})
    
    # Debug logging
    logger.info(f"Quiz state in send_next_question: {quiz}")
    
    if not quiz.get("active", False):
        return
    
    questions = quiz.get("questions", [])
    current_index = quiz.get("current_index", 0)
    chat_id = quiz.get("chat_id", update.effective_chat.id)
    
    # Check if we've reached the end of questions
    if current_index >= len(questions):
        await end_quiz(update, context)
        return
    
    # Get the current question
    question = questions[current_index]
    
    # Send the poll question
    poll_id, message_id = await send_quiz_question(context, chat_id, question)
    
    # Store poll information
    sent_polls = quiz.get("sent_polls", {})
    sent_polls[str(poll_id)] = {
        "question_index": current_index,
        "message_id": message_id,
        "poll_id": str(poll_id),
        "answers": {}
    }
    quiz["sent_polls"] = sent_polls
    
    # Update the quiz index for the next question
    quiz["current_index"] = current_index + 1
    context.user_data["quiz"] = quiz
    
    # Schedule the next question after 35 seconds (or final results if this was the last one)
    if current_index + 1 >= len(questions):
        # If this was the last question, schedule end_quiz after 35 seconds
        context.job_queue.run_once(
            end_quiz_job,
            35,
            data={'chat_id': chat_id, 'user_id': update.effective_user.id if update.effective_user else None}
        )
    else:
        # Otherwise schedule the next question after 35 seconds
        context.job_queue.run_once(
            send_next_question_job,
            35,
            data={'chat_id': chat_id, 'user_id': update.effective_user.id if update.effective_user else None}
        )

async def send_next_question_job(context):
    """Function to send the next question from a job."""
    job = context.job
    chat_id = job.data.get('chat_id')
    user_id = job.data.get('user_id')
    
    # Create a dummy update
    class DummyUpdate:
        def __init__(self, chat_id, user_id):
            self.effective_chat = type('obj', (object,), {'id': chat_id})
            self.effective_user = type('obj', (object,), {'id': user_id})
            self.effective_message = None
    
    dummy_update = DummyUpdate(chat_id, user_id)
    await send_next_question(dummy_update, context)

async def end_quiz_job(context):
    """Function to end the quiz from a job."""
    job = context.job
    chat_id = job.data.get('chat_id')
    user_id = job.data.get('user_id')
    
    # Create a dummy update
    class DummyUpdate:
        def __init__(self, chat_id, user_id):
            self.effective_chat = type('obj', (object,), {'id': chat_id})
            self.effective_user = type('obj', (object,), {'id': user_id})
            self.effective_message = None
    
    dummy_update = DummyUpdate(chat_id, user_id)
    await end_quiz(dummy_update, context)

async def poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle poll answers from users."""
    answer = update.poll_answer
    poll_id = answer.poll_id
    user = answer.user
    selected_options = answer.option_ids
    
    # Debug log
    logger.info(f"Poll answer received from {user.first_name} (ID: {user.id}) for poll {poll_id}")
    logger.info(f"Selected options: {selected_options}")
    
    # Loop through all user data to find which quiz contains this poll
    found_quiz = False
    
    for user_id, user_data in context.dispatcher.user_data.items():
        quiz = user_data.get("quiz", {})
        
        if not quiz.get("active", False):
            continue
            
        sent_polls = quiz.get("sent_polls", {})
        
        # Check both string and non-string poll IDs
        if poll_id in sent_polls or str(poll_id) in sent_polls:
            found_quiz = True
            poll_key = poll_id if poll_id in sent_polls else str(poll_id)
            poll_info = sent_polls[poll_key]
            
            # Get the question
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
                if "participants" not in quiz:
                    quiz["participants"] = {}
                
                if str(user.id) not in quiz["participants"]:
                    quiz["participants"][str(user.id)] = {
                        "name": user.first_name,
                        "username": user.username or "",
                        "correct": 0,
                        "answered": 0
                    }
                
                # Update stats
                quiz["participants"][str(user.id)]["answered"] += 1
                if is_correct:
                    quiz["participants"][str(user.id)]["correct"] += 1
                
                # Update user global stats
                user_stats = get_user_data(user.id)
                user_stats["total_answers"] = user_stats.get("total_answers", 0) + 1
                if is_correct:
                    user_stats["correct_answers"] = user_stats.get("correct_answers", 0) + 1
                save_user_data(user.id, user_stats)
                
                # Save everything back
                sent_polls[poll_key] = poll_info
                quiz["sent_polls"] = sent_polls
                user_data["quiz"] = quiz
                context.dispatcher.user_data[user_id] = user_data
                
                # Debug log
                logger.info(f"Updated quiz state for user {user_id}")
                logger.info(f"Current participants: {quiz['participants']}")
                break
    
    if not found_quiz:
        logger.warning(f"No active quiz found for poll {poll_id}")

async def end_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """End the quiz and display results with all participants."""
    # Find the quiz in the user data
    quiz = context.user_data.get("quiz", {})
    
    # Debug log
    logger.info(f"Quiz data at end_quiz: {quiz}")
    
    if not quiz.get("active", False):
        return
    
    # Mark the quiz as inactive
    quiz["active"] = False
    context.user_data["quiz"] = quiz
    
    # Get chat ID and questions
    chat_id = quiz.get("chat_id", update.effective_chat.id)
    questions = quiz.get("questions", [])
    questions_count = len(questions)
    
    # Get all participants and their scores
    participants = quiz.get("participants", {})
    
    # If no participants recorded, try to reconstruct from poll answers
    if not participants:
        participants = {}
        # Check sent polls for answers
        for poll_id, poll_info in quiz.get("sent_polls", {}).items():
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
    
    # Also make sure current user is in participants
    if update.effective_user and str(update.effective_user.id) not in participants:
        user = update.effective_user
        participants[str(user.id)] = {
            "name": user.first_name,
            "username": user.username or "",
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

async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Move to the next question in the quiz."""
    await send_next_question(update, context)

async def poll_to_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Convert a Telegram poll to a quiz question."""
    # Instruct user to forward a poll
    await update.message.reply_text(
        "To convert a Telegram poll to a quiz question, please forward me a poll message."
        "\n\nMake sure it's the poll itself, not just text."
    )

async def handle_forwarded_poll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a forwarded poll message."""
    message = update.message
    
    # Check if this is a poll
    if message.forward_from_chat and message.poll:
        poll = message.poll
        
        # Extract poll data
        question_text = poll.question
        options = [option.text for option in poll.options]
        
        # Store in context for later use
        context.user_data["poll2q"] = {
            "question": question_text,
            "options": options
        }
        
        # Ask for correct answer
        options_text = "\n".join([f"{i}. {opt}" for i, opt in enumerate(options)])
        
        # Create keyboard for selecting the correct answer
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
            f"Please select the correct answer:\n\n{options_text}",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "That doesn't seem to be a poll. Please forward a message containing a poll."
        )

async def handle_poll_answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the selection of correct answer for poll conversion."""
    query = update.callback_query
    await query.answer()
    
    answer_index = int(query.data.replace("poll_answer_", ""))
    poll_data = context.user_data.get("poll2q", {})
    poll_data["answer"] = answer_index
    context.user_data["poll2q"] = poll_data
    
    # Choose category
    categories = ["General Knowledge", "Science", "History", "Geography", "Entertainment", "Sports"]
    keyboard = [[InlineKeyboardButton(cat, callback_data=f"pollcat_{cat}")] for cat in categories]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Selected answer: {answer_index}. {poll_data['options'][answer_index]}\n\n"
        f"Now choose a category for this question:",
        reply_markup=reply_markup
    )

async def handle_poll_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle category selection for poll conversion."""
    query = update.callback_query
    await query.answer()
    
    category = query.data.replace("pollcat_", "")
    poll_data = context.user_data.get("poll2q", {})
    poll_data["category"] = category
    context.user_data["poll2q"] = poll_data
    
    # Save the question
    question_id = get_next_question_id()
    questions = load_questions()
    questions[str(question_id)] = poll_data
    save_questions(questions)
    
    await query.edit_message_text(
        f"✅ Question added successfully with ID: {question_id}\n\n"
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
    application.add_handler(CommandHandler("next", next_question))
    
    # Add conversation handler for adding questions
    add_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_question_start)],
        states={
            QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_text)],
            OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_options)],
            ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_answer)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(add_conv_handler)
    
    # Add callback query handler for category selection
    application.add_handler(CallbackQueryHandler(category_callback, pattern=r"^category_"))
    
    # Add poll-to-question conversion handlers
    application.add_handler(CommandHandler("poll2q", poll_to_question))
    # Use a more compatible way to check for forwarded polls
    application.add_handler(MessageHandler(
        filters.FORWARDED & ~filters.COMMAND, 
        handle_forwarded_poll
    ))
    application.add_handler(CallbackQueryHandler(handle_poll_answer_callback, pattern=r"^poll_answer_"))
    application.add_handler(CallbackQueryHandler(handle_poll_category_selection, pattern=r"^pollcat_"))
    
    # Add poll answer handler - CRITICAL for tracking participants
    application.add_handler(PollAnswerHandler(poll_answer))
    
    # Start the Bot
    application.run_polling()

if __name__ == "__main__":
    main()