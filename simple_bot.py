"""
Simple Telegram Quiz Bot with proper participant tracking and automatic sequencing
"""

import json
import logging
import os
import random
import asyncio
import time
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, Poll
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, PollAnswerHandler, CallbackQueryHandler

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment variable
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7631768276:AAFwTYA8CK5tTHQfExI-w9cxPLnlLJa4iW0")

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
        "💡 /quiz - Start a new quiz (automatic sequence)\n"
        "📊 /stats - View your quiz statistics\n"
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

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a quiz session with random questions."""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    # Load all questions
    all_questions = load_questions()
    if not all_questions:
        await update.message.reply_text("No questions available. Add some questions first!")
        return
    
    # Initialize quiz state
    context.chat_data["quiz"] = {
        "active": True,
        "current_index": 0,
        "questions": [],
        "sent_polls": {},
        "participants": {},
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
        context.chat_data["quiz"]["questions"].append(question)
    
    await update.message.reply_text(
        f"Starting a quiz with {num_questions} questions! Questions will automatically proceed after 30 seconds.\n\n"
        f"First question coming up..."
    )
    
    # Send the first question
    await asyncio.sleep(2)  # Small delay before first question
    await send_question(context, chat_id, 0)

async def send_question(context, chat_id, question_index):
    """Send a question to the chat."""
    quiz = context.chat_data.get("quiz", {})
    if not quiz.get("active", False):
        return
    
    questions = quiz.get("questions", [])
    if question_index >= len(questions):
        await end_quiz(context, chat_id)
        return
    
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
    
    # Store the poll information
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
    
    # Schedule the next question
    if question_index + 1 < len(questions):
        # Schedule next question after 30 seconds
        asyncio.create_task(schedule_next_question(context, chat_id, question_index + 1))
    else:
        # This is the last question, schedule end quiz
        asyncio.create_task(schedule_end_quiz(context, chat_id))

async def schedule_next_question(context, chat_id, next_index):
    """Schedule sending the next question."""
    await asyncio.sleep(30)  # Wait 30 seconds
    
    # Check if quiz is still active before sending next question
    quiz = context.chat_data.get("quiz", {})
    if quiz.get("active", False):
        await send_question(context, chat_id, next_index)

async def schedule_end_quiz(context, chat_id):
    """Schedule the end of quiz."""
    await asyncio.sleep(30)  # Wait 30 seconds after last question
    await end_quiz(context, chat_id)

async def poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle poll answers from users."""
    answer = update.poll_answer
    poll_id = answer.poll_id
    user = answer.user
    selected_options = answer.option_ids
    
    # Find which chat this poll belongs to
    for chat_id, chat_data in context.bot_data.items():
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
                
                # Record the answer
                if "answers" not in poll_info:
                    poll_info["answers"] = {}
                
                is_correct = False
                if selected_options and selected_options[0] == correct_answer:
                    is_correct = True
                
                poll_info["answers"][str(user.id)] = {
                    "user_name": user.first_name,
                    "username": user.username,
                    "option_id": selected_options[0] if selected_options else None,
                    "is_correct": is_correct
                }
                
                # Update participants info
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
                
                quiz["participants"] = participants
                sent_polls[str(poll_id)] = poll_info
                quiz["sent_polls"] = sent_polls
                context.chat_data["quiz"] = quiz
                
                # Update user's global stats
                user_stats = get_user_data(user.id)
                user_stats["total_answers"] += 1
                if is_correct:
                    user_stats["correct_answers"] += 1
                save_user_data(user.id, user_stats)
                
                break

async def end_quiz(context, chat_id):
    """End the quiz and display results."""
    quiz = context.chat_data.get("quiz", {})
    
    if not quiz.get("active", False):
        return
    
    # Mark quiz as inactive
    quiz["active"] = False
    context.chat_data["quiz"] = quiz
    
    # Get all questions
    questions = quiz.get("questions", [])
    questions_count = len(questions)
    
    # Get all participants and scores
    participants = quiz.get("participants", {})
    
    # If no participants found, try to reconstruct from poll answers
    if not participants:
        participants = {}
        sent_polls = quiz.get("sent_polls", {})
        for poll_id, poll_info in sent_polls.items():
            for user_id, answer_info in poll_info.get("answers", {}).items():
                if user_id not in participants:
                    participants[user_id] = {
                        "name": answer_info.get("user_name", f"User {user_id}"),
                        "username": answer_info.get("username", ""),
                        "correct": 0,
                        "answered": 0
                    }
                
                participants[user_id]["answered"] += 1
                if answer_info.get("is_correct", False):
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
    
    # Sort participants by correct answers
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

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Basic command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("stats", stats_command))
    
    # Critical: Add poll answer handler for tracking participants
    application.add_handler(PollAnswerHandler(poll_answer))
    
    # Start the Bot
    application.run_polling()

if __name__ == "__main__":
    main()
