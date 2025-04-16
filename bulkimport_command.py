"""
Bulk Import Command for Telegram Quiz Bot
- Allows pasting multiple questions at once
- Parses text into properly formatted questions
- Saves questions to the existing storage system
"""

import re
import json
import logging

# Dynamically import Telegram modules to avoid import errors when just testing
try:
    from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
    from telegram.ext import (
        ConversationHandler, CommandHandler, MessageHandler, 
        filters, CallbackQueryHandler, ContextTypes
    )
    TELEGRAM_IMPORTED = True
except ImportError:
    # Create dummy objects for testing without Telegram
    TELEGRAM_IMPORTED = False
    class DummyClass: pass
    Update = InlineKeyboardMarkup = InlineKeyboardButton = DummyClass
    ConversationHandler = CommandHandler = MessageHandler = DummyClass
    CallbackQueryHandler = ContextTypes = DummyClass
    filters = DummyClass()
    filters.TEXT = filters.COMMAND = DummyClass()

# Conversation states
PASTE_QUESTIONS, CONFIRM_IMPORT, ASSIGN_CATEGORY = range(200, 203)

# Example formats to show the user
EXAMPLE_FORMATS = """
Examples of supported formats:

Format 1:
Q: What is the capital of France?
A) Berlin
B) Madrid
C) Paris
D) Rome
Answer: C

Format 2:
1. Which planet is known as the Red Planet?
1) Venus
2) Mars
3) Jupiter
4) Saturn
Correct: 2

Format 3:
Question: Who wrote "Romeo and Juliet"?
Options:
- Charles Dickens
- Jane Austen
- William Shakespeare
- Mark Twain
Answer: William Shakespeare
"""

# Function to get the bulk import handler - this will be imported by the main bot
def get_bulk_import_handler():
    """Return the ConversationHandler for bulk import."""
    # Only try to return a handler if Telegram is properly imported
    if not TELEGRAM_IMPORTED:
        logging.warning("Telegram modules not available. Handler cannot be created.")
        return None
        
    # Import these inside the function to avoid circular imports
    # and to allow dynamically loading when needed
    try:
        from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters
        
        return ConversationHandler(
            entry_points=[CommandHandler("bulkimport", bulkimport_command)],
            states={
                PASTE_QUESTIONS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, parse_questions),
                ],
                CONFIRM_IMPORT: [
                    CallbackQueryHandler(confirm_import, pattern=r"^(confirm|cancel)_import$"),
                ],
                ASSIGN_CATEGORY: [
                    CallbackQueryHandler(assign_category, pattern=r"^cat_"),
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel)]
        )
    except ImportError:
        logging.warning("Could not create handler due to missing Telegram imports")
        return None

async def bulkimport_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the bulk import conversation."""
    user = update.effective_user
    
    # Store an empty list for parsed questions
    context.user_data['parsed_questions'] = []
    
    await update.message.reply_html(
        f"Hi {user.mention_html()}! Let's import multiple questions at once.\n\n"
        f"Please paste your questions below. I can recognize several common formats.\n"
        f"{EXAMPLE_FORMATS}\n\n"
        f"Type /cancel to abort the import process."
    )
    
    return PASTE_QUESTIONS

async def parse_questions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Parse the pasted questions."""
    text = update.message.text
    
    if not text or text.strip() == "":
        await update.message.reply_text("Please paste some questions or type /cancel.")
        return PASTE_QUESTIONS
    
    # Placeholder for parsed questions
    parsed_questions = []
    
    # Split text into potential question blocks
    # We'll try different splitting strategies
    blocks = []
    
    # Try to split by "Q:" or "Question:" pattern
    if "Q:" in text or "Question:" in text or re.search(r"\b[0-9]+\.", text):
        # Split by question markers
        split_pattern = r"(?:^|\n)(?:Q:|Question:|[0-9]+\.)\s"
        question_blocks = re.split(split_pattern, text, flags=re.MULTILINE)
        
        # Filter out empty blocks and re-add the Q: prefix for consistency
        for block in question_blocks:
            if block.strip():
                blocks.append(block.strip())
    else:
        # If no obvious question markers, try to analyze line by line
        lines = text.split('\n')
        current_block = []
        
        for line in lines:
            line = line.strip()
            if not line:
                if current_block:
                    blocks.append('\n'.join(current_block))
                    current_block = []
            else:
                current_block.append(line)
        
        if current_block:
            blocks.append('\n'.join(current_block))
    
    # Process each block
    for block in blocks:
        question_data = parse_question_block(block)
        if question_data:
            parsed_questions.append(question_data)
    
    # Store parsed questions in context
    context.user_data['parsed_questions'] = parsed_questions
    
    if not parsed_questions:
        await update.message.reply_text(
            "I couldn't parse any questions from your text. Please check the format and try again.\n\n"
            f"{EXAMPLE_FORMATS}\n\n"
            "Type /cancel to abort the import process."
        )
        return PASTE_QUESTIONS
    
    # Show a summary of what was parsed
    summary = f"✅ Successfully parsed {len(parsed_questions)} questions:\n\n"
    
    for i, q in enumerate(parsed_questions[:5], 1):
        summary += f"{i}. {q['question'][:50]}{'...' if len(q['question']) > 50 else ''}\n"
    
    if len(parsed_questions) > 5:
        summary += f"...and {len(parsed_questions) - 5} more\n"
    
    keyboard = [
        [
            InlineKeyboardButton("✓ Confirm Import", callback_data="confirm_import"),
            InlineKeyboardButton("✗ Cancel", callback_data="cancel_import"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(summary, reply_markup=reply_markup)
    
    return CONFIRM_IMPORT

def parse_question_block(text):
    """Parse a single question block into the required format."""
    # Initialize empty question data
    question_data = {
        "question": "",
        "options": [],
        "correct_answer": None,
        "category": "General Knowledge"  # Default category
    }
    
    # Extract the question text
    question_match = re.search(r"^(?:Q:|Question:|[0-9]+\.)\s*(.*?)(?:\n|\?|$)", text, re.IGNORECASE)
    if question_match:
        question_data["question"] = question_match.group(1).strip()
        if not question_data["question"].endswith("?"):
            question_data["question"] += "?"
    else:
        return None
    
    # Extract options - try different patterns
    
    # Pattern 1: A) Option, B) Option...
    options_pattern1 = re.findall(r"(?:^|\n)([A-D])[).:]\s*(.*?)(?=\n[A-D][).:]\s*|\n(?:Answer|Correct)|$)", text, re.DOTALL)
    
    # Pattern 2: 1) Option, 2) Option...
    # Split by line to process more intelligently
    lines = text.strip().split('\n')
    options_pattern2 = []
    question_pattern = re.match(r"^\s*([0-9]+)[.]\s+(.*)", lines[0]) if lines else None
    
    # Process each line that has a numeric prefix
    for line in lines:
        # Skip lines with question number or answer
        if line == lines[0] and question_pattern:
            continue
        if re.search(r"(?:Answer|Correct)", line, re.IGNORECASE):
            continue
            
        # Look for numbered options
        option_match = re.match(r"^\s*([1-4])[).:]\s+(.*)", line)
        if option_match:
            options_pattern2.append((option_match.group(1), option_match.group(2)))
    
    # Pattern 3: - Option (bullet points)
    options_pattern3 = re.findall(r"(?:^|\n)(?:Options:)?\s*(?:[-•*])\s*(.*?)(?=\n[-•*]\s*|\n(?:Answer|Correct)|$)", text, re.DOTALL)
    
    if options_pattern1:
        for letter, option in options_pattern1:
            question_data["options"].append(option.strip())
        
        # Look for the correct answer (letter)
        answer_match = re.search(r"(?:Answer|Correct)[^A-D]*([A-D])", text, re.IGNORECASE)
        if answer_match:
            letter = answer_match.group(1).upper()
            # Convert letter to index (A=0, B=1, etc.)
            correct_index = ord(letter) - ord('A')
            if 0 <= correct_index < len(question_data["options"]):
                question_data["correct_answer"] = correct_index
            
    elif options_pattern2:
        # Check if we need to skip the first option (when the question and first option might be the same)
        question_text = question_data["question"].strip('?').lower()
        all_options = []
        
        for number, option_text in options_pattern2:
            # We need to check if the option matches the question itself
            option_clean = option_text.strip().lower()
            if option_clean != question_text:
                all_options.append(option_text.strip())
        
        question_data["options"] = all_options
        
        # Look for the correct answer (number)
        answer_match = re.search(r"(?:Answer|Correct)[^1-4]*([1-4])", text, re.IGNORECASE)
        if answer_match:
            number = answer_match.group(1)
            # Convert to index (1=0, 2=1, etc.)
            correct_index = int(number) - 1
            if 0 <= correct_index < len(all_options):
                question_data["correct_answer"] = correct_index
            
    elif options_pattern3:
        question_data["options"] = [option.strip() for option in options_pattern3]
        
        # Look for the correct answer (text)
        answer_match = re.search(r"(?:Answer|Correct)[^A-Za-z]*(.+?)$", text, re.IGNORECASE | re.MULTILINE)
        if answer_match:
            correct_text = answer_match.group(1).strip()
            # Find the matching option
            for i, option in enumerate(question_data["options"]):
                if option.lower() == correct_text.lower() or option.lower().startswith(correct_text.lower()):
                    question_data["correct_answer"] = i
                    break
    
    # If we have options but no correct answer, try one more method
    if question_data["options"] and question_data["correct_answer"] is None:
        # Look for any mention of "correct" near an option
        for i, option in enumerate(question_data["options"]):
            if re.search(r"(?:correct|right|✓|✅)", option, re.IGNORECASE):
                question_data["correct_answer"] = i
                # Remove the "correct" marker from the option text
                clean_option = re.sub(r"\s*(?:correct|right|✓|✅).*", "", option, flags=re.IGNORECASE)
                question_data["options"][i] = clean_option.strip()
                break
    
    # Validate the parsed question
    if not question_data["question"] or not question_data["options"] or question_data["correct_answer"] is None:
        return None
    
    return question_data

async def confirm_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the confirmation of import."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_import":
        await query.edit_message_text("Import canceled. No questions were added.")
        return ConversationHandler.END
    
    # Prepare to ask for category
    categories = [
        "General Knowledge", "Science", "History", 
        "Geography", "Entertainment", "Sports"
    ]
    
    keyboard = []
    for category in categories:
        keyboard.append([InlineKeyboardButton(category, callback_data=f"cat_{category}")])
    
    # Add a "Skip" option to use default category
    keyboard.append([InlineKeyboardButton("Skip (use default)", callback_data="cat_skip")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Please select a category for all {len(context.user_data['parsed_questions'])} questions:",
        reply_markup=reply_markup
    )
    
    return ASSIGN_CATEGORY

async def assign_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Assign a category to all questions and save them."""
    query = update.callback_query
    await query.answer()
    
    parsed_questions = context.user_data.get('parsed_questions', [])
    
    if not parsed_questions:
        await query.edit_message_text("No questions to import. The process has been canceled.")
        return ConversationHandler.END
    
    # Extract category from callback data
    if query.data == "cat_skip":
        category = "General Knowledge"  # Default
    else:
        category = query.data[4:]  # Remove "cat_" prefix
    
    # Load existing questions
    try:
        with open("questions.json", 'r') as f:
            questions = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        questions = {}
    
    # Track how many questions were successfully added
    added_count = 0
    
    # Get the next question ID
    next_id = 1
    for qid in questions.keys():
        try:
            id_num = int(qid)
            if id_num >= next_id:
                next_id = id_num + 1
        except ValueError:
            pass
    
    # Add each parsed question
    for question_data in parsed_questions:
        # Assign the selected category
        question_data["category"] = category
        
        # Add to questions dictionary
        if str(next_id) not in questions:
            questions[str(next_id)] = [question_data]
        else:
            if not isinstance(questions[str(next_id)], list):
                questions[str(next_id)] = [questions[str(next_id)]]
            questions[str(next_id)].append(question_data)
        
        next_id += 1
        added_count += 1
    
    # Save updated questions
    try:
        with open("questions.json", 'w') as f:
            json.dump(questions, f, indent=4)
    except Exception as e:
        await query.edit_message_text(f"Error saving questions: {str(e)}")
        return ConversationHandler.END
    
    # Provide success feedback
    await query.edit_message_text(
        f"✅ Success! Added {added_count} new questions to the '{category}' category.\n\n"
        f"You can now use these questions in quizzes with the /quiz command."
    )
    
    # Clear user data
    context.user_data.pop('parsed_questions', None)
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    await update.message.reply_text("Bulk import canceled. No questions were added.")
    
    # Clear user data
    context.user_data.pop('parsed_questions', None)
    
    return ConversationHandler.END

# Usage instructions:
# To add this handler to your main bot application, add the following to your main bot file:
# from bulkimport_command import get_bulk_import_handler
# application.add_handler(get_bulk_import_handler())
