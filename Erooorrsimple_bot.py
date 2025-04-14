"""
Telegram Quiz Bot with negative marking functionality
Based on the original multi_id_quiz_bot.py but with added negative marking features
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
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Updater,
    CallbackContext,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackQueryHandler,
    PollAnswerHandler,
    ContextTypes
)
from telegram import Poll, Chat

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment variable
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7631768276:AAFWUidQIXRnw-CLxaNAPvc0YGef6u1iZWQ")

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
        "📄 /pdf2q - Extract questions from a PDF file\n"
        "⚙️ /negmark - Configure negative marking settings\n"
        "🧹 /resetpenalty - Reset your penalties\n"
        "ℹ️ /help - Show this help message\n\n"
        "Let's test your knowledge with some fun quizzes!\n\n"
        "🆕 NEW FEATURE: Use /pdf2q to automatically extract questions from PDF files!"
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
    
# ---------- PDF to Question functionality ----------
def extract_text_from_pdf(pdf_file_bytes: bytes) -> str:
    """Extract text from a PDF file"""
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

def extract_text_using_ocr(pdf_file_bytes: bytes) -> str:
    """Extract text from a PDF file using OCR with language detection"""
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
    """Extract questions from PDF text with Hindi language support"""
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
        answer = 0  # Default to first option
        
        # English answer patterns
        answer_match = re.search(r'(?:answer|answer:|ans|ans:|correct answer|correct answer:|correct|correct:)\s*([a-dA-D\d])', block, re.IGNORECASE)
        
        # Hindi answer patterns (उत्तर is Hindi for "answer")
        if not answer_match and language == 'hin':
            answer_match = re.search(r'(?:उत्तर|उत्तर:)\s*([a-dA-D\d])', block)
        
        if answer_match:
            answer_text = answer_match.group(1).upper()
            
            # Convert to index (0-based)
            answer_map = {"A": 0, "B": 1, "C": 2, "D": 3, "1": 0, "2": 1, "3": 2, "4": 3}
            answer = answer_map.get(answer_text, 0)
        
        # Only add if we have a question and options
        if question_text and len(options) >= 2:
            questions.append({
                "question": question_text,
                "options": options,
                "answer": answer,
                "category": "General Knowledge"  # Default category
            })
    
    logger.info(f"Extracted {len(questions)} questions from PDF text")
    return questions

async def pdf_to_question_command(update: Update, context: CallbackContext) -> int:
    """Command handler to start PDF to Question conversion"""
    await update.message.reply_text(
        "📄 PDF to Quiz Questions Converter\n\n"
        "Please upload a PDF file containing quiz questions.\n"
        "✨ Now with Hindi language support! ✨\n\n"
        "The file should contain questions in a format like:\n\n"
        "1. What is the capital of France?\n"
        "A. London\n"
        "B. Paris\n"
        "C. Berlin\n"
        "D. Rome\n"
        "Answer: B\n\n"
        "Or in Hindi:\n\n"
        "1. भारत की राजधानी क्या है?\n"
        "A. मुंबई\n"
        "B. नई दिल्ली\n"
        "C. कोलकाता\n"
        "D. चेन्नई\n"
        "उत्तर: B\n\n"
        "Send a PDF file now, or /cancel to abort."
    )
    return PDF_UPLOAD

async def handle_pdf_file(update: Update, context: CallbackContext) -> int:
    """Process the uploaded PDF file"""
    # Get the PDF file
    pdf_file = await update.message.document.get_file()
    pdf_data = await pdf_file.download_as_bytearray()
    
    # Save file info in context
    context.user_data["pdf_name"] = update.message.document.file_name
    context.user_data["pdf_data"] = pdf_data
    
    # Send processing message
    processing_msg = await update.message.reply_text("⏳ Processing PDF file, please wait...")
    
    try:
        # Extract text from PDF
        pdf_text = extract_text_from_pdf(pdf_data)
        
        if not pdf_text or len(pdf_text.strip()) < 50:
            await processing_msg.edit_text(
                "❌ Could not extract text from this PDF. "
                "The file might be encrypted, image-based without clear text, or empty."
            )
            return ConversationHandler.END
        
        # Extract questions from text
        questions = extract_questions_from_pdf(pdf_text)
        
        if not questions:
            await processing_msg.edit_text(
                "❌ Could not find any quiz questions in this PDF. "
                "Make sure the PDF contains properly formatted questions."
            )
            return ConversationHandler.END
        
        # Store extracted questions in user_data
        context.user_data["pdf_questions"] = questions
        
        # Build message text
        message_text = f"✅ Found {len(questions)} questions in the PDF!\n\nHere's a preview of the first question:\n\n"
        
        # Show the first question as preview
        question = questions[0]
        message_text += f"Q: {question['question']}\n\n"
        
        for i, option in enumerate(question['options']):
            message_text += f"{chr(65+i)}. {option}\n"
        
        message_text += f"\nCorrect Answer: {chr(65+question['answer'])}\n\n"
        message_text += "Would you like to add these questions to the quiz bank?"
        
        # Create keyboard
        keyboard = [
            [
                InlineKeyboardButton("✅ Add All", callback_data="pdf_add_all"),
                InlineKeyboardButton("❌ Cancel", callback_data="pdf_cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await processing_msg.edit_text(message_text, reply_markup=reply_markup)
        return PDF_PROCESSING
        
    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        await processing_msg.edit_text(
            f"❌ Error processing PDF: {str(e)}\n\n"
            "Please try with a different PDF file."
        )
        return ConversationHandler.END

async def process_pdf_questions(update: Update, context: CallbackContext) -> int:
    """Handle the confirmation of extracted PDF questions"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "pdf_cancel":
        await query.edit_message_text("❌ PDF import cancelled.")
        return ConversationHandler.END
    
    elif query.data == "pdf_add_all":
        # Show category selection options
        keyboard = [
            [
                InlineKeyboardButton("General Knowledge", callback_data="pdf_category_General Knowledge"),
                InlineKeyboardButton("Science", callback_data="pdf_category_Science")
            ],
            [
                InlineKeyboardButton("History", callback_data="pdf_category_History"),
                InlineKeyboardButton("Geography", callback_data="pdf_category_Geography")
            ],
            [
                InlineKeyboardButton("Entertainment", callback_data="pdf_category_Entertainment"),
                InlineKeyboardButton("Sports", callback_data="pdf_category_Sports")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Please select a category for these questions:",
            reply_markup=reply_markup
        )
        return PDF_CATEGORY_SELECTION

async def select_pdf_category(update: Update, context: CallbackContext) -> int:
    """Handle selection of category for the PDF questions"""
    query = update.callback_query
    await query.answer()
    
    # Extract category from callback data
    category = query.data.replace("pdf_category_", "")
    
    # Get extracted questions from user_data
    questions = context.user_data.get("pdf_questions", [])
    
    if not questions:
        await query.edit_message_text("❌ No questions found. Please try again.")
        return ConversationHandler.END
    
    # Update category for all questions
    for question in questions:
        question["category"] = category
    
    # Send importing message
    await query.edit_message_text("⏳ Importing questions...")
    
    # Import each question
    next_id = get_next_question_id()
    imported_count = 0
    
    for question in questions:
        add_question_with_id(next_id, question)
        next_id += 1
        imported_count += 1
    
    # Send success message
    await query.edit_message_text(
        f"✅ Successfully imported {imported_count} questions from the PDF into the '{category}' category!"
    )
    
    return ConversationHandler.END

async def cancel_pdf_import(update: Update, context: CallbackContext) -> int:
    """Cancel the PDF import process"""
    await update.message.reply_text("❌ PDF import cancelled.")
    return ConversationHandler.END

# ---------- URL to Question functionality ----------
def fetch_url_content(url: str) -> Optional[str]:
    """Fetch content from a URL using Trafilatura"""
    try:
        downloaded = trafilatura.fetch_url(url)
        text = trafilatura.extract(downloaded)
        
        if not text or len(text) < 100:
            # Try fallback method
            return fetch_url_content_with_bs4(url)
            
        return text
    except Exception as e:
        logger.error(f"Error fetching URL with trafilatura: {e}")
        return fetch_url_content_with_bs4(url)

def fetch_url_content_with_bs4(url: str) -> Optional[str]:
    """Fetch content from a URL using requests and BeautifulSoup as a backup method"""
    try:
        response = requests.get(url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.extract()
        
        # Get text
        text = soup.get_text()
        
        # Break into lines and remove leading and trailing space
        lines = (line.strip() for line in text.splitlines())
        # Break multi-headlines into a line each
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        # Remove blank lines
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return text
    except Exception as e:
        logger.error(f"Error fetching URL with BeautifulSoup: {e}")
        return None

def extract_questions_from_text(text: str) -> List[Dict]:
    """
    Extract questions and answers from text content
    Returns a list of question dictionaries in the format:
    {
        'question': 'What is the capital of France?',
        'options': ['Paris', 'London', 'Berlin', 'Madrid'],
        'correct_answer': 0,  # Index of correct answer
        'category': 'General Knowledge'
    }
    """
    questions = []
    
    # Look for pattern: number followed by question text
    question_pattern = r'\b(\d+)[.)]\s+([^\?\n]+\?)'
    questions_matches = re.finditer(question_pattern, text)
    
    for q_match in questions_matches:
        question_num = q_match.group(1)
        question_text = q_match.group(2).strip()
        
        # Search for options after this question
        q_start_pos = q_match.end()
        next_q_match = re.search(r'\b\d+[.)]\s+[^\?\n]+\?', text[q_start_pos:])
        q_end_pos = q_start_pos + next_q_match.start() if next_q_match else len(text)
        
        question_block = text[q_start_pos:q_end_pos]
        
        # Find options (a, b, c, d format or 1, 2, 3, 4 format)
        options = []
        
        # Try a), b), c), d) format
        option_matches = re.finditer(r'(?:^|\n)([a-d][.)]) ?([^\n]+)(?:\n|$)', question_block, re.IGNORECASE)
        
        for opt_match in option_matches:
            option_text = opt_match.group(2).strip()
            options.append(option_text)
        
        # If no options found, try other formats (1, 2, 3, 4 or custom parsing)
        if not options:
            # Try custom extraction based on line patterns
            lines = [l.strip() for l in question_block.split('\n') if l.strip()]
            if len(lines) >= 4:  # Assume first 4 non-empty lines are options
                options = lines[:4]
        
        # Only proceed if we found some options
        if len(options) >= 2:
            # Try to find the correct answer
            correct_answer = 0  # Default to first option
            
            # Look for patterns like "answer: a" or "correct: b"
            answer_match = re.search(r'(?:answer|correct)[^a-d]*([a-d])', question_block, re.IGNORECASE)
            
            if answer_match:
                answer_letter = answer_match.group(1).lower()
                # Convert letter to index (a=0, b=1, etc.)
                answer_idx = ord(answer_letter) - ord('a')
                if 0 <= answer_idx < len(options):
                    correct_answer = answer_idx
            
            questions.append({
                'question': question_text,
                'options': options,
                'answer': correct_answer,
                'category': 'General Knowledge'  # Default category
            })
    
    return questions

def extract_questions_alternative(text: str) -> List[Dict]:
    """Alternative method to extract questions from less structured content"""
    questions = []
    
    # Split the text into paragraphs
    paragraphs = text.split('\n\n')
    
    for i in range(len(paragraphs) - 1):
        paragraph = paragraphs[i].strip()
        next_paragraph = paragraphs[i + 1].strip()
        
        # Look for question-like patterns (ends with question mark)
        if paragraph.endswith('?'):
            options = []
            
            # Check if next paragraph might contain options
            lines = next_paragraph.split('\n')
            if len(lines) >= 2:
                # Extract potential options
                for line in lines[:4]:  # Limit to first 4 lines
                    line = line.strip()
                    if line and len(line) < 100:  # Reasonable length for an option
                        options.append(line)
            
            # If we have enough options, create a question
            if len(options) >= 2:
                questions.append({
                    'question': paragraph,
                    'options': options,
                    'answer': 0,  # Default to first option as correct
                    'category': 'General Knowledge'  # Default category
                })
    
    return questions

async def start_url_extraction(update: Update, context: CallbackContext) -> int:
    """Start the URL extraction process"""
    await update.message.reply_text(
        "🌐 URL to Quiz Questions Extractor\n\n"
        "Send me a URL containing quiz questions, and I'll extract them for you.\n"
        "This works best with Google Forms quizzes or similar content.\n\n"
        "Please send the URL now, or /cancel to abort."
    )
    return URL_INPUT

async def process_url(update: Update, context: CallbackContext) -> int:
    """Process the URL sent by the user"""
    url = update.message.text.strip()
    
    # Basic URL validation
    if not url.startswith('http'):
        await update.message.reply_text(
            "❌ That doesn't look like a valid URL. Please send a URL starting with http:// or https://."
        )
        return URL_INPUT
    
    # Send a processing message
    processing_msg = await update.message.reply_text("⏳ Processing URL...")
    
    try:
        # Fetch content from URL
        content = fetch_url_content(url)
        
        if not content:
            await processing_msg.edit_text(
                "❌ Could not extract content from this URL. Please try a different URL."
            )
            return URL_INPUT
        
        # Extract questions from content
        questions = extract_questions_from_text(content)
        
        # If no questions found, try alternative method
        if not questions:
            questions = extract_questions_alternative(content)
        
        if not questions:
            await processing_msg.edit_text(
                "❌ Could not find any quiz questions in this content. "
                "The URL might not contain properly formatted questions."
            )
            return URL_INPUT
        
        # Store extracted questions in user_data
        context.user_data['extracted_questions'] = questions
        context.user_data['url'] = url
        
        # Build message text
        message_text = f"✅ Found {len(questions)} questions!\n\nHere's a preview of the first question:\n\n"
        
        question = questions[0]
        message_text += f"Q: {question['question']}\n\n"
        
        for i, option in enumerate(question['options']):
            message_text += f"{chr(65+i)}. {option}\n"
        
        message_text += f"\nCorrect Answer: {chr(65+question['answer'])}\n\n"
        message_text += "Would you like to add these questions to the quiz bank?"
        
        # Create inline keyboard
        keyboard = [
            [
                InlineKeyboardButton("✅ Add All", callback_data="url_add_all"),
                InlineKeyboardButton("❌ Cancel", callback_data="url_cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await processing_msg.edit_text(message_text, reply_markup=reply_markup)
        return URL_CONFIRMATION
    
    except Exception as e:
        logger.error(f"Error processing URL: {e}")
        await processing_msg.edit_text(
            f"❌ Error processing URL: {str(e)}\n\nPlease try a different URL."
        )
        return URL_INPUT

async def confirm_questions(update: Update, context: CallbackContext) -> int:
    """Handle confirmation of extracted questions"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "url_cancel":
        await query.edit_message_text("❌ URL extraction cancelled.")
        return ConversationHandler.END
    
    elif query.data == "url_add_all":
        # Show category selection options
        keyboard = [
            [
                InlineKeyboardButton("General Knowledge", callback_data="url_category_General Knowledge"),
                InlineKeyboardButton("Science", callback_data="url_category_Science")
            ],
            [
                InlineKeyboardButton("History", callback_data="url_category_History"),
                InlineKeyboardButton("Geography", callback_data="url_category_Geography")
            ],
            [
                InlineKeyboardButton("Entertainment", callback_data="url_category_Entertainment"),
                InlineKeyboardButton("Sports", callback_data="url_category_Sports")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Please select a category for these questions:",
            reply_markup=reply_markup
        )
        return CATEGORY_SELECTION

async def select_category(update: Update, context: CallbackContext) -> int:
    """Handle selection of category for the extracted questions"""
    query = update.callback_query
    await query.answer()
    
    # Extract category from callback data
    category = query.data.replace("url_category_", "")
    
    # Get extracted questions from user_data
    questions = context.user_data.get('extracted_questions', [])
    
    if not questions:
        await query.edit_message_text("❌ No questions found. Please try again.")
        return ConversationHandler.END
    
    # Update category for all questions
    for question in questions:
        question['category'] = category
    
    # Send importing message
    await query.edit_message_text("⏳ Importing questions...")
    
    # Import each question
    next_id = get_next_question_id()
    for question in questions:
        add_question_with_id(next_id, question)
        next_id += 1
    
    # Send success message
    await query.edit_message_text(
        f"✅ Successfully imported {len(questions)} questions into the '{category}' category!"
    )
    
    return ConversationHandler.END

async def url_extraction_cancel(update: Update, context: CallbackContext) -> int:
    """Cancel the URL extraction process"""
    await update.message.reply_text("❌ URL extraction cancelled.")
    return ConversationHandler.END

# ---------- End URL to Question functionality ----------

async def stats_command(update: Update, context: CallbackContext) -> None:
    """Display user statistics."""
    await extended_stats_command(update, context)

# Add question functionality
async def add_question_start(update: Update, context: CallbackContext) -> int:
    """Start the process of adding a new question."""
    await update.message.reply_text(
        "Let's add a new question to the quiz database. Please send me the question text."
    )
    return QUESTION

async def add_question_text(update: Update, context: CallbackContext) -> int:
    """Save the question text and ask for options."""
    context.user_data["question"] = update.message.text
    
    await update.message.reply_text(
        "Great! Now send me the answer options as a single message. Separate each option with a new line."
    )
    return OPTIONS

async def add_question_options(update: Update, context: CallbackContext) -> int:
    """Save the options and ask for the correct answer."""
    options_text = update.message.text
    options = [option.strip() for option in options_text.split('\n') if option.strip()]
    
    if len(options) < 2:
        await update.message.reply_text(
            "Please provide at least 2 options, with each option on a new line."
        )
        return OPTIONS
    
    context.user_data["options"] = options
    
    # Create a message with numbered options for reference
    options_message = "Here are your options:\n\n"
    for i, option in enumerate(options):
        options_message += f"{i+1}. {option}\n"
    
    options_message += "\nPlease send the number of the correct answer (1, 2, 3, etc.)."
    
    await update.message.reply_text(options_message)
    return ANSWER

async def add_question_answer(update: Update, context: CallbackContext) -> int:
    """Save the correct answer and create the question."""
    try:
        # Convert input to integer and adjust to 0-based index
        answer = int(update.message.text.strip()) - 1
        options = context.user_data.get("options", [])
        
        if answer < 0 or answer >= len(options):
            await update.message.reply_text(
                f"Please enter a number between 1 and {len(options)}."
            )
            return ANSWER
        
        context.user_data["answer"] = answer
        
        # Ask for ID selection method
        keyboard = [
            [
                InlineKeyboardButton("Auto-generate ID", callback_data="auto_id"),
                InlineKeyboardButton("Enter custom ID", callback_data="custom_id")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "How would you like to assign an ID to this question?",
            reply_markup=reply_markup
        )
        
        return CUSTOM_ID
        
    except ValueError:
        await update.message.reply_text(
            "Please enter a valid number for the correct answer."
        )
        return ANSWER

async def custom_id_callback(update: Update, context: CallbackContext) -> int:
    """Handle ID selection method."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "auto_id":
        # Auto-generate ID
        question_id = get_next_question_id()
        context.user_data["question_id"] = question_id
        
        # Show category selection
        return await show_category_selection(update, context)
        
    elif query.data == "custom_id":
        # Ask for custom ID
        await query.edit_message_text(
            "Please enter a custom ID number for this question:"
        )
        context.user_data["awaiting_custom_id"] = True
        return CUSTOM_ID

async def custom_id_input(update: Update, context: CallbackContext) -> int:
    """Handle custom ID input."""
    try:
        question_id = int(update.message.text.strip())
        if question_id <= 0:
            await update.message.reply_text(
                "Please enter a positive number for the question ID."
            )
            return CUSTOM_ID
        
        context.user_data["question_id"] = question_id
        context.user_data["awaiting_custom_id"] = False
        
        # Show category selection
        return await show_category_selection(update, context)
        
    except ValueError:
        await update.message.reply_text(
            "Please enter a valid number for the question ID."
        )
        return CUSTOM_ID

async def show_category_selection(update: Update, context: CallbackContext) -> int:
    """Show category selection keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("General Knowledge", callback_data="category_General Knowledge"),
            InlineKeyboardButton("Science", callback_data="category_Science")
        ],
        [
            InlineKeyboardButton("History", callback_data="category_History"),
            InlineKeyboardButton("Geography", callback_data="category_Geography")
        ],
        [
            InlineKeyboardButton("Entertainment", callback_data="category_Entertainment"),
            InlineKeyboardButton("Sports", callback_data="category_Sports")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "Please select a category for this question:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Please select a category for this question:",
            reply_markup=reply_markup
        )
    
    return CATEGORY

async def category_callback(update: Update, context: CallbackContext) -> int:
    """Handle category selection."""
    query = update.callback_query
    await query.answer()
    
    # Extract category from callback data
    category = query.data.replace("category_", "")
    
    # Create the question object
    question_data = {
        "question": context.user_data["question"],
        "options": context.user_data["options"],
        "answer": context.user_data["answer"],
        "category": category
    }
    
    # Get the question ID
    question_id = context.user_data["question_id"]
    
    # Add the question
    add_question_with_id(question_id, question_data)
    
    # Get how many questions are now at this ID
    questions = load_questions()
    question_count = len(questions[str(question_id)]) if isinstance(questions[str(question_id)], list) else 1
    
    await query.edit_message_text(
        f"✅ Question added successfully with ID: {question_id}\n\n"
        f"This ID now has {question_count} question(s)\n\n"
        f"Question: {question_data['question']}\n"
        f"Category: {category}\n"
        f"Options: {len(question_data['options'])}\n"
        f"Correct answer: {question_data['answer']+1}. {question_data['options'][question_data['answer']]}"
    )
    
    return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext) -> int:
    """Cancel the current operation."""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

async def delete_command(update: Update, context: CallbackContext) -> None:
    """Delete a question by ID."""
    message_parts = update.message.text.split()
    
    if len(message_parts) < 2:
        await update.message.reply_text(
            "Please provide a question ID to delete.\n"
            "Example: /delete 42"
        )
        return
    
    try:
        question_id = int(message_parts[1])
        
        # Try to get the question first
        question = get_question_by_id(question_id)
        
        if not question:
            await update.message.reply_text(f"❌ Question with ID {question_id} not found.")
            return
        
        # Delete the question
        success = delete_question_by_id(question_id)
        
        if success:
            await update.message.reply_text(f"✅ Question with ID {question_id} deleted successfully.")
        else:
            await update.message.reply_text(f"❌ Failed to delete question with ID {question_id}.")
            
    except ValueError:
        await update.message.reply_text("Please provide a valid question ID (number).")

# Quiz functionality
async def quiz_command(update: Update, context: CallbackContext) -> None:
    """Start a quiz session with random questions."""
    message_parts = update.message.text.split()
    
    num_questions = 5  # Default
    category = None
    
    # Parse command arguments
    if len(message_parts) > 1:
        try:
            num_questions = int(message_parts[1])
            num_questions = max(1, min(20, num_questions))  # Limit between 1 and 20
        except ValueError:
            # If not a number, could be a category
            category = message_parts[1]
    
    if len(message_parts) > 2:
        category = message_parts[2]
    
    # Load all questions
    questions_dict = load_questions()
    
    if not questions_dict:
        await update.message.reply_text("❌ No questions available in the database.")
        return
    
    # Flatten the questions dictionary to a list
    all_questions = []
    for q_id, questions in questions_dict.items():
        if isinstance(questions, list):
            all_questions.extend(questions)
        else:
            all_questions.append(questions)
    
    # Filter by category if specified
    if category:
        all_questions = [q for q in all_questions if q.get("category", "").lower() == category.lower()]
        
        if not all_questions:
            await update.message.reply_text(f"❌ No questions found in category '{category}'.")
            return
    
    # Shuffle and limit
    random.shuffle(all_questions)
    selected_questions = all_questions[:num_questions]
    
    # Store quiz state
    chat_id = update.effective_chat.id
    context.chat_data[chat_id] = {
        "quiz_questions": selected_questions,
        "current_index": 0,
        "participants": {},
        "correct_option": None
    }
    
    # Send the first question
    await update.message.reply_text(f"📝 Starting quiz with {len(selected_questions)} questions!")
    await asyncio.sleep(1)  # Small delay before first question
    await send_question(context, chat_id, 0)

async def send_question(context, chat_id, question_index):
    """Send a quiz question and schedule next one."""
    try:
        quiz_data = context.chat_data.get(chat_id, {})
        questions = quiz_data.get("quiz_questions", [])
        
        if question_index >= len(questions):
            await schedule_end_quiz(context, chat_id)
            return
        
        question = questions[question_index]
        
        # Send the question as a poll
        options = question.get("options", [])
        correct_option = question.get("answer", 0)
        
        # Store correct option for later reference
        quiz_data["correct_option"] = correct_option
        
        # Send quiz poll (anonymous voting to prevent showing correct answer)
        sent_message = await context.bot.send_poll(
            chat_id=chat_id,
            question=f"Question {question_index + 1}/{len(questions)}: {question.get('question', '')}",
            options=options,
            type="quiz",
            correct_option_id=correct_option,
            is_anonymous=False,
            explanation=f"Category: {question.get('category', 'General Knowledge')}"
        )
        
        # Store poll_id to track answers
        quiz_data["current_poll_id"] = sent_message.poll.id
        quiz_data["current_index"] = question_index
        
        # Schedule the next question
        next_index = question_index + 1
        if next_index < len(questions):
            await schedule_next_question(context, chat_id, next_index)
        else:
            await schedule_end_quiz(context, chat_id)
            
    except Exception as e:
        logger.error(f"Error sending question: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Error sending question: {str(e)}"
        )

async def schedule_next_question(context, chat_id, next_index):
    """Schedule the next question with delay."""
    # Wait 15 seconds before next question
    await asyncio.sleep(15)
    await send_question(context, chat_id, next_index)

async def schedule_end_quiz(context, chat_id):
    """Schedule end of quiz with delay."""
    # Wait 15 seconds before ending
    await asyncio.sleep(15)
    await end_quiz(context, chat_id)

async def poll_answer(update: Update, context: CallbackContext) -> None:
    """Handle poll answers from users with negative marking."""
    poll_id = update.poll_answer.poll_id
    user_id = update.poll_answer.user.id
    selected_option = update.poll_answer.option_ids[0] if update.poll_answer.option_ids else None
    
    # Find which chat this poll belongs to
    for chat_id, quiz_data in context.chat_data.items():
        if quiz_data.get("current_poll_id") == poll_id:
            # Found the chat
            if user_id not in quiz_data.get("participants", {}):
                quiz_data["participants"][user_id] = {
                    "name": update.poll_answer.user.first_name,
                    "correct": 0,
                    "total": 0,
                    "penalties": 0
                }
            
            # Get user data
            user_data = quiz_data["participants"][user_id]
            user_data["total"] += 1
            
            # Check if answer is correct
            correct_option = quiz_data.get("correct_option")
            
            if selected_option == correct_option:
                user_data["correct"] += 1
            else:
                # Apply negative marking
                current_question = quiz_data.get("current_index", 0)
                questions = quiz_data.get("quiz_questions", [])
                
                if current_question < len(questions):
                    category = questions[current_question].get("category", "General Knowledge")
                    penalty = get_penalty_for_category(category)
                    
                    if penalty > 0:
                        user_data["penalties"] += penalty
            
            # Update user data in chat_data
            quiz_data["participants"][user_id] = user_data
            break

async def end_quiz(context, chat_id):
    """End the quiz and display results with all participants and penalties."""
    quiz_data = context.chat_data.get(chat_id, {})
    participants = quiz_data.get("participants", {})
    
    if not participants:
        await context.bot.send_message(
            chat_id=chat_id,
            text="📊 Quiz ended! No one participated in this quiz."
        )
        return
    
    # Prepare results message
    results_message = "📊 Quiz Results:\n\n"
    
    # Sort participants by score (correct answers minus penalties)
    sorted_participants = sorted(
        participants.items(),
        key=lambda x: (x[1]["correct"] - x[1]["penalties"]),
        reverse=True
    )
    
    for user_id, data in sorted_participants:
        name = data["name"]
        correct = data["correct"]
        total = data["total"]
        penalties = data["penalties"]
        
        # Calculate score with penalties
        score = max(0, correct - penalties)
        percentage = (correct / total * 100) if total > 0 else 0
        
        results_message += f"👤 {name}:\n"
        results_message += f"✓ Correct: {correct}/{total} ({percentage:.1f}%)\n"
        
        if NEGATIVE_MARKING_ENABLED and penalties > 0:
            results_message += f"✗ Penalties: {penalties:.2f} points\n"
            results_message += f"⭐ Final Score: {score:.2f} points\n"
        else:
            results_message += f"⭐ Score: {correct} points\n"
        
        results_message += "\n"
        
        # Update user's overall stats
        user_data = get_user_data(user_id)
        user_data["total_answers"] = user_data.get("total_answers", 0) + total
        user_data["correct_answers"] = user_data.get("correct_answers", 0) + correct
        save_user_data(user_id, user_data)
        
        # Update penalties
        if NEGATIVE_MARKING_ENABLED and penalties > 0:
            update_user_penalties(user_id, penalties)
    
    if NEGATIVE_MARKING_ENABLED:
        results_message += "ℹ️ Negative marking was applied to incorrect answers.\n"
        results_message += "Use /stats to see your overall statistics.\n"
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=results_message
    )
    
    # Clean up quiz data
    if chat_id in context.chat_data:
        del context.chat_data[chat_id]

# Poll to Question conversion
async def poll_to_question(update: Update, context: CallbackContext) -> None:
    """Convert a Telegram poll to a quiz question."""
    await update.message.reply_text(
        "🔄 Poll to Quiz Question Converter\n\n"
        "Forward me a poll message, and I'll convert it to a quiz question.\n"
        "The poll should have options and a correct answer marked."
    )

async def handle_forwarded_poll(update: Update, context: CallbackContext) -> None:
    """Handle a forwarded poll message."""
    # Check if the message contains a poll
    if not update.message.forward_from_chat or not update.message.poll:
        return
    
    poll = update.message.poll
    
    # Check if it's a quiz poll with correct answer
    if poll.type != "quiz" or poll.correct_option_id is None:
        await update.message.reply_text(
            "❌ This is not a quiz poll. Please forward a quiz poll with a correct answer marked."
        )
        return
    
    # Create question data
    poll_data = {
        "question": poll.question,
        "options": [option.text for option in poll.options],
        "answer": poll.correct_option_id,
        "category": "General Knowledge"  # Default category
    }
    
    # Store in context
    context.user_data["poll_data"] = poll_data
    
    # Ask for correct answer confirmation
    options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(poll_data["options"])])
    correct_option = poll_data["options"][poll_data["answer"]]
    
    keyboard = [
        [
            InlineKeyboardButton("✓ Correct", callback_data="poll_answer_confirm"),
            InlineKeyboardButton("✗ Change", callback_data="poll_answer_change")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📝 Poll Question: {poll_data['question']}\n\n"
        f"Options:\n{options_text}\n\n"
        f"Correct Answer: {poll_data['answer']+1}. {correct_option}\n\n"
        f"Is this information correct?",
        reply_markup=reply_markup
    )

async def handle_poll_answer(update: Update, context: CallbackContext) -> None:
    """Handle selection of correct answer for poll conversion."""
    query = update.callback_query
    await query.answer()
    
    poll_data = context.user_data.get("poll_data", {})
    
    if not poll_data:
        await query.edit_message_text("❌ No poll data found. Please start over.")
        return
    
    if query.data == "poll_answer_confirm":
        # Ask for ID selection method
        keyboard = [
            [
                InlineKeyboardButton("Auto-generate ID", callback_data="pollid_auto"),
                InlineKeyboardButton("Enter custom ID", callback_data="pollid_custom")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "How would you like to assign an ID to this question?",
            reply_markup=reply_markup
        )
    
    elif query.data == "poll_answer_change":
        # Show options for selecting correct answer
        keyboard = []
        row = []
        
        for i, option in enumerate(poll_data.get("options", [])):
            # Create buttons in rows of 2
            row.append(InlineKeyboardButton(f"{i+1}", callback_data=f"poll_answer_{i}"))
            
            if len(row) == 2 or i == len(poll_data.get("options", [])) - 1:
                keyboard.append(row)
                row = []
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📝 Question: {poll_data.get('question', '')}\n\n"
            f"Select the correct answer:",
            reply_markup=reply_markup
        )
    
    elif query.data.startswith("poll_answer_"):
        # Set the selected answer as correct
        answer_idx = int(query.data.replace("poll_answer_", ""))
        
        if 0 <= answer_idx < len(poll_data.get("options", [])):
            poll_data["answer"] = answer_idx
            context.user_data["poll_data"] = poll_data
            
            # Ask for ID selection method
            keyboard = [
                [
                    InlineKeyboardButton("Auto-generate ID", callback_data="pollid_auto"),
                    InlineKeyboardButton("Enter custom ID", callback_data="pollid_custom")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"✅ Correct answer set to: {answer_idx+1}. {poll_data['options'][answer_idx]}\n\n"
                f"How would you like to assign an ID to this question?",
                reply_markup=reply_markup
            )

async def handle_poll_id_selection(update: Update, context: CallbackContext) -> None:
    """Handle ID method selection for poll conversion."""
    query = update.callback_query
    await query.answer()
    
    poll_data = context.user_data.get("poll_data", {})
    
    if not poll_data:
        await query.edit_message_text("❌ No poll data found. Please start over.")
        return
    
    if query.data == "pollid_auto":
        # Auto-generate ID
        question_id = get_next_question_id()
        context.user_data["poll_question_id"] = question_id
        
        # Show category selection
        keyboard = [
            [
                InlineKeyboardButton("General Knowledge", callback_data="pollcat_General Knowledge"),
                InlineKeyboardButton("Science", callback_data="pollcat_Science")
            ],
            [
                InlineKeyboardButton("History", callback_data="pollcat_History"),
                InlineKeyboardButton("Geography", callback_data="pollcat_Geography")
            ],
            [
                InlineKeyboardButton("Entertainment", callback_data="pollcat_Entertainment"),
                InlineKeyboardButton("Sports", callback_data="pollcat_Sports")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"Question ID: {question_id} (auto-generated)\n\n"
            f"Please select a category for this question:",
            reply_markup=reply_markup
        )
    
    elif query.data == "pollid_custom":
        # Ask for custom ID
        await query.edit_message_text(
            "Please enter a custom ID number for this question:"
        )
        context.user_data["awaiting_poll_id"] = True

async def handle_poll_custom_id(update: Update, context: CallbackContext) -> None:
    """Handle custom ID input for poll conversion."""
    try:
        question_id = int(update.message.text.strip())
        
        if question_id <= 0:
            await update.message.reply_text(
                "Please enter a positive number for the question ID."
            )
            return
        
        context.user_data["poll_question_id"] = question_id
        context.user_data["awaiting_poll_id"] = False
        
        # Show category selection
        keyboard = [
            [
                InlineKeyboardButton("General Knowledge", callback_data="pollcat_General Knowledge"),
                InlineKeyboardButton("Science", callback_data="pollcat_Science")
            ],
            [
                InlineKeyboardButton("History", callback_data="pollcat_History"),
                InlineKeyboardButton("Geography", callback_data="pollcat_Geography")
            ],
            [
                InlineKeyboardButton("Entertainment", callback_data="pollcat_Entertainment"),
                InlineKeyboardButton("Sports", callback_data="pollcat_Sports")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"Question ID: {question_id}\n\n"
            f"Please select a category for this question:",
            reply_markup=reply_markup
        )
        
    except ValueError:
        await update.message.reply_text(
            "Please enter a valid number for the question ID."
        )

async def handle_poll_category(update: Update, context: CallbackContext) -> None:
    """Handle category selection for poll conversion."""
    query = update.callback_query
    await query.answer()
    
    # Extract category from callback data
    category = query.data.replace("pollcat_", "")
    
    poll_data = context.user_data.get("poll_data", {})
    question_id = context.user_data.get("poll_question_id")
    
    if not poll_data or question_id is None:
        await query.edit_message_text("❌ No poll data found. Please start over.")
        return
    
    # Update category
    poll_data["category"] = category
    
    # Add the question
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
        f"Correct answer: {poll_data['answer']+1}. {poll_data['options'][poll_data['answer']]}"
    )

def main() -> None:
    """Start the bot."""
    # Create the updater using the bot token
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # Basic command handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("quiz", quiz_command))
    dispatcher.add_handler(CommandHandler("stats", stats_command))  # This calls extended_stats_command
    dispatcher.add_handler(CommandHandler("delete", delete_command))
    
    # NEGATIVE MARKING ADDITION: Add new command handlers
    dispatcher.add_handler(CommandHandler("negmark", negative_marking_settings))
    dispatcher.add_handler(CommandHandler("resetpenalty", reset_user_penalty_command))
    dispatcher.add_handler(CallbackQueryHandler(negative_settings_callback, pattern=r"^neg_mark_"))
    
    # URL to Question command and handlers
    url_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("url2q", start_url_extraction)],
        states={
            URL_INPUT: [MessageHandler(Filters.text & ~Filters.command, process_url)],
            URL_CONFIRMATION: [CallbackQueryHandler(confirm_questions, pattern=r'^url_')],
            CATEGORY_SELECTION: [CallbackQueryHandler(select_category, pattern=r'^url_category_')]
        },
        fallbacks=[CommandHandler("cancel", url_extraction_cancel)]
    )
    dispatcher.add_handler(url_conv_handler)
    
    # Poll to question command and handlers
    dispatcher.add_handler(CommandHandler("poll2q", poll_to_question))
    dispatcher.add_handler(MessageHandler(
        Filters.forwarded & ~Filters.command, 
        handle_forwarded_poll
    ))
    dispatcher.add_handler(CallbackQueryHandler(handle_poll_answer, pattern=r"^poll_answer_"))
    dispatcher.add_handler(CallbackQueryHandler(handle_poll_id_selection, pattern=r"^pollid_"))
    dispatcher.add_handler(CallbackQueryHandler(handle_poll_category, pattern=r"^pollcat_"))
    
    # Custom ID message handler for poll
    dispatcher.add_handler(MessageHandler(
        Filters.text & ~Filters.command,
        handle_poll_custom_id,
        lambda update, context: context.user_data.get("awaiting_poll_id", False)
    ))
    
    # Add question conversation handler
    add_question_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_question_start)],
        states={
            QUESTION: [MessageHandler(Filters.text & ~Filters.command, add_question_text)],
            OPTIONS: [MessageHandler(Filters.text & ~Filters.command, add_question_options)],
            ANSWER: [MessageHandler(Filters.text & ~Filters.command, add_question_answer)],
            CUSTOM_ID: [
                CallbackQueryHandler(custom_id_callback, pattern=r"^(auto_id|custom_id)$"),
                MessageHandler(Filters.text & ~Filters.command, custom_id_input, 
                    lambda update, context: context.user_data.get("awaiting_custom_id", False)
                )
            ],
            CATEGORY: [CallbackQueryHandler(category_callback, pattern=r"^category_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    dispatcher.add_handler(add_question_handler)
    
    # Add PDF2Q conversation handler
    pdf_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("pdf2q", pdf_to_question_command)],
        states={
            PDF_UPLOAD: [MessageHandler(Filters.document.pdf, handle_pdf_file)],
            PDF_PROCESSING: [CallbackQueryHandler(process_pdf_questions, pattern=r'^pdf_')],
            PDF_CATEGORY_SELECTION: [CallbackQueryHandler(select_pdf_category, pattern=r'^pdf_category_')]
        },
        fallbacks=[CommandHandler("cancel", cancel_pdf_import)]
    )
    dispatcher.add_handler(pdf_conv_handler)
    
    # Poll Answer Handler - CRITICAL for tracking all participants
    dispatcher.add_handler(PollAnswerHandler(poll_answer))
    
    # Start the Bot
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
