"""
Telegram Quiz Clone Tester Script

This is a minimal script that tests the quiz cloning feature.
It does only one thing: Clone a quiz from @QuizBot.

IMPORTANT: THIS IS NOT THE FULL BOT - it's just a tester script!
"""

import asyncio
import logging
import json
import re
import os
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# HARDCODED CREDENTIALS - as native Python types (no strings for integer values)
API_ID = 28624690  # Integer, not a string
API_HASH = "67e6593b5a9b5ab20b11ccef6700af5f"  # String
PHONE_NUMBER = "+919351504990"  # String

# Quiz ID to test with (default to a sample quiz if none provided)
TEST_QUIZ_ID = "5640"  # From your screenshot

# File to save cloned questions
OUTPUT_FILE = "cloned_questions.json"

async def extract_quiz_from_quizbot(quiz_id):
    """
    Core function: Extract quiz questions from @QuizBot
    """
    print(f"Starting quiz clone test for ID: {quiz_id}")
    print(f"Using API_ID: {API_ID}")
    print(f"Using API_HASH: {API_HASH}")
    
    # Initialize client (with hard-coded credentials)
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    
    try:
        print("Connecting to Telegram...")
        await client.connect()
        
        # Check authorization
        if not await client.is_user_authorized():
            print(f"Not authorized. Sending code to {PHONE_NUMBER}...")
            await client.send_code_request(PHONE_NUMBER)
            print("A verification code has been sent to your phone.")
            print("Please enter the code you received: ", end="")
            code = input()
            await client.sign_in(PHONE_NUMBER, code)
        
        print("Successfully connected to Telegram!")
        
        # Get QuizBot entity
        print("Contacting @QuizBot...")
        quizbot_entity = await client.get_entity("QuizBot")
        
        # Send /start command with quiz ID
        print(f"Starting quiz {quiz_id}...")
        await client.send_message(quizbot_entity, f"/start {quiz_id}")
        
        # Wait for bot response
        await asyncio.sleep(2)
        
        # Check if the quiz is valid
        messages = await client.get_messages(quizbot_entity, limit=5)
        valid_quiz = False
        quiz_title = "Unknown Quiz"
        
        for msg in messages:
            if hasattr(msg, 'text') and "start the quiz" in msg.text.lower():
                valid_quiz = True
                lines = msg.text.split('\n')
                if lines:
                    quiz_title = lines[0].strip()
                break
        
        if not valid_quiz:
            print(f"Error: ID {quiz_id} doesn't seem to be a valid quiz.")
            return False
        
        print(f"Found quiz: {quiz_title}")
        
        # Click "Start Quiz" button
        button_clicked = False
        async for message in client.iter_messages(quizbot_entity, limit=10):
            if hasattr(message, 'buttons') and message.buttons:
                for row in message.buttons:
                    for button in row:
                        if hasattr(button, 'text') and "start" in button.text.lower() and "quiz" in button.text.lower():
                            await message.click(text=button.text)
                            button_clicked = True
                            break
                    if button_clicked:
                        break
            if button_clicked:
                break
        
        if not button_clicked:
            print("Could not find the Start Quiz button.")
            return False
        
        # Wait for first question
        await asyncio.sleep(3)
        
        # Extract questions
        print("Extracting questions...")
        questions = []
        max_questions = 50
        question_count = 0
        
        while question_count < max_questions:
            messages = await client.get_messages(quizbot_entity, limit=5)
            found_question = False
            
            for msg in messages:
                if hasattr(msg, 'poll') and msg.poll:
                    found_question = True
                    poll = msg.poll
                    
                    # Extract question data
                    question_text = poll.question
                    options = [opt.text for opt in poll.options]
                    
                    # Create question object
                    question_data = {
                        "question": question_text,
                        "options": options,
                        "answer": 0,  # Default to first option
                        "category": "Imported"
                    }
                    
                    questions.append(question_data)
                    question_count += 1
                    
                    print(f"Found question {question_count}: {question_text[:30]}...")
                    
                    # Click next button
                    next_clicked = False
                    for message in messages:
                        if hasattr(message, 'buttons') and message.buttons:
                            await message.click(0)
                            next_clicked = True
                            break
                    
                    if not next_clicked:
                        print("Could not find next button, might be the last question.")
                        break
                    
                    # Wait for next question
                    await asyncio.sleep(2)
                    break
            
            if not found_question:
                # Check if we reached the end
                end_reached = False
                for msg in messages:
                    if hasattr(msg, 'text') and msg.text and ("result" in msg.text.lower() or "score" in msg.text.lower()):
                        end_reached = True
                        break
                
                if end_reached or question_count > 0:
                    break
                elif question_count == 0:
                    await asyncio.sleep(3)
                    continue
        
        # Save questions to file
        if questions:
            with open(OUTPUT_FILE, 'w') as f:
                json.dump(questions, f, indent=2)
            
            print(f"\nSUCCESS! Cloned {len(questions)} questions from quiz {quiz_id}")
            print(f"Questions saved to {OUTPUT_FILE}")
            return True
        else:
            print("No questions were found in this quiz.")
            return False
    
    except Exception as e:
        print(f"Error occurred: {str(e)}")
        return False
    
    finally:
        await client.disconnect()

async def main():
    """Main function"""
    if len(sys.argv) > 1:
        quiz_id = sys.argv[1]
    else:
        quiz_id = TEST_QUIZ_ID
    
    print("="*50)
    print("TELEGRAM QUIZ CLONE TESTER")
    print("="*50)
    print("This script tests the capability to clone quizzes from @QuizBot")
    print("by using the Telethon library and hardcoded credentials.")
    print()
    
    success = await extract_quiz_from_quizbot(quiz_id)
    
    if success:
        print("\nTest completed successfully!")
    else:
        print("\nTest completed with errors.")
    
    print("="*50)

if __name__ == "__main__":
    asyncio.run(main())