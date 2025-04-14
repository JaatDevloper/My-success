"""
Telegram Quiz Bot with negative marking functionality and PDF question import capability
Based on the original multi_id_quiz_bot.py but with added features for negative marking
and support for importing questions from PDF files with multilingual support (English and Hindi)
"""

import json
import logging
import os
import random
import asyncio
import io
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler, PollAnswerHandler
import pdfplumber
import langdetect

# Try importing OCR libraries - they are optional but provide better PDF extraction
try:
    import pytesseract
    from pdf2image import convert_from_bytes
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

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
CUSTOM_ID = range(9, 10)
WAITING_FOR_PDF = range(10, 11)  # PDF import conversation state
PDF_ID_CHOICE = range(11, 12)  # Choose ID method for PDF import
PDF_CUSTOM_ID = range(12, 13)  # Enter custom ID for PDF import

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
    """Add a question with a specific ID, directly replacing any existing question"""
    questions = load_questions()
    str_id = str(question_id)
    
    # Directly assign the question data to the ID (no lists)
    questions[str_id] = question_data
    
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

# ---------- PDF IMPORT FUNCTIONALITY ----------
def detect_pdf_language(text):
    """Detect if the text is Hindi or English"""
    try:
        lang = langdetect.detect(text)
        return "hi" if lang == "hi" else "en"
    except:
        # Default to English if detection fails
        return "en"

def extract_text_from_pdf(pdf_file):
    """Extract text from PDF file with proper encoding for multilingual support"""
    text = ""
    
    try:
        # Try extracting with pdfplumber first
        with pdfplumber.open(pdf_file) as pdf:
            logger.info(f"PDF has {len(pdf.pages)} pages")
            for page_num, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n\n"
                    logger.info(f"Extracted text from page {page_num+1} using pdfplumber")
                else:
                    logger.info(f"No text extracted from page {page_num+1} using pdfplumber")
        
        # If text is minimal or empty and OCR is available, try OCR
        if (not text.strip() or len(text) < 100) and OCR_AVAILABLE:
            logger.info("Text extraction with pdfplumber insufficient, trying OCR...")
            pdf_file.seek(0)  # Reset file position
            
            try:
                # Convert PDF to images
                images = convert_from_bytes(pdf_file.read())
                logger.info(f"Converted PDF to {len(images)} images for OCR")
                
                # Extract text from images using OCR
                for i, image in enumerate(images):
                    # Try with English+Hindi if available, fallback to English
                    try:
                        page_text = pytesseract.image_to_string(image, lang='eng+hin')
                        logger.info(f"OCR processed page {i+1} with eng+hin")
                    except:
                        page_text = pytesseract.image_to_string(image, lang='eng')
                        logger.info(f"OCR processed page {i+1} with eng only")
                    
                    text += page_text + "\n\n"
            except Exception as ocr_error:
                logger.error(f"OCR error: {ocr_error}")
                # If OCR fails but we have some text from pdfplumber, use that
                if not text.strip():
                    logger.error("Both text extraction methods failed")
        
        # Log a preview of the extracted text
        text_preview = text[:200].replace('\n', ' ')
        logger.info(f"Extracted text preview: {text_preview}...")
        
        # Check if the text seems to contain questions
        has_questions = bool(re.search(r'\d+[\.\)]', text))
        has_options = bool(re.search(r'[A-D][\.\)]', text))
        
        logger.info(f"Text analysis - Has question numbering: {has_questions}, Has options: {has_options}")
        
        if not has_questions and not has_options:
            logger.warning("The extracted text doesn't appear to contain quiz questions in the expected format")
    
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
    
    return text

def parse_pdf_questions(pdf_text):
    """Parse questions from PDF text with support for English and Hindi"""
    # Detect language
    language = detect_pdf_language(pdf_text)
    logger.info(f"Detected language: {language}")
    
    questions = []
    
    # Log the first part of the text for debugging
    text_preview = pdf_text[:500].replace('\n', ' ')
    logger.info(f"PDF text preview: {text_preview}...")
    
    # First attempt: Find all question blocks using a more reliable pattern
    question_blocks = re.findall(r'(\d+[\.\)]\s*[^\n]+(?:\n[^\d\n][^\n]*)*)', pdf_text)
    logger.info(f"Found {len(question_blocks)} potential question blocks")
    
    for block in question_blocks:
        # Extract question text
        question_match = re.match(r'\d+[\.\)]\s*([^\n]+)', block)
        if not question_match:
            continue
            
        question_text = question_match.group(1).strip()
        logger.info(f"Processing question: {question_text[:50]}...")
        
        # Extract options - try with letter labels first
        options = []
        if language == 'hi':
            # Hindi options
            option_patterns = [
                r'[अ][\.\)]\s*([^\n]+)',
                r'[आ][\.\)]\s*([^\n]+)',
                r'[इ][\.\)]\s*([^\n]+)',
                r'[ई][\.\)]\s*([^\n]+)'
            ]
            answer_pattern = r'(?:उत्तर|उत्तर:|उत्तर\s*:|समाधान|समाधान:|समाधान\s*:)\s*([अआइईउऊएओ1234])'
            
            for pattern in option_patterns:
                option_match = re.search(pattern, block)
                if option_match:
                    options.append(option_match.group(1).strip())
        else:
            # English options with letter labels
            letter_options = re.findall(r'([A-D][\.\)]\s*[^\n]+)', block)
            
            # If letter options not found, try with number labels
            if not letter_options or len(letter_options) < 2:
                letter_options = re.findall(r'(\d[\.\)]\s*[^\n]+)', block)
            
            # Clean up the option text
            for opt in letter_options:
                # Extract the option letter/number for later use in answer mapping
                opt_label = opt[0].upper()
                
                # Remove option identifier (A., B., etc)
                option_text = re.sub(r'^[A-D\d][\.\)]\s*', '', opt).strip()
                options.append(option_text)
        
        # Extract answer
        answer = None
        if language == 'hi':
            answer_match = re.search(r'(?:उत्तर|उत्तर:|उत्तर\s*:|समाधान|समाधान:|समाधान\s*:)\s*([अआइईउऊएओ1234])', block)
            if answer_match:
                answer_text = answer_match.group(1).upper()
                answer_map = {"अ": 0, "आ": 1, "इ": 2, "ई": 3, "1": 0, "2": 1, "3": 2, "4": 3}
                answer = answer_map.get(answer_text, 0)
        else:
            # Try various answer patterns
            answer_match = re.search(r'(?:answer|answer:|ans|ans:|correct answer|correct answer:|correct|correct:)\s*([a-dA-D1-4])', block, re.IGNORECASE)
            
            if answer_match:
                answer_text = answer_match.group(1).upper()
                answer_map = {"A": 0, "B": 1, "C": 2, "D": 3, "1": 0, "2": 1, "3": 2, "4": 3}
                answer = answer_map.get(answer_text, 0)
            else:
                # Try to find "Correct: X" pattern
                for letter_idx, letter in enumerate(['A', 'B', 'C', 'D']):
                    if re.search(fr'\b[Cc]orrect\s*[\:\-\s]\s*{letter}\b', block):
                        answer = letter_idx
                        break
        
        # Default to first option if answer not found
        if answer is None and options:
            logger.info(f"No answer found for question '{question_text[:30]}...', defaulting to first option")
            answer = 0
        
        # Only add if we have a question and at least 2 options
        if question_text and len(options) >= 2:
            questions.append({
                "question": question_text,
                "options": options,
                "answer": answer if answer is not None else 0,
                "language": language
            })
    
    # If first method didn't work, try alternative approach for PDFs with different layouts
    if not questions:
        logger.info("Trying alternative question extraction method...")
        
        # For English PDFs
        if language != 'hi':
            # Look for questions with numbers and question marks
            q_matches = re.finditer(r'\d+[\.\)]\s*([^\n]+\?)', pdf_text)
            
            for q_match in q_matches:
                question_text = q_match.group(1).strip()
                question_pos = q_match.start()
                
                # Get surrounding text (next 300 chars)
                context = pdf_text[question_pos:question_pos + 300]
                
                # Find options (looking for A. B. C. D. pattern)
                option_matches = re.findall(r'[A-D][\.\)]\s*([^\n]+)', context)
                
                if len(option_matches) >= 2:
                    options = [opt.strip() for opt in option_matches[:4]]
                    
                    # Look for answer
                    answer = 0  # Default
                    answer_match = re.search(r'(?:answer|ans|correct)[\:\s]+([A-D])', context, re.IGNORECASE)
                    if answer_match:
                        ans = answer_match.group(1).upper()
                        answer = ord(ans) - ord('A')  # Convert A->0, B->1, etc.
                    
                    questions.append({
                        "question": question_text,
                        "options": options,
                        "answer": answer,
                        "language": language
                    })
        
        # For Hindi PDFs - similar approach with Hindi characters
        else:
            # Special processing for Hindi PDFs could be added here
            pass
    
    logger.info(f"Total questions extracted: {len(questions)}")
    return questions

def format_questions_for_bot(questions):
    """Format parsed questions to match the bot's question format"""
    formatted_questions = []
    
    for q in questions:
        # Generate a category based on language
        category = "Hindi Questions" if q.get("language") == "hi" else "General Knowledge"
        
        formatted_question = {
            "question": q["question"],
            "options": q["options"],
            "answer": q["answer"],
            "category": category
        }
        formatted_questions.append(formatted_question)
    
    return formatted_questions

def extract_and_save_pdf_questions(pdf_data, custom_id_start=None):
    """
    Extract questions from PDF and save them to the questions file
    
    Args:
        pdf_data: The binary PDF data
        custom_id_start: Optional starting ID for the questions (if None, auto-generate IDs)
    """
    try:
        # Create BytesIO object from PDF data
        pdf_file = io.BytesIO(pdf_data)
        
        # Extract text from PDF
        pdf_text = extract_text_from_pdf(pdf_file)
        
        # Parse questions from text
        parsed_questions = parse_pdf_questions(pdf_text)
        
        # Format questions for the bot
        formatted_questions = format_questions_for_bot(parsed_questions)
        
        # Add questions to the database
        questions_added = 0
        for i, question in enumerate(formatted_questions):
            if custom_id_start is not None:
                # Use custom ID sequence
                question_id = custom_id_start + i
            else:
                # Get next available ID
                question_id = get_next_question_id()
                
            add_question_with_id(question_id, question)
            questions_added += 1
        
        # If using custom IDs, log the range
        id_range_info = ""
        if custom_id_start is not None and questions_added > 0:
            id_range_info = f" (IDs {custom_id_start} to {custom_id_start + questions_added - 1})"
        
        return {
            "success": True,
            "questions_added": questions_added,
            "id_start": custom_id_start if custom_id_start is not None else None,
            "id_end": (custom_id_start + questions_added - 1) if custom_id_start is not None and questions_added > 0 else None,
            "message": f"Successfully imported {questions_added} questions{id_range_info} from the PDF."
        }
    
    except Exception as e:
        logger.error(f"Error extracting questions from PDF: {e}")
        return {
            "success": False,
            "questions_added": 0,
            "message": f"Error importing questions: {str(e)}"
        }

async def import_pdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for the /importpdf command - initiates PDF import flow"""
    # Ask user if they want to use a custom ID range
    keyboard = [
        [InlineKeyboardButton("Auto-generate IDs", callback_data="pdf_auto_id")],
        [InlineKeyboardButton("Specify custom ID", callback_data="pdf_custom_id")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📄 How would you like to assign IDs to the imported questions?",
        reply_markup=reply_markup
    )
    return PDF_ID_CHOICE

async def pdf_id_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the ID choice for PDF import"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "pdf_auto_id":
        # Auto-generate IDs
        context.user_data["pdf_import"] = {"custom_id": None}
        await query.edit_message_text(
            "📄 Please send me a PDF file containing quiz questions. "
            "I'll extract the questions and add them to the quiz database with auto-generated IDs.\n\n"
            "The PDF should contain numbered questions with lettered options (A, B, C, D) "
            "and marked answers. I support both English and Hindi questions.\n\n"
            "Send /cancel to cancel the import process."
        )
        return WAITING_FOR_PDF
    
    elif query.data == "pdf_custom_id":
        # Ask for custom starting ID
        await query.edit_message_text(
            "Please enter the starting ID number for the imported questions:"
        )
        return PDF_CUSTOM_ID
    
    return ConversationHandler.END

async def pdf_custom_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom starting ID input for PDF import"""
    try:
        starting_id = int(update.message.text)
        if starting_id < 0:
            await update.message.reply_text("ID must be a positive number. Please try again:")
            return PDF_CUSTOM_ID
        
        context.user_data["pdf_import"] = {"custom_id": starting_id}
        
        await update.message.reply_text(
            f"📄 Questions will be imported starting from ID {starting_id}.\n\n"
            "Please send me a PDF file containing quiz questions.\n\n"
            "The PDF should contain numbered questions with lettered options (A, B, C, D) "
            "and marked answers. I support both English and Hindi questions.\n\n"
            "Send /cancel to cancel the import process."
        )
        return WAITING_FOR_PDF
    
    except ValueError:
        await update.message.reply_text("Please enter a valid number for the starting ID:")
        return PDF_CUSTOM_ID

async def pdf_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle PDF file reception"""
    # Check if this is a PDF file
    if not update.message.document or (update.message.document and not update.message.document.file_name.lower().endswith('.pdf')):
        await update.message.reply_text(
            "❌ That's not a PDF file. Please send a PDF file or /cancel to exit."
        )
        return WAITING_FOR_PDF
    
    # Get file from Telegram
    file = await context.bot.get_file(update.message.document.file_id)
    
    # Download file content
    pdf_data = await file.download_as_bytearray()
    
    # Show processing message
    await update.message.reply_text("🔄 Processing PDF, please wait...")
    
    # Get custom ID if set
    custom_id = None
    if "pdf_import" in context.user_data and "custom_id" in context.user_data["pdf_import"]:
        custom_id = context.user_data["pdf_import"]["custom_id"]
    
    # Extract and save questions
    result = extract_and_save_pdf_questions(pdf_data, custom_id)
    
    if result["success"]:
        id_info = ""
        if result["id_start"] is not None:
            id_info = f"\nQuestions were assigned IDs from {result['id_start']} to {result['id_end']}."
            
        await update.message.reply_text(
            f"✅ {result['message']}\n{id_info}\n\n"
            f"You can now start a quiz with /quiz to see the imported questions."
        )
    else:
        await update.message.reply_text(
            f"❌ {result['message']}\n\n"
            "Please check the PDF format and try again, or send a different PDF file."
        )
    
    # Clear PDF import data
    if "pdf_import" in context.user_data:
        del context.user_data["pdf_import"]
    
    return ConversationHandler.END

async def cancel_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the PDF import process"""
    await update.message.reply_text(
        "PDF import cancelled. Use /importpdf to start again."
    )
    return ConversationHandler.END
# ---------- END PDF IMPORT FUNCTIONALITY ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the command /start is issued."""
    user = update.effective_user
    welcome_text = (
        f"👋 Hello, {user.first_name}!\n\n"
        "Welcome to the Quiz Bot with Negative Marking. Here's what you can do:\n\n"
        "💡 /quiz - Start a new quiz (auto-sequence)\n"
        "🛑 /stopquiz - Stop an ongoing quiz\n"
        "📊 /stats - View your quiz statistics with penalties\n"
        "➕ /add - Add a new question to the quiz bank\n"
        "✏️ /edit - Edit an existing question\n"
        "❌ /delete - Delete a question\n"
        "🔄 /poll2q - Convert a Telegram poll to a quiz question\n"
        "📄 /importpdf - Import questions from a PDF file\n"
        "⚙️ /negmark - Configure negative marking settings\n"
        "🧹 /resetpenalty - Reset your penalties\n"
        "ℹ️ /help - Show this help message\n\n"
        "Let's test your knowledge with some fun quizzes!"
    )
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help message."""
    user = update.effective_user
    help_text = (
        f"👋 Hello, {user.first_name}!\n\n"
        "Welcome to the Quiz Bot with Negative Marking. Here's what you can do:\n\n"
        "💡 /quiz - Start a new quiz (auto-sequence)\n"
        "🛑 /stopquiz - Stop an ongoing quiz\n"
        "📊 /stats - View your quiz statistics with penalties\n"
        "➕ /add - Add a new question to the quiz bank\n"
        "✏️ /edit - Edit an existing question\n"
        "❌ /delete - Delete a question\n"
        "🔄 /poll2q - Convert a Telegram poll to a quiz question\n"
        "📄 /importpdf - Import questions from a PDF file (with custom IDs)\n"
        "⚙️ /negmark - Configure negative marking settings\n"
        "🧹 /resetpenalty - Reset your penalties\n"
        "ℹ️ /help - Show this help message\n\n"
        "Let's test your knowledge with some fun quizzes!"
    )
    await update.message.reply_text(help_text)

# ---------- NEGATIVE MARKING COMMAND ADDITIONS ----------
async def extended_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

async def negative_marking_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

async def negative_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        # Exit settings
        await query.edit_message_text("Settings closed. Use /negmark to access settings again.")

async def reset_user_penalty_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset penalties for a specific user."""
    args = context.args
    
    if args and len(args) > 0:
        try:
            user_id = int(args[0])
            reset_user_penalties(user_id)
            await update.message.reply_text(f"✅ Penalties for user ID {user_id} have been reset.")
        except ValueError:
            await update.message.reply_text("❌ Please provide a valid numeric user ID.")
    else:
        # Reset current user's penalties
        user_id = update.effective_user.id
        reset_user_penalties(user_id)
        await update.message.reply_text("✅ Your penalties have been reset.")
# ---------- END NEGATIVE MARKING COMMAND ADDITIONS ----------

# Original function (unchanged)
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display user statistics."""
    # Call the extended stats command instead to show penalties
    await extended_stats_command(update, context)

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
        # Auto-generate ID
        question_id = get_next_question_id()
        context.user_data["new_question"]["id"] = question_id
        
        # Ask for category
        keyboard = [
            [InlineKeyboardButton("General Knowledge", callback_data="cat_general")],
            [InlineKeyboardButton("Science", callback_data="cat_science")],
            [InlineKeyboardButton("History", callback_data="cat_history")],
            [InlineKeyboardButton("Geography", callback_data="cat_geography")],
            [InlineKeyboardButton("Entertainment", callback_data="cat_entertainment")],
            [InlineKeyboardButton("Sports", callback_data="cat_sports")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Please select a category for this question:",
            reply_markup=reply_markup
        )
        return CATEGORY
    elif query.data == "custom_id":
        await query.edit_message_text(
            "Please enter a custom ID number for this question:"
        )
        return CUSTOM_ID

async def custom_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom ID input."""
    try:
        question_id = int(update.message.text)
        context.user_data["new_question"]["id"] = question_id
        
        # Ask for category
        keyboard = [
            [InlineKeyboardButton("General Knowledge", callback_data="cat_general")],
            [InlineKeyboardButton("Science", callback_data="cat_science")],
            [InlineKeyboardButton("History", callback_data="cat_history")],
            [InlineKeyboardButton("Geography", callback_data="cat_geography")],
            [InlineKeyboardButton("Entertainment", callback_data="cat_entertainment")],
            [InlineKeyboardButton("Sports", callback_data="cat_sports")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Please select a category for this question:",
            reply_markup=reply_markup
        )
        return CATEGORY
    except ValueError:
        await update.message.reply_text(
            "Please enter a valid number for the ID."
        )
        return CUSTOM_ID

async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle category selection."""
    query = update.callback_query
    await query.answer()
    
    # Map callback data to category names
    categories = {
        "cat_general": "General Knowledge",
        "cat_science": "Science",
        "cat_history": "History",
        "cat_geography": "Geography",
        "cat_entertainment": "Entertainment",
        "cat_sports": "Sports"
    }
    
    selected_category = categories.get(query.data, "General Knowledge")
    new_question = context.user_data["new_question"]
    new_question["category"] = selected_category
    
    # Save the question
    question_id = new_question.get("id", get_next_question_id())
    question_data = {
        "question": new_question["question"],
        "options": new_question["options"],
        "answer": new_question["answer"],
        "category": new_question["category"]
    }
    
    add_question_with_id(question_id, question_data)
    
    await query.edit_message_text(
        f"✅ Question added successfully with ID: {question_id}\n\n"
        f"Question: {new_question['question']}\n"
        f"Category: {new_question['category']}"
    )
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current operation."""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a question by ID."""
    try:
        if not context.args or len(context.args) == 0:
            await update.message.reply_text(
                "Please provide a question ID to delete.\n"
                "Example: /delete 5"
            )
            return
            
        question_id = int(context.args[0])
        if delete_question_by_id(question_id):
            await update.message.reply_text(f"Question {question_id} deleted successfully.")
        else:
            await update.message.reply_text(f"Question {question_id} not found.")
    except ValueError:
        await update.message.reply_text("Please provide a valid question ID number.")

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a quiz session with random questions."""
    try:
        # Check if a quiz is already running in this chat
        if context.chat_data.get("quiz_running", False):
            await update.message.reply_text(
                "⚠️ A quiz is already running in this chat. "
                "Use /stopquiz to stop the current quiz before starting a new one."
            )
            return
            
        questions = load_questions()
        
        if not questions:
            await update.message.reply_text(
                "There are no questions in the database yet. Use /add to add some!"
            )
            return
        
        # Extract all questions from all IDs
        all_questions = []
        for q_id, q_list in questions.items():
            if isinstance(q_list, list):
                all_questions.extend(q_list)
            else:
                all_questions.append(q_list)
        
        # Randomize the order
        random.shuffle(all_questions)
        
        # Limit to 5 questions
        quiz_questions = all_questions[:5]
        
        # Save the questions to context
        context.chat_data["quiz_questions"] = quiz_questions
        context.chat_data["current_question"] = 0
        context.chat_data["participants"] = {}
        context.chat_data["quiz_running"] = True
        context.chat_data["quiz_tasks"] = []  # To track scheduled tasks
        
        # Start the quiz
        await update.message.reply_text(
            "🎮 Starting a new quiz session! 5 questions will be sent, one every 15 seconds."
        )
        
        # Send the first question
        await send_question(context, update.effective_chat.id, 0)
        
    except Exception as e:
        logger.error(f"Error starting quiz: {e}")
        await update.message.reply_text(f"Error starting quiz: {str(e)}")

async def send_question(context, chat_id, question_index):
    """Send a quiz question and schedule next one."""
    try:
        quiz_questions = context.chat_data["quiz_questions"]
        
        if question_index >= len(quiz_questions):
            # End of quiz
            await schedule_end_quiz(context, chat_id)
            return
        
        question = quiz_questions[question_index]
        options = question["options"]
        correct_option_id = question["answer"]
        
        # Send as a poll
        message = await context.bot.send_poll(
            chat_id,
            question["question"],
            options,
            type="quiz",
            correct_option_id=correct_option_id,
            is_anonymous=False,
            open_period=12,  # 12 seconds to answer
        )
        
        # Save the poll ID for this question
        quiz_questions[question_index]["poll_id"] = message.poll.id
        quiz_questions[question_index]["poll_message_id"] = message.message_id
        
        # Schedule next question
        await schedule_next_question(context, chat_id, question_index + 1)
        
    except Exception as e:
        logger.error(f"Error sending quiz question: {e}")
        await context.bot.send_message(chat_id, f"Error sending question: {str(e)}")

async def schedule_next_question(context, chat_id, next_index):
    """Schedule the next question with delay."""
    # Wait for the current poll to close (12 seconds) + some buffer
    await asyncio.sleep(15)
    await send_question(context, chat_id, next_index)

async def schedule_end_quiz(context, chat_id):
    """Schedule end of quiz with delay."""
    # Wait for the last question to finish
    await asyncio.sleep(15)
    await end_quiz(context, chat_id)

async def poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle poll answers from users with negative marking."""
    try:
        # Get answer data
        answer = update.poll_answer
        poll_id = answer.poll_id
        user_id = answer.user.id
        selected_option = answer.option_ids[0] if answer.option_ids else None
        
        # Initialize participants dict if it doesn't exist
        if "participants" not in context.chat_data:
            context.chat_data["participants"] = {}
            
        # Initialize participant data if not exists
        if user_id not in context.chat_data["participants"]:
            context.chat_data["participants"][user_id] = {
                "name": answer.user.first_name,
                "correct": 0,
                "incorrect": 0,
                "total": 0,
                "penalties": 0
            }
        
        # Find which question this poll belongs to
        quiz_questions = context.chat_data.get("quiz_questions", [])
        question = None
        for q in quiz_questions:
            if q.get("poll_id") == poll_id:
                question = q
                break
        
        if not question:
            return
        
        # Record the answer
        correct_option = question["answer"]
        is_correct = selected_option == correct_option
        participant = context.chat_data["participants"][user_id]
        
        if is_correct:
            participant["correct"] += 1
        else:
            participant["incorrect"] += 1
            # Apply negative marking penalty
            category = question.get("category", "General Knowledge")
            penalty = get_penalty_for_category(category)
            participant["penalties"] += penalty
            
            # Also update user's permanent penalties
            if NEGATIVE_MARKING_ENABLED:
                apply_penalty(user_id, category)
        
        participant["total"] += 1
        
        # Update user stats in permanent storage
        user_data = get_user_data(user_id)
        user_data["total_answers"] = user_data.get("total_answers", 0) + 1
        if is_correct:
            user_data["correct_answers"] = user_data.get("correct_answers", 0) + 1
        save_user_data(user_id, user_data)
        
    except Exception as e:
        logger.error(f"Error handling poll answer: {e}")

async def end_quiz(context, chat_id, forced=False):
    """End the quiz and display results with all participants and penalties."""
    try:
        # Initialize participants dict if it doesn't exist
        if "participants" not in context.chat_data:
            context.chat_data["participants"] = {}
            
        participants = context.chat_data.get("participants", {})
        
        # Mark the quiz as no longer running
        context.chat_data["quiz_running"] = False
        
        message_prefix = "📊 Quiz ended! " 
        if forced:
            message_prefix = "🛑 Quiz stopped manually! "
            
        # Even if no real participants, we create a dummy participant 
        # to ensure results are shown and to troubleshoot the issue
        if not participants:
            logger.info("No participants detected in the quiz")
            
            # Create a debug message but don't return yet - continue to show results
            debug_msg = f"{message_prefix}No participants were detected in this quiz session. "
            await context.bot.send_message(chat_id, debug_msg)
        
        # Sort participants by score (correct answers adjusted by penalties)
        sorted_participants = sorted(
            participants.items(),
            key=lambda x: (x[1]["correct"] - x[1]["penalties"]),
            reverse=True
        )
        
        # Create results message
        results = f"{message_prefix}Results:\n\n"
        
        for user_id, data in sorted_participants:
            # Calculate the adjusted score with penalties
            raw_score = data["correct"]
            penalties = data["penalties"]
            adjusted_score = max(0, raw_score - penalties)
            
            results += (
                f"👤 {data['name']}\n"
                f"✅ Correct: {data['correct']}\n"
                f"❌ Incorrect: {data['incorrect']}\n"
            )
            
            # Only show penalties if negative marking is enabled
            if NEGATIVE_MARKING_ENABLED and penalties > 0:
                results += f"⚠️ Penalties: {penalties:.2f}\n"
                results += f"🏆 Final Score: {adjusted_score:.2f}\n"
            else:
                results += f"🏆 Score: {raw_score}\n"
                
            results += "\n"
        
        negative_marking_status = "enabled" if NEGATIVE_MARKING_ENABLED else "disabled"
        results += f"Note: Negative marking is {negative_marking_status}."
        
        await context.bot.send_message(chat_id, results)
        
    except Exception as e:
        logger.error(f"Error ending quiz: {e}")
        await context.bot.send_message(chat_id, f"Error displaying quiz results: {str(e)}")

async def stop_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stop a running quiz immediately."""
    try:
        if not context.chat_data.get("quiz_running", False):
            await update.message.reply_text(
                "⚠️ There's no quiz currently running in this chat."
            )
            return
        
        # Force end the quiz
        await end_quiz(context, update.effective_chat.id, forced=True)
        
        await update.message.reply_text(
            "Quiz has been stopped. Final results are displayed above."
        )
        
    except Exception as e:
        logger.error(f"Error stopping quiz: {e}")
        await update.message.reply_text(f"Error stopping quiz: {str(e)}")

# Poll to Question Conversion
async def poll_to_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Convert a Telegram poll to a quiz question."""
    await update.message.reply_text(
        "Forward me a poll and I'll convert it to a quiz question.\n"
        "The poll should have the correct answer marked."
    )

async def handle_forwarded_poll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a forwarded poll message."""
    message = update.message
    
    # Check if this is a forwarded poll
    if message.forward_from and message.poll:
        poll = message.poll
        
        if poll.type != "quiz":
            await message.reply_text(
                "This is not a quiz poll. Only quiz polls with a correct answer can be converted."
            )
            return
        
        # Store poll data in user data
        context.user_data["poll_conversion"] = {
            "question": poll.question,
            "options": [option.text for option in poll.options],
            "correct_option_id": poll.correct_option_id
        }
        
        # Format the poll data for display
        options_text = "\n".join([f"{i}. {opt}" for i, opt in enumerate(context.user_data["poll_conversion"]["options"])])
        
        await message.reply_text(
            f"I'll convert this poll to a quiz question:\n\n"
            f"Question: {poll.question}\n\n"
            f"Options:\n{options_text}\n\n"
            f"Correct answer: {poll.correct_option_id}\n\n"
            "Please select how you want to assign an ID to this question:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Auto-generate ID", callback_data="poll_auto_id")],
                [InlineKeyboardButton("Specify custom ID", callback_data="poll_custom_id")]
            ])
        )

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle selection of correct answer for poll conversion."""
    query = update.callback_query
    await query.answer()
    
    # Get options and selection
    poll_data = context.user_data["poll_conversion"]
    answer_idx = int(query.data.split("_")[1])
    poll_data["correct_option_id"] = answer_idx
    
    await query.edit_message_text(
        f"Selected answer: {answer_idx}. {poll_data['options'][answer_idx]}\n\n"
        "Please choose how to assign an ID to this question:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Auto-generate ID", callback_data="poll_auto_id")],
            [InlineKeyboardButton("Specify custom ID", callback_data="poll_custom_id")]
        ])
    )

async def handle_poll_id_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ID method selection for poll conversion."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "poll_auto_id":
        # Auto-generate ID
        question_id = get_next_question_id()
        context.user_data["poll_conversion"]["id"] = question_id
        
        # Ask for category
        await query.edit_message_text(
            f"Using auto-generated ID: {question_id}\n\n"
            "Please select a category for this question:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("General Knowledge", callback_data="poll_cat_general")],
                [InlineKeyboardButton("Science", callback_data="poll_cat_science")],
                [InlineKeyboardButton("History", callback_data="poll_cat_history")],
                [InlineKeyboardButton("Geography", callback_data="poll_cat_geography")],
                [InlineKeyboardButton("Entertainment", callback_data="poll_cat_entertainment")],
                [InlineKeyboardButton("Sports", callback_data="poll_cat_sports")]
            ])
        )
    elif query.data == "poll_custom_id":
        await query.edit_message_text(
            "Please send me the custom ID number for this question:"
        )

async def handle_poll_custom_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle custom ID input for poll conversion."""
    try:
        question_id = int(update.message.text)
        context.user_data["poll_conversion"]["id"] = question_id
        
        # Ask for category
        keyboard = [
            [InlineKeyboardButton("General Knowledge", callback_data="poll_cat_general")],
            [InlineKeyboardButton("Science", callback_data="poll_cat_science")],
            [InlineKeyboardButton("History", callback_data="poll_cat_history")],
            [InlineKeyboardButton("Geography", callback_data="poll_cat_geography")],
            [InlineKeyboardButton("Entertainment", callback_data="poll_cat_entertainment")],
            [InlineKeyboardButton("Sports", callback_data="poll_cat_sports")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"Using custom ID: {question_id}\n\n"
            "Please select a category for this question:",
            reply_markup=reply_markup
        )
    except ValueError:
        await update.message.reply_text(
            "Please enter a valid number for the ID."
        )

async def handle_poll_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle category selection for poll conversion."""
    query = update.callback_query
    await query.answer()
    
    # Map callback data to category names
    categories = {
        "poll_cat_general": "General Knowledge",
        "poll_cat_science": "Science",
        "poll_cat_history": "History",
        "poll_cat_geography": "Geography",
        "poll_cat_entertainment": "Entertainment",
        "poll_cat_sports": "Sports"
    }
    
    selected_category = categories.get(query.data, "General Knowledge")
    poll_data = context.user_data["poll_conversion"]
    
    # Save the question
    question_id = poll_data.get("id", get_next_question_id())
    question_data = {
        "question": poll_data["question"],
        "options": poll_data["options"],
        "answer": poll_data["correct_option_id"],
        "category": selected_category
    }
    
    add_question_with_id(question_id, question_data)
    
    await query.edit_message_text(
        f"✅ Question added successfully with ID: {question_id}\n\n"
        f"Question: {poll_data['question']}\n"
        f"Category: {selected_category}"
    )

def main() -> None:
    """Run the bot."""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Basic commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("stopquiz", stop_quiz_command))
    application.add_handler(CommandHandler("poll2q", poll_to_question))

    # Negative marking commands
    application.add_handler(CommandHandler("extendedstats", extended_stats_command))
    application.add_handler(CommandHandler("negmark", negative_marking_settings))
    application.add_handler(CommandHandler("resetpenalty", reset_user_penalty_command))
    application.add_handler(CallbackQueryHandler(negative_settings_callback, pattern="^neg_mark_"))

    # PDF import handler
    pdf_import_handler = ConversationHandler(
        entry_points=[CommandHandler("importpdf", import_pdf_command)],
        states={
            PDF_ID_CHOICE: [
                CallbackQueryHandler(pdf_id_choice_callback, pattern="^pdf_(auto|custom)_id$")
            ],
            PDF_CUSTOM_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, pdf_custom_id_input),
                CommandHandler("cancel", cancel_import)
            ],
            WAITING_FOR_PDF: [
                MessageHandler(filters.ATTACHMENT, pdf_received),
                CommandHandler("cancel", cancel_import)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_import)]
    )
    application.add_handler(pdf_import_handler)

    # Add question conversation handler
    add_question_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_question_start)],
        states={
            QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_text)],
            OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_options)],
            ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_answer)],
            CUSTOM_ID: [
                CallbackQueryHandler(custom_id_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_id_input)
            ],
            CATEGORY: [CallbackQueryHandler(category_callback)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(add_question_handler)

    # Poll handling
    application.add_handler(MessageHandler(
        filters.FORWARDED & filters.POLL, 
        handle_forwarded_poll
    ))
    application.add_handler(CallbackQueryHandler(handle_poll_answer, pattern="^ans_"))
    application.add_handler(CallbackQueryHandler(handle_poll_id_selection, pattern="^poll_(auto|custom)_id$"))
    application.add_handler(CallbackQueryHandler(handle_poll_category, pattern="^poll_cat_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_poll_custom_id))

    # Poll answer handler
    application.add_handler(PollAnswerHandler(poll_answer))

    # Start the Bot
    application.run_polling()

if __name__ == "__main__":
    main()
