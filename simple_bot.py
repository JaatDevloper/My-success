# OCR + PDF Text Extraction + Block-Level Deduplication
import os
import re

# Handle imports with try-except to avoid crashes
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
    # Setup Tesseract path
    pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"
    os.environ['TESSDATA_PREFIX'] = "/usr/share/tesseract-ocr/5/tessdata"
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

def extract_text_from_pdf(file_path):
    """Extract text from a PDF file using multiple methods with fallbacks"""
    # Try with pdfplumber first if available
    if PDFPLUMBER_AVAILABLE:
        try:
            text = ""
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        text += t + "\n"
            if text.strip():
                return text.splitlines()
        except Exception as e:
            print("pdfplumber failed:", e)

    # Fallback to PyMuPDF if available
    if PYMUPDF_AVAILABLE:
        try:
            text = ""
            doc = fitz.open(file_path)
            for page in doc:
                t = page.get_text()
                if t:
                    text += t + "\n"
            if text.strip():
                return text.splitlines()
        except Exception as e:
            print("PyMuPDF failed:", e)

    # Final fallback: OCR with Tesseract if available
    if PYMUPDF_AVAILABLE and PIL_AVAILABLE and TESSERACT_AVAILABLE:
        try:
            text = ""
            doc = fitz.open(file_path)
            for page in doc:
                pix = page.get_pixmap(dpi=300)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                t = pytesseract.image_to_string(img, lang='hin')
                if t:
                    text += t + "\n"
            return text.splitlines()
        except Exception as e:
            print("Tesseract OCR failed:", e)
    
    # If nothing worked or no extractors available, return empty
    return []

def group_and_deduplicate_questions(lines):
    blocks = []
    current_block = []
    seen_blocks = set()

    for line in lines:
        if re.match(r'^Q[\.:\d]', line.strip(), re.IGNORECASE) and current_block:
            block_text = "\n".join(current_block).strip()
            if block_text not in seen_blocks:
                seen_blocks.add(block_text)
                blocks.append(current_block)
            current_block = []
        current_block.append(line.strip())

    if current_block:
        block_text = "\n".join(current_block).strip()
        if block_text not in seen_blocks:
            seen_blocks.add(block_text)
            blocks.append(current_block)

    final_lines = []
    for block in blocks:
        final_lines.extend(block)
        final_lines.append("")  # spacing
    return final_lines


"""
Enhanced Telegram Quiz Bot with PDF Import, Hindi Support, Advanced Negative Marking & PDF Results
- Based on the original multi_id_quiz_bot.py
- Added advanced negative marking features with customizable values per quiz
- Added PDF import with automatic question extraction
- Added Hindi language support for PDFs
- Added automatic PDF result generation with professional design and INSANE watermark
"""

# Import libraries for PDF generation
try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# Constants for PDF Results
PDF_RESULTS_DIR = "pdf_results"

def ensure_pdf_directory():
    """Ensure the PDF results directory exists and is writable"""
    global PDF_RESULTS_DIR
    
    # Try the default directory
    try:
        # Always set to a known location first
        PDF_RESULTS_DIR = os.path.join(os.getcwd(), "pdf_results")
        os.makedirs(PDF_RESULTS_DIR, exist_ok=True)
        
        # Test write permissions with a small test file
        test_file = os.path.join(PDF_RESULTS_DIR, "test_write.txt")
        with open(test_file, 'w') as f:
            f.write("Test write access")
        # If we get here, the directory is writable
        os.remove(test_file)
        logger.info(f"PDF directory verified and writable: {PDF_RESULTS_DIR}")
        return True
    except Exception as e:
        logger.error(f"Error setting up PDF directory: {e}")
        # If the first attempt failed, try a temporary directory
        try:
            PDF_RESULTS_DIR = os.path.join(os.getcwd(), "temp")
            os.makedirs(PDF_RESULTS_DIR, exist_ok=True)
            logger.info(f"Using alternative PDF directory: {PDF_RESULTS_DIR}")
            return True
        except Exception as e2:
            logger.error(f"Failed to create alternative PDF directory: {e2}")
            # Last resort - use current directory
            PDF_RESULTS_DIR = "."
            logger.info(f"Using current directory for PDF files")
            return False

# Try to set up the PDF directory at startup
try:
    os.makedirs(PDF_RESULTS_DIR, exist_ok=True)
except Exception:
    # If we can't create it now, we'll try again later in ensure_pdf_directory
    pass

# Import libraries for PDF handling
try:
    import PyPDF2
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

try:
    from PIL import Image
    IMAGE_SUPPORT = True
except ImportError:
    IMAGE_SUPPORT = False

import tempfile
TEMP_DIR = tempfile.mkdtemp()

import json
import re
import logging
import os
import random
import asyncio
import datetime
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler, PollAnswerHandler

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment variable
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7631768276:AAHLThlb--gKVa9as7G9Wu-MZkS-lOysCOk")

# Conversation states
QUESTION, OPTIONS, ANSWER, CATEGORY = range(4)
EDIT_SELECT, EDIT_QUESTION, EDIT_OPTIONS = range(4, 7)
CLONE_URL, CLONE_MANUAL = range(7, 9)
CUSTOM_ID = range(9, 10)

# PDF import conversation states (use high numbers to avoid conflicts)
PDF_UPLOAD, PDF_CUSTOM_ID, PDF_PROCESSING = range(100, 103)

# TXT import conversation states (use even higher numbers)
TXT_UPLOAD, TXT_CUSTOM_ID, TXT_PROCESSING = range(200, 203)

# Data files
QUESTIONS_FILE = "questions.json"
USERS_FILE = "users.json"
TEMP_DIR = "temp"

# Create temp directory if it doesn't exist
os.makedirs(TEMP_DIR, exist_ok=True)

# Create PDF Results directory
PDF_RESULTS_DIR = "pdf_results"
os.makedirs(PDF_RESULTS_DIR, exist_ok=True)

# Store quiz results for PDF generation
QUIZ_RESULTS_FILE = "quiz_results.json"
PARTICIPANTS_FILE = "participants.json"

# ---------- ENHANCED NEGATIVE MARKING ADDITIONS ----------
# Negative marking configuration
NEGATIVE_MARKING_ENABLED = True
DEFAULT_PENALTY = 0.25  # Default penalty for incorrect answers (0.25 points)
MAX_PENALTY = 1.0       # Maximum penalty for incorrect answers (1.0 points)
MIN_PENALTY = 0.0       # Minimum penalty for incorrect answers (0.0 points)

# Predefined negative marking options for selection
NEGATIVE_MARKING_OPTIONS = [
    ("None", 0.0),
    ("0.24", 0.24),
    ("0.33", 0.33),
    ("0.50", 0.50),
    ("1.00", 1.0)
]

# Advanced negative marking options with more choices
ADVANCED_NEGATIVE_MARKING_OPTIONS = [
    ("None", 0.0),
    ("Light (0.24)", 0.24),
    ("Moderate (0.33)", 0.33),
    ("Standard (0.50)", 0.50),
    ("Strict (0.75)", 0.75),
    ("Full (1.00)", 1.0),
    ("Extra Strict (1.25)", 1.25),
    ("Competitive (1.50)", 1.5),
    ("Custom", "custom")
]

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

# New file to store quiz-specific negative marking values
QUIZ_PENALTIES_FILE = "quiz_penalties.json"

def load_quiz_penalties():
    """Load quiz-specific penalties from file"""
    try:
        if os.path.exists(QUIZ_PENALTIES_FILE):
            with open(QUIZ_PENALTIES_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading quiz penalties: {e}")
        return {}

def save_quiz_penalties(penalties):
    """Save quiz-specific penalties to file"""
    try:
        with open(QUIZ_PENALTIES_FILE, 'w') as f:
            json.dump(penalties, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving quiz penalties: {e}")
        return False

def get_quiz_penalty(quiz_id):
    """Get negative marking value for a specific quiz ID"""
    penalties = load_quiz_penalties()
    return penalties.get(str(quiz_id), DEFAULT_PENALTY)

def set_quiz_penalty(quiz_id, penalty_value):
    """Set negative marking value for a specific quiz ID"""
    penalties = load_quiz_penalties()
    penalties[str(quiz_id)] = float(penalty_value)
    return save_quiz_penalties(penalties)

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
        penalties[user_id_str] = 0.0
    
    # Convert the penalty value to float and add it
    penalty_float = float(penalty_value)
    penalties[user_id_str] = float(penalties[user_id_str]) + penalty_float
    
    # Save updated penalties
    save_penalties(penalties)
    return penalties[user_id_str]

def get_penalty_for_quiz_or_category(quiz_id, category=None):
    """Get the penalty value for a specific quiz or category"""
    # Return 0 if negative marking is disabled
    if not NEGATIVE_MARKING_ENABLED:
        return 0
    
    # First check if there's a quiz-specific penalty
    quiz_penalties = load_quiz_penalties()
    if str(quiz_id) in quiz_penalties:
        return quiz_penalties[str(quiz_id)]
    
    # Fallback to category-specific penalty
    if category:
        penalty = CATEGORY_PENALTIES.get(category, DEFAULT_PENALTY)
    else:
        penalty = DEFAULT_PENALTY
    
    # Ensure penalty is within allowed range
    return max(MIN_PENALTY, min(MAX_PENALTY, penalty))

def apply_penalty(user_id, quiz_id=None, category=None):
    """Apply penalty to a user for an incorrect answer"""
    penalty = get_penalty_for_quiz_or_category(quiz_id, category)
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
        raw_score = float(correct)
        penalty = float(penalty)
        adjusted_score = max(0.0, raw_score - penalty)
        
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
# ---------- END ENHANCED NEGATIVE MARKING ADDITIONS ----------

# ---------- PDF RESULTS GENERATION FUNCTIONS ----------
def load_participants():
    """Load participants data"""
    try:
        if os.path.exists(PARTICIPANTS_FILE):
            with open(PARTICIPANTS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading participants: {e}")
        return {}

def save_participants(participants):
    """Save participants data"""
    try:
        with open(PARTICIPANTS_FILE, 'w') as f:
            json.dump(participants, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving participants: {e}")
        return False

def add_participant(user_id, user_name, first_name=None):
    """Add or update participant information"""
    participants = load_participants()
    participants[str(user_id)] = {
        "user_name": user_name,
        "first_name": first_name or user_name,
        "last_active": datetime.datetime.now().isoformat()
    }
    return save_participants(participants)

def get_participant_name(user_id):
    """Get participant name from user_id"""
    participants = load_participants()
    user_data = participants.get(str(user_id), {})
    return user_data.get("first_name", "Participant")

# Quiz result management
def load_quiz_results():
    """Load quiz results"""
    try:
        if os.path.exists(QUIZ_RESULTS_FILE):
            with open(QUIZ_RESULTS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading quiz results: {e}")
        return {}

def save_quiz_results(results):
    """Save quiz results"""
    try:
        with open(QUIZ_RESULTS_FILE, 'w') as f:
            json.dump(results, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving quiz results: {e}")
        return False

def add_quiz_result(quiz_id, user_id, user_name, total_questions, correct_answers, 
                   wrong_answers, skipped, penalty, score, adjusted_score):
    """Add quiz result for a participant"""
    results = load_quiz_results()
    
    # Initialize quiz results if not exists
    if str(quiz_id) not in results:
        results[str(quiz_id)] = {"participants": []}
    
    # Add participant result
    results[str(quiz_id)]["participants"].append({
        "user_id": str(user_id),
        "user_name": user_name,
        "timestamp": datetime.datetime.now().isoformat(),
        "total_questions": total_questions,
        "correct_answers": correct_answers,
        "wrong_answers": wrong_answers,
        "skipped": skipped,
        "penalty": penalty,
        "score": score,
        "adjusted_score": adjusted_score
    })
    
    # Add/update participant info
    add_participant(user_id, user_name)
    
    # Save results
    return save_quiz_results(results)

def get_quiz_results(quiz_id):
    """Get results for a specific quiz"""
    results = load_quiz_results()
    return results.get(str(quiz_id), {"participants": []})

def get_quiz_leaderboard(quiz_id):
    """Get leaderboard for a specific quiz"""
    quiz_results = get_quiz_results(quiz_id)
    participants = quiz_results.get("participants", [])
    
    # Sort by adjusted score (highest first)
    sorted_participants = sorted(
        participants, 
        key=lambda x: x.get("adjusted_score", 0), 
        reverse=True
    )
    
    # Remove duplicate users based on user_id and user_name
    # This fixes the issue of the same user appearing multiple times in the results
    deduplicated_participants = []
    processed_users = set()  # Track processed users by ID and name combo
    
    for participant in sorted_participants:
        user_id = participant.get("user_id", "")
        user_name = participant.get("user_name", "")
        unique_key = f"{user_id}_{user_name}"
        
        if unique_key not in processed_users:
            processed_users.add(unique_key)
            deduplicated_participants.append(participant)
    
    # Assign ranks to deduplicated list
    for i, participant in enumerate(deduplicated_participants):
        participant["rank"] = i + 1
    
    return deduplicated_participants

# PDF Generation Class 
class InsaneResultPDF(FPDF):
    """Custom PDF class for quiz results with INSANE watermark"""
    
    def __init__(self, quiz_id, title=None):
        # Initialize with explicit parameters to avoid potential issues
        super().__init__(orientation='P', unit='mm', format='A4')
        self.quiz_id = quiz_id
        self.title = title or f"Quiz {quiz_id} Results"
        self.set_author("QuizBot")
        self.set_creator("QuizBot")
        self.set_title(self.title)
        # Set some default settings
        # FPDF doesn't have set_margin, set individual margins instead
        self.set_left_margin(10)
        self.set_right_margin(10)
        self.set_top_margin(10)
        self.set_auto_page_break(True, margin=15)
        
    def header(self):
        # Logo or Title
        self.set_font('Arial', 'B', 16)
        self.set_text_color(0, 51, 102)  # Dark blue
        self.cell(0, 10, self.title, 0, 1, 'C')
        self.ln(5)
        
    def footer(self):
        # Footer with page number
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128, 128, 128)  # Gray
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', 0, 0, 'C')
        self.cell(0, 10, f'Generated on {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}', 0, 0, 'R')
        
    def add_watermark(self):
        # Save current position
        x, y = self.get_x(), self.get_y()
        
        try:
            # Add "INSANE" watermark (simplified to avoid rotation issues)
            self.set_font('Arial', 'B', 60)
            self.set_text_color(220, 220, 220)  # Light gray
            
            # Position the watermark in the center of the page
            # Using a simpler approach without rotation
            self.set_xy(50, 100)
            self.cell(100, 30, "INSANE", 0, 0, 'C')
            
            # Reset position and color
            self.set_xy(x, y)
            self.set_text_color(0, 0, 0)  # Reset to black
        except Exception as e:
            logger.error(f"Error adding watermark: {e}")
            # Continue without watermark
        
    def create_leaderboard_table(self, leaderboard):
        self.add_watermark()
        
        # Table header
        self.set_font('Arial', 'B', 10)
        self.set_fill_color(70, 130, 180)  # Steel blue
        self.set_text_color(255, 255, 255)  # White
        
        # Column widths
        col_widths = [15, 60, 20, 20, 20, 20, 25]
        header_texts = ["Rank", "Participant", "Marks", "Right", "Wrong", "Skip", "Penalty"]
        
        # Draw header row
        self.set_x(10)
        for i, text in enumerate(header_texts):
            self.cell(col_widths[i], 10, text, 1, 0, 'C', True)
        self.ln()
        
        # Table rows
        alternate_color = False
        for entry in leaderboard:
            # Alternate row colors
            if alternate_color:
                self.set_fill_color(220, 230, 241)  # Light blue
            else:
                self.set_fill_color(245, 245, 245)  # Light gray
            alternate_color = not alternate_color
            
            self.set_text_color(0, 0, 0)  # Black text
            self.set_font('Arial', '', 10)
            
            # Process user name to handle encoding issues
            try:
                # Better handling of names to avoid question marks and HTML-like tags
                raw_name = str(entry.get('user_name', 'Unknown'))
                
                # More aggressive sanitization to fix special character issues
                # Only allow ASCII letters, numbers, spaces, and common punctuation
                safe_chars = []
                for c in raw_name:
                    # Allow basic ASCII characters and some safe symbols
                    if (32 <= ord(c) <= 126):
                        safe_chars.append(c)
                    else:
                        # Replace non-ASCII with a safe underscore
                        safe_chars.append('_')
                
                cleaned_name = ''.join(safe_chars)
                
                # Further cleanup for HTML-like tags that might appear in some names
                cleaned_name = cleaned_name.replace('<', '').replace('>', '').replace('/', '')
                
                # Default display name to the cleaned version
                display_name = cleaned_name
                
                # If name was heavily modified or empty after cleaning, use fallback
                if not cleaned_name or cleaned_name.isspace():
                    display_name = f"User_{entry.get('rank', '')}"
                    
                # Add user_id to always guarantee uniqueness in the PDF
                user_id = entry.get('user_id')
                if user_id and (len(cleaned_name) < 3 or '_' in cleaned_name):
                    # Only add ID suffix for names that needed sanitizing
                    display_name += f"_{str(user_id)[-4:]}"
            except Exception as e:
                # Fallback to a safe name
                display_name = f"User_{entry.get('rank', '')}"
                logger.error(f"Error processing name for PDF: {e}")
            
            # Row content
            self.set_x(10)
            self.cell(col_widths[0], 10, str(entry.get("rank", "")), 1, 0, 'C', True)
            self.cell(col_widths[1], 10, display_name[:25], 1, 0, 'L', True)
            self.cell(col_widths[2], 10, str(entry.get("adjusted_score", 0)), 1, 0, 'C', True)
            self.cell(col_widths[3], 10, str(entry.get("correct_answers", 0)), 1, 0, 'C', True)
            self.cell(col_widths[4], 10, str(entry.get("wrong_answers", 0)), 1, 0, 'C', True)
            self.cell(col_widths[5], 10, str(entry.get("skipped", 0)), 1, 0, 'C', True)
            self.cell(col_widths[6], 10, str(entry.get("penalty", 0)), 1, 0, 'C', True)
            self.ln()
        
    def add_quiz_statistics(self, leaderboard, penalty_value):
        # Add quiz summary
        self.ln(10)
        self.set_font('Arial', 'B', 12)
        self.set_text_color(0, 51, 102)  # Dark blue
        self.cell(0, 10, "Quiz Statistics", 0, 1, 'L')
        
        # Basic statistics
        self.set_font('Arial', '', 10)
        self.set_text_color(0, 0, 0)  # Black
        
        total_participants = len(leaderboard)
        avg_score = sum(p.get("adjusted_score", 0) for p in leaderboard) / max(1, total_participants)
        avg_correct = sum(p.get("correct_answers", 0) for p in leaderboard) / max(1, total_participants)
        avg_wrong = sum(p.get("wrong_answers", 0) for p in leaderboard) / max(1, total_participants)
        
        stats = [
            f"Total Participants: {total_participants}",
            f"Average Score: {avg_score:.2f}",
            f"Average Correct Answers: {avg_correct:.2f}",
            f"Average Wrong Answers: {avg_wrong:.2f}",
            f"Negative Marking: {penalty_value:.2f} points per wrong answer"
        ]
        
        for stat in stats:
            self.cell(0, 7, stat, 0, 1, 'L')
            
        # Date and time  
        self.ln(5)
        self.set_font('Arial', 'I', 10)
        self.cell(0, 7, f"Report generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 0, 1, 'L')
        
    def add_score_distribution(self, leaderboard):
        """Add score distribution graph (simplified version)"""
        if not leaderboard:
            return
        
        self.ln(10)
        self.set_font('Arial', 'B', 12)
        self.set_text_color(0, 51, 102)  # Dark blue
        self.cell(0, 10, "Score Distribution", 0, 1, 'L')
        
        # Simple text-based distribution for FPDF
        score_ranges = {
            "0-20": 0,
            "21-40": 0,
            "41-60": 0,
            "61-80": 0,
            "81-100": 0,
            "101+": 0
        }
        
        # Count participants in each score range
        for entry in leaderboard:
            score = entry.get("adjusted_score", 0)
            if score <= 20:
                score_ranges["0-20"] += 1
            elif score <= 40:
                score_ranges["21-40"] += 1
            elif score <= 60:
                score_ranges["41-60"] += 1
            elif score <= 80:
                score_ranges["61-80"] += 1
            elif score <= 100:
                score_ranges["81-100"] += 1
            else:
                score_ranges["101+"] += 1
        
        # Display the distribution
        self.set_font('Arial', '', 10)
        self.set_text_color(0, 0, 0)  # Black
        
        for range_name, count in score_ranges.items():
            # Create a simple bar using ASCII characters instead of unicode
            # to avoid encoding issues
            bar = "=" * count
            self.cell(30, 7, range_name, 0, 0, 'L')
            self.cell(10, 7, str(count), 0, 0, 'R')
            self.cell(0, 7, bar, 0, 1, 'L')

def generate_pdf_results(quiz_id, title=None):
    """Generate PDF results for a quiz"""
    global PDF_RESULTS_DIR
    
    logger.info(f"Starting PDF generation for quiz ID: {quiz_id}")
    
    # Use our enhanced PDF directory validation function
    ensure_pdf_directory()
    logger.info(f"Using PDF directory: {PDF_RESULTS_DIR}")
    
    if not FPDF_AVAILABLE:
        logger.warning("FPDF library not available, cannot generate PDF results")
        return None
    
    # Make sure the directory exists and is writable
    try:
        # Manual directory check and creation as a fallback
        if not os.path.exists(PDF_RESULTS_DIR):
            os.makedirs(PDF_RESULTS_DIR, exist_ok=True)
            logger.info(f"Created PDF directory: {PDF_RESULTS_DIR}")
        
        # Test file write permission
        test_file = os.path.join(PDF_RESULTS_DIR, "test_permission.txt")
        with open(test_file, 'w') as f:
            f.write("Testing write permission")
        os.remove(test_file)
        logger.info("PDF directory is writable")
    except Exception as e:
        logger.error(f"Error with PDF directory: {e}")
        # Fallback to current directory
        PDF_RESULTS_DIR = os.getcwd()
        logger.info(f"Fallback to current directory: {PDF_RESULTS_DIR}")
    
    # Get data
    try:    
        leaderboard = get_quiz_leaderboard(quiz_id)
        penalty_value = get_quiz_penalty(quiz_id)
    except Exception as e:
        logger.error(f"Error getting leaderboard or penalty: {e}")
        return None
    
    # Create PDF
    try:
        # Create the FPDF object
        logger.info("Creating PDF object...")
        pdf = InsaneResultPDF(quiz_id, title)
        pdf.alias_nb_pages()
        pdf.add_page()
        
        # Add content section by section with error handling
        try:
            logger.info("Adding leaderboard table...")
            pdf.create_leaderboard_table(leaderboard)
        except Exception as e:
            logger.error(f"Error adding leaderboard: {e}")
            # Continue anyway
        
        try:
            logger.info("Adding statistics...")
            pdf.add_quiz_statistics(leaderboard, penalty_value)
        except Exception as e:
            logger.error(f"Error adding statistics: {e}")
            # Continue anyway
            
        try:
            logger.info("Adding score distribution...")
            pdf.add_score_distribution(leaderboard)
        except Exception as e:
            logger.error(f"Error adding score distribution: {e}")
            # Continue anyway
        
        # Save the PDF with absolute path
        timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        filename = os.path.join(PDF_RESULTS_DIR, f"quiz_{quiz_id}_results_{timestamp}.pdf")
        logger.info(f"Saving PDF to: {filename}")
        
        # Try to output with error catching
        try:
            # Use 'F' (write to file) output method for better error handling
            pdf.output(filename, 'F')
            logger.info("PDF output completed successfully")
        except Exception as e:
            logger.error(f"Error in PDF output: {e}")
            
            # Try with encoding fallback and more robust error handling
            try:
                # Create a simpler PDF with sanitized content 
                logger.info("Trying to create fallback PDF with stronger character sanitization...")
                
                # Get leaderboard data again for the simple PDF
                leaderboard = get_quiz_leaderboard(quiz_id)
                penalty_value = get_quiz_penalty(quiz_id)
                
                # Use a clean, simple PDF with proper content
                simple_pdf = FPDF()
                simple_pdf.add_page()
                
                # Add title
                simple_pdf.set_font('Arial', 'B', 16)
                simple_pdf.cell(0, 10, f'Quiz {quiz_id} Results', 0, 1, 'C')
                simple_pdf.ln(5)
                
                # Add subtitle
                simple_pdf.set_font('Arial', 'I', 12)
                simple_pdf.cell(0, 10, 'Simplified PDF due to encoding issues', 0, 1, 'C')
                simple_pdf.ln(10)
                
                # Add leaderboard table header
                simple_pdf.set_font('Arial', 'B', 12)
                simple_pdf.cell(10, 10, 'Rank', 1, 0, 'C')
                simple_pdf.cell(60, 10, 'Name', 1, 0, 'C')
                simple_pdf.cell(30, 10, 'Score', 1, 0, 'C')
                simple_pdf.cell(30, 10, 'Correct', 1, 0, 'C')
                simple_pdf.cell(30, 10, 'Wrong', 1, 0, 'C')
                simple_pdf.cell(30, 10, 'Skipped', 1, 1, 'C')
                
                # Add leaderboard data
                simple_pdf.set_font('Arial', '', 10)
                
                # Safely add leaderboard entries - with stronger character sanitization
                rank = 1
                if leaderboard and isinstance(leaderboard, list):
                    for entry in leaderboard:
                        try:
                            # Better handling of names to avoid question marks and HTML-like tags
                            raw_name = str(entry.get('user_name', 'Unknown'))
                            
                            # More aggressive sanitization to fix special character issues
                            # Only allow ASCII letters, numbers, spaces, and common punctuation
                            safe_chars = []
                            for c in raw_name:
                                # Allow basic ASCII characters and some safe symbols
                                if (32 <= ord(c) <= 126):
                                    safe_chars.append(c)
                                else:
                                    # Replace non-ASCII with a safe underscore
                                    safe_chars.append('_')
                            
                            cleaned_name = ''.join(safe_chars)
                            
                            # Further cleanup for HTML-like tags that might appear in some names
                            cleaned_name = cleaned_name.replace('<', '').replace('>', '').replace('/', '')
                            
                            # Default display name to the cleaned version
                            display_name = cleaned_name
                            
                            # If name was heavily modified or empty after cleaning, use fallback
                            if not cleaned_name or cleaned_name.isspace():
                                display_name = f"User_{entry.get('rank', '')}"
                                
                            # Add user_id to always guarantee uniqueness in the PDF
                            user_id = entry.get('user_id')
                            if user_id and (len(cleaned_name) < 3 or '_' in cleaned_name):
                                # Only add ID suffix for names that needed sanitizing
                                display_name += f"_{str(user_id)[-4:]}"
                            
                            # Get other values
                            score = float(entry.get('adjusted_score', 0))
                            correct = int(entry.get('correct_answers', 0))
                            wrong = int(entry.get('wrong_answers', 0))
                            skipped = int(entry.get('skipped', 0))
                            
                            simple_pdf.cell(10, 10, str(rank), 1, 0, 'C')
                            simple_pdf.cell(60, 10, display_name, 1, 0, 'L')
                            simple_pdf.cell(30, 10, f"{score:.2f}", 1, 0, 'C')
                            simple_pdf.cell(30, 10, str(correct), 1, 0, 'C')
                            simple_pdf.cell(30, 10, str(wrong), 1, 0, 'C')
                            simple_pdf.cell(30, 10, str(skipped), 1, 1, 'C')
                            
                            rank += 1
                        except Exception as e:
                            logger.error(f"Error adding leaderboard entry: {e}")
                            continue
                else:
                    # No leaderboard data available
                    simple_pdf.cell(0, 10, "No leaderboard data available", 1, 1, 'C')
                
                # Add summary statistics
                simple_pdf.ln(10)
                simple_pdf.set_font('Arial', 'B', 14)
                simple_pdf.cell(0, 10, "Quiz Summary", 0, 1, 'L')
                simple_pdf.ln(5)
                
                # Add quiz statistics
                simple_pdf.set_font('Arial', '', 12)
                
                if leaderboard and isinstance(leaderboard, list):
                    # Calculate statistics
                    total_participants = len(leaderboard)
                    avg_score = sum(float(entry.get('adjusted_score', 0)) for entry in leaderboard) / total_participants if total_participants > 0 else 0
                    
                    simple_pdf.cell(0, 8, f"Total Participants: {total_participants}", 0, 1, 'L')
                    simple_pdf.cell(0, 8, f"Negative Marking: {penalty_value}", 0, 1, 'L')
                    simple_pdf.cell(0, 8, f"Average Score: {avg_score:.2f}", 0, 1, 'L')
                else:
                    simple_pdf.cell(0, 8, "No statistics available", 0, 1, 'L')
                
                # Add footer with timestamp
                simple_pdf.ln(15)
                simple_pdf.set_font('Arial', 'I', 10)
                simple_pdf.cell(0, 10, f"Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 0, 1, 'R')
                
                # Add a special note about the simplification
                simple_pdf.ln(15)
                simple_pdf.set_font('Arial', 'B', 12)
                simple_pdf.set_text_color(200, 0, 0)  # Red text
                simple_pdf.cell(0, 10, "Note: This is a simplified PDF due to encoding issues with special characters.", 0, 1, 'C')
                
                # Save with a different name
                simple_filename = os.path.join(PDF_RESULTS_DIR, f"quiz_{quiz_id}_simple.pdf")
                
                # Try different encoding options to ensure it works
                try:
                    simple_pdf.output(simple_filename, 'F')
                    logger.info("Successfully created PDF with standard output")
                except Exception as e3:
                    logger.error(f"Error in standard output: {e3}")
                    # Final fallback - create the absolute minimum PDF
                    try:
                        minimal_pdf = FPDF()
                        minimal_pdf.add_page()
                        minimal_pdf.set_font('Arial', 'B', 16)
                        minimal_pdf.cell(0, 10, f'Quiz {quiz_id} Results', 0, 1, 'C')
                        minimal_pdf.ln(10)
                        minimal_pdf.set_font('Arial', '', 12)
                        minimal_pdf.cell(0, 10, 'Error creating detailed PDF - basic version provided', 0, 1, 'C')
                        minimal_pdf.ln(10)
                        minimal_pdf.cell(0, 10, f'Generated on: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}', 0, 1, 'C')
                        
                        simple_filename = os.path.join(PDF_RESULTS_DIR, f"quiz_{quiz_id}_minimal.pdf")
                        minimal_pdf.output(simple_filename)
                        logger.info("Created minimal PDF as final fallback")
                    except Exception as e4:
                        logger.error(f"Final PDF fallback failed: {e4}")
                        return None
                
                filename = simple_filename
                logger.info(f"PDF output succeeded with simplified PDF: {filename}")
            except Exception as e2:
                logger.error(f"Error in fallback pdf.output: {e2}")
                return None
        
        # Verify the PDF was created successfully
        if os.path.exists(filename):
            file_size = os.path.getsize(filename)
            if file_size > 0:
                logger.info(f"Successfully generated PDF: {filename} (Size: {file_size} bytes)")
                return filename
            else:
                logger.error(f"PDF file was created but is empty: {filename}")
                return None
        else:
            logger.error(f"PDF file was not created properly: {filename}")
            return None
    except Exception as e:
        logger.error(f"Unexpected error in PDF generation: {e}")
        return None

def process_quiz_end(quiz_id, user_id, user_name, total_questions, correct_answers, 
                   wrong_answers, skipped, penalty, score, adjusted_score):
    """Process quiz end - add result and generate PDF"""
    # Add the quiz result to the database
    add_quiz_result(quiz_id, user_id, user_name, total_questions, correct_answers, 
                   wrong_answers, skipped, penalty, score, adjusted_score)
    
    # Generate PDF results
    pdf_file = generate_pdf_results(quiz_id)
    
    return pdf_file

async def handle_quiz_end_with_pdf(update, context, quiz_id, user_id, user_name, 
                                  total_questions, correct_answers, wrong_answers, 
                                  skipped, penalty, score, adjusted_score):
    """Handle quiz end with PDF generation"""
    try:
        # Send message first to indicate we're working on it
        await update.message.reply_text("📊 *Generating Quiz Results PDF...*", parse_mode="Markdown")
        
        # Log the start of PDF generation with all parameters for debugging
        logger.info(f"Starting PDF generation for quiz_id: {quiz_id}, user: {user_name}, " +
                   f"score: {score}, adjusted_score: {adjusted_score}")
        
        # Generate the PDF with better error handling
        pdf_file = process_quiz_end(
            quiz_id, user_id, user_name, total_questions, correct_answers,
            wrong_answers, skipped, penalty, score, adjusted_score
        )
        
        logger.info(f"PDF generation process returned: {pdf_file}")
        
        # Enhanced file verification
        file_valid = False
        if pdf_file:
            try:
                # Verify the file exists and has minimum size
                if os.path.exists(pdf_file):
                    file_size = os.path.getsize(pdf_file)
                    logger.info(f"Found PDF file: {pdf_file} with size {file_size} bytes")
                    
                    if file_size > 100:  # Ensure at least 100 bytes
                        # Extra verification - check first few bytes for PDF signature
                        with open(pdf_file, 'rb') as f:
                            file_header = f.read(5)
                            if file_header == b'%PDF-':
                                file_valid = True
                                logger.info(f"PDF header verified successfully")
                            else:
                                logger.error(f"File exists but doesn't have PDF header: {pdf_file}")
                    else:
                        logger.error(f"PDF file too small (size: {file_size}): {pdf_file}")
                else:
                    logger.error(f"PDF file does not exist: {pdf_file}")
            except Exception as e:
                logger.error(f"Error verifying PDF file: {e}")
        else:
            logger.error("PDF generation returned None or empty path")
        
        # If PDF was generated successfully and verified, send it
        if file_valid:
            try:
                # Send the PDF file
                chat_id = update.effective_chat.id
                logger.info(f"Sending PDF to chat_id: {chat_id}")
                
                with open(pdf_file, 'rb') as file:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=file,
                        filename=f"Quiz_{quiz_id}_Results.pdf",
                        caption=f"📈 Quiz {quiz_id} Results - INSANE Learning Platform"
                    )
                    
                # Send success message with penalty info
                penalty_text = f"{penalty} point{'s' if penalty != 1 else ''}" if penalty > 0 else "None"
                
                # Calculate percentage safely
                try:
                    total_float = float(total_questions)
                    adjusted_float = float(adjusted_score)
                    percentage = (adjusted_float / total_float * 100) if total_float > 0 else 0.0
                except (TypeError, ZeroDivisionError, ValueError):
                    percentage = 0.0
                    
                success_message = (
                    f"✅ PDF Results generated successfully!\n\n"
                    f"Quiz ID: {quiz_id}\n"
                    f"Total Questions: {total_questions}\n"
                    f"Correct Answers: {correct_answers}\n"
                    f"Negative Marking: {penalty_text}\n"
                    f"Final Score: {adjusted_score:.2f} ({percentage:.1f}%)"
                )
                await update.message.reply_text(success_message)
                
                logger.info("PDF document sent successfully")
                return True
            except Exception as e:
                logger.error(f"Error sending PDF: {str(e)}")
                await update.message.reply_text(f"❌ Error sending PDF results: {str(e)}")
                return False
        else:
            # If PDF generation failed, notify the user
            logger.error("PDF file validation failed")
            await update.message.reply_text("❌ Sorry, couldn't generate PDF results. File validation failed.")
            return False
    except Exception as e:
        logger.error(f"Unexpected error in PDF handling: {str(e)}")
        try:
            await update.message.reply_text(f"❌ Unexpected error: {str(e)}")
        except:
            logger.error("Could not send error message to chat")
        return False
# ---------- END PDF RESULTS GENERATION FUNCTIONS ----------

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

# ---------- PDF IMPORT UTILITIES ----------
def detect_language(text):
    """
    Simple language detection to identify if text contains Hindi
    Returns 'hi' if Hindi characters are detected, 'en' otherwise
    """
    # Unicode ranges for Hindi (Devanagari script)
    hindi_range = range(0x0900, 0x097F + 1)
    
    for char in text:
        if ord(char) in hindi_range:
            return 'hi'
    
    return 'en'

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    welcome_text = (
        f"✨ 𝙒𝙚𝙡𝙘𝙤𝙢𝙚, {user.mention_html()} ✨\n\n"
        "🧠 <b>𝗤𝘂𝗶𝘇 𝗠𝗮𝘀𝘁𝗲𝗿 𝗕𝗼𝘁</b> is here to challenge your mind and test your skills!\n\n"
        "<b>𝗛𝗲𝗿𝗲’𝘀 𝘄𝗵𝗮𝘁 𝘆𝗼𝘂 𝗰𝗮𝗻 𝗱𝗼:</b>\n"
        "• ⚡ <b>Start a Quiz:</b> /quiz\n"
        "• 📊 <b>Check Stats:</b> /stats\n"
        "• ➕ <b>Add Question:</b> /add\n"
        "• ✏️ <b>Edit Question:</b> /edit\n"
        "• ❌ <b>Delete Question:</b> /delete\n"
        "• 🔄 <b>Poll to Quiz:</b> /poll2q\n"
        "• ℹ️ <b>Help & Commands:</b> /help\n\n"
        
        "📄 <b>𝗙𝗶𝗹𝗲 𝗜𝗺𝗽𝗼𝗿𝘁 & Custom ID:</b>\n"
        "• 📥 <b>Import from PDF:</b> /pdfimport\n"
        "• 📝 <b>Import from TXT:</b> /txtimport\n"
        "• 🆔 <b>Start Quiz by ID:</b> /quizid\n"
        "• ℹ️ <b>PDF Info:</b> /pdfinfo\n\n"
        
        "⚙️ <b>𝗔𝗱𝘃𝗮𝗻𝗰𝗲𝗱 𝗤𝘂𝗶𝘇 𝗦𝗲𝘁𝘁𝗶𝗻𝗴𝘀:</b>\n"
        "• ⚙️ <b>Negative Marking:</b> /negmark\n"
        "• 🧹 <b>Reset Penalties:</b> /resetpenalty\n"
        "• ✋ <b>Stop Quiz Anytime:</b> /stop\n\n"
        
        "🔥 <b>Let’s go — become the legend of the leaderboard!</b> 🏆\n\n"
        "👨‍💻 <b>Developed by</b> <a href='https://t.me/JaatCoderX'>@JaatCoderX</a>\n"  
    )
    await update.message.reply_html(welcome_text)
    
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
    
    # Validate the question before processing
    if not question.get("question") or not question["question"].strip():
        logger.error(f"Empty question text for question {question_index}")
        error_msg = (
            f"❌ Could not display question #{question_index+1}.\n"
            f"Reason: Text must be non-empty\n\n"
            "Moving to next question..."
        )
        await context.bot.send_message(chat_id=chat_id, text=error_msg)
        # Skip to next question
        await schedule_next_question(context, chat_id, question_index + 1)
        return
    
    # Make sure we have at least 2 options (Telegram requirement)
    if not question.get("options") or len(question["options"]) < 2:
        logger.error(f"Not enough options for question {question_index}")
        error_msg = (
            f"❌ Could not display question #{question_index+1}.\n"
            f"Reason: At least 2 options required\n\n"
            "Moving to next question..."
        )
        await context.bot.send_message(chat_id=chat_id, text=error_msg)
        # Skip to next question
        await schedule_next_question(context, chat_id, question_index + 1)
        return
    
    # Check for empty options
    empty_options = [i for i, opt in enumerate(question["options"]) if not opt or not opt.strip()]
    if empty_options:
        logger.error(f"Empty options found for question {question_index}: {empty_options}")
        # Fix by replacing empty options with placeholder text
        for i in empty_options:
            question["options"][i] = "(No option provided)"
        logger.info(f"Replaced empty options with placeholder text")
    
    # Telegram limits for polls:
    # - Question text: 300 characters
    # - Option text: 100 characters
    # Truncate if necessary
    question_text = question["question"]
    if len(question_text) > 290:  # Leave some margin
        question_text = question_text[:287] + "..."
        logger.info(f"Truncated question text from {len(question['question'])} to 290 characters")
    
    # Prepare and truncate options if needed, and limit to 10 options (Telegram limit)
    options = []
    for i, option in enumerate(question["options"]):
        # Only process the first 10 options (Telegram limit)
        if i >= 10:
            logger.warning(f"Question has more than 10 options, truncating to 10 (Telegram limit)")
            break
        
        if len(option) > 97:  # Leave some margin
            option = option[:94] + "..."
            logger.info(f"Truncated option from {len(option)} to 97 characters")
        options.append(option)
    
    # If we had to truncate options, make sure the correct answer is still valid
    correct_answer = question["answer"]
    if len(question["options"]) > 10 and correct_answer >= 10:
        logger.warning(f"Correct answer index {correct_answer} is out of range after truncation, defaulting to 0")
        correct_answer = 0
    elif correct_answer >= len(options):
        logger.warning(f"Correct answer index {correct_answer} is out of range of options list, defaulting to 0")
        correct_answer = 0
    else:
        correct_answer = question["answer"]
    
    try:
        # Send the poll with our validated correct_answer
        message = await context.bot.send_poll(
            chat_id=chat_id,
            question=question_text,
            options=options,
            type="quiz",
            correct_option_id=correct_answer,
            is_anonymous=False,
            open_period=25  # Close poll after 25 seconds
        )
    except Exception as e:
        logger.error(f"Error sending poll: {str(e)}")
        # Send a message instead if poll fails
        error_msg = (
            f"❌ Could not display question #{question_index+1}.\n"
            f"Reason: {str(e)}\n\n"
            "Moving to next question..."
        )
        await context.bot.send_message(chat_id=chat_id, text=error_msg)
        
        # Skip to next question
        await schedule_next_question(context, chat_id, question_index + 1)
        return
    
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
    await asyncio.sleep(15)  # Wait 30 seconds
    
    # Check if quiz is still active
    quiz = context.chat_data.get("quiz", {})
    if quiz.get("active", False):
        await send_question(context, chat_id, next_index)

async def schedule_end_quiz(context, chat_id):
    """Schedule end of quiz with delay."""
    await asyncio.sleep(15)  # Wait 30 seconds after last question
    
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
                
                # ENHANCED NEGATIVE MARKING: Apply quiz-specific penalty for incorrect answers
                if NEGATIVE_MARKING_ENABLED and not is_correct:
                    # Get quiz ID from the quiz data
                    quiz_id = quiz.get("quiz_id", None)
                    
                    # Get and apply penalty (quiz-specific if available, otherwise category-based)
                    penalty = get_penalty_for_quiz_or_category(quiz_id, category)
                    
                    if penalty > 0:
                        # Record the penalty in the user's answer
                        user_answer = poll_info["answers"][str(user.id)]
                        user_answer["penalty"] = penalty
                        
                        # Apply the penalty to the user's record
                        current_penalty = update_user_penalties(user.id, penalty)
                        
                        logger.info(f"Applied penalty of {penalty} to user {user.id}, total penalties: {current_penalty}, quiz ID: {quiz_id}")
                
                # Save back to quiz
                quiz["participants"] = participants
                sent_polls[str(poll_id)] = poll_info
                quiz["sent_polls"] = sent_polls
                # Using the proper way to update chat_data
                chat_data["quiz"] = quiz
                
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
    
    # ENHANCED NEGATIVE MARKING: Calculate scores with quiz-specific penalties
    final_scores = []
    
    # Get quiz-specific negative marking value
    quiz_id = quiz.get("quiz_id", None)
    neg_value = quiz.get("negative_marking", None)
    
    # If not found in quiz state, try to get from storage
    if neg_value is None and quiz_id:
        neg_value = get_quiz_penalty(quiz_id)
    
    for user_id, user_data in participants.items():
        user_name = user_data.get("name", f"User {user_id}")
        correct_count = user_data.get("correct", 0)
        participation_count = user_data.get("participation", user_data.get("answered", 0))
        
        # Get penalty points for this user
        penalty_points = get_user_penalties(user_id)
        
        # Calculate adjusted score with proper decimal precision
        # First ensure all values are proper floats for calculation
        correct_count_float = float(correct_count)
        penalty_points_float = float(penalty_points)
        # Calculate the difference, but don't allow negative scores
        adjusted_score = max(0.0, correct_count_float - penalty_points_float)
        # Ensure we're preserving decimal values with explicit float conversion
        
        final_scores.append({
            "user_id": user_id,
            "name": user_name,
            "correct": correct_count,
            "participation": participation_count,
            "penalty": penalty_points,
            "adjusted_score": adjusted_score,
            "neg_value": neg_value  # Store negative marking value to show in results
        })
    
    # Sort by adjusted score (highest first) and then by raw score
    final_scores.sort(key=lambda x: (x["adjusted_score"], x["correct"]), reverse=True)
    
    # Create results message
    results_message = f"🏁 The quiz has finished!\n\n{questions_count} questions answered\n\n"
    
    # Format results
    if final_scores:
        if NEGATIVE_MARKING_ENABLED:
            # Get the negative marking value from the first score entry
            neg_value_text = ""
            if final_scores and "neg_value" in final_scores[0] and final_scores[0]["neg_value"] is not None:
                neg_value = final_scores[0]["neg_value"]
                neg_value_text = f" ({neg_value} points per wrong answer)"
            
            results_message += f"❗ Negative marking was enabled for this quiz{neg_value_text}\n\n"
        
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
                # Include penalty information with formatted decimal values
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
    
    # Generate and send PDF results if the quiz had an ID
    if quiz_id and FPDF_AVAILABLE and final_scores:
        try:
            # Get winner details for PDF generation
            first_user = final_scores[0]
            user_id = first_user.get("user_id")
            user_name = first_user.get("name", f"User {user_id}")
            correct_answers = first_user.get("correct", 0)
            total_questions = questions_count
            wrong_answers = total_questions - correct_answers if "wrong" not in first_user else first_user.get("wrong", 0)
            skipped = total_questions - (correct_answers + wrong_answers)
            penalty = first_user.get("penalty", 0)
            score = correct_answers
            adjusted_score = first_user.get("adjusted_score", score - penalty)
            
            # Store results for all participants first
            for user_data in final_scores:
                user_id = user_data.get("user_id")
                user_name = user_data.get("name", f"User {user_id}")
                correct_answers = user_data.get("correct", 0)
                total_questions = questions_count
                wrong_answers = user_data.get("wrong", total_questions - correct_answers)
                skipped = total_questions - (correct_answers + wrong_answers)
                penalty = user_data.get("penalty", 0)
                score = correct_answers
                adjusted_score = user_data.get("adjusted_score", score - penalty)
                
                # Store the result for this user
                add_quiz_result(
                    quiz_id, user_id, user_name, total_questions, 
                    correct_answers, wrong_answers, skipped, 
                    penalty, score, adjusted_score
                )
            
            # Create a robust fake update object for the enhanced PDF handler
            # This implementation properly works with the reply_text method
            class FakeUpdate:
                class FakeMessage:
                    def __init__(self, chat_id, context):
                        self.chat_id = chat_id
                        self.context = context
                    
                    async def reply_text(self, text, **kwargs):
                        try:
                            # Ensure text parameter is explicitly passed first
                            logger.info(f"Sending message to {self.chat_id}: {text[:30]}...")
                            return await self.context.bot.send_message(
                                chat_id=self.chat_id, 
                                text=text, 
                                **kwargs
                            )
                        except Exception as e:
                            logger.error(f"Error in reply_text: {e}")
                            # Try a simplified approach as fallback
                            try:
                                return await self.context.bot.send_message(
                                    chat_id=self.chat_id, 
                                    text=str(text)
                                )
                            except Exception as e2:
                                logger.error(f"Failed with fallback too: {e2}")
                                return False
                
                def __init__(self, chat_id, context):
                    self.effective_chat = type('obj', (object,), {'id': chat_id})
                    # Create a proper FakeMessage instance
                    self.message = self.FakeMessage(chat_id, context)
            
            # Create with both chat_id and context
            fake_update = FakeUpdate(chat_id, context)
            
            # Use the enhanced PDF generation function
            await handle_quiz_end_with_pdf(
                fake_update, context, quiz_id, user_id, user_name,
                total_questions, correct_answers, wrong_answers,
                skipped, penalty, score, adjusted_score
            )
            
        except Exception as e:
            logger.error(f"Error generating PDF results: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ Could not generate PDF results: {str(e)}"
            )
# ---------- END QUIZ WITH PDF RESULTS MODIFICATIONS ----------

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

# ---------- PDF IMPORT FUNCTIONS ----------
def extract_text_from_pdf(pdf_file_path):
    """
    Extract text from a PDF file using PyPDF2
    Returns a list of extracted text content from each page
    """
    try:
        logger.info(f"Extracting text from PDF: {pdf_file_path}")
        
        if not PDF_SUPPORT:
            logger.warning("PyPDF2 not installed, cannot extract text from PDF.")
            return ["PyPDF2 module not available. Please install PyPDF2 to enable PDF text extraction."]
        
        extracted_text = []
        with open(pdf_file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text = page.extract_text()
                # Check for Hindi text
                if text:
                    lang = detect_language(text)
                    if lang == 'hi':
                        logger.info("Detected Hindi text in PDF")
                
                extracted_text.append(text if text else "")
        return extracted_text
    except Exception as e:
        logger.error(f"Error in direct text extraction: {e}")
        return []




def parse_questions_from_text(text_list, custom_id=None):
    """Improved parser with correct answer text and answer letter (A/B/C/D)"""
    import re
    questions = []
    question_block = []

    for page_text in text_list:
        if not page_text:
            continue
        lines = page_text.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if re.match(r'^(Q\.|\d+[:.)])', line, re.IGNORECASE):
                if question_block:
                    questions.append('\n'.join(question_block))
                    question_block = []
            question_block.append(line)

        if question_block:
            questions.append('\n'.join(question_block))
            question_block = []

    parsed_questions = []
    for block in questions:
        lines = block.split('\n')
        question_text = ""
        options = []
        answer = 0
        
        # Track if an option is marked with a checkmark or asterisk
        option_with_mark = None

        for line in lines:
            if re.match(r'^(Q\.|\d+[:.)])', line, re.IGNORECASE):
                question_text = re.sub(r'^(Q\.|\d+[:.)])\s*', '', line).strip()
            elif re.match(r'^[A-D1-4][).]', line.strip()):
                # Check if this option has a checkmark or asterisk
                option_index = len(options)
                option_text = re.sub(r'^[A-D1-4][).]\s*', '', line).strip()
                
                # Check for various marks
                if any(mark in option_text for mark in ['*', '✓', '✔', '✅']):
                    option_with_mark = option_index
                    # Clean the option text by removing the mark
                    option_text = re.sub(r'[\*✓✔✅]', '', option_text).strip()
                
                options.append(option_text)
            elif re.match(r'^(Ans|Answer|उत्तर|सही उत्तर|जवाब)[:\-\s]+', line, re.IGNORECASE):
                match = re.search(r'[ABCDabcd1-4]', line)
                if match:
                    answer_char = match.group().upper()
                    answer = {'A': 0, '1': 0, 'B': 1, '2': 1, 'C': 2, '3': 2, 'D': 3, '4': 3}.get(answer_char, 0)

        if question_text and len(options) >= 2:
            # Use option_with_mark if it was detected
            if option_with_mark is not None:
                answer = option_with_mark
                
            parsed_questions.append({
                'question': question_text,
                'options': options,
                'answer': answer,
                'answer_option': ['A', 'B', 'C', 'D'][answer] if answer < 4 else "A",
                'correct_answer': options[answer] if answer < len(options) else "",
                'category': 'General Knowledge'
            })

    return parsed_questions
    for page_text in text_list:
        if not page_text:
            continue
        lines = page_text.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if re.match(r'^(Q\.|\d+[:.)])', line, re.IGNORECASE):
                if question_block:
                    questions.append('\n'.join(question_block))
                    question_block = []
            question_block.append(line)

        if question_block:
            questions.append('\n'.join(question_block))
            question_block = []

    parsed_questions = []
    for block in questions:
        lines = block.split('\n')
        question_text = ""
        options = []
        answer = 0

        for line in lines:
            if re.match(r'^(Q\.|\d+[:.)])', line, re.IGNORECASE):
                question_text = re.sub(r'^(Q\.|\d+[:.)])\s*', '', line).strip()
            elif re.match(r'^[A-D1-4][).]', line.strip()):
                options.append(re.sub(r'^[A-D1-4][).]\s*', '', line).strip())
            elif re.match(r'^(Ans|Answer|उत्तर)[:\-\s]+', line, re.IGNORECASE):
                match = re.search(r'[ABCDabcd1-4]', line)
                if match:
                    answer_char = match.group().upper()
                    answer = {'A': 0, '1': 0, 'B': 1, '2': 1, 'C': 2, '3': 2, 'D': 3, '4': 3}.get(answer_char, 0)

        if question_text and len(options) >= 2:
            parsed_questions.append({
                'question': question_text,
                'options': options,
                'answer': answer,
                'correct_answer': options[answer] if answer < len(options) else "",
                'category': 'General Knowledge'
            })

    return parsed_questions
    for page_text in text_list:
        if not page_text:
            continue
        lines = page_text.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if re.match(r'^(Q\.|\d+[:.)])', line, re.IGNORECASE):
                if question_block:
                    questions.append('\n'.join(question_block))
                    question_block = []
            question_block.append(line)

        if question_block:
            questions.append('\n'.join(question_block))
            question_block = []

    parsed_questions = []
    for block in questions:
        lines = block.split('\n')
        question_text = ""
        options = []
        answer = 0

        for line in lines:
            if re.match(r'^(Q\.|\d+[:.)])', line, re.IGNORECASE):
                question_text = re.sub(r'^(Q\.|\d+[:.)])\s*', '', line).strip()
            elif re.match(r'^[A-D1-4][).]', line.strip()):
                options.append(re.sub(r'^[A-D1-4][).]\s*', '', line).strip())
            elif re.match(r'^(Ans|Answer|उत्तर)[:\-\s]+', line, re.IGNORECASE):
                match = re.search(r'[ABCDabcd1-4]', line)
                if match:
                    answer_char = match.group().upper()
                    answer = {'A': 0, '1': 0, 'B': 1, '2': 1, 'C': 2, '3': 2, 'D': 3, '4': 3}.get(answer_char, 0)

        if question_text and len(options) >= 2:
            parsed_questions.append({
                'question': question_text,
                'options': options,
                'answer': answer,
                'category': 'General Knowledge'
            })

    return parsed_questions
    # Simple question pattern detection:
    # - Question starts with a number or "Q." or "Question"
    # - Options start with A), B), C), D) or similar
    # - Answer might be marked with "Ans:" or "Answer:"
    
    for page_text in text_list:
        if not page_text or not page_text.strip():
            continue
            
        lines = page_text.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Check if line starts a new question
            if (line.startswith('Q.') or 
                (line and line[0].isdigit() and len(line) > 2 and line[1:3] in ['. ', ') ', '- ']) or
                line.lower().startswith('question')):
                
                # Save previous question if exists
                if current_question and 'question' in current_question and 'options' in current_question:
                    if len(current_question['options']) >= 2:  # Must have at least 2 options
                        questions.append(current_question)
                
                # Start a new question
                current_question = {
                    'question': line,
                    'options': [],
                    'answer': None,
                    'category': 'General Knowledge'  # Default category
                }
                
                # Collect question text that may span multiple lines
                j = i + 1
                option_detected = False
                while j < len(lines) and not option_detected:
                    next_line = lines[j].strip()
                    # Check if this line starts an option
                    if (next_line.startswith('A)') or next_line.startswith('A.') or
                        next_line.startswith('a)') or next_line.startswith('1)') or
                        next_line.startswith('B)') or next_line.startswith('B.')):
                        option_detected = True
                    else:
                        current_question['question'] += ' ' + next_line
                        j += 1
                
                i = j - 1 if option_detected else j  # Adjust index to continue from option lines or next line
            
            # Check for options
            
            elif current_question and re.match(r"^(ans|answer|correct answer)[:\- ]", line.strip(), re.IGNORECASE):
                # Extract option letter from the answer line using regex
                match = re.search(r"[ABCDabcd1-4]", line)
                if match:
                    char = match.group().upper()
                    current_question['answer'] = {
                        'A': 0, '1': 0,
                        'B': 1, '2': 1,
                        'C': 2, '3': 2,
                        'D': 3, '4': 3
                    }.get(char, 0)
    
            i += 1
    
    # Add the last question if it exists
    if current_question and 'question' in current_question and 'options' in current_question:
        if len(current_question['options']) >= 2:
            questions.append(current_question)
    
    # Post-process questions
    processed_questions = []
    for q in questions:
        # If no correct answer is identified, default to first option
        if q['answer'] is None:
            q['answer'] = 0
        
        # Clean up the question text
        q['question'] = q['question'].replace('Q.', '').replace('Question:', '').strip()
        
        # Clean up option texts
        cleaned_options = []
        for opt in q['options']:
            # Remove option identifiers (A), B), etc.)
            if opt and opt[0].isalpha() and len(opt) > 2 and opt[1] in [')', '.', '-']:
                opt = opt[2:].strip()
            elif opt and opt[0].isdigit() and len(opt) > 2 and opt[1] in [')', '.', '-']:
                opt = opt[2:].strip()
            cleaned_options.append(opt)
        
        q['options'] = cleaned_options
        
        # Only include questions with adequate options
        if len(q['options']) >= 2:
            processed_questions.append(q)
            
    # Log how many questions were extracted
    logger.info(f"Extracted {len(processed_questions)} questions from PDF")
    
    return processed_questions

async def pdf_import_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the PDF import process."""
    await update.message.reply_text(
        "📚 Let's import questions from a PDF file!\n\n"
        "Send me the PDF file you want to import questions from."
    )
    return PDF_UPLOAD

async def pdf_file_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the PDF file upload."""
    # Check if a document was received
    if not update.message.document:
        await update.message.reply_text("Please send a PDF file.")
        return PDF_UPLOAD
    
    # Check if it's a PDF file
    file = update.message.document
    if not file.file_name.lower().endswith('.pdf'):
        await update.message.reply_text("Please send a PDF file (with .pdf extension).")
        return PDF_UPLOAD
    
    # Ask for a custom ID
    await update.message.reply_text(
        "Please provide a custom ID for these questions.\n"
        "All questions from this PDF will be saved under this ID.\n"
        "Enter a number or a short text ID (e.g., 'science_quiz' or '42'):"
    )
    
    # Store the file ID for later download
    context.user_data['pdf_file_id'] = file.file_id
    return PDF_CUSTOM_ID

async def pdf_custom_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the custom ID input for PDF questions."""
    custom_id = update.message.text.strip()
    
    # Validate the custom ID
    if not custom_id:
        await update.message.reply_text("Please provide a valid ID.")
        return PDF_CUSTOM_ID
    
    # Store the custom ID
    context.user_data['pdf_custom_id'] = custom_id
    
    # Let user know we're processing the PDF
    status_message = await update.message.reply_text(
        "⏳ Processing the PDF file. This may take a moment..."
    )
    
    # Store the status message ID for updating
    context.user_data['status_message_id'] = status_message.message_id
    
    # Download and process the PDF file
    return await process_pdf_file(update, context)

async def process_pdf_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the PDF file and extract questions."""
    try:
        # Get file ID and custom ID from user data
        file_id = context.user_data.get('pdf_file_id')
        custom_id = context.user_data.get('pdf_custom_id')
        
        if not file_id or not custom_id:
            await update.message.reply_text("Error: Missing file or custom ID information.")
            return ConversationHandler.END
        
        # Check if PDF support is available
        if not PDF_SUPPORT:
            await update.message.reply_text(
                "❌ PDF support is not available. Please install PyPDF2 module.\n"
                "You can run: pip install PyPDF2"
            )
            return ConversationHandler.END
        
        # Download the file
        file = await context.bot.get_file(file_id)
        pdf_file_path = os.path.join(TEMP_DIR, f"{custom_id}_import.pdf")
        await file.download_to_drive(pdf_file_path)
        
        # Update status message
        status_message_id = context.user_data.get('status_message_id')
        if status_message_id:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_message_id,
                text="⏳ PDF downloaded. Extracting text and questions..."
            )
        
        # Extract text from PDF
        extracted_text_list = group_and_deduplicate_questions(extract_text_from_pdf(pdf_file_path))
        
        # Update status message
        if status_message_id:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_message_id,
                text="⏳ Text extracted. Parsing questions..."
            )
        
        # Parse questions from the extracted text
        questions = parse_questions_from_text(extracted_text_list, custom_id)
        
        # Clean up temporary files
        if os.path.exists(pdf_file_path):
            os.remove(pdf_file_path)
        
        # Check if we found any questions
        if not questions:
            await update.message.reply_text(
                "❌ No questions could be extracted from the PDF.\n"
                "Please make sure the PDF contains properly formatted questions and options."
            )
            return ConversationHandler.END
        
        # Update status message
        if status_message_id:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_message_id,
                text=f"✅ Found {len(questions)} questions! Saving to the database..."
            )
        
        # Save the questions under the custom ID
        all_questions = load_questions()
        
        # Prepare the questions data structure
        if custom_id not in all_questions:
            all_questions[custom_id] = []
        
        # Check if all_questions[custom_id] is a list
        if not isinstance(all_questions[custom_id], list):
            all_questions[custom_id] = [all_questions[custom_id]]
            
        # Add all extracted questions to the custom ID
        all_questions[custom_id].extend(questions)
        
        # Save the updated questions
        save_questions(all_questions)
        
        # Send completion message
        await update.message.reply_text(
            f"✅ Successfully imported {len(questions)} questions from the PDF!\n\n"
            f"They have been saved under the custom ID: '{custom_id}'\n\n"
            f"You can start a quiz with these questions using:\n"
            f"/quizid {custom_id}"
        )
        
        # End the conversation
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        await update.message.reply_text(
            f"❌ An error occurred while processing the PDF: {str(e)}\n"
            "Please try again or use a different PDF file."
        )
        return ConversationHandler.END

async def show_negative_marking_options(update: Update, context: ContextTypes.DEFAULT_TYPE, quiz_id, questions=None):
    """Show negative marking options for a quiz"""
    # Create more organized inline keyboard with advanced negative marking options
    keyboard = []
    row = []
    
    # Log the quiz ID for debugging
    logger.info(f"Showing negative marking options for quiz_id: {quiz_id}")
    logger.info(f"Question count: {len(questions) if questions else 0}")
    
    # Format buttons in rows of 3
    for i, (label, value) in enumerate(ADVANCED_NEGATIVE_MARKING_OPTIONS):
        # Create a new row every 3 buttons
        if i > 0 and i % 3 == 0:
            keyboard.append(row)
            row = []
            
        # Create callback data with quiz_id preserved exactly as is
        # No matter what format quiz_id has
        if value == "custom":
            callback_data = f"negmark_{quiz_id}_custom"
        else:
            callback_data = f"negmark_{quiz_id}_{value}"
        
        # Log callback data for debugging
        logger.info(f"Creating button with callback_data: {callback_data}")
            
        row.append(InlineKeyboardButton(label, callback_data=callback_data))
    
    # Add any remaining buttons
    if row:
        keyboard.append(row)
        
    # Add a cancel button
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"negmark_cancel")])
    
    # Get question count
    question_count = len(questions) if questions and isinstance(questions, list) else 0
    
    # Send message with quiz details
    await update.message.reply_text(
        f"🔢 *Select Negative Marking Value*\n\n"
        f"Quiz ID: `{quiz_id}`\n"
        f"Total questions: {question_count}\n\n"
        f"How many points should be deducted for wrong answers?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Ensure quiz_id is exactly preserved in context key
    key = f"temp_quiz_{quiz_id}_questions"
    logger.info(f"Storing questions under key: {key}")
    
    # Store questions in context for later use after user selects negative marking
    if questions:
        # Store quiz_id as is without modifications
        context.user_data[key] = questions

async def negative_marking_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback queries from negative marking selection"""
    query = update.callback_query
    await query.answer()
    
    # Extract data from callback
    full_data = query.data
    logger.info(f"Full callback data: {full_data}")
    
    # Special handling for cancel operation
    if full_data == "negmark_cancel":
        await query.edit_message_text("❌ Quiz canceled.")
        return
    
    # Split data more carefully to preserve quiz ID
    # Format: "negmark_{quiz_id}_{value}"
    if full_data.count("_") < 2:
        await query.edit_message_text("❌ Invalid callback data format. Please try again.")
        return
    
    # Extract command, quiz_id and value
    first_underscore = full_data.find("_")
    last_underscore = full_data.rfind("_")
    
    command = full_data[:first_underscore]  # Should be "negmark"
    neg_value_or_custom = full_data[last_underscore+1:]  # Value is after the last underscore
    quiz_id = full_data[first_underscore+1:last_underscore]  # Quiz ID is everything in between
    
    logger.info(f"Parsed callback data: command={command}, quiz_id={quiz_id}, value={neg_value_or_custom}")
    
    # Handle custom negative marking value request
    if neg_value_or_custom == "custom":
        # Ask for custom value
        await query.edit_message_text(
            f"Please enter a custom negative marking value for quiz {quiz_id}.\n\n"
            f"Enter a number between 0 and 2.0 (can include decimal points, e.g., 0.75).\n"
            f"0 = No negative marking\n"
            f"0.33 = 1/3 point deducted per wrong answer\n"
            f"1.0 = 1 full point deducted per wrong answer\n\n"
            f"Type your value and send it as a message."
        )
        
        # Store in context that we're waiting for custom value
        context.user_data["awaiting_custom_negmark"] = True
        context.user_data["custom_negmark_quiz_id"] = quiz_id
        return
    
    try:
        # Regular negative marking value
        neg_value = float(neg_value_or_custom)
        
        # Save the selected negative marking value for this quiz
        set_quiz_penalty(quiz_id, neg_value)
        
        # Get the questions for this quiz
        questions = context.user_data.get(f"temp_quiz_{quiz_id}_questions", [])
        
        if not questions or len(questions) == 0:
            await query.edit_message_text(
                f"❌ Error: No questions found for quiz ID: {quiz_id}\n"
                f"This could be due to a parsing error or missing questions.\n"
                f"Please check your quiz ID and try again."
            )
            return
        
        # Log question count to debug issues
        logger.info(f"Starting quiz with {len(questions)} questions for ID {quiz_id}")
        
        # Clean up temporary data
        if f"temp_quiz_{quiz_id}_questions" in context.user_data:
            del context.user_data[f"temp_quiz_{quiz_id}_questions"]
        
        # Start the quiz
        await start_quiz_with_negative_marking(update, context, quiz_id, questions, neg_value)
    except ValueError as e:
        # Handle any parsing errors
        logger.error(f"Error parsing negative marking value: {e}")
        await query.edit_message_text(f"❌ Invalid negative marking value. Please try again.")
    except Exception as e:
        # Handle any other errors
        logger.error(f"Error in negative marking callback: {e}")
        await query.edit_message_text(f"❌ An error occurred: {str(e)}. Please try again.")

async def handle_custom_negative_marking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle custom negative marking value input"""
    if not context.user_data.get("awaiting_custom_negmark", False):
        return
    
    try:
        # Parse the custom value
        custom_value = float(update.message.text.strip())
        
        # Validate range (0 to 2.0)
        if custom_value < 0 or custom_value > 2.0:
            await update.message.reply_text(
                "⚠️ Value must be between 0 and 2.0. Please try again."
            )
            return
            
        # Get the quiz ID
        quiz_id = context.user_data.get("custom_negmark_quiz_id")
        if not quiz_id:
            await update.message.reply_text("❌ Error: Quiz ID not found. Please start over.")
            return
            
        # Clean up context
        del context.user_data["awaiting_custom_negmark"]
        del context.user_data["custom_negmark_quiz_id"]
        
        # Save the custom negative marking value
        set_quiz_penalty(quiz_id, custom_value)
        
        # Get questions for this quiz
        questions = context.user_data.get(f"temp_quiz_{quiz_id}_questions", [])
        
        # Clean up
        if f"temp_quiz_{quiz_id}_questions" in context.user_data:
            del context.user_data[f"temp_quiz_{quiz_id}_questions"]
        
        # Confirm and start quiz
        await update.message.reply_text(
            f"✅ Custom negative marking set to {custom_value} for quiz {quiz_id}.\n"
            f"Starting quiz with {len(questions)} questions..."
        )
        
        # Initialize quiz in chat data
        chat_id = update.effective_chat.id
        user = update.effective_user
        
        # Initialize quiz state
        context.chat_data["quiz"] = {
            "active": True,
            "current_index": 0,
            "questions": questions,
            "sent_polls": {},
            "participants": {},
            "chat_id": chat_id,
            "creator": {
                "id": user.id,
                "name": user.first_name,
                "username": user.username
            },
            "negative_marking": custom_value,  # Store custom negative marking value
            "quiz_id": quiz_id  # Store quiz ID for reference
        }
        
        # Send first question with slight delay
        await asyncio.sleep(1)
        await send_question(context, chat_id, 0)
        
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid value. Please enter a valid number (e.g., 0.5, 1.0, 1.25)."
        )
    except Exception as e:
        logger.error(f"Error in custom negative marking: {e}")
        await update.message.reply_text(
            f"❌ An error occurred: {str(e)}. Please try again."
        )

async def start_quiz_with_negative_marking(update: Update, context: ContextTypes.DEFAULT_TYPE, quiz_id, questions, neg_value):
    """Start a quiz with custom negative marking value"""
    query = update.callback_query
    chat_id = query.message.chat_id
    user = query.from_user
    
    # Initialize quiz state
    context.chat_data["quiz"] = {
        "active": True,
        "current_index": 0,
        "questions": questions,
        "sent_polls": {},
        "participants": {},
        "chat_id": chat_id,
        "creator": {
            "id": user.id,
            "name": user.first_name,
            "username": user.username
        },
        "negative_marking": neg_value,  # Store negative marking value in quiz state
        "quiz_id": quiz_id  # Store quiz ID for reference
    }
    
    # Update the message to show the selected negative marking
    neg_text = f"{neg_value}" if neg_value > 0 else "No negative marking"
    await query.edit_message_text(
        f"✅ Starting quiz with ID: {quiz_id}\n"
        f"📝 Total questions: {len(questions)}\n"
        f"⚠️ Negative marking: {neg_text}\n\n"
        f"First question coming up..."
    )
    
    # Send first question with slight delay
    await asyncio.sleep(2)
    await send_question(context, chat_id, 0)

async def quiz_with_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a quiz with questions from a specific ID."""
    # Check if an ID was provided
    if not context.args or not context.args[0]:
        await update.message.reply_text(
            "Please provide an ID to start a quiz with.\n"
            "Example: /quizid science_quiz"
        )
        return
    
    # Get the full ID by joining all arguments (in case ID contains spaces)
    quiz_id = " ".join(context.args)
    logger.info(f"Starting quiz with ID: {quiz_id}")
    
    # Load all questions
    all_questions = load_questions()
    
    # Check if the ID exists
    if quiz_id not in all_questions:
        await update.message.reply_text(
            f"❌ No questions found with ID: '{quiz_id}'\n"
            "Please check the ID and try again."
        )
        return
    
    # Get questions for the given ID
    questions = all_questions[quiz_id]
    
    # If it's not a list, convert it to a list
    if not isinstance(questions, list):
        questions = [questions]
    
    # Check if there are any questions
    if not questions:
        await update.message.reply_text(
            f"❌ No questions found with ID: '{quiz_id}'\n"
            "Please check the ID and try again."
        )
        return
    
    # Show negative marking options
    await show_negative_marking_options(update, context, quiz_id, questions)

async def pdf_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show information about PDF import feature."""
    pdf_support_status = "✅ AVAILABLE" if PDF_SUPPORT else "❌ NOT AVAILABLE"
    image_support_status = "✅ AVAILABLE" if IMAGE_SUPPORT else "❌ NOT AVAILABLE"
    
    info_text = (
        "📄 PDF Import Feature Guide\n\n"
        f"PDF Support: {pdf_support_status}\n"
        f"Image Processing: {image_support_status}\n\n"
        "Use the /pdfimport command to import questions from a PDF file.\n\n"
        "How it works:\n"
        "1. The bot will ask you to upload a PDF file.\n"
        "2. Send a PDF file containing questions and options.\n"
        "3. Provide a custom ID to save all questions from this PDF.\n"
        "4. The bot will extract questions and detect Hindi text if present.\n"
        "5. All extracted questions will be saved under your custom ID.\n\n"
        "PDF Format Tips:\n"
        "- Questions should start with 'Q.', a number, or 'Question:'\n"
        "- Options should be labeled as A), B), C), D) or 1), 2), 3), 4)\n"
        "- Answers can be indicated with 'Ans:' or 'Answer:'\n"
        "- Hindi text is fully supported\n\n"
        "To start a quiz with imported questions, use:\n"
        "/quizid YOUR_CUSTOM_ID"
    )
    await update.message.reply_text(info_text)

# ====== /stop command ======
async def stop_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    quiz = context.chat_data.get("quiz", {})

    if quiz.get("active", False):
        quiz["active"] = False
        context.chat_data["quiz"] = quiz
        await update.message.reply_text("✅ Quiz has been stopped.")
    else:
        await update.message.reply_text("ℹ️ No quiz is currently running.")

# ---------- TXT IMPORT COMMAND HANDLERS ----------
async def txtimport_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the text import process"""
    await update.message.reply_text(
        "📄 <b>Text File Import Wizard</b>\n\n"
        "Please upload a <b>.txt file</b> containing quiz questions.\n\n"
        "<b>File Format:</b>\n"
        "• Questions MUST end with a question mark (?) to be detected\n"
        "• Questions should start with 'Q1.' or '1.' format (e.g., 'Q1. What is...?')\n"
        "• Options should be labeled as A), B), C), D) with one option per line\n"
        "• Correct answer can be indicated with:\n"
        "  - Asterisk after option: B) Paris*\n"
        "  - Check marks after option: C) Berlin✓ or C) Berlin✔ or C) Berlin✅\n"
        "  - Answer line: Ans: B or Answer: B\n"
        "  - Hindi format: उत्तर: B or सही उत्तर: B\n\n"
        "<b>English Example:</b>\n"
        "Q1. What is the capital of France?\n"
        "A) London\n"
        "B) Paris*\n"
        "C) Berlin\n"
        "D) Rome\n\n"
        "<b>Hindi Example:</b>\n"
        "Q1. भारत की राजधानी कौन सी है?\n"
        "A) मुंबई\n"
        "B) दिल्ली\n"
        "C) कोलकाता\n"
        "D) चेन्नई\n"
        "उत्तर: B\n\n"
        "Send /cancel to abort the import process.",
        parse_mode='HTML'
    )
    return TXT_UPLOAD

async def receive_txt_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle text file upload - more robust implementation"""
    try:
        # Check if the message contains a document
        if not update.message.document:
            await update.message.reply_text(
                "❌ Please upload a text file (.txt)\n"
                "Try again or /cancel to abort."
            )
            return TXT_UPLOAD
    
        # Check if it's a text file
        file = update.message.document
        if not file.file_name.lower().endswith('.txt'):
            await update.message.reply_text(
                "❌ Only .txt files are supported.\n"
                "Please upload a text file or /cancel to abort."
            )
            return TXT_UPLOAD
    
        # Download the file
        status_message = await update.message.reply_text("⏳ Downloading file...")
        
        # Ensure temp directory exists
        os.makedirs(TEMP_DIR, exist_ok=True)
        logger.info(f"Temporary directory: {os.path.abspath(TEMP_DIR)}")
        
        try:
            # Get the file from Telegram
            new_file = await context.bot.get_file(file.file_id)
            
            # Create a unique filename with timestamp to avoid collisions
            import time
            timestamp = int(time.time())
            file_path = os.path.join(TEMP_DIR, f"{timestamp}_{file.file_id}_{file.file_name}")
            logger.info(f"Saving file to: {file_path}")
            
            # Download the file
            await new_file.download_to_drive(file_path)
            logger.info(f"File downloaded successfully to {file_path}")
            
            # Verify file exists and has content
            if not os.path.exists(file_path):
                logger.error(f"File download failed - file does not exist at {file_path}")
                await update.message.reply_text("❌ File download failed. Please try again.")
                return TXT_UPLOAD
                
            if os.path.getsize(file_path) == 0:
                logger.error(f"Downloaded file is empty: {file_path}")
                await update.message.reply_text("❌ The uploaded file is empty. Please provide a file with content.")
                os.remove(file_path)
                return TXT_UPLOAD
                
            # Update status message
            await status_message.edit_text("✅ File downloaded successfully!")
            
            # Store the file path in context
            context.user_data['txt_file_path'] = file_path
            context.user_data['txt_file_name'] = file.file_name
            
            # Generate automatic ID based on filename and timestamp
            # Create a sanitized version of the filename (remove spaces and special chars)
            base_filename = os.path.splitext(file.file_name)[0]
            sanitized_name = ''.join(c if c.isalnum() or c == '_' else '_' for c in base_filename)
            
            # Use a more distinctive format to avoid parsing issues
            auto_id = f"txt_{timestamp}_quiz_{sanitized_name}"
            logger.info(f"Generated automatic ID: {auto_id}")
            
            # Store the auto ID in context
            context.user_data['txt_custom_id'] = auto_id
            
            # Notify user that processing has begun
            await update.message.reply_text(
                f"⏳ Processing text file with auto-generated ID: <b>{auto_id}</b>...\n"
                "This may take a moment depending on the file size.",
                parse_mode='HTML'
            )
            
            # Process file directly instead of asking for custom ID, but must return END
            await process_txt_file(update, context)
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            await update.message.reply_text(f"❌ Download failed: {str(e)}. Please try again.")
            return TXT_UPLOAD
            
    except Exception as e:
        logger.error(f"Unexpected error in receive_txt_file: {e}")
        await update.message.reply_text(
            "❌ An unexpected error occurred while processing your upload.\n"
            "Please try again or contact the administrator."
        )
        return TXT_UPLOAD

async def set_custom_id_txt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Set custom ID for the imported questions from text file and process the file immediately"""
    custom_id = update.message.text.strip()
    
    # Log the received custom ID for debugging
    logger.info(f"Received custom ID: {custom_id}, Type: {type(custom_id)}")
    
    # Basic validation for the custom ID
    if not custom_id or ' ' in custom_id:
        await update.message.reply_text(
            "❌ Invalid ID. Please provide a single word without spaces.\n"
            "Try again or /cancel to abort."
        )
        return TXT_CUSTOM_ID
    
    # Convert the custom_id to a string to handle numeric IDs properly
    custom_id = str(custom_id)
    logger.info(f"After conversion: ID={custom_id}, Type={type(custom_id)}")
    
    # Store the custom ID
    context.user_data['txt_custom_id'] = custom_id
    
    # Get file path from context
    file_path = context.user_data.get('txt_file_path')
    logger.info(f"File path from context: {file_path}")
    
    try:
        # Send processing message
        await update.message.reply_text(
            f"⏳ Processing text file with ID: <b>{custom_id}</b>...\n"
            "This may take a moment depending on the file size.",
            parse_mode='HTML'
        )
        
        # Validate file path
        if not file_path or not os.path.exists(file_path):
            logger.error(f"File not found at path: {file_path}")
            await update.message.reply_text("❌ File not found or download failed. Please try uploading again.")
            return ConversationHandler.END
        
        # Read the text file with proper error handling
        try:
            logger.info(f"Attempting to read file: {file_path}")
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                logger.info(f"Successfully read file with UTF-8 encoding, content length: {len(content)}")
        except UnicodeDecodeError:
            # Try with another encoding if UTF-8 fails
            try:
                logger.info("UTF-8 failed, trying UTF-16")
                with open(file_path, 'r', encoding='utf-16') as f:
                    content = f.read()
                    logger.info(f"Successfully read file with UTF-16 encoding, content length: {len(content)}")
            except UnicodeDecodeError:
                # If both fail, try latin-1 which should accept any bytes
                logger.info("UTF-16 failed, trying latin-1")
                with open(file_path, 'r', encoding='latin-1') as f:
                    content = f.read()
                    logger.info(f"Successfully read file with latin-1 encoding, content length: {len(content)}")
        
        # Detect if text contains Hindi
        lang = detect_language(content)
        logger.info(f"Language detected: {lang}")
        
        # Split file into lines and count them
        lines = content.splitlines()
        logger.info(f"Split content into {len(lines)} lines")
        
        # Extract questions
        logger.info("Starting question extraction...")
        questions = extract_questions_from_txt(lines)
        logger.info(f"Extracted {len(questions)} questions")
        
        if not questions:
            logger.warning("No valid questions found in the text file")
            await update.message.reply_text(
                "❌ No valid questions found in the text file.\n"
                "Please check the file format and try again."
            )
            # Clean up
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Removed file: {file_path}")
            return ConversationHandler.END
        
        # Save questions with the custom ID
        logger.info(f"Adding {len(questions)} questions with ID: {custom_id}")
        added = add_questions_with_id(custom_id, questions)
        logger.info(f"Added {added} questions with ID: {custom_id}")
        
        # Clean up
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Removed file: {file_path}")
        
        # Send completion message
        logger.info("Sending completion message")
        await update.message.reply_text(
            f"✅ Successfully imported <b>{len(questions)}</b> questions with ID: <b>{custom_id}</b>\n\n"
            f"Language detected: <b>{lang}</b>\n\n"
            f"To start a quiz with these questions, use:\n"
            f"<code>/quizid {custom_id}</code>",
            parse_mode='HTML'
        )
        
        logger.info("Text import process completed successfully")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}", exc_info=True)
        try:
            await update.message.reply_text(
                f"❌ An error occurred during import: {str(e)}\n"
                "Please try again or contact the administrator."
            )
        except Exception as msg_error:
            logger.error(f"Error sending error message: {str(msg_error)}")
            
        # Clean up any temporary files on error
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Removed file: {file_path}")
            except Exception as cleanup_error:
                logger.error(f"Error removing file: {str(cleanup_error)}")
                
        return ConversationHandler.END

async def process_txt_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the uploaded text file and extract questions"""
    # Retrieve file path and custom ID from context
    file_path = context.user_data.get('txt_file_path')
    custom_id = context.user_data.get('txt_custom_id')
    
    # Ensure custom_id is treated as a string
    if custom_id is not None:
        custom_id = str(custom_id)
    
    logger.info(f"Processing txt file. Path: {file_path}, ID: {custom_id}")
    
    # Early validation
    if not file_path:
        logger.error("No file path found in context")
        if update.message:
            await update.message.reply_text("❌ File path not found. Please try uploading again.")
        return ConversationHandler.END
    
    if not os.path.exists(file_path):
        logger.error(f"File does not exist at path: {file_path}")
        if update.message:
            await update.message.reply_text("❌ File not found on disk. Please try uploading again.")
        return ConversationHandler.END
    
    # Use the original message that started the conversation if the current update doesn't have a message
    message_obj = update.message if update.message else update.effective_chat
    
    # Read the text file
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        # Try with another encoding if UTF-8 fails
        try:
            with open(file_path, 'r', encoding='utf-16') as f:
                content = f.read()
        except UnicodeDecodeError:
            # If both fail, try latin-1 which should accept any bytes
            with open(file_path, 'r', encoding='latin-1') as f:
                content = f.read()
    
    # Detect if text contains Hindi
    lang = detect_language(content)
    
    # Split file into lines
    lines = content.splitlines()
    
    # Extract questions
    questions = extract_questions_from_txt(lines)
    
    if not questions:
        error_msg = "❌ No valid questions found in the text file.\nPlease check the file format and try again."
        if hasattr(message_obj, "reply_text"):
            await message_obj.reply_text(error_msg)
        else:
            await context.bot.send_message(chat_id=message_obj.id, text=error_msg)
        
        # Clean up
        if os.path.exists(file_path):
            os.remove(file_path)
        return ConversationHandler.END
    
    # Save questions with the custom ID
    added = add_questions_with_id(custom_id, questions)
    logger.info(f"Added {added} questions with ID: {custom_id}")
    
    # Clean up
    if os.path.exists(file_path):
        os.remove(file_path)
    
    # Send completion message
    success_msg = (
        f"✅ Successfully imported <b>{len(questions)}</b> questions with ID: <b>{custom_id}</b>\n\n"
        f"Language detected: <b>{lang}</b>\n\n"
        f"To start a quiz with these questions, use:\n"
        f"<code>/quizid {custom_id}</code>"
    )
    
    try:
        if hasattr(message_obj, "reply_text"):
            await message_obj.reply_text(success_msg, parse_mode='HTML')
        else:
            await context.bot.send_message(
                chat_id=message_obj.id, 
                text=success_msg,
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"Failed to send completion message: {e}")
        # Try one more time without parse_mode as fallback
        try:
            plain_msg = f"✅ Successfully imported {len(questions)} questions with ID: {custom_id}. Use /quizid {custom_id} to start a quiz."
            await context.bot.send_message(chat_id=update.effective_chat.id, text=plain_msg)
        except Exception as e2:
            logger.error(f"Final attempt to send message failed: {e2}")
    
    return ConversationHandler.END

async def txtimport_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the import process"""
    # Clean up any temporary files
    file_path = context.user_data.get('txt_file_path')
    if file_path and os.path.exists(file_path):
        os.remove(file_path)
    
    await update.message.reply_text(
        "❌ Text import process cancelled.\n"
        "You can start over with /txtimport"
    )
    return ConversationHandler.END

def extract_questions_from_txt(lines):
    """
    Extract questions, options, and answers from text file lines
    Returns a list of question dictionaries with text truncated to fit Telegram limits
    Specially optimized for Hindi/Rajasthani quiz formats with numbered options and checkmarks
    """
    questions = []
    
    # Telegram character limits
    MAX_QUESTION_LENGTH = 290  # Telegram limit for poll questions is 300, leaving 10 for safety
    MAX_OPTION_LENGTH = 97     # Telegram limit for poll options is 100, leaving 3 for safety
    MAX_OPTIONS_COUNT = 10     # Telegram limit for number of poll options
    
    # Define patterns for specific quiz format: numbered options with checkmarks (✓, ✅)
    # This pattern matches lines like "(1) Option text" or "1. Option text" or "1 Option text"
    numbered_option_pattern = re.compile(r'^\s*\(?(\d+)\)?[\.\s]\s*(.*?)\s*$', re.UNICODE)
    
    # This pattern specifically detects options with checkmarks
    option_with_checkmark = re.compile(r'.*[✓✅].*$', re.UNICODE)
    
    # Patterns to filter out metadata/promotional lines
    skip_patterns = [
        r'^\s*RT:.*',    # Retweet marker
        r'.*<ggn>.*',    # HTML-like tags
        r'.*Ex:.*',      # Example marker
        r'.*@\w+.*',     # Twitter/Telegram handles
        r'.*\bBy\b.*',   # Credit line
        r'.*https?://.*', # URLs
        r'.*t\.me/.*'    # Telegram links
    ]
    
    # Process the file by blocks (each block is a question with its options)
    # Each block typically starts with a question and is followed by options
    current_block = []
    blocks = []
    
    # Group the content into blocks separated by empty lines
    for line in lines:
        line = line.strip()
        
        # Skip empty lines, use them as block separators
        if not line:
            if current_block:
                blocks.append(current_block)
                current_block = []
            continue
            
        # Skip metadata/promotional lines
        should_skip = False
        for pattern in skip_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                should_skip = True
                break
                
        if should_skip:
            continue
            
        # Add the line to the current block
        current_block.append(line)
    
    # Add the last block if it exists
    if current_block:
        blocks.append(current_block)
    
    # Process each block to extract questions and options
    for block in blocks:
        if not block:
            continue
        
        # The first line is almost always the question
        question_text = block[0]
        
        # Clean the question text
        # Only keep the actual question - remove any trailing text that might be option-like
        # First, check if there's a question mark - if so, keep only text up to the question mark
        if "?" in question_text:
            question_text = question_text.split("?")[0] + "?"
        
        # Additionally, remove any option-like patterns that may have been included
        question_text = re.sub(r'\(\d+\).*$', '', question_text).strip()
        question_text = re.sub(r'\d+\..*$', '', question_text).strip()
        
        # Make absolutely sure we're not including any option text after the question
        if " " in question_text and len(question_text.split()) > 5:
            words = question_text.split()
            # Check if the last word might be an option
            if len(words[-1]) < 10 and not any(char in words[-1] for char in "?।"):
                question_text = " ".join(words[:-1])
        
        # If the question is too long, truncate it
        if len(question_text) > MAX_QUESTION_LENGTH:
            question_text = question_text[:MAX_QUESTION_LENGTH-3] + "..."
        
        # Process the remaining lines as options
        options = []
        correct_answer = 0  # Default to first option
        has_correct_marked = False
        
        for i, line in enumerate(block[1:]):
            # Skip any promotional/metadata lines within the block
            should_skip = False
            for pattern in skip_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    should_skip = True
                    break
                    
            if should_skip:
                continue
            
            # Check if this is a numbered option
            option_match = numbered_option_pattern.match(line)
            
            if option_match:
                # Extract the option number and text
                option_num = int(option_match.group(1))
                option_text = option_match.group(2).strip()
                
                # Check if this option has a checkmark (✓, ✅)
                has_checkmark = option_with_checkmark.match(line) is not None
                
                # Remove the checkmark from the option text
                option_text = re.sub(r'[✓✅]', '', option_text).strip()
                
                # If the option is too long, truncate it
                if len(option_text) > MAX_OPTION_LENGTH:
                    option_text = option_text[:MAX_OPTION_LENGTH-3] + "..."
                
                # Ensure the options list has enough slots
                while len(options) < option_num:
                    options.append("")
                
                # Add the option text (using 1-based indexing)
                options[option_num-1] = option_text
                
                # If this option has a checkmark, mark it as the correct answer
                if has_checkmark:
                    correct_answer = option_num - 1  # Convert to 0-based for internal use
                    has_correct_marked = True
            else:
                # This might be an unnumbered option or part of the question
                # Check if it has a checkmark
                has_checkmark = option_with_checkmark.match(line) is not None
                
                # Clean the text
                option_text = re.sub(r'[✓✅]', '', line).strip()
                
                # Always treat lines after the question as options, not part of the question text
                if len(option_text) > MAX_OPTION_LENGTH:
                    option_text = option_text[:MAX_OPTION_LENGTH-3] + "..."
                
                options.append(option_text)
                
                # If it has a checkmark, mark it as correct
                if has_checkmark:
                    correct_answer = len(options) - 1
                    has_correct_marked = True
        
        # Only add the question if we have a question text and at least 2 options
        if question_text and len(options) >= 2:
            # Clean up options list - remove any empty options
            options = [opt for opt in options if opt]
            
            # Ensure we don't exceed Telegram's limit of 10 options
            if len(options) > MAX_OPTIONS_COUNT:
                options = options[:MAX_OPTIONS_COUNT]
            
            # Make sure the correct_answer is still valid after cleaning
            if correct_answer >= len(options):
                correct_answer = 0
            
            # Add the question to our list
            questions.append({
                "question": question_text,
                "options": options,
                "answer": correct_answer,
                "category": "Imported"
            })
    
    # If the block-based approach didn't work (no questions found),
    # fall back to line-by-line processing with a simpler approach
    if not questions:
        # Variables for simple line-by-line processing
        current_question = None
        current_options = []
        correct_answer = 0
        
        for line in lines:
            line = line.strip()
            if not line:
                # End of block, save current question if we have one
                if current_question and len(current_options) >= 2:
                    questions.append({
                        "question": current_question[:MAX_QUESTION_LENGTH],
                        "options": current_options[:MAX_OPTIONS_COUNT],
                        "answer": correct_answer if correct_answer < len(current_options) else 0,
                        "category": "Imported"
                    })
                    current_question = None
                    current_options = []
                    correct_answer = 0
                continue
                
            # Skip promotional/metadata content
            should_skip = False
            for pattern in skip_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    should_skip = True
                    break
            if should_skip:
                continue
                
            # Check if this is a numbered option
            option_match = numbered_option_pattern.match(line)
            
            # If we don't have a question yet, this line becomes our question
            if current_question is None:
                # Check if line is a numbered option - if so, it's not a question
                if option_match:
                    # Skip, we need a question first
                    continue
                    
                # This line is our question
                current_question = line
                
                # If there's a question mark, keep only text up to the question mark
                if "?" in current_question:
                    current_question = current_question.split("?")[0] + "?"
                
                continue
                
            # If we already have a question, check if this is a numbered option
            if option_match:
                option_num = int(option_match.group(1))
                option_text = option_match.group(2).strip()
                
                # Check if this option has a checkmark
                has_checkmark = '✓' in line or '✅' in line
                
                # Remove checkmark from option text
                option_text = re.sub(r'[✓✅]', '', option_text).strip()
                
                # If option is too long, truncate it
                if len(option_text) > MAX_OPTION_LENGTH:
                    option_text = option_text[:MAX_OPTION_LENGTH-3] + "..."
                
                # Make sure options list has space for this option
                while len(current_options) < option_num:
                    current_options.append("")
                
                # Add the option (1-based indexing)
                current_options[option_num-1] = option_text
                
                # If it has a checkmark, it's the correct answer
                if has_checkmark:
                    correct_answer = option_num - 1
            else:
                # This might be an answer indicator like "उत्तर: B"
                answer_match = re.match(r'^\s*(?:उत्तर|सही उत्तर|Ans|Answer|जवाब)[\s:\.\-]+([A-D1-4])', line, re.IGNORECASE | re.UNICODE)
                
                if answer_match:
                    answer_text = answer_match.group(1)
                    if answer_text.isdigit():
                        # Convert numeric answer (1-4) to zero-based index (0-3)
                        correct_answer = int(answer_text) - 1
                    else:
                        # Convert letter (A-D) to index (0-3)
                        try:
                            correct_answer = "ABCD".index(answer_text.upper())
                        except ValueError:
                            correct_answer = 0
                else:
                    # Not a numbered option or answer indicator
                    # Could be an unnumbered option
                    has_checkmark = '✓' in line or '✅' in line
                    
                    # Clean and add as a regular option
                    option_text = re.sub(r'[✓✅]', '', line).strip()
                    
                    # Truncate if needed
                    if len(option_text) > MAX_OPTION_LENGTH:
                        option_text = option_text[:MAX_OPTION_LENGTH-3] + "..."
                        
                    # Add to options
                    current_options.append(option_text)
                    
                    # If it has a checkmark, it's the correct answer
                    if has_checkmark:
                        correct_answer = len(current_options) - 1
        
        # Don't forget to add the last question if we have one
        if current_question and len(current_options) >= 2:
            # Final sanity check on correct_answer
            if correct_answer >= len(current_options):
                correct_answer = 0
                
            questions.append({
                "question": current_question[:MAX_QUESTION_LENGTH],
                "options": current_options[:MAX_OPTIONS_COUNT],
                "answer": correct_answer,
                "category": "Imported"
            })
    
    # Final log message about the total questions found
    logger.info(f"Extracted {len(questions)} questions from text file")
    return questions

class QuizQuestionsPDF:
    """Generates PDFs with quiz questions and correct answers"""
    
    def __init__(self):
        """Initialize the PDF generator"""
        # Ensure PDF directory exists
        ensure_pdf_directory()
    
    def generate_quiz_pdf(self, quiz_data, quiz_id):
        """Generate a PDF with quiz questions, options, and correct answers"""
        # Try ReportLab first if available
        if REPORTLAB_AVAILABLE:
            pdf_path = self.generate_quiz_pdf_reportlab(quiz_data, quiz_id)
            if pdf_path:
                return pdf_path
        
        # Fall back to FPDF if ReportLab fails or isn't available
        if FPDF_AVAILABLE:
            pdf_path = self.generate_quiz_pdf_fpdf(quiz_data, quiz_id)
            if pdf_path:
                return pdf_path
        
        # If all methods fail, return None
        logger.error("Failed to generate quiz PDF - no PDF libraries available")
        return None
    
    def generate_quiz_pdf_reportlab(self, quiz_data, quiz_id):
        """Generate PDF using ReportLab (preferred method)"""
        try:
            # Make sure ReportLab is available
            if not REPORTLAB_AVAILABLE:
                logger.error("ReportLab library not available")
                return None

            # Import necessary modules (already verified by REPORTLAB_AVAILABLE flag)
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.lib.units import inch
            
            # Generate a unique filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"quiz_{quiz_id}_{timestamp}.pdf"
            file_path = os.path.join(PDF_RESULTS_DIR, filename)
            
            # Ensure the directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Create the PDF document
            doc = SimpleDocTemplate(
                file_path,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72
            )
            
            # Define styles
            styles = getSampleStyleSheet()
            title_style = styles["Title"]
            heading_style = styles["Heading1"]
            normal_style = styles["Normal"]
            
            # Create custom style for questions
            question_style = ParagraphStyle(
                'Question',
                parent=styles['Normal'],
                fontSize=12,
                spaceAfter=6,
                spaceBefore=12,
                fontName='Helvetica-Bold'
            )
            
            # Create custom style for options
            option_style = ParagraphStyle(
                'Option',
                parent=styles['Normal'],
                fontSize=11,
                leftIndent=20,
                spaceAfter=2
            )
            
            # Content elements
            elements = []
            
            # Add title
            title = Paragraph(f"Quiz #{quiz_id} - Questions and Answers", title_style)
            elements.append(title)
            elements.append(Spacer(1, 0.25*inch))
            
            # Add timestamp
            date_text = f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            date_paragraph = Paragraph(date_text, normal_style)
            elements.append(date_paragraph)
            elements.append(Spacer(1, 0.25*inch))
            
            # Add questions and options
            for i, question_data in enumerate(quiz_data, 1):
                # Extract question and options
                question_text = question_data.get('question', 'Unknown Question')
                options = question_data.get('options', [])
                correct_answer_index = question_data.get('answer', 0)
                
                # Format the question with number
                question = Paragraph(f"Q{i}. {question_text}", question_style)
                elements.append(question)
                
                # Add each option
                for j, option in enumerate(options):
                    # Mark correct answer with ✅
                    if j == correct_answer_index:
                        option_text = f"{chr(65+j)}. {option} ✅"
                    else:
                        option_text = f"{chr(65+j)}. {option}"
                    
                    option_paragraph = Paragraph(option_text, option_style)
                    elements.append(option_paragraph)
                
                elements.append(Spacer(1, 0.15*inch))
            
            # Build the PDF
            doc.build(elements)
            logger.info(f"Quiz questions PDF generated successfully: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Error generating quiz PDF with ReportLab: {e}")
            return None
    
    def generate_quiz_pdf_fpdf(self, quiz_data, quiz_id):
        """Generate PDF using FPDF (fallback method)"""
        try:
            # Make sure FPDF is available
            if not FPDF_AVAILABLE:
                logger.error("FPDF library not available")
                return None

            # Generate a unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"quiz_{quiz_id}_{timestamp}.pdf"
            file_path = os.path.join(PDF_RESULTS_DIR, filename)
            
            # Ensure the directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Create PDF instance
            pdf = FPDF()
            pdf.add_page()
            
            # Set up fonts
            pdf.set_font("Arial", "B", 16)
            
            # Add title
            pdf.cell(0, 10, f"Quiz #{quiz_id} - Questions and Answers", 0, 1, "C")
            pdf.ln(5)
            
            # Add timestamp
            pdf.set_font("Arial", "", 10)
            pdf.cell(0, 10, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 0, 1, "R")
            pdf.ln(5)
            
            # Add questions and options
            for i, question_data in enumerate(quiz_data, 1):
                # Extract question and options
                question_text = question_data.get('question', 'Unknown Question')
                options = question_data.get('options', [])
                correct_answer_index = question_data.get('answer', 0)
                
                # Add question
                pdf.set_font("Arial", "B", 12)
                pdf.multi_cell(0, 10, f"Q{i}. {question_text}", 0, "L")
                
                # Add options
                pdf.set_font("Arial", "", 11)
                for j, option in enumerate(options):
                    # Mark correct answer with ✅
                    if j == correct_answer_index:
                        option_text = f"{chr(65+j)}. {option} \u2705"  # Unicode for ✅
                    else:
                        option_text = f"{chr(65+j)}. {option}"
                    
                    # Calculate left margin for options (indentation)
                    pdf.set_x(20)
                    pdf.multi_cell(0, 8, option_text, 0, "L")
                
                pdf.ln(5)
            
            # Save PDF
            pdf.output(file_path)
            logger.info(f"Quiz questions PDF generated successfully: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Error generating quiz PDF with FPDF: {e}")
            return None

async def quizpdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /quizpdf command to generate a PDF with quiz questions and answers"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Send initial processing message
    processing_message = await context.bot.send_message(
        chat_id=chat_id,
        text="🔄 Processing your PDF request..."
    )
    
    try:
        # Check if a quiz ID was provided as argument
        quiz_id = None
        if context.args and len(context.args) > 0:
            # Try to extract quiz ID from arguments
            try:
                quiz_id = context.args[0]
                # Check if the quiz ID is valid (numeric)
                if not re.match(r'^\d+$', quiz_id):
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=processing_message.message_id,
                        text="❌ Invalid Quiz ID format. Please provide a numeric ID."
                    )
                    return
            except Exception as e:
                logger.error(f"Error parsing quiz ID: {e}")
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=processing_message.message_id,
                    text="❌ Error parsing Quiz ID. Please try again."
                )
                return
        else:
            # If no quiz ID provided, use user's most recent quiz
            user_data = get_user_data(user_id)
            recent_quizzes = user_data.get('recent_quizzes', [])
            
            if recent_quizzes:
                quiz_id = recent_quizzes[-1]
            else:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=processing_message.message_id,
                    text="❌ No recent quiz found. Please specify a Quiz ID or take a quiz first."
                )
                return
        
        # Get quiz questions
        questions = load_questions()
        quiz_questions = questions.get(str(quiz_id), [])
        
        if not quiz_questions:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=processing_message.message_id,
                text=f"❌ No questions found for Quiz ID: {quiz_id}."
            )
            return
        
        # Update status message
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=processing_message.message_id,
            text=f"🔄 Generating PDF for Quiz #{quiz_id}..."
        )
        
        try:
            # Make sure PDF directory exists
            ensure_pdf_directory()
            
            # Initialize PDF generator
            pdf_generator = QuizQuestionsPDF()
            
            # Log the quiz data for debugging
            logger.info(f"Attempting to generate PDF for quiz ID: {quiz_id}")
            logger.info(f"Number of questions: {len(quiz_questions)}")
            
            # Generate PDF
            pdf_path = pdf_generator.generate_quiz_pdf(quiz_questions, quiz_id)
            
            # Check if PDF was created
            if not pdf_path or not os.path.exists(pdf_path):
                logger.error(f"PDF generation failed. Path: {pdf_path}, Exists: {os.path.exists(pdf_path) if pdf_path else False}")
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=processing_message.message_id,
                    text="❌ Failed to generate PDF. Please try again."
                )
                return
        except Exception as e:
            logger.error(f"Error in PDF generation: {str(e)}")
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=processing_message.message_id,
                text=f"❌ Error generating PDF: {str(e)}"
            )
            return
        
        # Send the PDF file
        with open(pdf_path, 'rb') as pdf_file:
            await context.bot.send_document(
                chat_id=chat_id,
                document=pdf_file,
                filename=f"Quiz_{quiz_id}_Questions.pdf",
                caption=f"📋 Quiz #{quiz_id} - Questions and Answers"
            )
        
        # Update the processing message
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=processing_message.message_id,
            text=f"✅ PDF for Quiz #{quiz_id} has been generated and sent!"
        )
        
        # Clean up the PDF file to save space
        try:
            os.remove(pdf_path)
        except Exception as e:
            logger.error(f"Error removing PDF file: {e}")
    
    except Exception as e:
        logger.error(f"Error processing quizpdf command: {e}")
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=processing_message.message_id,
            text=f"❌ An error occurred: {str(e)}"
        )

def add_questions_with_id(custom_id, questions_list):
    """
    Add questions with a custom ID
    Returns the number of questions added
    """
    try:
        # Ensure custom_id is treated as a string to avoid dictionary key issues
        custom_id = str(custom_id)
        logger.info(f"Adding questions with ID (after conversion): {custom_id}, Type: {type(custom_id)}")
        
        # Additional data validation to catch any issues
        if not questions_list:
            logger.error("Empty questions list passed to add_questions_with_id")
            return 0
        
        # Validate questions before adding them - filter out invalid ones
        valid_questions = []
        for q in questions_list:
            # Check if question text is not empty and has at least 2 options
            if q.get('question') and len(q.get('options', [])) >= 2:
                # Make sure all required fields are present and non-empty
                if all(key in q and q[key] is not None for key in ['question', 'options', 'answer']):
                    # Make sure the question text is not empty
                    if q['question'].strip() != '':
                        # Make sure all options have text
                        if all(opt.strip() != '' for opt in q['options']):
                            valid_questions.append(q)
                            continue
            logger.warning(f"Skipped invalid question: {q}")
        
        if not valid_questions:
            logger.error("No valid questions found after validation!")
            return 0
            
        logger.info(f"Validated questions: {len(valid_questions)} of {len(questions_list)} are valid")
            
        # Load existing questions
        questions = load_questions()
        logger.info(f"Loaded existing questions dictionary, keys: {list(questions.keys())}")
        
        # Check if custom ID already exists
        if custom_id in questions:
            logger.info(f"ID {custom_id} exists in questions dict")
            # If the ID exists but isn't a list, convert it to a list
            if not isinstance(questions[custom_id], list):
                questions[custom_id] = [questions[custom_id]]
                logger.info(f"Converted existing entry to list for ID {custom_id}")
            # Add the new questions to the list
            original_len = len(questions[custom_id])
            questions[custom_id].extend(valid_questions)
            logger.info(f"Extended question list from {original_len} to {len(questions[custom_id])} items")
        else:
            # Create a new list with these questions
            questions[custom_id] = valid_questions
            logger.info(f"Created new entry for ID {custom_id} with {len(valid_questions)} questions")
        
        # Save the updated questions
        logger.info(f"Saving updated questions dict with {len(questions)} IDs")
        save_questions(questions)
        
        return len(valid_questions)
    except Exception as e:
        logger.error(f"Error in add_questions_with_id: {str(e)}", exc_info=True)
        return 0

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Basic command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("stop", stop_quiz_command))
    application.add_handler(CommandHandler("stats", stats_command))  # This calls extended_stats_command
    application.add_handler(CommandHandler("delete", delete_command))
    
    # NEGATIVE MARKING ADDITION: Add new command handlers
    application.add_handler(CommandHandler("negmark", negative_marking_settings))
    application.add_handler(CommandHandler("resetpenalty", reset_user_penalty_command))
    application.add_handler(CallbackQueryHandler(negative_settings_callback, pattern=r"^neg_mark_"))
    
    # PDF IMPORT ADDITION: Add new command handlers
    application.add_handler(CommandHandler("pdfinfo", pdf_info_command))
    application.add_handler(CommandHandler("quizid", quiz_with_id_command))
    
    # PDF QUESTIONS ADDITION: Add handler for quizpdf command
    application.add_handler(CommandHandler("quizpdf", quizpdf_command))

    # Add handler for negative marking selection callback
    application.add_handler(CallbackQueryHandler(negative_marking_callback, pattern=r"^negmark_"))
    
    # Add handler for custom negative marking value input
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.UpdateType.MESSAGE,
        handle_custom_negative_marking,
        lambda update, context: context.user_data.get("awaiting_custom_negmark", False)
    ))
    
    # PDF import conversation handler
    pdf_import_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("pdfimport", pdf_import_command)],
        states={
            PDF_UPLOAD: [MessageHandler(filters.Document.ALL, pdf_file_received)],
            PDF_CUSTOM_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, pdf_custom_id_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(pdf_import_conv_handler)
    
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
    
    # TXT Import Command Handler
    # Use the same TXT import states defined at the top level
    # No need to redefine them here
    
    # Text Import conversation handler - simplified without custom ID step
    txtimport_handler = ConversationHandler(
        entry_points=[CommandHandler("txtimport", txtimport_start)],
        states={
            TXT_UPLOAD: [
                MessageHandler(filters.Document.ALL, receive_txt_file),
                CommandHandler("cancel", txtimport_cancel),
            ],
            # No TXT_CUSTOM_ID state - we'll automatically generate an ID instead
        },
        fallbacks=[CommandHandler("cancel", txtimport_cancel)],
    )
    application.add_handler(txtimport_handler)
    
    # Start the Bot
    application.run_polling()

if __name__ == "__main__":
    main()
