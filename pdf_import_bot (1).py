"""
Telegram Quiz Bot with negative marking and PDF import functionality
Supports Hindi language questions by using OCR
"""

import json
import logging
import os
import random
import asyncio
import re
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# PDF Processing imports
import PyPDF2
from pdf2image import convert_from_path
import pytesseract

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
CUSTOM_ID = range(9, 10)
PDF_RECEIVING, PDF_PROCESSING, PDF_CONFIRM = range(10, 13)

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

# ---------- PDF IMPORT ADDITIONS ----------
async def extract_text_from_pdf(pdf_path: str, hindi_support: bool = True) -> str:
    """Extract text from PDF file - supports Hindi through OCR if needed"""
    text = ""
    try:
        # First try direct extraction
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            direct_text = ""
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                direct_text += page.extract_text()
        
        # If we got reasonable text and Hindi support not specifically requested, return it
        if len(direct_text) > 100 and not hindi_support:
            return direct_text
            
        # Otherwise, try OCR (especially for Hindi or scanned documents)
        # Convert PDF to images
        images = convert_from_path(pdf_path)
        
        # Perform OCR with Hindi language support
        ocr_text = ""
        for img in images:
            if hindi_support:
                # Use Hindi language pack if available, fallback to English
                try:
                    page_text = pytesseract.image_to_string(img, lang='hin+eng')
                except pytesseract.TesseractError:
                    page_text = pytesseract.image_to_string(img)
            else:
                page_text = pytesseract.image_to_string(img)
            
            ocr_text += page_text + "\n\n"
        
        # Choose the better result (usually OCR for Hindi, direct extraction for English)
        if len(ocr_text) > len(direct_text) or hindi_support:
            text = ocr_text
        else:
            text = direct_text
            
        return text
        
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        return f"Error processing PDF: {str(e)}"

async def parse_questions_from_text(text: str) -> List[Dict[str, Any]]:
    """Parse quiz questions from extracted text"""
    questions = []
    
    # Log the extracted text for debugging
    logger.info(f"Extracted text length: {len(text)}")
    logger.info(f"Extracted text sample: {text[:500]}...")
    
    # Pre-process text: clean up whitespace and normalize
    text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
    text = text.replace('\x0c', '\n')  # Replace form feed with newline
    
    # Split into lines for better processing
    lines = text.split('\n')
    lines = [line.strip() for line in lines if line.strip()]
    
    # Different patterns to match question formats
    patterns = [
        # Pattern 1: Q1. Question text? a) option1 b) option2 c) option3 d) option4
        r'(?:Q|q|प्रश्न)[.\s]*(\d+)[.\s]*\s*([^?]+\??)\s*(?:[aअ])[.\s)*]\s*([^बb]+)\s*(?:[bब])[.\s)*]\s*([^cग]+)\s*(?:[cग])[.\s)*]\s*([^dड]+)\s*(?:[dड])[.\s)*]\s*([^\n]+)',
        
        # Pattern 2: 1. Question text? Option1, Option2, Option3, Option4
        r'(\d+)[.\s)]*\s*([^?]+\??)\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,\n]+)',
        
        # Pattern 3: Question text? 1. Option1 2. Option2 3. Option3 4. Option4
        r'([^?]+\??)\s*(?:1|१)[.\s)]\s*([^\d]+)\s*(?:2|२)[.\s)]\s*([^\d]+)\s*(?:3|३)[.\s)]\s*([^\d]+)\s*(?:4|४)[.\s)]\s*([^\d\n]+)'
    ]
    
    # Try to find structured questions with regular expressions
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.MULTILINE)
        
        for match in matches:
            try:
                if len(match.groups()) == 6:  # Pattern 1 or 2
                    question_id = match.group(1)
                    question_text = match.group(2).strip()
                    options = [
                        match.group(3).strip(),
                        match.group(4).strip(),
                        match.group(5).strip(),
                        match.group(6).strip()
                    ]
                else:  # Pattern 3
                    question_text = match.group(1).strip()
                    options = [
                        match.group(2).strip(),
                        match.group(3).strip(),
                        match.group(4).strip(),
                        match.group(5).strip()
                    ]
                    question_id = "auto"
                
                # Create question dictionary
                question = {
                    "question": question_text,
                    "options": options,
                    "answer": 0,  # Default to first option
                    "category": "General Knowledge",  # Default category
                    "pdf_imported": True,  # Mark as imported
                    "needs_review": True   # Flag for review
                }
                
                questions.append((question_id, question))
                
            except Exception as e:
                logger.error(f"Error parsing question pattern: {e}")
    
    # If no questions found with regex, try heuristic-based parsing
    if not questions:
        try:
            # Identify question lines (those ending with ? or containing question words)
            question_indicators = [
                r'.*\?',  # Ends with ?
                r'.*किस.*',  # Hindi: which
                r'.*कौन.*',  # Hindi: who
                r'.*क्या.*',  # Hindi: what
                r'.*what.*',
                r'.*which.*',
                r'.*where.*',
                r'.*when.*',
                r'.*how.*',
                r'.*who.*',
                r'.*why.*'
            ]
            
            question_pattern = '|'.join(question_indicators)
            question_lines = []
            
            for i, line in enumerate(lines):
                if re.match(question_pattern, line, re.IGNORECASE):
                    question_lines.append((i, line))
            
            # Process each potential question
            for q_idx, (line_idx, question_text) in enumerate(question_lines):
                # Look for options after the question
                options = []
                option_count = 0
                search_idx = line_idx + 1
                
                # Option patterns to look for
                option_patterns = [
                    r'^\s*(?:[aA]|अ)[).]\s*(.*)',  # a) or A) or अ)
                    r'^\s*(?:[bB]|ब)[).]\s*(.*)',  # b) or B) or ब)
                    r'^\s*(?:[cC]|स)[).]\s*(.*)',  # c) or C) or स)
                    r'^\s*(?:[dD]|द)[).]\s*(.*)',  # d) or D) or द)
                    r'^\s*(?:1|१)[).]\s*(.*)',     # 1) or १)
                    r'^\s*(?:2|२)[).]\s*(.*)',     # 2) or २)
                    r'^\s*(?:3|३)[).]\s*(.*)',     # 3) or ३)
                    r'^\s*(?:4|४)[).]\s*(.*)'      # 4) or ४)
                ]
                
                # Try to find options in the next few lines
                while search_idx < len(lines) and option_count < 4 and search_idx < line_idx + 8:
                    line = lines[search_idx]
                    for pattern in option_patterns:
                        match = re.match(pattern, line)
                        if match:
                            options.append(match.group(1).strip())
                            option_count += 1
                            break
                    search_idx += 1
                
                # If we found 4 options, create a question
                if len(options) >= 3:  # At least 3 options to be a reasonable quiz question
                    # Pad to 4 options if needed
                    while len(options) < 4:
                        options.append(f"Option {len(options)+1}")
                        
                    question = {
                        "question": question_text.strip(),
                        "options": options,
                        "answer": 0,  # Default to first option
                        "category": "General Knowledge",
                        "pdf_imported": True,
                        "needs_review": True
                    }
                    questions.append((f"auto_{q_idx+1}", question))
            
            # If still no questions found, try another approach - look for numerical sequences
            if not questions:
                # Find all numbered items that might be questions
                numbered_items = []
                current_item = None
                
                for line in lines:
                    # Check if line starts with a number
                    num_match = re.match(r'^\s*(\d+)[.)\s]+(.*)', line)
                    if num_match:
                        if current_item:
                            numbered_items.append(current_item)
                        num = int(num_match.group(1))
                        text = num_match.group(2).strip()
                        current_item = {"num": num, "text": text, "options": []}
                    elif current_item and re.match(r'^[a-dA-D][.)]', line):
                        # This looks like an option (a), b), etc.)
                        option_text = re.sub(r'^[a-dA-D][.)]', '', line).strip()
                        current_item["options"].append(option_text)
                
                if current_item:
                    numbered_items.append(current_item)
                
                # Process the numbered items into questions
                for idx, item in enumerate(numbered_items):
                    if item["options"]:
                        # This item has options, so it's probably a question
                        question = {
                            "question": item["text"],
                            "options": item["options"][:4],  # Take up to 4 options
                            "answer": 0,
                            "category": "General Knowledge",
                            "pdf_imported": True,
                            "needs_review": True
                        }
                        
                        # Pad options if needed
                        while len(question["options"]) < 4:
                            question["options"].append(f"Option {len(question['options'])+1}")
                            
                        questions.append((str(item["num"]), question))
            
            # Last-ditch effort: parse as comma-separated options
            if not questions:
                for i, line in enumerate(lines):
                    if "?" in line:
                        # This looks like a question
                        q_text = line.strip()
                        
                        # Check if the next line has comma-separated options
                        if i + 1 < len(lines):
                            options_text = lines[i + 1]
                            if "," in options_text:
                                options = [opt.strip() for opt in options_text.split(",")]
                                if len(options) >= 3:  # Must have at least 3 options
                                    # Pad to 4 options if needed
                                    while len(options) < 4:
                                        options.append(f"Option {len(options)+1}")
                                        
                                    question = {
                                        "question": q_text,
                                        "options": options[:4],  # Take up to 4 options
                                        "answer": 0,
                                        "category": "General Knowledge",
                                        "pdf_imported": True,
                                        "needs_review": True
                                    }
                                    questions.append((f"auto_{i+1}", question))
        
        except Exception as e:
            logger.error(f"Error in heuristic parsing: {e}")
    
    logger.info(f"Total questions parsed: {len(questions)}")
    return questions

async def download_file(context: ContextTypes.DEFAULT_TYPE, file_id: str, destination: str) -> bool:
    """Download a file from Telegram to local storage"""
    try:
        file = await context.bot.get_file(file_id)
        await file.download_to_drive(destination)
        return True
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        return False

async def import_pdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the PDF import process"""
    await update.message.reply_text(
        "📄 Let's import questions from a PDF file!\n\n"
        "Please send me the PDF file containing quiz questions. "
        "I can process both English and Hindi content using OCR.\n\n"
        "For best results, the PDF should contain questions in one of these formats:\n"
        "- Q1. Question text? a) option1 b) option2 c) option3 d) option4\n"
        "- 1. Question text? Option1, Option2, Option3, Option4\n"
        "- Question text? 1. Option1 2. Option2 3. Option3 4. Option4\n\n"
        "Send /cancel to stop the import process."
    )
    return PDF_RECEIVING

async def receive_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle received PDF file"""
    # Check if we received a document that's a PDF
    if not update.message.document or not update.message.document.file_name.lower().endswith('.pdf'):
        await update.message.reply_text(
            "Please send a valid PDF file. The file should have a .pdf extension."
        )
        return PDF_RECEIVING
    
    # Inform user that processing is starting
    progress_message = await update.message.reply_text(
        "📄 PDF file received! Starting to process...\n"
        "This may take a minute or two depending on the file size and complexity."
    )
    
    # Create temp directory for processing
    with tempfile.TemporaryDirectory() as temp_dir:
        pdf_path = os.path.join(temp_dir, "questions.pdf")
        
        # Download the file
        file_id = update.message.document.file_id
        if not await download_file(context, file_id, pdf_path):
            await update.message.reply_text(
                "❌ Error downloading the PDF file. Please try again later."
            )
            return ConversationHandler.END
        
        # Update progress
        await progress_message.edit_text(
            "📄 PDF downloaded successfully!\n"
            "Now extracting text with Hindi language support..."
        )
        
        # Extract text from PDF with Hindi support
        try:
            extracted_text = await extract_text_from_pdf(pdf_path, hindi_support=True)
            
            if not extracted_text or len(extracted_text) < 50:
                await update.message.reply_text(
                    "❌ Could not extract sufficient text from the PDF. "
                    "The file might be encrypted, image-based, or in an unsupported format."
                )
                return ConversationHandler.END
                
            # Update progress
            await progress_message.edit_text(
                "📄 Text extracted successfully!\n"
                "Now parsing questions and options..."
            )
            
            # Parse questions from text
            parsed_questions = await parse_questions_from_text(extracted_text)
            
            if not parsed_questions:
                await update.message.reply_text(
                    "❌ Could not find any questions in the PDF. "
                    "Make sure the questions follow one of the supported formats."
                )
                return ConversationHandler.END
            
            # Store parsed questions in context for review
            context.user_data["pdf_questions"] = parsed_questions
            
            # Show preview of found questions
            preview_text = f"✅ Found {len(parsed_questions)} questions in the PDF!\n\n"
            
            # Show preview of the first 3 questions
            for i, (question_id, question) in enumerate(parsed_questions[:3]):
                preview_text += f"Question {i+1}: {question['question'][:50]}...\n"
                preview_text += "Options:\n"
                for j, option in enumerate(question['options']):
                    preview_text += f"  {j+1}. {option[:30]}...\n"
                preview_text += "\n"
            
            if len(parsed_questions) > 3:
                preview_text += f"...and {len(parsed_questions) - 3} more questions\n\n"
                
            preview_text += (
                "For each question:\n"
                "- Default answer is set to first option\n"
                "- Default category is 'General Knowledge'\n\n"
                "You'll need to review and set correct answers later."
            )
            
            # Create import confirmation keyboard
            keyboard = [
                [InlineKeyboardButton("✅ Import All Questions", callback_data="pdf_import_all")],
                [InlineKeyboardButton("❌ Cancel Import", callback_data="pdf_cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await progress_message.edit_text(preview_text, reply_markup=reply_markup)
            
            return PDF_CONFIRM
            
        except Exception as e:
            logger.error(f"Error processing PDF: {e}")
            await update.message.reply_text(
                f"❌ Error processing the PDF: {str(e)}"
            )
            return ConversationHandler.END

async def pdf_import_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle PDF import confirmation callbacks"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "pdf_cancel":
        await query.edit_message_text("PDF import cancelled.")
        return ConversationHandler.END
    
    if query.data == "pdf_import_all":
        # Get parsed questions
        parsed_questions = context.user_data.get("pdf_questions", [])
        
        if not parsed_questions:
            await query.edit_message_text("❌ No questions found to import.")
            return ConversationHandler.END
        
        # Import all questions
        imported_count = 0
        for question_id, question_data in parsed_questions:
            try:
                # If auto-generated ID, get next available
                if question_id == "auto" or question_id.startswith("auto_"):
                    question_id = get_next_question_id()
                else:
                    # Try to convert to int, fallback to auto if not possible
                    try:
                        question_id = int(question_id)
                    except ValueError:
                        question_id = get_next_question_id()
                
                # Add the question
                add_question_with_id(question_id, question_data)
                imported_count += 1
                
            except Exception as e:
                logger.error(f"Error importing question: {e}")
        
        # Report success
        success_text = (
            f"✅ Successfully imported {imported_count} questions from PDF!\n\n"
            f"Use /pdflist to see all PDF-imported questions that need review.\n"
            f"Use /pdfreview to start reviewing the correct answers.\n\n"
            f"Note: All imported questions have:\n"
            f"- First option set as the default correct answer\n"
            f"- 'General Knowledge' as the default category"
        )
        
        await query.edit_message_text(success_text)
        
        # Clean up
        if "pdf_questions" in context.user_data:
            del context.user_data["pdf_questions"]
        
        return ConversationHandler.END

async def list_pdf_questions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all questions imported from PDF that need review"""
    questions = load_questions()
    
    # Find PDF-imported questions that need review
    pdf_questions = []
    for qid, question_list in questions.items():
        if isinstance(question_list, list):
            for q in question_list:
                if q.get("pdf_imported") and q.get("needs_review"):
                    pdf_questions.append((qid, q))
        elif isinstance(question_list, dict) and question_list.get("pdf_imported") and question_list.get("needs_review"):
            pdf_questions.append((qid, question_list))
    
    if not pdf_questions:
        await update.message.reply_text(
            "No PDF-imported questions found that need review."
        )
        return
    
    # Create message showing all questions that need review
    message = f"📄 PDF-Imported Questions Needing Review ({len(pdf_questions)})\n\n"
    
    for i, (qid, question) in enumerate(pdf_questions[:10]):  # Show first 10
        message += f"ID {qid}: {question['question'][:50]}...\n"
    
    if len(pdf_questions) > 10:
        message += f"\n...and {len(pdf_questions) - 10} more questions\n"
    
    message += "\nUse /pdfreview to start reviewing these questions."
    
    await update.message.reply_text(message)

async def start_pdf_review_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start the review process for PDF-imported questions"""
    questions = load_questions()
    
    # Find PDF-imported questions that need review
    pdf_questions = []
    for qid, question_list in questions.items():
        if isinstance(question_list, list):
            for i, q in enumerate(question_list):
                if q.get("pdf_imported") and q.get("needs_review"):
                    pdf_questions.append((qid, i, q))
        elif isinstance(question_list, dict) and question_list.get("pdf_imported") and question_list.get("needs_review"):
            pdf_questions.append((qid, None, question_list))
    
    if not pdf_questions:
        await update.message.reply_text(
            "No PDF-imported questions found that need review."
        )
        return
    
    # Store the questions for review
    context.user_data["pdf_review_questions"] = pdf_questions
    context.user_data["pdf_review_index"] = 0
    
    # Show the first question
    await show_pdf_review_question(update, context)

async def show_pdf_review_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show a PDF-imported question for review"""
    questions = context.user_data.get("pdf_review_questions", [])
    index = context.user_data.get("pdf_review_index", 0)
    
    if not questions or index >= len(questions):
        await update.message.reply_text(
            "No more questions to review!"
        )
        return
    
    # Get the current question
    qid, subindex, question = questions[index]
    
    # Create message showing the question
    message = f"📝 Question Review ({index + 1}/{len(questions)})\n\n"
    message += f"Question: {question['question']}\n\n"
    message += "Options:\n"
    
    for i, option in enumerate(question['options']):
        message += f"{i}. {option}\n"
    
    message += f"\nCurrent answer: {question['answer']}. {question['options'][question['answer']]}\n"
    message += f"Current category: {question['category']}\n\n"
    
    # Create keyboard for selecting the correct answer and category
    keyboard = []
    
    # Answer selection buttons
    answer_row = []
    for i in range(min(4, len(question['options']))):
        answer_row.append(
            InlineKeyboardButton(f"Answer: {i}", callback_data=f"pdfans_{i}")
        )
    keyboard.append(answer_row)
    
    # Category selection buttons
    categories = ["General Knowledge", "Science", "History", "Geography", "Entertainment", "Sports"]
    for i in range(0, len(categories), 2):
        category_row = []
        for j in range(i, min(i+2, len(categories))):
            category_row.append(
                InlineKeyboardButton(categories[j], callback_data=f"pdfcat_{categories[j]}")
            )
        keyboard.append(category_row)
    
    # Navigation buttons
    nav_row = []
    if index > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data="pdfrev_prev"))
    nav_row.append(InlineKeyboardButton("Skip", callback_data="pdfrev_skip"))
    if index < len(questions) - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data="pdfrev_next"))
    keyboard.append(nav_row)
    
    # Save button
    keyboard.append([InlineKeyboardButton("✅ Save and Finish", callback_data="pdfrev_save")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send or edit message based on context
    if update.callback_query:
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message, reply_markup=reply_markup)

async def pdf_review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle PDF review callbacks"""
    query = update.callback_query
    await query.answer()
    
    # Get review data
    questions = context.user_data.get("pdf_review_questions", [])
    index = context.user_data.get("pdf_review_index", 0)
    
    if not questions or index >= len(questions):
        await query.edit_message_text("No more questions to review!")
        return
    
    # Get current question data
    qid, subindex, question = questions[index]
    
    # Handle different callback data
    if query.data.startswith("pdfans_"):
        # Update answer
        answer_index = int(query.data.replace("pdfans_", ""))
        if 0 <= answer_index < len(question['options']):
            question['answer'] = answer_index
        
        # Show updated question
        await show_pdf_review_question(update, context)
    
    elif query.data.startswith("pdfcat_"):
        # Update category
        category = query.data.replace("pdfcat_", "")
        question['category'] = category
        
        # Show updated question
        await show_pdf_review_question(update, context)
    
    elif query.data == "pdfrev_prev":
        # Go to previous question
        if index > 0:
            context.user_data["pdf_review_index"] = index - 1
        
        # Show previous question
        await show_pdf_review_question(update, context)
    
    elif query.data == "pdfrev_next" or query.data == "pdfrev_skip":
        # Go to next question
        if index < len(questions) - 1:
            context.user_data["pdf_review_index"] = index + 1
        
        # Show next question
        await show_pdf_review_question(update, context)
    
    elif query.data == "pdfrev_save":
        # Save all reviewed questions
        questions_to_save = {}
        
        for qid, subindex, question in questions:
            # Mark as reviewed
            question['needs_review'] = False
            
            # Handle single question or list of questions
            curr_questions = load_questions()
            
            if qid in curr_questions:
                if isinstance(curr_questions[qid], list) and subindex is not None:
                    # Replace in list
                    curr_questions[qid][subindex] = question
                else:
                    # Replace single question
                    curr_questions[qid] = question
                
                # Store for save
                questions_to_save = curr_questions
        
        # Save questions
        if questions_to_save:
            save_questions(questions_to_save)
        
        # Confirmation message
        await query.edit_message_text(
            f"✅ Successfully saved {len(questions)} reviewed questions!\n\n"
            f"You can start a quiz with these questions using /quiz"
        )
        
        # Clean up
        if "pdf_review_questions" in context.user_data:
            del context.user_data["pdf_review_questions"]
        if "pdf_review_index" in context.user_data:
            del context.user_data["pdf_review_index"]
# ---------- END PDF IMPORT ADDITIONS ----------

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
        "Welcome to the Quiz Bot with Negative Marking and PDF Import. Here's what you can do:\n\n"
        "💡 /quiz - Start a new quiz (auto-sequence)\n"
        "📊 /stats - View your quiz statistics with penalties\n"
        "➕ /add - Add a new question to the quiz bank\n"
        "✏️ /edit - Edit an existing question\n"
        "❌ /delete - Delete a question\n"
        "🔄 /poll2q - Convert a Telegram poll to a quiz question\n"
        "⚙️ /negmark - Configure negative marking settings\n"
        "🧹 /resetpenalty - Reset your penalties\n"
        "📄 /pdfimport - Import questions from a PDF file (supports Hindi)\n"
        "📑 /pdflist - List PDF-imported questions that need review\n"
        "✏️ /pdfreview - Review and correct PDF-imported questions\n"
        "ℹ️ /help - Show this help message\n\n"
        "Let's test your knowledge with some fun quizzes!"
    )
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help message."""
    await start(update, context)

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
    
    # Include negative marking information in the message
    negative_status = "ENABLED" if NEGATIVE_MARKING_ENABLED else "DISABLED"
    
    await update.message.reply_text(
        f"Starting a quiz with {num_questions} questions! Questions will automatically proceed after 30 seconds.\n\n"
        f"❗ Negative marking is {negative_status} - incorrect answers will deduct points!\n\n"
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

# ---------- NEGATIVE MARKING POLL ANSWER MODIFICATIONS ----------
async def poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle poll answers from users with negative marking."""
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
                category = question.get("category", "General Knowledge")
                
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
                        "answered": 0,
                        "participation": 0  # For backward compatibility
                    }
                
                participants[str(user.id)]["answered"] += 1
                participants[str(user.id)]["participation"] += 1  # For backward compatibility
                if is_correct:
                    participants[str(user.id)]["correct"] += 1
                
                # NEGATIVE MARKING ADDITION: Apply penalty for incorrect answers
                if NEGATIVE_MARKING_ENABLED and not is_correct:
                    # Get and apply penalty
                    penalty = get_penalty_for_category(category)
                    if penalty > 0:
                        # Record the penalty in the user's answer
                        user_answer = poll_info["answers"][str(user.id)]
                        user_answer["penalty"] = penalty
                        # Apply the penalty to the user's record
                        current_penalty = update_user_penalties(user.id, penalty)
                        logger.info(f"Applied penalty of {penalty} to user {user.id}, total penalties: {current_penalty}")
                
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
# ---------- END NEGATIVE MARKING POLL ANSWER MODIFICATIONS ----------

# ---------- NEGATIVE MARKING END QUIZ MODIFICATIONS ----------
async def end_quiz(context, chat_id):
    """End the quiz and display results with all participants and penalties."""
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
                        "answered": 0,
                        "participation": 0  # For backward compatibility
                    }
                
                participants[user_id]["answered"] += 1
                participants[user_id]["participation"] += 1  # For backward compatibility
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
            "answered": 0,
            "participation": 0  # For backward compatibility
        }
    
    # NEGATIVE MARKING ADDITION: Calculate scores with penalties
    final_scores = []
    for user_id, user_data in participants.items():
        user_name = user_data.get("name", f"User {user_id}")
        correct_count = user_data.get("correct", 0)
        participation_count = user_data.get("participation", user_data.get("answered", 0))
        
        # Get penalty points for this user
        penalty_points = get_user_penalties(user_id)
        
        # Calculate adjusted score
        adjusted_score = max(0, correct_count - penalty_points)
        
        final_scores.append({
            "user_id": user_id,
            "name": user_name,
            "correct": correct_count,
            "participation": participation_count,
            "penalty": penalty_points,
            "adjusted_score": adjusted_score
        })
    
    # Sort by adjusted score (highest first) and then by raw score
    final_scores.sort(key=lambda x: (x["adjusted_score"], x["correct"]), reverse=True)
    
    # Create results message
    results_message = f"🏁 The quiz has finished!\n\n{questions_count} questions answered\n\n"
    
    # Format results
    if final_scores:
        if NEGATIVE_MARKING_ENABLED:
            results_message += "❗ Negative marking was enabled for this quiz\n\n"
        
        winner_data = final_scores[0]
        winner_name = winner_data.get("name", "Quiz Taker")
        
        results_message += f"🏆 Congratulations to the winner: {winner_name}!\n\n"
        results_message += "📊 Final Ranking 📊\n"
        
        # Show all participants with ranks
        for i, data in enumerate(final_scores):
            rank_emoji = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
            
            name = data.get("name", f"Player {i+1}")
            correct = data.get("correct", 0)
            participation = data.get("participation", 0)
            penalty = data.get("penalty", 0)
            adjusted = data.get("adjusted_score", correct)
            
            percentage = (correct / questions_count * 100) if questions_count > 0 else 0
            adjusted_percentage = (adjusted / questions_count * 100) if questions_count > 0 else 0
            
            if NEGATIVE_MARKING_ENABLED and penalty > 0:
                # Include penalty information
                results_message += (
                    f"{rank_emoji} {name}: {correct}/{participation} ({percentage:.1f}%)\n"
                    f"   Penalty: -{penalty:.2f} points\n"
                    f"   Final score: {adjusted:.2f} points ({adjusted_percentage:.1f}%)\n\n"
                )
            else:
                # Standard format without penalties
                results_message += f"{rank_emoji} {name}: {correct}/{participation} ({percentage:.1f}%)\n"
    else:
        results_message += "No participants found for this quiz."
    
    # Send results
    await context.bot.send_message(
        chat_id=chat_id,
        text=results_message
    )
# ---------- END NEGATIVE MARKING END QUIZ MODIFICATIONS ----------

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
    application.add_handler(CommandHandler("stats", stats_command))  # This calls extended_stats_command
    application.add_handler(CommandHandler("delete", delete_command))
    
    # NEGATIVE MARKING ADDITION: Add new command handlers
    application.add_handler(CommandHandler("negmark", negative_marking_settings))
    application.add_handler(CommandHandler("resetpenalty", reset_user_penalty_command))
    application.add_handler(CallbackQueryHandler(negative_settings_callback, pattern=r"^neg_mark_"))
    
    # PDF IMPORT ADDITION: Add PDF command handlers
    pdf_import_handler = ConversationHandler(
        entry_points=[CommandHandler("pdfimport", import_pdf_command)],
        states={
            PDF_RECEIVING: [
                MessageHandler(filters.ATTACHMENT & ~filters.COMMAND, receive_pdf),
                CommandHandler("cancel", cancel)
            ],
            PDF_CONFIRM: [
                CallbackQueryHandler(pdf_import_callback, pattern=r"^pdf_")
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(pdf_import_handler)
    application.add_handler(CommandHandler("pdflist", list_pdf_questions_command))
    application.add_handler(CommandHandler("pdfreview", start_pdf_review_command))
    application.add_handler(CallbackQueryHandler(pdf_review_callback, pattern=r"^pdfrev_"))
    application.add_handler(CallbackQueryHandler(pdf_review_callback, pattern=r"^pdfans_"))
    application.add_handler(CallbackQueryHandler(pdf_review_callback, pattern=r"^pdfcat_"))
    
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