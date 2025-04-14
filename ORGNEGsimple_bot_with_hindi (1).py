"""
Telegram Quiz Bot with negative marking functionality
Based on the original multi_id_quiz_bot.py but with added Hindi language support for PDF import
"""

import json
import logging
import os
import random
import asyncio
import re
import io
import tempfile
import requests
from bs4 import BeautifulSoup
import trafilatura
from typing import Dict, List, Optional, Tuple
import PyPDF2
from pdf2image import convert_from_bytes
import pytesseract
from telegram import (
    Update, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    Poll,
    Chat
)
from telegram.ext import (
    Updater,
    CallbackContext,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackQueryHandler,
    PollAnswerHandler
)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment variable
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Conversation states
QUESTION, OPTIONS, ANSWER, CATEGORY = range(4)
EDIT_SELECT, EDIT_QUESTION, EDIT_OPTIONS = range(4, 7)
CLONE_URL, CLONE_MANUAL = range(7, 9)
CUSTOM_ID = range(9, 10)

# URL extraction states for conversation handler
URL_INPUT, URL_CONFIRMATION, CATEGORY_SELECTION = range(100, 103)

# PDF extraction states for conversation handler
PDF_UPLOAD, PDF_PROCESSING, PDF_CATEGORY_SELECTION = range(200, 203)

# Data files
QUESTIONS_FILE = "questions.json"
USERS_FILE = "users.json"

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

# New file to track penalties
PENALTIES_FILE = "penalties.json"

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

async def start(update: Update, context: CallbackContext) -> None:
    """Send a welcome message when the command /start is issued."""
    user = update.effective_user
    welcome_text = (
        f"👋 Hello, {user.first_name}!\n\n"
        "Welcome to the Quiz Bot with Negative Marking. Here's what you can do:\n\n"
        "💡 /quiz - Start a new quiz (auto-sequence)\n"
        "📊 /stats - View your quiz statistics with penalties\n"
        "➕ /add - Add a new question to the quiz bank\n"
        "✏️ /edit - Edit an existing question\n"
        "❌ /delete - Delete a question\n"
        "🔄 /poll2q - Convert a Telegram poll to a quiz question\n"
        "🌐 /url2q - Extract questions from a Google URL with quiz content\n"
        "📄 /pdf2q - Extract questions from a PDF file (Now with Hindi support!)\n"
        "⚙️ /negmark - Configure negative marking settings\n"
        "🧹 /resetpenalty - Reset your penalties\n"
        "ℹ️ /help - Show this help message\n\n"
        "Let's test your knowledge with some fun quizzes!\n\n"
        "🆕 NEW FEATURE: Use /pdf2q to automatically extract questions from PDF files in English and Hindi!"
    )
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: CallbackContext) -> None:
    """Show help message."""
    await start(update, context)

# ---------- NEGATIVE MARKING COMMAND ADDITIONS ----------
async def extended_stats_command(update: Update, context: CallbackContext) -> None:
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
    
    await update.message.reply_text(stats_text)

async def negative_marking_settings(update: Update, context: CallbackContext) -> None:
    """Show and manage negative marking settings."""
    keyboard = [
        [InlineKeyboardButton("Enable Negative Marking", callback_data="neg_mark_enable")],
        [InlineKeyboardButton("Disable Negative Marking", callback_data="neg_mark_disable")],
        [InlineKeyboardButton("Reset All Penalties", callback_data="neg_mark_reset")],
        [InlineKeyboardButton("Back", callback_data="neg_mark_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔧 Negative Marking Settings\n\n"
        "You can enable/disable negative marking or reset penalties.",
        reply_markup=reply_markup
    )

async def negative_settings_callback(update: Update, context: CallbackContext) -> None:
    """Handle callback queries from negative marking settings."""
    query = update.callback_query
    await query.answer()
    
    global NEGATIVE_MARKING_ENABLED
    
    if query.data == "neg_mark_enable":
        NEGATIVE_MARKING_ENABLED = True
        await query.edit_message_text("✅ Negative marking has been enabled.")
    
    elif query.data == "neg_mark_disable":
        NEGATIVE_MARKING_ENABLED = False
        await query.edit_message_text("✅ Negative marking has been disabled.")
    
    elif query.data == "neg_mark_reset":
        reset_user_penalties()
        await query.edit_message_text("✅ All user penalties have been reset.")
    
    elif query.data == "neg_mark_back":
        await query.edit_message_text("✅ Settings closed.")

async def reset_user_penalty_command(update: Update, context: CallbackContext) -> None:
    """Reset penalties for a specific user."""
    user = update.effective_user
    
    # Reset penalties for this user
    reset_user_penalties(user.id)
    
    await update.message.reply_text(
        f"✅ Your penalties have been reset to zero.\n\n"
        f"Use /stats to view your updated statistics."
    )
    
# ---------- IMPROVED PDF TO QUESTION FUNCTIONALITY WITH HINDI SUPPORT ----------

def detect_language(text: str) -> str:
    """
    Detect if text contains Hindi characters
    
    Args:
        text: Text to analyze
        
    Returns:
        Language code ('hin' for Hindi, 'eng' for English)
    """
    # Check for Hindi Unicode range (basic Devanagari)
    hindi_pattern = re.compile(r'[\u0900-\u097F]')
    
    if hindi_pattern.search(text):
        return 'hin'
    return 'eng'

def extract_text_from_pdf(pdf_file_bytes: bytes) -> str:
    """
    Extract text from a PDF file with fallback to OCR.
    
    Args:
        pdf_file_bytes: PDF file content in bytes
        
    Returns:
        Extracted text
    """
    text = ""
    try:
        # Try to extract text using PyPDF2
        pdf_file = io.BytesIO(pdf_file_bytes)
        reader = PyPDF2.PdfReader(pdf_file)
        
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n\n"
                
        if len(text.strip()) < 100:
            # If text extraction yielded little text, try OCR
            logger.info("PyPDF2 extracted little text, trying OCR")
            return extract_text_using_ocr(pdf_file_bytes)
            
        return text
    except Exception as e:
        logger.error(f"Error extracting text from PDF with PyPDF2: {e}")
        # Fall back to OCR
        return extract_text_using_ocr(pdf_file_bytes)

def extract_text_using_ocr(pdf_file_bytes: bytes) -> str:
    """
    Extract text from a PDF file using OCR with language detection.
    
    Args:
        pdf_file_bytes: PDF file content in bytes
        
    Returns:
        Extracted text
    """
    text = ""
    try:
        # Convert PDF to images
        images = convert_from_bytes(pdf_file_bytes)
        
        # Use pytesseract to extract text from each image
        for i, image in enumerate(images):
            # First try with English (faster)
            page_text = pytesseract.image_to_string(image, lang='eng')
            
            # If Hindi characters are detected, redo with Hindi OCR
            if detect_language(page_text) == 'hin':
                logger.info(f"Hindi text detected on page {i+1}, using Hindi OCR")
                page_text = pytesseract.image_to_string(image, lang='hin')
            
            text += page_text + "\n\n"
            
        return text
    except Exception as e:
        logger.error(f"Error extracting text from PDF with OCR: {e}")
        return text

def extract_questions_from_pdf(text: str) -> List[Dict]:
    """
    Extract questions from PDF text with support for Hindi.
    
    Args:
        text: Text extracted from PDF
        
    Returns:
        List of question dictionaries
    """
    questions = []
    
    # Detect language
    language = detect_language(text)
    logger.info(f"Detected question language: {language}")
    
    # Find all question blocks with numbers
    question_blocks = re.findall(r'(\d+[\.\)]\s*[^\n]+(?:\n[^\d\n][^\n]*)*)', text)
    
    for block in question_blocks:
        # Extract question
        question_match = re.match(r'\d+[\.\)]\s*([^\n]+)', block)
        if not question_match:
            continue
            
        question_text = question_match.group(1).strip()
        
        # Extract options
        options = []
        option_matches = re.findall(r'([A-D][\.\)]\s*[^\n]+)', block)
        
        # If options with letters not found, try with numbers
        if not option_matches:
            option_matches = re.findall(r'(\d\)[\.\)]*\s*[^\n]+)', block)
        
        # Clean up the option text
        for opt in option_matches:
            # Remove option identifier (A., B., etc)
            option_text = re.sub(r'^[A-D\d][\.\)]\s*', '', opt).strip()
            options.append(option_text)
        
        # Extract answer
        answer = None
        
        # Handle English answer format
        answer_match = re.search(r'(?:answer|answer:|ans|ans:|correct answer|correct answer:|correct|correct:)\s*([a-dA-D\d])', block, re.IGNORECASE)
        
        # Handle Hindi answer format (उत्तर)
        if not answer_match:
            answer_match = re.search(r'(?:उत्तर|उत्तर:)\s*([a-dA-D\d])', block)
        
        if answer_match:
            answer_text = answer_match.group(1).upper()
            
            # Convert to index (0-based)
            answer_map = {"A": 0, "B": 1, "C": 2, "D": 3, "1": 0, "2": 1, "3": 2, "4": 3}
            answer = answer_map.get(answer_text, 0)
        
        # Only add if we have a question and options
        if question_text and len(options) >= 2:
            question_data = {
                "question": question_text,
                "options": options,
                "correct_answer": answer if answer is not None else 0,
                "category": "General Knowledge"  # Default category
            }
            questions.append(question_data)
    
    logger.info(f"Extracted {len(questions)} questions from PDF text")
    return questions

async def pdf_to_question_command(update: Update, context: CallbackContext) -> int:
    """Command handler to start PDF to Question conversion"""
    await update.message.reply_text(
        "📄 PDF to Question Converter\n\n"
        "Please send me a PDF file containing quiz questions.\n"
        "I can extract questions automatically from English and Hindi PDFs.\n\n"
        "For best results, use PDFs with clear question formatting like:\n"
        "1. What is the capital of France?\n"
        "A. London\n"
        "B. Paris\n"
        "C. Berlin\n"
        "D. Rome\n"
        "Answer: B\n\n"
        "Or Hindi format:\n"
        "1. भारत की राजधानी क्या है?\n"
        "A. मुंबई\n"
        "B. दिल्ली\n"
        "C. चेन्नई\n"
        "D. कोलकाता\n"
        "उत्तर: B\n\n"
        "Send /cancel to abort."
    )
    return PDF_UPLOAD

async def handle_pdf_file(update: Update, context: CallbackContext) -> int:
    """Process the uploaded PDF file"""
    # Check if the message contains a document
    if not update.message.document:
        await update.message.reply_text("Please send a PDF file.")
        return PDF_UPLOAD
    
    # Check if the document is a PDF
    file = update.message.document
    if not file.file_name.lower().endswith('.pdf'):
        await update.message.reply_text("The file is not a PDF. Please send a PDF file.")
        return PDF_UPLOAD
    
    try:
        # Send processing message
        processing_msg = await update.message.reply_text("⏳ Processing PDF... This may take a moment.")
        
        # Download the PDF file
        pdf_file = await context.bot.get_file(file.file_id)
        pdf_bytes = await pdf_file.download_as_bytearray()
        
        # Extract text from PDF
        text = extract_text_from_pdf(pdf_bytes)
        
        # Extract questions from text
        questions = extract_questions_from_pdf(text)
        
        # Store the questions in user_data for later use
        context.user_data['pdf_questions'] = questions
        
        # Update processing message
        if questions:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=processing_msg.message_id,
                text=f"✅ PDF processed successfully! Extracted {len(questions)} questions."
            )
            
            # Show preview of the first question
            if questions:
                preview = (
                    f"Preview of first question:\n\n"
                    f"Question: {questions[0]['question']}\n"
                    f"Options:\n"
                )
                
                for i, option in enumerate(questions[0]['options']):
                    preview += f"{chr(65+i)}. {option}\n"
                
                preview += f"Correct answer: {chr(65 + questions[0]['correct_answer'])}\n\n"
                preview += "Would you like to add these questions to the quiz database?"
                
                # Create keyboard for confirmation
                keyboard = [
                    [InlineKeyboardButton("Yes, add all questions", callback_data="pdf_add_all")],
                    [InlineKeyboardButton("No, cancel", callback_data="pdf_cancel")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(preview, reply_markup=reply_markup)
                return PDF_PROCESSING
            
        else:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=processing_msg.message_id,
                text="❌ No valid questions found in the PDF. Please try another file."
            )
            return PDF_UPLOAD
        
    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}")
        await update.message.reply_text(f"Error processing PDF: {str(e)}")
        return PDF_UPLOAD

async def process_pdf_questions(update: Update, context: CallbackContext) -> int:
    """Handle the confirmation of extracted PDF questions"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "pdf_add_all":
        # Add all questions
        questions = context.user_data.get('pdf_questions', [])
        
        if not questions:
            await query.edit_message_text("No questions found to add.")
            return ConversationHandler.END
        
        # Let user select category
        categories = [
            "General Knowledge", "Science", "History", "Geography",
            "Entertainment", "Sports", "Custom"
        ]
        
        keyboard = []
        for category in categories:
            keyboard.append([InlineKeyboardButton(category, callback_data=f"pdf_cat_{category}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Please select a category for these questions:",
            reply_markup=reply_markup
        )
        
        return PDF_CATEGORY_SELECTION
        
    elif query.data == "pdf_cancel":
        # Cancel the operation
        await query.edit_message_text("PDF import cancelled.")
        return ConversationHandler.END

async def select_pdf_category(update: Update, context: CallbackContext) -> int:
    """Handle selection of category for the PDF questions"""
    query = update.callback_query
    await query.answer()
    
    # Check if it's a category selection
    if query.data.startswith("pdf_cat_"):
        category = query.data[8:]  # Remove "pdf_cat_" prefix
        
        if category == "Custom":
            # Ask user to enter a custom category
            await query.edit_message_text(
                "Please enter a custom category name for these questions:"
            )
            # Set state for custom category input
            context.user_data['awaiting_custom_category'] = True
            return PDF_CATEGORY_SELECTION
        
        # Set the category for all questions
        questions = context.user_data.get('pdf_questions', [])
        for question in questions:
            question['category'] = category
        
        # Add questions to the database
        added_count = 0
        for question in questions:
            try:
                question_id = get_next_question_id()
                add_question_with_id(question_id, question)
                added_count += 1
            except Exception as e:
                logger.error(f"Error adding question: {str(e)}")
        
        # Send success message
        await query.edit_message_text(
            f"✅ Successfully added {added_count} questions with category '{category}'!"
        )
        
        # Clear user data
        if 'pdf_questions' in context.user_data:
            del context.user_data['pdf_questions']
        
        return ConversationHandler.END
    
    # Handle custom category input (this will be text input, not a callback query)
    elif context.user_data.get('awaiting_custom_category', False):
        custom_category = update.message.text.strip()
        
        # Set the category for all questions
        questions = context.user_data.get('pdf_questions', [])
        for question in questions:
            question['category'] = custom_category
        
        # Add questions to the database
        added_count = 0
        for question in questions:
            try:
                question_id = get_next_question_id()
                add_question_with_id(question_id, question)
                added_count += 1
            except Exception as e:
                logger.error(f"Error adding question: {str(e)}")
        
        # Send success message
        await update.message.reply_text(
            f"✅ Successfully added {added_count} questions with category '{custom_category}'!"
        )
        
        # Clear user data
        if 'pdf_questions' in context.user_data:
            del context.user_data['pdf_questions']
        if 'awaiting_custom_category' in context.user_data:
            del context.user_data['awaiting_custom_category']
        
        return ConversationHandler.END

async def cancel_pdf_import(update: Update, context: CallbackContext) -> int:
    """Cancel the PDF import process"""
    await update.message.reply_text("PDF import cancelled.")
    
    # Clear user data
    if 'pdf_questions' in context.user_data:
        del context.user_data['pdf_questions']
    if 'awaiting_custom_category' in context.user_data:
        del context.user_data['awaiting_custom_category']
    
    return ConversationHandler.END

# ... Rest of the original file continues below ...

# [Include all other functions from the original file]

def main() -> None:
    """Start the bot."""
    try:
        # Create the Updater and pass it your bot's token
        updater = Updater(BOT_TOKEN)

        # Get the dispatcher to register handlers
        dispatcher = updater.dispatcher

        # Conversation handler for adding questions
        add_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('add', add_question_start)],
            states={
                QUESTION: [MessageHandler(Filters.text & ~Filters.command, add_question_text)],
                OPTIONS: [MessageHandler(Filters.text & ~Filters.command, add_question_options)],
                ANSWER: [MessageHandler(Filters.text & ~Filters.command, add_question_answer)],
                CUSTOM_ID: [
                    CallbackQueryHandler(custom_id_callback, pattern='^(auto_id|custom_id)$'),
                    MessageHandler(Filters.text & ~Filters.command, custom_id_input)
                ],
                CATEGORY: [
                    CallbackQueryHandler(category_callback),
                    MessageHandler(Filters.text & ~Filters.command, show_category_selection)
                ],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )
        
        # Conversation handler for URL extraction
        url_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('url2q', start_url_extraction)],
            states={
                URL_INPUT: [MessageHandler(Filters.text & ~Filters.command, process_url)],
                URL_CONFIRMATION: [CallbackQueryHandler(confirm_questions, pattern='^(confirm|cancel)$')],
                CATEGORY_SELECTION: [CallbackQueryHandler(select_category)],
            },
            fallbacks=[CommandHandler('cancel', url_extraction_cancel)],
        )
        
        # Conversation handler for PDF to question
        pdf_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('pdf2q', pdf_to_question_command)],
            states={
                PDF_UPLOAD: [
                    MessageHandler(Filters.document, handle_pdf_file),
                    CommandHandler('cancel', cancel_pdf_import)
                ],
                PDF_PROCESSING: [
                    CallbackQueryHandler(process_pdf_questions, pattern='^pdf_')
                ],
                PDF_CATEGORY_SELECTION: [
                    CallbackQueryHandler(select_pdf_category, pattern='^pdf_cat_'),
                    MessageHandler(Filters.text & ~Filters.command, select_pdf_category)
                ],
            },
            fallbacks=[CommandHandler('cancel', cancel_pdf_import)],
        )

        # Add conversation handlers
        dispatcher.add_handler(add_conv_handler)
        dispatcher.add_handler(url_conv_handler)
        dispatcher.add_handler(pdf_conv_handler)
        
        # Add command handlers
        dispatcher.add_handler(CommandHandler("start", start))
        dispatcher.add_handler(CommandHandler("help", help_command))
        dispatcher.add_handler(CommandHandler("stats", stats_command))
        dispatcher.add_handler(CommandHandler("delete", delete_command))
        dispatcher.add_handler(CommandHandler("quiz", quiz_command))
        dispatcher.add_handler(CommandHandler("poll2q", poll_to_question))
        
        # Negative marking command handlers
        dispatcher.add_handler(CommandHandler("negmark", negative_marking_settings))
        dispatcher.add_handler(CallbackQueryHandler(negative_settings_callback, pattern="^neg_mark_"))
        dispatcher.add_handler(CommandHandler("resetpenalty", reset_user_penalty_command))
        
        # Add handlers for poll answers and forwarded polls
        dispatcher.add_handler(PollAnswerHandler(poll_answer))
        dispatcher.add_handler(MessageHandler(Filters.poll, handle_forwarded_poll))
        
        # Add callback query handlers for poll conversion
        dispatcher.add_handler(CallbackQueryHandler(handle_poll_answer, pattern="^poll_answer_"))
        dispatcher.add_handler(CallbackQueryHandler(handle_poll_id_selection, pattern="^poll_id_"))
        dispatcher.add_handler(CallbackQueryHandler(handle_poll_custom_id, pattern="^poll_custom_id_"))
        dispatcher.add_handler(CallbackQueryHandler(handle_poll_category, pattern="^poll_cat_"))

        # Start the Bot
        updater.start_polling()
        logger.info("Bot started successfully!")

        # Run the bot until you press Ctrl-C or the process receives SIGINT, SIGTERM or SIGABRT
        updater.idle()
    except Exception as e:
        logger.error(f"Error running bot: {str(e)}")

if __name__ == '__main__':
    main()