#!/usr/bin/env python

# OCR + PDF Text Extraction + Block-Level Deduplication
import os
import re
import json
import logging
import random
import asyncio
import datetime
import tempfile
from pathlib import Path
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler, PollAnswerHandler

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

# Import libraries for PDF handling
try:
    import PyPDF2
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment variable
BOT_TOKEN = os.environ.get("7631768276:AAGw1hZ9d9hEjQTEaxaifZ92-tmELkllyc8")
if not BOT_TOKEN:
    logger.error("BOT_TOKEN environment variable not set. Please set this to your Telegram bot token.")
    import sys
    sys.exit(1)
else:
    logger.info(f"BOT_TOKEN found with length: {len(BOT_TOKEN)}")
    # Strip any whitespace that might have been added
    BOT_TOKEN = BOT_TOKEN.strip()

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

# ---------- QUIZ PENALTIES FUNCTIONS ----------
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

# ---------- PARTICIPANT FUNCTIONS ----------
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

# ---------- QUIZ RESULTS FUNCTIONS ----------
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
        "total_questions": total_questions,
        "correct_answers": correct_answers,
        "wrong_answers": wrong_answers,
        "skipped": skipped,
        "penalty": penalty,
        "score": score,
        "adjusted_score": adjusted_score,
        "timestamp": datetime.datetime.now().isoformat()
    })
    
    # Save updated results
    save_quiz_results(results)
    return True

def get_quiz_results(quiz_id):
    """Get results for a specific quiz"""
    results = load_quiz_results()
    return results.get(str(quiz_id), {"participants": []})

def get_quiz_leaderboard(quiz_id):
    """Get leaderboard for a specific quiz"""
    results = get_quiz_results(quiz_id)
    participants = results.get("participants", [])
    
    # Sort by adjusted score (highest first), then by timestamp (earliest first)
    sorted_participants = sorted(
        participants, 
        key=lambda x: (-x.get("adjusted_score", 0), x.get("timestamp", ""))
    )
    
    return sorted_participants

# ---------- PDF RESULTS GENERATION ----------
class InsaneResultPDF(FPDF):
    """Custom PDF class for quiz results with INSANE watermark"""
    
    def __init__(self, quiz_id, title=None):
        super().__init__()
        self.quiz_id = quiz_id
        self.title = title or f"Quiz {quiz_id} Results"
        self.WIDTH = 210
        self.HEIGHT = 297
        
        # Add a page
        self.add_page()
        
        # Set up the document
        self.set_author("INSANE Quiz System")
        self.set_title(self.title)
        self.set_creator("Telegram Quiz Bot")
        self.set_subject("Quiz Results")
        
        # Add watermark
        self.add_watermark()
    
    def header(self):
        # Set up fonts
        self.set_font('Arial', 'B', 24)
        
        # Title
        self.set_fill_color(20, 40, 75)  # Dark blue background
        self.set_text_color(220, 220, 220)  # Light gray text
        self.cell(0, 20, self.title, 0, 1, 'C', 1)
        
        # Subtitle with timestamp
        self.set_font('Arial', 'I', 10)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cell(0, 8, f"Generated on {timestamp}", 0, 1, 'C', 1)
        
        # Add some spacing
        self.ln(10)
    
    def footer(self):
        # Set position at 1.5 cm from bottom
        self.set_y(-15)
        
        # Footer text
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128, 128, 128)  # Gray text
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", 0, 0, 'C')
        self.cell(0, 10, "Generated by INSANE Quiz System", 0, 0, 'R')
    
    def add_watermark(self):
        # Save current position
        x, y = self.get_x(), self.get_y()
        
        # Set font for watermark
        self.set_font('Arial', 'B', 60)
        self.set_text_color(230, 230, 230, alpha=0.4)  # Very light gray, transparent
        
        # Calculate diagonal placement
        diagonal_x = 30
        diagonal_y = 80
        
        # Rotate text and place watermark
        self.rotate(45, diagonal_x, diagonal_y)
        self.text(diagonal_x, diagonal_y, "INSANE")
        
        # Reset rotation and position
        self.rotate(0)
        self.set_xy(x, y)
        
        # Set text color back to normal
        self.set_text_color(0, 0, 0)  # Black
    
    def create_leaderboard_table(self, leaderboard):
        # Set up font
        self.set_font('Arial', 'B', 12)
        self.set_fill_color(200, 220, 255)  # Light blue header
        self.set_text_color(0, 0, 0)  # Black text
        
        # Column widths
        col_widths = [10, 50, 25, 25, 25, 25, 30]  # Adjusted for better fit
        
        # Table header
        headers = ["#", "Participant", "Correct", "Wrong", "Penalty", "Score", "Adjusted"]
        for i, header in enumerate(headers):
            self.cell(col_widths[i], 10, header, 1, 0, 'C', 1)
        self.ln()
        
        # Table data
        self.set_font('Arial', '', 10)
        alternate_fill = False
        
        for i, participant in enumerate(leaderboard[:20]):  # Show top 20 only
            rank = i + 1
            name = participant.get("user_name", "Unknown")
            correct = participant.get("correct_answers", 0)
            wrong = participant.get("wrong_answers", 0)
            penalty = round(participant.get("penalty", 0), 2)
            score = participant.get("score", 0)
            adjusted = round(participant.get("adjusted_score", 0), 2)
            
            # Alternate row colors
            alternate_fill = not alternate_fill
            if alternate_fill:
                self.set_fill_color(240, 240, 255)  # Very light blue
            else:
                self.set_fill_color(255, 255, 255)  # White
            
            # Highlight top 3
            if rank <= 3:
                self.set_text_color(0, 0, 150)  # Dark blue for top 3
                self.set_font('Arial', 'B', 10)
            else:
                self.set_text_color(0, 0, 0)  # Black for others
                self.set_font('Arial', '', 10)
            
            # Print data
            self.cell(col_widths[0], 8, str(rank), 1, 0, 'C', 1)
            self.cell(col_widths[1], 8, name[:20], 1, 0, 'L', 1)  # Truncate long names
            self.cell(col_widths[2], 8, str(correct), 1, 0, 'C', 1)
            self.cell(col_widths[3], 8, str(wrong), 1, 0, 'C', 1)
            self.cell(col_widths[4], 8, str(penalty), 1, 0, 'C', 1)
            self.cell(col_widths[5], 8, str(score), 1, 0, 'C', 1)
            self.cell(col_widths[6], 8, str(adjusted), 1, 0, 'C', 1)
            self.ln()
        
        # Reset text color
        self.set_text_color(0, 0, 0)
    
    def add_quiz_statistics(self, leaderboard, penalty_value):
        """Add quiz statistics section"""
        # Only add stats if we have participants
        if not leaderboard:
            return
            
        # Add some spacing
        self.ln(15)
        
        # Set up font for section title
        self.set_font('Arial', 'B', 16)
        self.set_fill_color(20, 40, 75)  # Dark blue background
        self.set_text_color(220, 220, 220)  # Light gray text
        self.cell(0, 10, "Quiz Statistics", 0, 1, 'C', 1)
        self.ln(5)
        
        # Reset text color
        self.set_text_color(0, 0, 0)
        
        # Calculate statistics
        total_participants = len(leaderboard)
        total_questions = leaderboard[0].get("total_questions", 0) if leaderboard else 0
        
        # Count correct/incorrect answers across all participants
        total_correct = sum(p.get("correct_answers", 0) for p in leaderboard)
        total_wrong = sum(p.get("wrong_answers", 0) for p in leaderboard)
        total_skipped = sum(p.get("skipped", 0) for p in leaderboard)
        
        # Calculate averages
        avg_correct = total_correct / total_participants if total_participants > 0 else 0
        avg_wrong = total_wrong / total_participants if total_participants > 0 else 0
        avg_skipped = total_skipped / total_participants if total_participants > 0 else 0
        
        # Get highest and lowest scores
        highest_score = max((p.get("adjusted_score", 0) for p in leaderboard), default=0)
        lowest_score = min((p.get("adjusted_score", 0) for p in leaderboard), default=0)
        
        # Display statistics
        self.set_font('Arial', '', 12)
        statistics = [
            f"Total Participants: {total_participants}",
            f"Total Questions: {total_questions}",
            f"Negative Marking: {penalty_value} points per wrong answer",
            f"Average Correct Answers: {avg_correct:.2f}",
            f"Average Wrong Answers: {avg_wrong:.2f}",
            f"Average Skipped Questions: {avg_skipped:.2f}",
            f"Highest Score: {highest_score:.2f}",
            f"Lowest Score: {lowest_score:.2f}"
        ]
        
        for stat in statistics:
            self.cell(0, 8, stat, 0, 1, 'L')
    
    def add_score_distribution(self, leaderboard):
        """Add score distribution graph (simplified version)"""
        # Only add graph if we have enough participants
        if len(leaderboard) < 3:
            return
            
        # Add some spacing
        self.ln(15)
        
        # Set up font for section title
        self.set_font('Arial', 'B', 16)
        self.set_fill_color(20, 40, 75)  # Dark blue background
        self.set_text_color(220, 220, 220)  # Light gray text
        self.cell(0, 10, "Score Distribution", 0, 1, 'C', 1)
        self.ln(5)
        
        # Reset text color
        self.set_text_color(0, 0, 0)
        
        # We'll create a simple text-based distribution here
        # In a more advanced version, you could use a charting library to create a proper graph
        # and then embed it in the PDF
        
        # Extract adjusted scores
        scores = [p.get("adjusted_score", 0) for p in leaderboard]
        
        # Create score ranges (0-25%, 25-50%, 50-75%, 75-100%)
        max_possible = leaderboard[0].get("total_questions", 10)  # Max possible score
        score_ranges = [
            (0, max_possible * 0.25),
            (max_possible * 0.25, max_possible * 0.5),
            (max_possible * 0.5, max_possible * 0.75),
            (max_possible * 0.75, max_possible + 1)  # +1 to include max score
        ]
        
        # Count scores in each range
        range_counts = [0, 0, 0, 0]
        for score in scores:
            for i, (low, high) in enumerate(score_ranges):
                if low <= score < high:
                    range_counts[i] += 1
                    break
        
        # Calculate percentages
        total = len(scores)
        percentages = [count / total * 100 if total > 0 else 0 for count in range_counts]
        
        # Display distribution
        self.set_font('Arial', '', 12)
        range_labels = ["0-25%", "25-50%", "50-75%", "75-100%"]
        
        for i, (label, count, percentage) in enumerate(zip(range_labels, range_counts, percentages)):
            text = f"{label}: {count} participants ({percentage:.1f}%)"
            self.cell(0, 8, text, 0, 1, 'L')

def generate_pdf_results(quiz_id, title=None):
    """Generate PDF results for a quiz"""
    # Check if FPDF is available
    if not FPDF_AVAILABLE:
        logger.error("FPDF is not available. Cannot generate PDF results.")
        return None
        
    try:
        # Ensure PDF directory exists
        ensure_pdf_directory()
        
        # Get the leaderboard
        leaderboard = get_quiz_leaderboard(quiz_id)
        if not leaderboard:
            logger.error(f"No results found for quiz {quiz_id}. Cannot generate PDF.")
            return None
            
        # Get negative marking value for this quiz
        penalty_value = get_quiz_penalty(quiz_id)
        
        # Create the PDF
        pdf = InsaneResultPDF(quiz_id, title)
        
        # Create leaderboard table
        pdf.create_leaderboard_table(leaderboard)
        
        # Add quiz statistics
        pdf.add_quiz_statistics(leaderboard, penalty_value)
        
        # Add score distribution
        pdf.add_score_distribution(leaderboard)
        
        # Generate the filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"quiz_{quiz_id}_results_{timestamp}.pdf"
        filepath = os.path.join(PDF_RESULTS_DIR, filename)
        
        # Save the PDF
        pdf.output(filepath)
        logger.info(f"Generated PDF results at {filepath}")
        
        return filepath
        
    except Exception as e:
        logger.error(f"Error generating PDF results: {e}")
        return None

def process_quiz_end(quiz_id, user_id, user_name, total_questions, correct_answers, 
                   wrong_answers, skipped, penalty, score, adjusted_score):
    """Process quiz end - add result and generate PDF"""
    try:
        # Record the quiz result
        add_quiz_result(
            quiz_id, user_id, user_name, total_questions, correct_answers,
            wrong_answers, skipped, penalty, score, adjusted_score
        )
        
        # Generate PDF for the quiz results
        pdf_path = generate_pdf_results(quiz_id)
        
        return pdf_path
    except Exception as e:
        logger.error(f"Error processing quiz end: {e}")
        return None

async def handle_quiz_end_with_pdf(update, context, quiz_id, user_id, user_name, 
                                  total_questions, correct_answers, wrong_answers, 
                                  skipped, penalty, score, adjusted_score):
    """Handle quiz end with PDF generation"""
    try:
        # Process quiz end and generate PDF
        pdf_path = process_quiz_end(
            quiz_id, user_id, user_name, total_questions, correct_answers,
            wrong_answers, skipped, penalty, score, adjusted_score
        )
        
        if pdf_path and os.path.exists(pdf_path):
            # Send the PDF as a document
            await update.message.reply_document(
                document=open(pdf_path, 'rb'),
                caption=f"📊 Complete results for Quiz {quiz_id}\n\n"
                       f"Generated by INSANE Quiz System"
            )
            logger.info(f"Sent PDF results for quiz {quiz_id} to user {user_id}")
        else:
            await update.message.reply_text(
                "⚠️ Could not generate PDF results. Please try again later."
            )
            
    except Exception as e:
        logger.error(f"Error handling quiz end with PDF: {e}")
        await update.message.reply_text(
            "⚠️ An error occurred while generating PDF results."
        )

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
        return True
    except Exception as e:
        logger.error(f"Error saving questions: {e}")
        return False

def get_next_question_id():
    """Get the next available question ID"""
    questions = load_questions()
    numeric_ids = [int(qid) for qid in questions.keys() if qid.isdigit()]
    next_id = max(numeric_ids) + 1 if numeric_ids else 1
    return str(next_id)

def get_question_by_id(question_id):
    """Get a question by its ID"""
    questions = load_questions()
    return questions.get(str(question_id))

def delete_question_by_id(question_id):
    """Delete a question by its ID"""
    questions = load_questions()
    question_id = str(question_id)
    if question_id in questions:
        del questions[question_id]
        save_questions(questions)
        return True
    return False

def add_question_with_id(question_id, question_data):
    """Add a question with a specific ID, preserving existing questions with the same ID"""
    try:
        # Always make sure the ID is a string
        question_id = str(question_id)
        logger.info(f"Adding question with ID: {question_id}")
        
        questions = load_questions()
        
        # If the ID already exists, convert to a list or append to the existing list
        if question_id in questions:
            if isinstance(questions[question_id], list):
                questions[question_id].append(question_data)
                logger.info(f"Appended to existing question list for ID {question_id}")
            else:
                # Convert to list containing the existing question and the new one
                questions[question_id] = [questions[question_id], question_data]
                logger.info(f"Converted single question to list for ID {question_id}")
        else:
            # New ID, simply add the question
            questions[question_id] = question_data
            logger.info(f"Added new question with ID {question_id}")
            
        save_questions(questions)
        return True
    except Exception as e:
        logger.error(f"Error adding question with ID {question_id}: {e}")
        return False

def get_user_data(user_id):
    """Get user data from file"""
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                users = json.load(f)
                return users.get(str(user_id), {})
        return {}
    except Exception as e:
        logger.error(f"Error loading user data: {e}")
        return {}

def save_user_data(user_id, data):
    """Save user data to file"""
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                users = json.load(f)
        else:
            users = {}
        
        users[str(user_id)] = data
        
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving user data: {e}")
        return False

def detect_language(text):
    """
    Simple language detection to identify if text contains Hindi
    Returns 'hi' if Hindi characters are detected, 'en' otherwise
    """
    # Unicode ranges for Hindi characters
    hindi_pattern = re.compile(r'[\u0900-\u097F]')
    
    # Check if the text contains Hindi characters
    if hindi_pattern.search(text):
        return 'hi'
    return 'en'

# ---------- BOT COMMAND HANDLERS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"""Hi {user.mention_html()}! I'm your Interactive Quiz Bot! 🤖📚

Check out these commands:

- /help - Show help message
- /add - Add a new question
- /quiz - Start a random quiz
- /quizid <id> - Start quiz with specific ID
- /stats - View your stats
- /poll2q - Convert poll to question
- /txtimport - Import questions from text file
- /pdfimport - Import questions from PDF
- /pdfinfo - PDF import info

Ask me anything about the available commands!""",
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help message."""
    help_text = """
📚 *Interactive Quiz Bot Help* 📚

*Main Commands:*
/add - Add new questions interactively
/quiz <number> - Take a random quiz (specify # of questions)
/quizid <ID> - Take a quiz with a specific ID
/stats - View your quiz statistics

*Advanced Features:*
/poll2q - Convert a Telegram poll to a quiz question
/txtimport - Import questions from a text file
/pdfimport - Import questions from PDF with automatic parsing
/pdfinfo - Info about PDF import feature

*Additional Commands:*
/delete <ID> - Delete a specific question by ID
/negmark - Negative marking settings
/exstats - Extended statistics
/resetpenalty - Reset penalty points
/stop - Stop current quiz

*Custom ID Feature:*
When adding questions or importing from PDFs/text,
you can specify your own custom IDs - e.g. 'science2025'
or just a simple number like '10'

Need more help? Ask about a specific command!
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def extended_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display extended user statistics with penalty information."""
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    
    # Add participant record
    add_participant(user_id, user_name, update.effective_user.first_name)
    
    # Get extended stats
    stats = get_extended_user_stats(user_id)
    
    stats_text = f"""📊 *Extended Statistics for {user_name}*

🧮 *Basic Stats:*
➡️ Total Answers: {stats['total_answers']}
➡️ Correct Answers: {stats['correct_answers']}
➡️ Incorrect Answers: {stats['incorrect_answers']}

📉 *Negative Marking:*
➡️ Penalty Points: {stats['penalty_points']:.2f}

📈 *Scoring:*
➡️ Raw Score: {stats['raw_score']:.2f}
➡️ Adjusted Score: {stats['adjusted_score']:.2f}

Negative marking subtracts points for incorrect answers.
If enabled, different quizzes may have different penalty values.
"""
    
    await update.message.reply_text(stats_text, parse_mode='Markdown')

async def negative_marking_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show and manage negative marking settings."""
    # Check if user is an admin (this is a simplified check - modify as needed)
    user_id = update.effective_user.id
    
    # Show current negative marking settings
    settings_text = f"""⚙️ *Negative Marking Settings*

Negative marking deducts points for incorrect answers.

*Current Settings:*
➡️ Default penalty: {DEFAULT_PENALTY} points per wrong answer
➡️ Max penalty: {MAX_PENALTY} points
➡️ Min penalty: {MIN_PENALTY} points

You can set custom negative marking values when starting a quiz.
"""
    
    # Create keyboard for selecting options
    keyboard = []
    
    # Create advanced options
    for option_name, option_value in ADVANCED_NEGATIVE_MARKING_OPTIONS:
        keyboard.append([InlineKeyboardButton(
            f"{option_name}", 
            callback_data=f"neg_{option_value}"
        )])
    
    # Add reset button
    keyboard.append([InlineKeyboardButton("Reset All Penalties", callback_data="neg_reset_all")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        settings_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def negative_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback queries from negative marking settings."""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    if callback_data == "neg_reset_all":
        # Reset all penalties
        reset_user_penalties()
        await query.edit_message_text(
            "✅ All user penalties have been reset to zero."
        )
    elif callback_data.startswith("neg_"):
        # Set as default for next quiz
        value = callback_data.replace("neg_", "")
        
        if value == "custom":
            # Ask for custom value
            await query.edit_message_text(
                "Please enter a custom negative marking value (between 0 and 1.5):"
            )
            context.user_data["awaiting_custom_neg"] = True
        else:
            # Set the value
            try:
                value_float = float(value)
                DEFAULT_PENALTY = value_float  # This affects only memory, not the global constant
                await query.edit_message_text(
                    f"✅ Default negative marking for your next quiz set to {value_float} points per wrong answer."
                )
            except ValueError:
                await query.edit_message_text(
                    "❌ Invalid value. Please select a value from the options."
                )

async def reset_user_penalty_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset penalties for a specific user."""
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        # Reset penalties for the current user
        reset_user_penalties(user_id)
        await update.message.reply_text(
            "✅ Your penalty points have been reset to zero."
        )
    elif len(args) == 1 and args[0].lower() == "all":
        # Check if admin (simplified check)
        reset_user_penalties()  # Reset all
        await update.message.reply_text(
            "✅ All penalties have been reset for all users."
        )
    else:
        await update.message.reply_text(
            "❌ Invalid command format. Use /resetpenalty or /resetpenalty all"
        )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display user statistics."""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    user_name = update.effective_user.full_name
    
    # Add participant record
    add_participant(user_id, user_name, update.effective_user.first_name)
    
    total_answers = user_data.get("total_answers", 0)
    correct_answers = user_data.get("correct_answers", 0)
    
    # Calculate success rate
    success_rate = (correct_answers / total_answers * 100) if total_answers > 0 else 0
    
    await update.message.reply_text(
        f"📊 *Statistics for {user_name}*\n\n"
        f"Total answers: {total_answers}\n"
        f"Correct answers: {correct_answers}\n"
        f"Success rate: {success_rate:.1f}%\n\n"
        f"For more detailed stats with negative marking, use /exstats",
        parse_mode='Markdown'
    )

async def add_question_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the process of adding a new question."""
    # Clear any previous question data
    if 'new_question' in context.user_data:
        del context.user_data['new_question']
    
    # Initialize a new question
    context.user_data['new_question'] = {}
    
    # Ask for ID assignment method
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

async def custom_id_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle ID selection method."""
    query = update.callback_query
    await query.answer()
    
    # Log what we're doing
    logger.info(f"Received ID selection: {query.data}")
    
    if query.data == "auto_id":
        # Auto ID - proceed to question entry
        await query.edit_message_text("Please enter the question text:")
        return QUESTION
    else:
        # Custom ID - ask for custom ID
        await query.edit_message_text(
            "Please enter a custom ID for this question.\n\n"
            "This can be any text or number (e.g., 'hindi2025', 'science', '10').\n\n"
            "If the ID already exists, your question will be added to that ID without overwriting existing questions."
        )
        # Set flag to indicate we're awaiting custom ID input
        context.user_data["awaiting_custom_id"] = True
        return CUSTOM_ID

async def custom_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom ID input."""
    # Check if we're waiting for custom ID input
    if context.user_data.get("awaiting_custom_id", False):
        # Get the custom ID from the message text
        custom_id = update.message.text.strip()
        
        # Store in context for later use
        context.user_data["custom_id"] = custom_id
        context.user_data["awaiting_custom_id"] = False
        
        # Log the custom ID
        logger.info(f"Received custom ID: {custom_id}")
        
        # Acknowledge receipt of custom ID
        await update.message.reply_text(
            f"✅ Using custom ID: <b>{custom_id}</b>\n\nNow please enter the question text:", 
            parse_mode='HTML'
        )
        
        # Move to question entry state
        return QUESTION
    
    # If we're not awaiting custom ID, something went wrong - go back to start
    await update.message.reply_text(
        "❌ Something went wrong with the ID setup.\n"
        "Let's start over. Use /add to add a new question."
    )
    return ConversationHandler.END

async def add_question_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the question text and ask for options."""
    question_text = update.message.text
    
    # Store the question text
    if 'new_question' not in context.user_data:
        context.user_data['new_question'] = {}
    
    context.user_data['new_question']['question'] = question_text
    
    # Debug log
    logger.info(f"Stored question text: {question_text}")
    logger.info(f"Current user_data: {context.user_data}")
    
    await update.message.reply_text(
        "Please enter the options, one per line. For example:\n"
        "Option 1\n"
        "Option 2\n"
        "Option 3\n"
        "Option 4"
    )
    return OPTIONS

async def add_question_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the options and ask for the correct answer."""
    options_text = update.message.text
    options = [option.strip() for option in options_text.split('\n') if option.strip()]
    
    if len(options) < 2:
        await update.message.reply_text(
            "❌ You need to provide at least 2 options. Please enter the options again, one per line."
        )
        return OPTIONS
    
    # Store the options
    context.user_data['new_question']['options'] = options
    
    # Debug log
    logger.info(f"Stored options: {options}")
    
    # Create keyboard buttons for selecting the correct answer
    keyboard = []
    for i, option in enumerate(options):
        keyboard.append([InlineKeyboardButton(f"{i+1}. {option}", callback_data=f"answer_{i}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Please select the correct answer:",
        reply_markup=reply_markup
    )
    return ANSWER

async def add_question_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the correct answer and create the question."""
    query = update.callback_query
    await query.answer()
    
    answer_index = int(query.data.split('_')[1])
    context.user_data['new_question']['answer'] = answer_index
    
    # Show category selection
    categories = ["General Knowledge", "Science", "History", "Geography", "Entertainment", "Sports"]
    keyboard = [[InlineKeyboardButton(cat, callback_data=f"cat_{cat}")] for cat in categories]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Selected answer: {answer_index+1}. {context.user_data['new_question']['options'][answer_index]}\n\n"
        f"Now select a category for this question:",
        reply_markup=reply_markup
    )
    return CATEGORY

async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle category selection."""
    query = update.callback_query
    await query.answer()
    
    category = query.data.replace("cat_", "")
    context.user_data['new_question']['category'] = category
    
    # Determine question ID
    if "custom_id" in context.user_data:
        question_id = context.user_data["custom_id"]
        del context.user_data["custom_id"]
    else:
        question_id = get_next_question_id()
    
    # Add the question
    add_question_with_id(question_id, context.user_data['new_question'])
    
    # Show success message
    await query.edit_message_text(
        f"✅ Question added successfully with ID: {question_id}\n\n"
        f"Question: {context.user_data['new_question']['question']}\n"
        f"Category: {category}\n"
        f"Options: {len(context.user_data['new_question']['options'])}\n"
        f"Correct answer: {context.user_data['new_question']['answer']+1}. {context.user_data['new_question']['options'][context.user_data['new_question']['answer']]}"
    )
    
    # Clean up context
    if 'new_question' in context.user_data:
        del context.user_data['new_question']
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current operation."""
    await update.message.reply_text(
        "Operation cancelled. No changes were made."
    )
    return ConversationHandler.END

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a question by ID."""
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "❌ You need to specify the question ID to delete. Example: /delete 1"
        )
        return
    
    question_id = args[0]
    
    if delete_question_by_id(question_id):
        await update.message.reply_text(
            f"✅ Question with ID {question_id} has been deleted."
        )
    else:
        await update.message.reply_text(
            f"❌ Could not find question with ID {question_id}."
        )

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a quiz session with random questions."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_name = update.effective_user.username or update.effective_user.full_name
    
    # Add participant record
    add_participant(user_id, user_name, update.effective_user.first_name)
    
    # Check if a quiz is already running in this chat
    if context.chat_data.get('quiz_running', False):
        await update.message.reply_text(
            "❌ A quiz is already running in this chat. Please wait for it to finish or use /stop to stop it."
        )
        return
    
    # Get number of questions from arguments
    num_questions = 5  # Default
    if context.args and context.args[0].isdigit():
        num_questions = min(int(context.args[0]), 20)  # Max 20 questions
    
    # Load questions and select random ones
    questions = load_questions()
    if not questions:
        await update.message.reply_text(
            "❌ No questions found. Please add some questions first using /add."
        )
        return
    
    # Flatten the questions dictionary
    all_questions = []
    for qid, q_data in questions.items():
        if isinstance(q_data, list):
            # Multiple questions with this ID
            for q in q_data:
                all_questions.append((qid, q))
        else:
            # Single question with this ID
            all_questions.append((qid, q_data))
    
    # Check if we have enough questions
    if len(all_questions) < num_questions:
        num_questions = len(all_questions)
        await update.message.reply_text(
            f"⚠️ Not enough questions available. Using all {num_questions} available questions."
        )
    
    # Select random questions
    selected_questions = random.sample(all_questions, num_questions)
    
    # Store quiz data in context
    quiz_id = f"random_{int(datetime.datetime.now().timestamp())}"
    context.chat_data['quiz_running'] = True
    context.chat_data['quiz_id'] = quiz_id
    context.chat_data['questions'] = selected_questions
    context.chat_data['current_question'] = 0
    context.chat_data['participants'] = {}
    
    # Announce the quiz
    await update.message.reply_text(
        f"🎮 *Starting Quiz*\n\n"
        f"Number of questions: {num_questions}\n"
        f"Each question will be shown for 20 seconds.\n"
        f"Use /stop to end the quiz early.\n\n"
        f"First question coming up in 3 seconds...",
        parse_mode='Markdown'
    )
    
    # Schedule the first question with a delay
    await asyncio.sleep(3)
    await send_question(context, chat_id, 0)

async def send_question(context, chat_id, question_index):
    """Send a quiz question and schedule next one."""
    try:
        # Check if this is a valid question index
        if question_index >= len(context.chat_data['questions']):
            # No more questions, end the quiz
            await schedule_end_quiz(context, chat_id)
            return
        
        # Get the question
        _, question_data = context.chat_data['questions'][question_index]
        
        # Send as a poll
        message = await context.bot.send_poll(
            chat_id=chat_id,
            question=question_data['question'],
            options=question_data['options'],
            type='quiz',
            correct_option_id=question_data['answer'],
            is_anonymous=False,
            explanation=f"Question {question_index+1}/{len(context.chat_data['questions'])}",
            open_period=20,  # 20 seconds per question
        )
        
        # Store the poll_id for later reference
        context.chat_data['current_poll_id'] = message.poll.id
        
        # Schedule the next question
        await schedule_next_question(context, chat_id, question_index + 1)
    except Exception as e:
        logger.error(f"Error sending question: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Error sending question: {e}\n\nThe quiz has been terminated."
        )
        context.chat_data['quiz_running'] = False

async def schedule_next_question(context, chat_id, next_index):
    """Schedule the next question with delay."""
    # Update current question index
    context.chat_data['current_question'] = next_index
    
    # Schedule next question after 22 seconds (20 for poll + 2 buffer)
    await asyncio.sleep(22)
    
    # Check if quiz is still running
    if context.chat_data.get('quiz_running', False):
        await send_question(context, chat_id, next_index)

async def schedule_end_quiz(context, chat_id):
    """Schedule end of quiz with delay."""
    # Allow 2 more seconds for last answers
    await asyncio.sleep(2)
    
    # End the quiz
    if context.chat_data.get('quiz_running', False):
        await end_quiz(context, chat_id)

async def poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle poll answers from users with negative marking."""
    # Get the answer
    answer = update.poll_answer
    poll_id = answer.poll_id
    user_id = answer.user.id
    selected_option = answer.option_ids[0] if answer.option_ids else None
    
    # Check if this is from our quiz
    if not context.chat_data.get('quiz_running', False) or context.chat_data.get('current_poll_id') != poll_id:
        return
    
    # Get the current question
    question_index = context.chat_data['current_question'] - 1  # -1 because we've already moved to next q
    if question_index < 0 or question_index >= len(context.chat_data['questions']):
        return
    
    quiz_id, question_data = context.chat_data['questions'][question_index]
    correct_option = question_data['answer']
    
    # Initialize participant data if not exists
    if user_id not in context.chat_data['participants']:
        context.chat_data['participants'][user_id] = {
            'correct': 0,
            'wrong': 0,
            'answered': 0,
            'skipped': 0
        }
    
    # Update user's quiz performance
    if selected_option == correct_option:
        # Correct answer
        context.chat_data['participants'][user_id]['correct'] += 1
    else:
        # Wrong answer - apply negative marking
        context.chat_data['participants'][user_id]['wrong'] += 1
        
        # Apply penalty for wrong answer based on quiz ID
        category = question_data.get('category', None)
        apply_penalty(user_id, quiz_id, category)
    
    # Increment answer count
    context.chat_data['participants'][user_id]['answered'] += 1
    
    # Update user stats globally
    user_data = get_user_data(user_id)
    user_data['total_answers'] = user_data.get('total_answers', 0) + 1
    if selected_option == correct_option:
        user_data['correct_answers'] = user_data.get('correct_answers', 0) + 1
    save_user_data(user_id, user_data)

async def end_quiz(context, chat_id):
    """End the quiz and display results with all participants and penalties."""
    # Check if quiz is running
    if not context.chat_data.get('quiz_running', False):
        return
    
    # Get quiz data
    quiz_id = context.chat_data['quiz_id']
    questions = context.chat_data['questions']
    participants = context.chat_data['participants']
    
    # Get negative marking value for this quiz
    penalty_value = get_quiz_penalty(quiz_id)
    
    # If no one participated
    if not participants:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❗ Quiz ended. No one participated!"
        )
        context.chat_data['quiz_running'] = False
        return
    
    # Calculate results and generate message
    results_message = "🏁 *Quiz Results*\n\n"
    
    # Create a fake update object for PDF generation
    class FakeUpdate:
        class FakeMessage:
            def __init__(self, chat_id, context):
                self.chat_id = chat_id
                self.context = context
            
            async def reply_text(self, text, **kwargs):
                await self.context.bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    **kwargs
                )
                
            async def reply_document(self, document, **kwargs):
                await self.context.bot.send_document(
                    chat_id=self.chat_id,
                    document=document,
                    **kwargs
                )
                
        def __init__(self, chat_id, context):
            self.message = self.FakeMessage(chat_id, context)
            self.effective_chat = type('obj', (object,), {'id': chat_id})
    
    # Sort participants by score
    sorted_participants = []
    for user_id, stats in participants.items():
        # Calculate scores
        total_questions = len(questions)
        correct = stats['correct']
        wrong = stats['wrong']
        answered = stats['answered']
        skipped = total_questions - answered
        
        # Update skipped count
        participants[user_id]['skipped'] = skipped
        
        # Get user's penalty points
        penalty = get_user_penalties(user_id)
        
        # Calculate raw and adjusted scores
        score = correct
        adjusted_score = max(0, score - penalty)
        
        # Get user name
        user_name = get_participant_name(user_id)
        
        # Add to sorted list
        sorted_participants.append({
            'user_id': user_id,
            'user_name': user_name,
            'correct': correct,
            'wrong': wrong,
            'answered': answered,
            'skipped': skipped,
            'penalty': penalty,
            'score': score,
            'adjusted_score': adjusted_score
        })
    
    # Sort by adjusted score (highest first)
    sorted_participants.sort(key=lambda x: x['adjusted_score'], reverse=True)
    
    # Add top participants to results message
    results_message += "*Top Participants:*\n"
    for i, participant in enumerate(sorted_participants[:5]):  # Show top 5
        results_message += f"{i+1}. {participant['user_name']}: {participant['adjusted_score']:.2f} points\n"
    
    # Add negative marking info
    results_message += f"\n*Negative Marking:* {penalty_value} points per wrong answer"
    
    # Send results message
    await context.bot.send_message(
        chat_id=chat_id,
        text=results_message,
        parse_mode='Markdown'
    )
    
    # Process quiz end and generate PDF for all participants
    try:
        for participant in sorted_participants:
            user_id = participant['user_id']
            user_name = participant['user_name']
            total_questions = len(questions)
            correct = participant['correct']
            wrong = participant['wrong']
            skipped = participant['skipped']
            penalty = participant['penalty']
            score = participant['score']
            adjusted_score = participant['adjusted_score']
            
            # Add quiz result
            add_quiz_result(
                quiz_id, user_id, user_name, total_questions, correct,
                wrong, skipped, penalty, score, adjusted_score
            )
        
        # Generate and send PDF only once for the highest scorer
        if sorted_participants:
            fake_update = FakeUpdate(chat_id, context)
            top_participant = sorted_participants[0]
            
            await handle_quiz_end_with_pdf(
                fake_update, context, quiz_id, top_participant['user_id'],
                top_participant['user_name'], len(questions),
                top_participant['correct'], top_participant['wrong'],
                top_participant['skipped'], top_participant['penalty'],
                top_participant['score'], top_participant['adjusted_score']
            )
    except Exception as e:
        logger.error(f"Error processing quiz end: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ There was an error generating detailed results: {e}"
        )
    
    # End the quiz
    context.chat_data['quiz_running'] = False

async def poll_to_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Convert a Telegram poll to a quiz question."""
    # Clear any previous data
    if "poll2q" in context.user_data:
        del context.user_data["poll2q"]
    
    # Initialize empty poll data
    context.user_data["poll2q"] = {}
    
    logger.info("Starting poll2q conversation")
    
    await update.message.reply_text(
        "To convert a Telegram poll to a quiz question, please forward me a poll message.\n\n"
        "Make sure it's the poll itself, not just text."
    )
    return QUESTION

async def handle_forwarded_poll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle a forwarded poll message."""
    message = update.message
    
    # Log what we're receiving
    logger.info(f"Received forwarded message with poll: {message.poll is not None}")
    
    if hasattr(message, 'poll') and message.poll:
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
                f"{i+1}. {short_option}", 
                callback_data=f"poll_answer_{i}"
            )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"I've captured the poll: '{question_text}'\n\n"
            f"Please select the correct answer:",
            reply_markup=reply_markup
        )
        
        # Move to answer selection state
        return ANSWER
    else:
        # Not a valid poll
        await update.message.reply_text(
            "❌ That doesn't appear to be a poll. Please forward a message containing a poll."
        )
        return QUESTION

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle selection of correct answer for poll conversion."""
    query = update.callback_query
    await query.answer()
    
    # Log what we're doing
    logger.info(f"Poll answer selected: {query.data}")
    
    # Extract the answer index
    answer_index = int(query.data.replace("poll_answer_", ""))
    
    # Store the poll data with the answer
    poll_data = context.user_data.get("poll2q", {})
    poll_data["answer"] = answer_index
    context.user_data["poll2q"] = poll_data
    
    # Log the poll data for debugging
    logger.info(f"Poll data updated: {poll_data}")
    
    # Ask for custom ID or auto-generate
    keyboard = [
        [InlineKeyboardButton("Auto-generate ID", callback_data="pollid_auto")],
        [InlineKeyboardButton("Specify custom ID", callback_data="pollid_custom")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Selected answer: {answer_index+1}. {poll_data['options'][answer_index]}\n\n"
        f"How would you like to assign an ID to this question?",
        reply_markup=reply_markup
    )
    
    # Return the custom ID state for the conversation flow
    logger.info("Moving to CUSTOM_ID state for poll")
    return CUSTOM_ID

async def handle_poll_id_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle ID method selection for poll conversion."""
    query = update.callback_query
    await query.answer()
    
    # Track this callback in the logs
    logger.info(f"Received poll ID selection: {query.data}")
    
    if query.data == "pollid_auto":
        # Auto ID selected - set flag and clear any custom ID flags
        context.user_data["auto_poll_id_selected"] = True
        if "awaiting_poll_id" in context.user_data:
            del context.user_data["awaiting_poll_id"]
            
        # Show category selection
        categories = ["General Knowledge", "Science", "History", "Geography", "Entertainment", "Sports"]
        keyboard = [[InlineKeyboardButton(cat, callback_data=f"pollcat_{cat}")] for cat in categories]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Select a category for this question:",
            reply_markup=reply_markup
        )
        # Return category state for conversation flow
        logger.info("Moving to CATEGORY state with auto poll ID")
        return CATEGORY
    else:  # Custom ID selected
        # Ask for custom ID and set awaiting flag
        await query.edit_message_text(
            "Please send me the custom ID you want to use for this question.\n\n"
            "Your ID can be any text or number (for example: 'hindi2025' or '10').\n\n"
            "If the ID already exists, your question will be added to that ID without overwriting existing questions."
        )
        context.user_data["awaiting_poll_id"] = True
        # Clear auto ID flag if present
        if "auto_poll_id_selected" in context.user_data:
            del context.user_data["auto_poll_id_selected"]
            
        # Stay in the CUSTOM_ID state to wait for the custom ID input
        logger.info("Staying in CUSTOM_ID state, waiting for poll ID input")
        return CUSTOM_ID

async def handle_poll_custom_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom ID input for poll conversion."""
    # Log what we're doing
    logger.info(f"Handling poll custom ID: {update.message.text}")
    logger.info(f"Context data: {context.user_data}")
    
    # Always accept custom ID input regardless of awaiting_poll_id flag
    # This ensures the code works even if the flag wasn't properly set
    custom_id = update.message.text.strip()
    
    # Log what we've received
    logger.info(f"Received custom ID for poll: {custom_id}")
    
    # Store the ID - CRITICAL - do not convert to int, leave as string
    context.user_data["poll_custom_id"] = custom_id
    
    # Clear the awaiting flag if it exists
    if "awaiting_poll_id" in context.user_data:
        del context.user_data["awaiting_poll_id"]
        
    # Make sure we're properly tracking the context
    context.user_data['custom_poll_id_set'] = True
    
    # Show category selection
    categories = ["General Knowledge", "Science", "History", "Geography", "Entertainment", "Sports"]
    keyboard = [[InlineKeyboardButton(cat, callback_data=f"pollcat_{cat}")] for cat in categories]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send an acknowledgment message first to make sure user knows we received the ID
    success_message = f"✅ Using custom ID: <b>{custom_id}</b>"
    await update.message.reply_text(success_message, parse_mode='HTML')
    
    # Now ask for category
    await update.message.reply_text(
        "Now select a category for this question:",
        reply_markup=reply_markup
    )
    
    # Move to category selection state
    logger.info(f"Moving to CATEGORY state for poll with custom ID: {custom_id}")
    return CATEGORY

async def handle_poll_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
    logger.info(f"Adding question with ID: {question_id}, data: {poll_data}")
    result = add_question_with_id(question_id, poll_data)
    
    if not result:
        # If there was an error adding the question
        await query.edit_message_text(
            "❌ There was a problem adding the question. Please try again."
        )
        return ConversationHandler.END
    
    # Get how many questions are now at this ID
    questions = load_questions()
    if str(question_id) not in questions:
        # This should not happen if add_question_with_id was successful
        logger.error(f"Question ID {question_id} not found after adding!")
        question_count = 0
    else:
        question_count = len(questions[str(question_id)]) if isinstance(questions[str(question_id)], list) else 1
    
    success_message = (
        f"✅ Question added successfully with ID: {question_id}\n\n"
        f"This ID now has {question_count} question(s)\n\n"
        f"Question: {poll_data['question']}\n"
        f"Category: {category}\n"
        f"Options: {len(poll_data['options'])}\n"
        f"Correct answer: {poll_data['answer']+1}. {poll_data['options'][poll_data['answer']]}"
    )
    
    await query.edit_message_text(success_message)
    
    # End the conversation
    return ConversationHandler.END

async def quiz_with_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a quiz with questions from a specific ID."""
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "❌ You need to specify the quiz ID. Example: /quizid 10"
        )
        return
    
    quiz_id = args[0]
    
    # Get questions for this ID
    questions = load_questions()
    if quiz_id not in questions:
        await update.message.reply_text(
            f"❌ No questions found with ID {quiz_id}. Please check the ID and try again."
        )
        return
    
    # Get the number of questions
    if isinstance(questions[quiz_id], list):
        num_questions = len(questions[quiz_id])
        # Convert to format compatible with quiz_command
        selected_questions = [(quiz_id, q) for q in questions[quiz_id]]
    else:
        num_questions = 1
        selected_questions = [(quiz_id, questions[quiz_id])]
    
    # Check if a quiz is already running in this chat
    chat_id = update.effective_chat.id
    if context.chat_data.get('quiz_running', False):
        await update.message.reply_text(
            "❌ A quiz is already running in this chat. Please wait for it to finish or use /stop to stop it."
        )
        return
    
    # Show negative marking options before starting the quiz
    await show_negative_marking_options(update, context, quiz_id, selected_questions)

async def show_negative_marking_options(update: Update, context: ContextTypes.DEFAULT_TYPE, quiz_id, questions=None):
    """Show negative marking options for a quiz"""
    # Create keyboard for selecting negative marking value
    keyboard = []
    for option_name, option_value in ADVANCED_NEGATIVE_MARKING_OPTIONS:
        if option_value == "custom":
            keyboard.append([InlineKeyboardButton(option_name, callback_data=f"qneg_{quiz_id}_custom")])
        else:
            callback_data = f"qneg_{quiz_id}_{option_value}"
            keyboard.append([InlineKeyboardButton(option_name, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Store questions in context for later use
    if questions:
        context.user_data[f"quiz_{quiz_id}_questions"] = questions
    
    await update.message.reply_text(
        f"Please select negative marking value for quiz '{quiz_id}':\n\n"
        f"This determines how many points are deducted for wrong answers.",
        reply_markup=reply_markup
    )

async def negative_marking_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback queries from negative marking selection"""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    if callback_data.startswith("qneg_"):
        parts = callback_data.split("_")
        if len(parts) >= 3:
            quiz_id = parts[1]
            value = parts[2]
            
            if value == "custom":
                # Ask for custom negative marking value
                await query.edit_message_text(
                    f"Please enter a custom negative marking value for quiz '{quiz_id}':\n\n"
                    f"Enter a number between 0 and 1.5 (e.g., 0.33)"
                )
                context.user_data["awaiting_custom_neg_for_quiz"] = quiz_id
            else:
                # Set the negative marking value and start the quiz
                penalty_value = float(value)
                set_quiz_penalty(quiz_id, penalty_value)
                
                # Get the questions from context
                questions = context.user_data.get(f"quiz_{quiz_id}_questions")
                if questions:
                    # Clean up
                    del context.user_data[f"quiz_{quiz_id}_questions"]
                    
                    # Start the quiz with this negative marking value
                    await start_quiz_with_negative_marking(update, context, quiz_id, questions, penalty_value)
                else:
                    await query.edit_message_text(
                        f"✅ Negative marking set to {penalty_value} for quiz ID '{quiz_id}'\n\n"
                        f"Use /quizid {quiz_id} to start the quiz."
                    )
    
    else:
        await query.edit_message_text(
            "❌ Invalid selection. Please try again."
        )

async def handle_custom_negative_marking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle custom negative marking value input"""
    if "awaiting_custom_neg_for_quiz" in context.user_data:
        quiz_id = context.user_data["awaiting_custom_neg_for_quiz"]
        del context.user_data["awaiting_custom_neg_for_quiz"]
        
        try:
            value_text = update.message.text.strip()
            penalty_value = float(value_text)
            
            # Validate the value
            if penalty_value < 0 or penalty_value > 1.5:
                await update.message.reply_text(
                    "❌ Invalid value. Please enter a number between 0 and 1.5."
                )
                return
            
            # Set the negative marking value
            set_quiz_penalty(quiz_id, penalty_value)
            
            # Get the questions from context
            questions = context.user_data.get(f"quiz_{quiz_id}_questions")
            if questions:
                # Clean up
                del context.user_data[f"quiz_{quiz_id}_questions"]
                
                # Acknowledge the value and start the quiz
                await update.message.reply_text(
                    f"✅ Custom negative marking set to {penalty_value} for quiz ID '{quiz_id}'."
                )
                
                # Start the quiz with this negative marking value
                await start_quiz_with_negative_marking(update, context, quiz_id, questions, penalty_value)
            else:
                await update.message.reply_text(
                    f"✅ Custom negative marking set to {penalty_value} for quiz ID '{quiz_id}'\n\n"
                    f"Use /quizid {quiz_id} to start the quiz."
                )
                
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid number format. Please enter a valid number (e.g., 0.33)."
            )
    else:
        # Not awaiting custom negative marking
        pass

async def start_quiz_with_negative_marking(update: Update, context: ContextTypes.DEFAULT_TYPE, quiz_id, questions, neg_value):
    """Start a quiz with custom negative marking value"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_name = update.effective_user.username or update.effective_user.full_name
    
    # Add participant record
    add_participant(user_id, user_name, update.effective_user.first_name)
    
    # Check if a quiz is already running in this chat
    if context.chat_data.get('quiz_running', False):
        if hasattr(update, 'callback_query'):
            await update.callback_query.edit_message_text(
                "❌ A quiz is already running in this chat. Please wait for it to finish or use /stop to stop it."
            )
        else:
            await update.message.reply_text(
                "❌ A quiz is already running in this chat. Please wait for it to finish or use /stop to stop it."
            )
        return
    
    # Get the number of questions
    num_questions = len(questions)
    
    # Store quiz data in context
    context.chat_data['quiz_running'] = True
    context.chat_data['quiz_id'] = quiz_id
    context.chat_data['questions'] = questions
    context.chat_data['current_question'] = 0
    context.chat_data['participants'] = {}
    
    # Announce the quiz with negative marking info
    announcement = (
        f"🎮 *Starting Quiz with ID: {quiz_id}*\n\n"
        f"Number of questions: {num_questions}\n"
        f"Negative marking: {neg_value} points per wrong answer\n"
        f"Each question will be shown for 20 seconds.\n"
        f"Use /stop to end the quiz early.\n\n"
        f"First question coming up in 3 seconds..."
    )
    
    if hasattr(update, 'callback_query'):
        await update.callback_query.edit_message_text(announcement, parse_mode='Markdown')
    else:
        await update.message.reply_text(announcement, parse_mode='Markdown')
    
    # Schedule the first question with a delay
    await asyncio.sleep(3)
    await send_question(context, chat_id, 0)

async def pdf_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show information about PDF import feature."""
    info_text = """
📄 *PDF Import Feature*

The /pdfimport command allows you to automatically extract questions from PDF documents.

*Supported PDF Types:*
- Text-based PDFs with extractable text
- Image-based PDFs with Hindi/English text
- PDFs containing structured questions and options

*Extraction Process:*
1. The system first attempts to extract text directly
2. If direct extraction fails, OCR is used for images
3. Questions and options are parsed automatically
4. Correct answers are detected based on formatting

*Best Practices:*
- Use PDFs with clear formatting
- Ensure questions have a clear structure
- Correct answers can be marked with ✓, ✅, or *
- Numbering formats like "1.", "Q1.", "Question 1" work best

*Starting a Quiz:*
After import, use /quizid [ID] to start a quiz with the imported questions.

For text-based imports, try /txtimport
"""
    await update.message.reply_text(info_text, parse_mode='Markdown')

async def stop_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    # Check if a quiz is running
    if context.chat_data.get('quiz_running', False):
        await update.message.reply_text("Stopping the current quiz...")
        await end_quiz(context, chat_id)
    else:
        await update.message.reply_text("No quiz is currently running in this chat.")

async def txtimport_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the text import process"""
    # Clear any previous import data
    for key in ["txt_file_path", "awaiting_txt_id", "txt_custom_id"]:
        if key in context.user_data:
            del context.user_data[key]
    
    await update.message.reply_text(
        "📄 *Text Import Feature*\n\n"
        "Please send me a text file containing your questions.\n\n"
        "The text will be processed to extract questions, options and correct answers automatically.\n\n"
        "*Supported formats:*\n"
        "- Questions with numbered or lettered options\n"
        "- Multiple languages including Hindi/Rajasthani\n"
        "- Correct answers marked with ✓ or ✅ or *\n"
        "- Or correct answers indicated by 'Ans: A', etc.\n"
        "\nUpload your text file now:",
        parse_mode='Markdown'
    )
    
    return TXT_UPLOAD

async def receive_txt_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle text file upload - more robust implementation"""
    # Check if this is a document
    if update.message.document:
        file = update.message.document
        
        # Check file size
        if file.file_size > 5 * 1024 * 1024:  # 5 MB limit
            await update.message.reply_text(
                "❌ File is too large. Please send a file under 5 MB."
            )
            return TXT_UPLOAD
            
        # Check file extension
        file_ext = os.path.splitext(file.file_name.lower())[1] if file.file_name else ""
        if file_ext not in [".txt", ".text"]:
            await update.message.reply_text(
                "❌ Please send a text file (.txt)."
            )
            return TXT_UPLOAD
            
        # Download the file
        temp_file_path = f"{TEMP_DIR}/{int(datetime.datetime.now().timestamp())}_{file.file_name}"
        new_file = await context.bot.get_file(file.file_id)
        await new_file.download_to_drive(temp_file_path)
        
        # Store the file path in context
        context.user_data["txt_file_path"] = temp_file_path
        context.user_data["txt_auto_id"] = get_next_question_id()
        
        # Ask for ID method
        keyboard = [
            [InlineKeyboardButton("Auto-generate ID", callback_data="txtid_auto")],
            [InlineKeyboardButton("Specify custom ID", callback_data="txtid_custom")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ File '{file.file_name}' received!\n\n"
            "How would you like to assign an ID for these questions?",
            reply_markup=reply_markup
        )
        
        return TXT_CUSTOM_ID
    else:
        await update.message.reply_text(
            "❌ Please send a text file document.\n\n"
            "*Hint:* Use the attachment button to upload a file, not paste text.",
            parse_mode='Markdown'
        )
        return TXT_UPLOAD

async def handle_txtid_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle text import ID selection callbacks"""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    logger.info(f"Received txtid callback: {callback_data}")
    
    if callback_data == "txtid_auto":
        # Use the auto-generated ID
        # Get the existing file path and auto ID from context
        file_path = context.user_data.get('txt_file_path')
        auto_id = context.user_data.get('txt_auto_id', get_next_question_id())
        context.user_data['txt_custom_id'] = auto_id
        
        logger.info(f"Processing text import with auto ID: {auto_id}")
        await query.edit_message_text(f"Processing with auto ID: {auto_id}...")
        
        # Process the file with the auto ID
        return await process_txt_file(update, context)
        
    elif callback_data == "txtid_custom":
        # Ask for custom ID
        await query.edit_message_text(
            "Please enter a custom ID for these questions (single word, no spaces):\n\n"
            "Example: 'june_quiz' or 'history2025'"
        )
        # Flag to indicate we're waiting for custom ID input
        context.user_data['awaiting_txt_id'] = True
        return TXT_CUSTOM_ID
    
    return TXT_CUSTOM_ID

async def set_custom_id_txt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Set custom ID for the imported questions from text file and process the file immediately"""
    if context.user_data.get('awaiting_txt_id'):
        custom_id = update.message.text.strip()
        
        # No need to validate much, just ensure it's not empty
        if not custom_id:
            await update.message.reply_text(
                "❌ Custom ID cannot be empty. Please enter a valid ID:\n"
                "Example: 'june_quiz' or 'history2025'"
            )
            return TXT_CUSTOM_ID
        
        # Store the ID in context
        context.user_data['txt_custom_id'] = custom_id
        del context.user_data['awaiting_txt_id']
        
        # Acknowledge receipt of custom ID
        await update.message.reply_text(f"✅ Using custom ID: <b>{custom_id}</b>", parse_mode='HTML')
        
        # Process the file with this custom ID
        return await process_txt_file(update, context)
    else:
        await update.message.reply_text(
            "❌ Something went wrong. Please start over with /txtimport"
        )
        return ConversationHandler.END

async def process_txt_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the uploaded text file and extract questions"""
    # Log what's happening
    logger.info(f"Processing text file with context: {list(context.user_data.keys())}")
    
    # For callback queries, we need to handle update.callback_query
    # For message-based updates, we use update.message
    # Determine which type of update we're handling
    callback_query = getattr(update, 'callback_query', None)
    message = callback_query.message if callback_query else getattr(update, 'message', None)
    
    if not message:
        logger.error("Neither callback_query message nor message found in update")
        return ConversationHandler.END
    
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
        error_text = "❌ File path not found. Please try uploading again."
        if callback_query:
            await callback_query.edit_message_text(error_text)
        else:
            await message.reply_text(error_text)
        return ConversationHandler.END
    
    if not os.path.exists(file_path):
        logger.error(f"File does not exist at path: {file_path}")
        error_text = "❌ File not found on disk. Please try uploading again."
        if callback_query:
            await callback_query.edit_message_text(error_text)
        else:
            await message.reply_text(error_text)
        return ConversationHandler.END
    
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
    
    # Extract questions - Using your existing function
    # This function should be properly defined elsewhere in your code
    from extract_questions_from_txt import extract_questions_from_txt
    questions = extract_questions_from_txt(lines)
    
    if not questions:
        error_msg = "❌ No valid questions found in the text file.\nPlease check the file format and try again."
        try:
            if callback_query:
                await callback_query.edit_message_text(error_msg)
            else:
                await message.reply_text(error_msg)
        except Exception as e:
            logger.error(f"Error sending no questions found message: {e}")
        
        # Clean up
        if os.path.exists(file_path):
            os.remove(file_path)
        return ConversationHandler.END
    
    # Save questions with the custom ID
    success = False
    try:
        logger.info(f"Adding {len(questions)} questions with ID: {custom_id}")
        for question in questions:
            add_question_with_id(custom_id, question)
        success = True
        logger.info(f"Successfully added {len(questions)} questions with ID: {custom_id}")
    except Exception as e:
        logger.error(f"Error adding questions: {e}")
        error_msg = f"❌ Error saving questions: {e}\nPlease try again."
        if callback_query:
            await callback_query.edit_message_text(error_msg)
        else:
            await message.reply_text(error_msg)
        # Clean up
        if os.path.exists(file_path):
            os.remove(file_path)
        return ConversationHandler.END
    
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
        # Different message sending based on update type
        if callback_query:
            await callback_query.edit_message_text(success_msg, parse_mode='HTML')
        else:
            await message.reply_text(success_msg, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Failed to send completion message: {e}")
        # Try one more time without parse_mode as fallback
        try:
            plain_msg = f"✅ Successfully imported {len(questions)} questions with ID: {custom_id}. Use /quizid {custom_id} to start a quiz."
            if callback_query:
                await callback_query.edit_message_text(plain_msg)
            else:
                await message.reply_text(plain_msg)
        except Exception as e2:
            logger.error(f"Final attempt to send message failed: {e2}")
    
    return ConversationHandler.END

def main() -> None:
    """Start the bot."""
    # Log startup information
    logger.info(f"Starting bot at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"BOT_TOKEN available: {bool(BOT_TOKEN)}")
    
    # Ensure directories exist
    os.makedirs(TEMP_DIR, exist_ok=True)
    os.makedirs(PDF_RESULTS_DIR, exist_ok=True)
    
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).build()

    # Basic commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("exstats", extended_stats_command))
    application.add_handler(CommandHandler("neg", negative_marking_settings))
    application.add_handler(CommandHandler("negmark", negative_marking_settings))  # Alias
    application.add_handler(CommandHandler("resetpenalty", reset_user_penalty_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("quizid", quiz_with_id_command))
    application.add_handler(CommandHandler("stop", stop_quiz_command))
    application.add_handler(CommandHandler("pdfinfo", pdf_info_command))
    
    # Poll to question command and handlers - using ConversationHandler
    poll2q_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("poll2q", poll_to_question)],
        states={
            QUESTION: [MessageHandler(filters.FORWARDED & ~filters.COMMAND, handle_forwarded_poll)],
            ANSWER: [CallbackQueryHandler(handle_poll_answer, pattern=r"^poll_answer_")],
            CUSTOM_ID: [
                CallbackQueryHandler(handle_poll_id_selection, pattern=r"^pollid_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_poll_custom_id)
            ],
            CATEGORY: [CallbackQueryHandler(handle_poll_category, pattern=r"^pollcat_")]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,  # Allow re-entering the conversation
        name="poll2q_handler"  # Adding name for better tracking in logs
    )
    application.add_handler(poll2q_conv_handler)
    
    # Add question conversation handler
    add_question_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_question_start)],
        states={
            CUSTOM_ID: [
                CallbackQueryHandler(custom_id_callback, pattern=r"^(auto|custom)_id$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_id_input)
            ],
            QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_text)],
            OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_question_options)],
            ANSWER: [CallbackQueryHandler(add_question_answer, pattern=r"^answer_\d+$")],
            CATEGORY: [CallbackQueryHandler(category_callback, pattern=r"^cat_")]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,  # Allow re-entering the conversation
        name="add_question_handler"  # Adding name for better tracking in logs
    )
    application.add_handler(add_question_handler)
    
    # Text import conversation handler
    txtimport_handler = ConversationHandler(
        entry_points=[CommandHandler("txtimport", txtimport_start)],
        states={
            TXT_UPLOAD: [MessageHandler(filters.Document.ALL & ~filters.COMMAND, receive_txt_file)],
            TXT_CUSTOM_ID: [
                CallbackQueryHandler(handle_txtid_callback, pattern=r"^txtid_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_custom_id_txt)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,  # Allow re-entering the conversation
        name="txtimport_handler"  # Adding name for better tracking in logs
    )
    application.add_handler(txtimport_handler)
    
    # Handle callback queries not covered by other handlers
    application.add_handler(CallbackQueryHandler(negative_settings_callback, pattern=r"^neg_"))
    application.add_handler(CallbackQueryHandler(negative_marking_callback, pattern=r"^qneg_"))
    
    # Handle poll answers
    application.add_handler(PollAnswerHandler(poll_answer))
    
    # Run the bot until the user presses Ctrl-C
    logger.info("Starting polling...")
    application.run_polling()

if __name__ == "__main__":
    main()
