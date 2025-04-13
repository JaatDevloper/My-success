"""
Extended Telegram Quiz Bot with negative marking
This script extends the original quiz bot by adding negative marking functionality
"""

import logging
import os
import json
import sys

# First, make sure we can import from attached_assets directory
sys.path.append(os.path.join(os.getcwd(), "attached_assets"))

try:
    # Try to import the original bot
    from attached_assets.multi_id_quiz_bot import (
        BOT_TOKEN, 
        load_questions, 
        get_user_data, 
        save_user_data,
        poll_answer as original_poll_answer
    )
except ImportError as e:
    print(f"Error importing original bot: {e}")
    print("Make sure the original bot file exists at attached_assets/multi_id_quiz_bot.py")
    sys.exit(1)

# Import negative marking functionality
from negative_marking import (
    get_extended_user_stats, 
    toggle_negative_marking, 
    update_penalty_settings,
    reset_user_penalties, 
    is_negative_marking_enabled, 
    apply_penalty
)

try:
    import telegram
    from telegram.ext import Updater, CommandHandler, CallbackQueryHandler
except ImportError as e:
    print(f"Error importing telegram library: {e}")
    print("Make sure python-telegram-bot is installed")
    print("You can install it with: pip install python-telegram-bot")
    sys.exit(1)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

def extended_stats_command(update, context):
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
    negative_marking_status = "enabled" if is_negative_marking_enabled() else "disabled"
    stats_text += f"Note: Negative marking is currently {negative_marking_status}."
    
    update.message.reply_text(stats_text)

def negative_marking_settings(update, context):
    """Show and manage negative marking settings."""
    keyboard = [
        [telegram.InlineKeyboardButton("Enable Negative Marking", callback_data="neg_mark_enable")],
        [telegram.InlineKeyboardButton("Disable Negative Marking", callback_data="neg_mark_disable")],
        [telegram.InlineKeyboardButton("Update Default Penalty", callback_data="neg_mark_default")],
        [telegram.InlineKeyboardButton("Reset All Penalties", callback_data="neg_mark_reset")],
        [telegram.InlineKeyboardButton("Back", callback_data="neg_mark_back")]
    ]
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        "🔧 Negative Marking Settings\n\n"
        "You can enable/disable negative marking or adjust penalty values.",
        reply_markup=reply_markup
    )

def negative_settings_callback(update, context):
    """Handle callback queries from negative marking settings."""
    query = update.callback_query
    query.answer()
    
    if query.data == "neg_mark_enable":
        toggle_negative_marking(True)
        query.edit_message_text("✅ Negative marking has been enabled.")
    
    elif query.data == "neg_mark_disable":
        toggle_negative_marking(False)
        query.edit_message_text("✅ Negative marking has been disabled.")
    
    elif query.data == "neg_mark_reset":
        reset_user_penalties()
        query.edit_message_text("✅ All user penalties have been reset.")
    
    elif query.data == "neg_mark_default":
        keyboard = [
            [telegram.InlineKeyboardButton("0.25 points", callback_data="penalty_0.25")],
            [telegram.InlineKeyboardButton("0.50 points", callback_data="penalty_0.5")],
            [telegram.InlineKeyboardButton("1.00 point", callback_data="penalty_1.0")],
            [telegram.InlineKeyboardButton("No penalty", callback_data="penalty_0.0")],
            [telegram.InlineKeyboardButton("Back", callback_data="neg_mark_back_to_settings")]
        ]
        reply_markup = telegram.InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
            "Select default penalty value for incorrect answers:",
            reply_markup=reply_markup
        )
    
    elif query.data.startswith("penalty_"):
        try:
            penalty = float(query.data.split("_")[1])
            update_penalty_settings(default_penalty=penalty)
            query.edit_message_text(f"✅ Default penalty updated to {penalty} points.")
        except (ValueError, IndexError):
            query.edit_message_text("❌ Invalid penalty value.")
    
    elif query.data == "neg_mark_back_to_settings":
        # Go back to settings menu
        keyboard = [
            [telegram.InlineKeyboardButton("Enable Negative Marking", callback_data="neg_mark_enable")],
            [telegram.InlineKeyboardButton("Disable Negative Marking", callback_data="neg_mark_disable")],
            [telegram.InlineKeyboardButton("Update Default Penalty", callback_data="neg_mark_default")],
            [telegram.InlineKeyboardButton("Reset All Penalties", callback_data="neg_mark_reset")],
            [telegram.InlineKeyboardButton("Back", callback_data="neg_mark_back")]
        ]
        reply_markup = telegram.InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
            "🔧 Negative Marking Settings\n\n"
            "You can enable/disable negative marking or adjust penalty values.",
            reply_markup=reply_markup
        )
    
    elif query.data == "neg_mark_back":
        # Exit settings
        query.edit_message_text("Settings closed. Use /negmark to access settings again.")

def reset_user_penalty_command(update, context):
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

def extended_poll_answer(update, context):
    """Extended handler for poll answers to apply penalties for incorrect answers."""
    # First, call the original poll_answer function to handle standard behavior
    original_poll_answer(update, context)
    
    # If negative marking is not enabled, don't add any penalties
    if not is_negative_marking_enabled():
        return
    
    # Now, apply penalties for incorrect answers
    answer = update.poll_answer
    poll_id = answer.poll_id
    user = answer.user
    selected_options = answer.option_ids
    
    # Debug log
    logger.info(f"Extended poll answer processing for {user.first_name} (ID: {user.id}) for poll {poll_id}")
    
    # Check all chat data to find the quiz this poll belongs to
    for chat_id, chat_data in context.dispatcher.chat_data.items():
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
                category = question.get("category", "General Knowledge")
                
                # Check if the answer is incorrect
                is_correct = False
                if selected_options and len(selected_options) > 0:
                    is_correct = selected_options[0] == correct_answer
                
                # Apply penalty for incorrect answer
                if not is_correct:
                    logger.info(f"Applying penalty for user {user.id} in category {category}")
                    penalty = apply_penalty(user.id, category)
                    logger.info(f"Penalty applied: {penalty} points")
                
                break

def main():
    """Start the extended bot with negative marking."""
    try:
        # Create the Updater
        updater = Updater(BOT_TOKEN, use_context=True)
        
        # Get the dispatcher to register handlers
        dp = updater.dispatcher
        
        # Register extended stats command
        dp.add_handler(CommandHandler("stats", extended_stats_command))
        
        # Register negative marking commands
        dp.add_handler(CommandHandler("negmark", negative_marking_settings))
        dp.add_handler(CommandHandler("resetpenalty", reset_user_penalty_command))
        
        # Register callback query handler for negative marking settings
        dp.add_handler(CallbackQueryHandler(negative_settings_callback, pattern="^neg_mark_|^penalty_"))
        
        # Replace poll answer handler to include negative marking
        for handler in dp.handlers.get(0, []):
            if isinstance(handler, PollAnswerHandler):
                dp.remove_handler(handler)
                break
        # Add our extended poll answer handler
        dp.add_handler(PollAnswerHandler(extended_poll_answer))
        
        # Start the Bot
        updater.start_polling()
        updater.idle()
    
    except Exception as e:
        logger.error(f"Error starting extended bot: {e}")
        print(f"Error starting extended bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    # Make sure the original bot is imported and all dependencies are available
    try:
        from telegram.ext import PollAnswerHandler
        main()
    except ImportError as e:
        print(f"Error importing required modules: {e}")
        print("Make sure all dependencies are installed.")
        sys.exit(1)