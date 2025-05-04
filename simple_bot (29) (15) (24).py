# OCR + PDF Text Extraction + Block-Level Deduplication
import os
import re

# Enhanced HTML Generator Function
def ensure_directory(directory):
    """Ensure the directory exists"""
    if not os.path.exists(directory):
        os.makedirs(directory)
        logger.info(f"Created directory: {directory}")

def generate_enhanced_html_report(quiz_id, title=None, questions_data=None, leaderboard=None, quiz_metadata=None):
    """Generate an enhanced HTML report for the quiz with charts and visualizations"""
    import json
    import datetime
    
    try:
        # Ensure html_results directory exists
        html_dir = "html_results"
        ensure_directory(html_dir)
        
        # Create filename with timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        html_filename = f"quiz_{quiz_id}_results_{timestamp}.html"
        html_filepath = os.path.join(html_dir, html_filename)
        
        # Set title with fallback
        if not title:
            title = f"Quiz {quiz_id} Performance Analysis"
        
        # Sanitize inputs
        sanitized_questions = []
        if questions_data and isinstance(questions_data, dict):
            # Convert dict of questions to list
            for qid, question in questions_data.items():
                if isinstance(question, dict):
                    cleaned_question = {
                        "id": str(qid),
                        "question": question.get("question", ""),
                        "options": question.get("options", []),
                        "answer": question.get("answer", 0)
                    }
                    sanitized_questions.append(cleaned_question)
        elif questions_data and isinstance(questions_data, list):
            # Already a list, just sanitize each item
            for question in questions_data:
                if isinstance(question, dict):
                    sanitized_questions.append(question)
        
        # Sanitize leaderboard data
        sanitized_leaderboard = []
        if leaderboard and isinstance(leaderboard, list):
            for participant in leaderboard:
                if isinstance(participant, dict):
                    sanitized_leaderboard.append(participant)
        
        # Remove duplicate users based on user_id
        deduplicated_participants = []
        processed_users = set()  # Track processed users by ID
        
        # Sort leaderboard by score first
        sorted_participants = sorted(
            sanitized_leaderboard, 
            key=lambda x: x.get("adjusted_score", 0) if isinstance(x, dict) else 0, 
            reverse=True
        )
        
        for participant in sorted_participants:
            user_id = participant.get("user_id", "")
            
            # Only add each user once based on user_id
            if user_id and user_id not in processed_users:
                processed_users.add(user_id)
                deduplicated_participants.append(participant)
        
        # Use the deduplicated list for display
        sorted_leaderboard = deduplicated_participants
        
        # Calculate stats
        total_participants = len(sorted_leaderboard)
        
        if total_participants > 0:
            # Calculate statistics for all participants
            avg_score = sum(p.get("adjusted_score", 0) for p in sorted_leaderboard) / total_participants
            avg_correct = sum(p.get("correct_answers", 0) for p in sorted_leaderboard) / total_participants
            avg_wrong = sum(p.get("wrong_answers", 0) for p in sorted_leaderboard) / total_participants
        else:
            avg_score = avg_correct = avg_wrong = 0
        
        # Extract negative marking value from metadata
        negative_marking = quiz_metadata.get("negative_marking", 0) if quiz_metadata else 0
        total_questions = quiz_metadata.get("total_questions", len(sanitized_questions)) if quiz_metadata else len(sanitized_questions)
        
        # Prepare participant data for charts (top 10 only)
        chart_names = []
        chart_scores = []
        chart_correct = []
        chart_wrong = []
        
        for i, participant in enumerate(sorted_leaderboard[:10]):  # Limit to top 10
            name = participant.get("user_name", f"User {i+1}")
            score = participant.get("adjusted_score", 0)
            correct = participant.get("correct_answers", 0)
            wrong = participant.get("wrong_answers", 0)
            
            chart_names.append(name)
            chart_scores.append(score)
            chart_correct.append(correct)
            chart_wrong.append(wrong)
        
        # Create the HTML content with Chart.js
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title}</title>
            <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.7.1/chart.min.js"></script>
            <style>
                :root {{
                    --primary: #4361ee;
                    --secondary: #3f37c9;
                    --success: #4cc9f0;
                    --danger: #f72585;
                    --warning: #f8961e;
                    --info: #4895ef;
                    --light: #f8f9fa;
                    --dark: #212529;
                }}
                
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    background-color: #f5f7fa;
                    margin: 0;
                    padding: 0;
                }}
                
                .container {{
                    max-width: 1000px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                
                .header {{
                    background: linear-gradient(135deg, var(--primary), var(--secondary));
                    color: white;
                    padding: 25px;
                    border-radius: 10px;
                    margin-bottom: 25px;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                }}
                
                .header h1 {{
                    margin: 0;
                    font-size: 28px;
                }}
                
                .header p {{
                    margin: 10px 0 0;
                    opacity: 0.9;
                }}
                
                .card {{
                    background: white;
                    border-radius: 10px;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.05);
                    padding: 25px;
                    margin-bottom: 25px;
                    transition: transform 0.3s ease;
                }}
                
                .card:hover {{
                    transform: translateY(-5px);
                    box-shadow: 0 6px 12px rgba(0,0,0,0.1);
                }}
                
                .card h2 {{
                    margin-top: 0;
                    color: var(--primary);
                    border-bottom: 2px solid #eee;
                    padding-bottom: 10px;
                }}
                
                .chart-container {{
                    position: relative;
                    height: 300px;
                    margin: 20px 0;
                }}
                
                .stats-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 15px;
                    margin: 20px 0;
                }}
                
                .stat-card {{
                    background: var(--light);
                    border-radius: 8px;
                    padding: 15px;
                    text-align: center;
                    border-left: 4px solid var(--primary);
                }}
                
                .gold {{
                    border-left-color: #FFD700;
                    background-color: rgba(255, 215, 0, 0.1);
                }}
                
                .silver {{
                    border-left-color: #C0C0C0;
                    background-color: rgba(192, 192, 192, 0.1);
                }}
                
                .bronze {{
                    border-left-color: #CD7F32;
                    background-color: rgba(205, 127, 50, 0.1);
                }}
                
                .stat-value {{
                    font-size: 24px;
                    font-weight: bold;
                    margin: 10px 0;
                    color: var(--dark);
                }}
                
                .stat-label {{
                    font-size: 14px;
                    color: #666;
                }}
                
                .stat-name {{
                    font-weight: bold;
                    margin-bottom: 5px;
                }}
                
                .question {{
                    border-left: 4px solid var(--info);
                    padding: 15px;
                    margin-bottom: 20px;
                    background: rgba(72, 149, 239, 0.05);
                    border-radius: 0 8px 8px 0;
                }}
                
                .question-text {{
                    font-weight: bold;
                    margin-bottom: 10px;
                }}
                
                .metrics {{
                    display: flex;
                    flex-wrap: wrap;
                    gap: 15px;
                }}
                
                .metric {{
                    flex: 1;
                    min-width: 120px;
                    background: white;
                    padding: 10px;
                    border-radius: 8px;
                    text-align: center;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                }}
                
                .metric-value {{
                    font-size: 18px;
                    font-weight: bold;
                }}
                
                .metric-label {{
                    font-size: 12px;
                    color: #666;
                }}
                
                .leaderboard {{
                    width: 100%;
                    border-collapse: collapse;
                    margin: 20px 0;
                }}
                
                .leaderboard th, .leaderboard td {{
                    padding: 12px;
                    text-align: left;
                    border-bottom: 1px solid #eee;
                }}
                
                .leaderboard th {{
                    background-color: var(--light);
                    font-weight: bold;
                    color: var(--primary);
                }}
                
                .leaderboard tr:hover {{
                    background-color: rgba(67, 97, 238, 0.05);
                }}
                
                .rank {{
                    width: 60px;
                    text-align: center;
                    font-weight: bold;
                }}
                
                .gold-rank {{
                    color: #FFD700;
                }}
                
                .silver-rank {{
                    color: #808080;
                }}
                
                .bronze-rank {{
                    color: #CD7F32;
                }}
                
                .badge {{
                    display: inline-block;
                    padding: 3px 10px;
                    border-radius: 20px;
                    font-size: 12px;
                    font-weight: bold;
                }}
                
                .easy-badge {{
                    background-color: rgba(40, 167, 69, 0.2);
                    color: #28a745;
                }}
                
                .medium-badge {{
                    background-color: rgba(255, 193, 7, 0.2);
                    color: #d39e00;
                }}
                
                .hard-badge {{
                    background-color: rgba(220, 53, 69, 0.2);
                    color: #dc3545;
                }}
                
                .options-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 10px;
                    margin-top: 10px;
                }}
                
                .option {{
                    display: flex;
                    align-items: center;
                    padding: 8px;
                    border-radius: 4px;
                    border: 1px solid #ddd;
                }}
                
                .option-marker {{
                    width: 20px;
                    height: 20px;
                    border-radius: 50%;
                    margin-right: 10px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-weight: bold;
                    font-size: 12px;
                    color: white;
                }}
                
                .correct-option {{
                    background-color: rgba(40, 167, 69, 0.1);
                    border-color: #28a745;
                }}
                
                .correct-marker {{
                    background-color: #28a745;
                }}
                
                @media (max-width: 768px) {{
                    .container {{
                        padding: 15px;
                    }}
                    
                    .header {{
                        padding: 20px;
                    }}
                    
                    .card {{
                        padding: 15px;
                    }}
                    
                    .chart-container {{
                        height: 250px;
                    }}
                    
                    .stats-grid {{
                        grid-template-columns: 1fr 1fr;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{title}</h1>
                    <p>Quiz ID: {quiz_id} | Generated on {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
                </div>
        
                <div class="card">
                    <h2>Top Performers</h2>
                    <div class="stats-grid">
        """
        
        # Add top performers cards
        medals = [("gold", "🥇 1st Place"), ("silver", "🥈 2nd Place"), ("bronze", "🥉 3rd Place")]
        for i, participant in enumerate(sorted_leaderboard[:3]):
            if i < len(medals) and i < len(sorted_leaderboard):
                medal_class, medal_label = medals[i]
                name = participant.get("user_name", f"User {i+1}")
                score = participant.get("adjusted_score", 0)
                correct = participant.get("correct_answers", 0)
                wrong = participant.get("wrong_answers", 0)
                
                # Calculate percentage if possible
                total_attempts = correct + wrong
                percentage = (correct / total_attempts) * 100 if total_attempts > 0 else 0
                
                # Add this participant's card
                html_content += f"""
                    <div class="stat-card {medal_class}">
                        <div class="stat-label">{medal_label}</div>
                        <div class="stat-name">{name}</div>
                        <div class="stat-value">{score}</div>
                        <div class="stat-label">Score | {percentage:.1f}% | {correct}/{total_attempts}</div>
                    </div>
                """
        
        html_content += """
                    </div>
                    <div class="chart-container">
                        <canvas id="topPerformersChart"></canvas>
                    </div>
                </div>
                
                <div class="card">
                    <h2>Class Performance</h2>
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="stat-label">Participants</div>
                            <div class="stat-value">""" + str(total_participants) + """</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">Average Score</div>
                            <div class="stat-value">""" + f"{avg_score:.1f}" + """</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">Average Correct</div>
                            <div class="stat-value">""" + f"{avg_correct:.1f}" + """</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">Negative Marking</div>
                            <div class="stat-value">""" + f"{negative_marking}" + """</div>
                        </div>
                    </div>
                    <div class="chart-container">
                        <canvas id="performanceChart"></canvas>
                    </div>
                </div>
                
                <div class="card">
                    <h2>Leaderboard</h2>
                    <table class="leaderboard">
                        <tr>
                            <th class="rank">Rank</th>
                            <th>Name</th>
                            <th>Score</th>
                            <th>Correct</th>
                            <th>Wrong</th>
                            <th>Accuracy</th>
                        </tr>
        """
        
        # Add rows for each participant
        for i, player in enumerate(sorted_leaderboard):
            name = player.get("user_name", f"Player {i+1}")
            score = player.get("adjusted_score", 0)
            correct = player.get("correct_answers", 0)
            wrong = player.get("wrong_answers", 0)
            
            # Calculate accuracy
            total_attempts = correct + wrong
            accuracy = (correct / total_attempts) * 100 if total_attempts > 0 else 0
            
            # Set rank styling
            rank_class = ""
            if i == 0:
                rank_class = "gold-rank"
            elif i == 1:
                rank_class = "silver-rank"
            elif i == 2:
                rank_class = "bronze-rank"
            
            # Add the row
            html_content += f"""
                        <tr>
                            <td class="rank {rank_class}">{i+1}</td>
                            <td>{name}</td>
                            <td>{score}</td>
                            <td>{correct}</td>
                            <td>{wrong}</td>
                            <td>{accuracy:.1f}%</td>
                        </tr>
            """
        
        # Add questions section if available
        if sanitized_questions:
            html_content += """
                </table>
            </div>
            
            <div class="card">
                <h2>Questions</h2>
            """
            
            for i, question in enumerate(sanitized_questions):
                q_text = question.get("question", "")
                options = question.get("options", [])
                answer_idx = question.get("answer", 0)
                
                # Determine difficulty based on success rate
                # This is a placeholder - you could calculate actual difficulty from response data
                difficulty = "medium-badge"
                difficulty_text = "Medium"
                
                html_content += f"""
                <div class="question">
                    <div class="question-text">
                        Q{i+1}: {q_text}
                        <span class="badge {difficulty}">{difficulty_text}</span>
                    </div>
                    <div class="options-grid">
                """
                
                # Add options
                for j, option in enumerate(options):
                    option_class = "correct-option" if j == answer_idx else ""
                    marker_class = "correct-marker" if j == answer_idx else ""
                    option_letter = chr(65 + j)  # A, B, C, D...
                    
                    html_content += f"""
                        <div class="option {option_class}">
                            <div class="option-marker {marker_class}">{option_letter}</div>
                            {option}
                        </div>
                    """
                
                html_content += """
                    </div>
                </div>
                """
        
        # Add charts and close HTML
        html_content += """
            </div>
            
            <script>
                // Top Performers Chart
                const topPerformersCtx = document.getElementById('topPerformersChart').getContext('2d');
                const topPerformersChart = new Chart(topPerformersCtx, {
                    type: 'bar',
                    data: {
                        labels: """ + json.dumps(chart_names) + """,
                        datasets: [{
                            label: 'Score',
                            data: """ + json.dumps(chart_scores) + """,
                            backgroundColor: [
                                'rgba(255, 215, 0, 0.6)',
                                'rgba(192, 192, 192, 0.6)',
                                'rgba(205, 127, 50, 0.6)',
                                'rgba(67, 97, 238, 0.6)',
                                'rgba(67, 97, 238, 0.6)',
                                'rgba(67, 97, 238, 0.6)',
                                'rgba(67, 97, 238, 0.6)',
                                'rgba(67, 97, 238, 0.6)',
                                'rgba(67, 97, 238, 0.6)',
                                'rgba(67, 97, 238, 0.6)'
                            ],
                            borderColor: [
                                'rgba(255, 215, 0, 1)',
                                'rgba(192, 192, 192, 1)',
                                'rgba(205, 127, 50, 1)',
                                'rgba(67, 97, 238, 1)',
                                'rgba(67, 97, 238, 1)',
                                'rgba(67, 97, 238, 1)',
                                'rgba(67, 97, 238, 1)',
                                'rgba(67, 97, 238, 1)',
                                'rgba(67, 97, 238, 1)',
                                'rgba(67, 97, 238, 1)'
                            ],
                            borderWidth: 1
                        }]
                    },
                    options: {
                        plugins: {
                            title: {
                                display: true,
                                text: 'Top Performers by Score',
                                font: {
                                    size: 16
                                }
                            },
                            legend: {
                                display: false
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: 'Score'
                                }
                            }
                        },
                        responsive: true,
                        maintainAspectRatio: false
                    }
                });

                // Performance Chart
                const performanceCtx = document.getElementById('performanceChart').getContext('2d');
                const performanceChart = new Chart(performanceCtx, {
                    type: 'bar',
                    data: {
                        labels: """ + json.dumps(chart_names) + """,
                        datasets: [
                            {
                                label: 'Correct',
                                data: """ + json.dumps(chart_correct) + """,
                                backgroundColor: 'rgba(40, 167, 69, 0.6)',
                                borderColor: 'rgba(40, 167, 69, 1)',
                                borderWidth: 1
                            },
                            {
                                label: 'Wrong',
                                data: """ + json.dumps(chart_wrong) + """,
                                backgroundColor: 'rgba(220, 53, 69, 0.6)',
                                borderColor: 'rgba(220, 53, 69, 1)',
                                borderWidth: 1
                            }
                        ]
                    },
                    options: {
                        plugins: {
                            title: {
                                display: true,
                                text: 'Correct vs. Wrong Answers',
                                font: {
                                    size: 16
                                }
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: true,
                                stacked: false,
                                title: {
                                    display: true,
                                    text: 'Count'
                                }
                            },
                            x: {
                                stacked: true
                            }
                        },
                        responsive: true,
                        maintainAspectRatio: false
                    }
                });
            </script>
            
            <div style="text-align: center; margin-top: 50px; color: #6c757d;">
                <p>Generated by Telegram Quiz Bot with Advanced Reporting | All Rights Reserved</p>
                <p>Date: """ + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """</p>
            </div>
        </div>
    </body>
    </html>
        """
        
        # Write to file
        with open(html_filepath, "w", encoding="utf-8") as f:
            f.write(html_content)
        
        logger.info(f"Enhanced HTML report generated at: {html_filepath}")
        return html_filepath
        
    except Exception as e:
        logger.error(f"Error generating enhanced HTML report: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None

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
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler, PollAnswerHandler, InlineQueryHandler

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment variable
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7631768276:AAE3FdUFsrk9gRvcHkiCOknZ-YzDY1uHYNU")

# Conversation states
QUESTION, OPTIONS, ANSWER, CATEGORY = range(4)
EDIT_SELECT, EDIT_QUESTION, EDIT_OPTIONS = range(4, 7)
CLONE_URL, CLONE_MANUAL = range(7, 9)
CUSTOM_ID = 9  # This should be a single integer, not a range

# PDF import conversation states (use high numbers to avoid conflicts)
PDF_UPLOAD, PDF_CUSTOM_ID, PDF_PROCESSING = range(100, 103)

# TXT import conversation states (use even higher numbers)
TXT_UPLOAD, TXT_CUSTOM_ID, TXT_PROCESSING = range(200, 203)

# Create conversation states for the quiz creation feature
CREATE_NAME, CREATE_QUESTIONS, CREATE_SECTIONS, CREATE_TIMER, CREATE_NEGATIVE_MARKING, CREATE_TYPE = range(300, 306)

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
    
    # Make sure user_name is a valid string
    safe_user_name = "Unknown"
    if user_name is not None:
        if isinstance(user_name, str):
            safe_user_name = user_name
        else:
            safe_user_name = str(user_name)
    
    # Don't allow "participants" as a user name (this would cause display issues)
    if safe_user_name.lower() == "participants":
        safe_user_name = f"User_{str(user_id)}"
    
    # Make sure first_name is a valid string
    safe_first_name = first_name
    if first_name is None:
        safe_first_name = safe_user_name
    elif not isinstance(first_name, str):
        safe_first_name = str(first_name)
    
    # Don't allow "participants" as a first name
    if safe_first_name.lower() == "participants":
        safe_first_name = f"User_{str(user_id)}"
    
    # Log participant info being saved
    logger.info(f"Saving participant info: ID={user_id}, username={safe_user_name}")
    
    participants[str(user_id)] = {
        "user_name": safe_user_name,
        "first_name": safe_first_name,
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
    
    # Make sure user_name is a valid string
    safe_user_name = "Unknown"
    if user_name is not None:
        if isinstance(user_name, str):
            safe_user_name = user_name
        else:
            safe_user_name = str(user_name)
            
    # Don't allow "participants" as a user name (this would cause display issues)
    if safe_user_name.lower() == "participants":
        safe_user_name = f"User_{str(user_id)}"
    
    # Log the user name being saved
    logger.info(f"Saving quiz result for user: {safe_user_name} (ID: {user_id})")
        
    # Add participant result
    results[str(quiz_id)]["participants"].append({
        "user_id": str(user_id),
        "user_name": safe_user_name,
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
    
    # Create a new list with participants that have ranks assigned
    ranked_participants = []
    for i, participant in enumerate(deduplicated_participants):
        # Create a copy to avoid modifying the original
        # Check if participant is a dictionary before calling copy()
        if isinstance(participant, dict):
            ranked_participant = participant.copy()
            ranked_participant["rank"] = i + 1
        else:
            # Handle case where participant might be a string or other type
            logger.warning(f"Participant is not a dictionary: {type(participant)}")
            # Create a new dictionary with what we know
            ranked_participant = {"rank": i + 1}
            if isinstance(participant, str):
                ranked_participant["user_name"] = participant
            
        ranked_participants.append(ranked_participant)
    
    return ranked_participants

# PDF Generation Class 
class InsaneResultPDF(FPDF):
    """Premium PDF class for stylish and professional quiz results"""
    
    def __init__(self, quiz_id, title=None):
        # Initialize with explicit parameters to avoid potential issues
        super().__init__(orientation='P', unit='mm', format='A4')
        self.quiz_id = quiz_id
        self.title = title or f"Quiz {quiz_id} Results"
        
        # Set professional metadata
        self.set_author("Telegram Quiz Bot")
        self.set_creator("Premium Quiz Results Generator")
        self.set_title(self.title)
        
        # Define brand colors for a cohesive professional look
        self.brand_primary = (25, 52, 152)     # Deep blue
        self.brand_secondary = (242, 100, 25)  # Vibrant orange
        self.brand_accent = (50, 168, 82)      # Green
        self.text_dark = (45, 45, 45)          # Almost black
        self.text_light = (250, 250, 250)      # Almost white
        self.background_light = (245, 245, 245) # Light gray
        
        # Set margins for a modern look
        self.set_left_margin(15)
        self.set_right_margin(15)
        self.set_top_margin(15)
        self.set_auto_page_break(True, margin=20)
        
    def header(self):
        try:
            # Save current state
            current_font = self.font_family
            current_style = self.font_style
            current_size = self.font_size_pt
            current_y = self.get_y()
            
            # Draw header background bar
            self.set_fill_color(*self.brand_primary)
            self.rect(0, 0, 210, 18, style='F')
            
            # Add title on the left
            self.set_xy(15, 5)
            self.set_font('Arial', 'B', 16)
            self.set_text_color(*self.text_light)
            self.cell(130, 10, self.title, 0, 0, 'L')
            
            # Add date in right corner
            self.set_xy(130, 5) 
            self.set_font('Arial', 'I', 8)
            self.set_text_color(*self.text_light)
            self.cell(65, 10, f'Generated: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}', 0, 0, 'R')
            
            # Add decorative accent line
            self.set_y(20)
            self.set_draw_color(*self.brand_secondary)
            self.set_line_width(0.5)
            self.line(15, 20, 195, 20)
            
            # Reset to original position plus offset
            self.set_y(current_y + 25)
            self.set_text_color(*self.text_dark)
            self.set_font(current_font, current_style, current_size)
        except Exception as e:
            logger.error(f"Error in header: {e}")
            # Fallback to simple header
            self.ln(5)
            self.set_font('Arial', 'B', 16)
            self.set_text_color(0, 0, 0)
            self.cell(0, 10, self.title, 0, 1, 'C')
            self.ln(10)
        
    def footer(self):
        try:
            # Draw footer decorative line
            self.set_y(-20)
            self.set_draw_color(*self.brand_primary)
            self.set_line_width(0.5)
            self.line(15, self.get_y(), 195, self.get_y())
            
            # Add professional branding and page numbering
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            self.set_text_color(*self.brand_primary)
            self.cell(100, 10, f'Premium Quiz Bot © {datetime.datetime.now().year}', 0, 0, 'L')
            self.set_text_color(*self.brand_secondary)
            self.cell(90, 10, f'Page {self.page_no()}/{{nb}}', 0, 0, 'R')
        except Exception as e:
            logger.error(f"Error in footer: {e}")
            # Fallback to simple footer
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', 0, 0, 'C')
        
    def add_watermark(self):
        # Save current position
        x, y = self.get_x(), self.get_y()
        
        try:
            # Save current state
            current_font = self.font_family
            current_style = self.font_style
            current_size = self.font_size_pt
            
            # Create premium watermark with transparency effect
            self.set_font('Arial', 'B', 80)
            
            # Set very light version of brand color for watermark
            r, g, b = self.brand_primary
            self.set_text_color(min(r+200, 255), min(g+200, 255), min(b+200, 255))
            
            # Position the watermark diagonally across the page
            self.set_xy(35, 100)
            self.cell(140, 40, "PREMIUM", 0, 0, 'C')
            
            # Reset to original state
            self.set_xy(x, y)
            self.set_text_color(*self.text_dark)
            self.set_font(current_font, current_style, current_size)
        except Exception as e:
            logger.error(f"Error adding watermark: {e}")
            # Continue without watermark
        
    def create_leaderboard_table(self, leaderboard):
        self.add_watermark()
        
        # Table header
        self.set_font('Arial', 'B', 10)
        self.set_fill_color(*self.brand_primary)  # Use brand color
        self.set_text_color(*self.text_light)  # Light text for contrast
        
        # Add table title
        self.ln(5)
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, "LEADERBOARD", 0, 1, 'L')
        self.ln(2)
        
        # Column widths
        col_widths = [15, 60, 20, 20, 20, 20, 25]
        header_texts = ["Rank", "Participant", "Marks", "Right", "Wrong", "Skip", "Penalty"]
        
        # Draw header row with rounded style
        self.set_x(15)
        self.set_font('Arial', 'B', 10)
        self.set_line_width(0.3)
        self.set_draw_color(*self.brand_primary)
        
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
                user_id = entry.get('user_id', '')
                rank = entry.get('rank', '')
                
                # Check for non-Latin characters or emojis that cause PDF problems
                has_non_latin = any(ord(c) > 127 for c in raw_name)
                
                if has_non_latin:
                    # For names with non-Latin characters, use a completely safe fallback
                    # that includes user information but avoids encoding issues
                    display_name = f"User{rank}_{str(user_id)[-4:]}"
                else:
                    # For Latin names, do regular sanitization
                    # Only allow ASCII letters, numbers, spaces, and common punctuation
                    safe_chars = []
                    for c in raw_name:
                        # Allow basic ASCII characters and some safe symbols
                        if (32 <= ord(c) <= 126):
                            safe_chars.append(c)
                        else:
                            # Replace any other character with an underscore
                            safe_chars.append('_')
                    
                    cleaned_name = ''.join(safe_chars)
                    
                    # Further cleanup for HTML-like tags that might appear in some names
                    cleaned_name = cleaned_name.replace('<', '').replace('>', '').replace('/', '')
                    
                    # Default display name to the cleaned version
                    display_name = cleaned_name
                    
                    # If name was heavily modified or empty after cleaning, use fallback
                    if not cleaned_name or cleaned_name.isspace():
                        display_name = f"User{rank}_{str(user_id)[-4:]}"
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
        # Add quiz summary with professional styling
        self.ln(15)
        
        # Section title with branded color and icon
        self.set_font('Arial', 'B', 14)
        self.set_text_color(*self.brand_primary)
        self.cell(0, 10, "QUIZ ANALYTICS", 0, 1, 'L')
        
        # Add decorative line under section title
        self.set_draw_color(*self.brand_secondary)
        self.set_line_width(0.3)
        self.line(15, self.get_y(), 100, self.get_y())
        self.ln(8)
        
        # Calculate statistics with robust error handling
        try:
            total_participants = len(leaderboard)
            avg_score = sum(p.get("adjusted_score", 0) for p in leaderboard) / max(1, total_participants)
            avg_correct = sum(p.get("correct_answers", 0) for p in leaderboard) / max(1, total_participants)
            avg_wrong = sum(p.get("wrong_answers", 0) for p in leaderboard) / max(1, total_participants)
            
            # Advanced statistics
            max_score = max((p.get("adjusted_score", 0) for p in leaderboard), default=0)
            min_score = min((p.get("adjusted_score", 0) for p in leaderboard), default=0) if leaderboard else 0
            
            # Create styled statistics boxes (2x3 grid)
            box_width = 85
            box_height = 25
            margin = 5
            
            # First row of statistics boxes
            self.set_y(self.get_y())
            self.set_x(15)
            
            # Box 1: Total Participants
            self.set_fill_color(*self.brand_primary)
            self.set_text_color(*self.text_light)
            self.rect(self.get_x(), self.get_y(), box_width, box_height, style='F')
            self.set_xy(self.get_x() + 5, self.get_y() + 5)
            self.set_font('Arial', 'B', 10)
            self.cell(box_width - 10, 6, "PARTICIPANTS", 0, 2, 'L')
            self.set_font('Arial', 'B', 14)
            self.cell(box_width - 10, 10, f"{total_participants}", 0, 0, 'L')
            
            # Box 2: Average Score
            self.set_xy(15 + box_width + margin, self.get_y() - 15)
            self.set_fill_color(*self.brand_secondary)
            self.rect(self.get_x(), self.get_y(), box_width, box_height, style='F')
            self.set_xy(self.get_x() + 5, self.get_y() + 5)
            self.set_font('Arial', 'B', 10)
            self.cell(box_width - 10, 6, "AVERAGE SCORE", 0, 2, 'L')
            self.set_font('Arial', 'B', 14)
            self.cell(box_width - 10, 10, f"{avg_score:.2f}", 0, 0, 'L')
            
            # Second row of statistics boxes
            self.set_y(self.get_y() + 10)
            self.set_x(15)
            
            # Box 3: Negative Marking
            self.set_fill_color(*self.brand_accent)
            self.rect(self.get_x(), self.get_y(), box_width, box_height, style='F')
            self.set_xy(self.get_x() + 5, self.get_y() + 5)
            self.set_font('Arial', 'B', 10)
            self.cell(box_width - 10, 6, "NEGATIVE MARKING", 0, 2, 'L')
            self.set_font('Arial', 'B', 14)
            self.cell(box_width - 10, 10, f"{penalty_value:.2f} pts/wrong", 0, 0, 'L')
            
            # Box 4: Average Correct/Wrong
            self.set_xy(15 + box_width + margin, self.get_y() - 15)
            self.set_fill_color(80, 80, 150)  # Purple shade
            self.rect(self.get_x(), self.get_y(), box_width, box_height, style='F')
            self.set_xy(self.get_x() + 5, self.get_y() + 5)
            self.set_font('Arial', 'B', 10)
            self.cell(box_width - 10, 6, "CORRECT vs WRONG", 0, 2, 'L')
            self.set_font('Arial', 'B', 14)
            self.cell(box_width - 10, 10, f"{avg_correct:.1f} / {avg_wrong:.1f}", 0, 0, 'L')
            
            # Reset text color
            self.set_text_color(*self.text_dark)
            self.ln(35)
            
        except Exception as e:
            # Fallback to simple stats if the styled version fails
            logger.error(f"Error in quiz statistics layout: {e}")
            self.set_text_color(0, 0, 0)
            self.set_font('Arial', '', 10)
            
            stats = [
                f"Total Participants: {total_participants}",
                f"Average Score: {avg_score:.2f}",
                f"Average Correct Answers: {avg_correct:.2f}",
                f"Average Wrong Answers: {avg_wrong:.2f}",
                f"Negative Marking: {penalty_value:.2f} points per wrong answer"
            ]
            
            for stat in stats:
                self.cell(0, 7, stat, 0, 1, 'L')
        
        # Date and time with professional style
        self.ln(5)
        self.set_font('Arial', 'I', 9)
        self.set_text_color(120, 120, 120)  # Medium gray
        self.cell(0, 7, f"Report generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 0, 1, 'L')
        
    def add_topper_comparison(self, leaderboard):
        """Add top performers comparison with detailed analytics"""
        if not leaderboard or len(leaderboard) < 1:
            return
            
        try:
            # Add section title with icon and branded styling
            self.ln(15)
            self.set_font('Arial', 'B', 14)
            self.set_text_color(*self.brand_primary)
            self.cell(0, 10, "TOP PERFORMERS ANALYSIS", 0, 1, 'L')
            
            # Add decorative line under section title
            self.set_draw_color(*self.brand_secondary)
            self.set_line_width(0.3)
            self.line(15, self.get_y(), 130, self.get_y())
            self.ln(8)
            
            # Get top 3 performers (or fewer if less than 3 participants)
            top_performers = sorted(
                leaderboard, 
                key=lambda x: x.get("adjusted_score", 0), 
                reverse=True
            )[:min(3, len(leaderboard))]
            
            # Calculate overall quiz stats for comparison
            total_participants = len(leaderboard)
            avg_score = sum(p.get("adjusted_score", 0) for p in leaderboard) / max(1, total_participants)
            avg_correct = sum(p.get("correct_answers", 0) for p in leaderboard) / max(1, total_participants)
            avg_wrong = sum(p.get("wrong_answers", 0) for p in leaderboard) / max(1, total_participants)
            avg_skipped = sum(p.get("skipped", 0) for p in leaderboard) / max(1, total_participants)
            avg_penalty = sum(p.get("penalty", 0) for p in leaderboard) / max(1, total_participants)
            
            # Set up parameters for the comparison chart
            metrics = ['Score', 'Correct', 'Wrong', 'Skipped', 'Penalty']
            metric_colors = [
                self.brand_secondary,  # Score - orange
                self.brand_accent,     # Correct - green
                (200, 50, 50),         # Wrong - red
                (100, 100, 150),       # Skipped - blue-gray
                (150, 80, 0)           # Penalty - brown
            ]
            
            # Create title row with column headers
            self.set_font('Arial', 'B', 10)
            self.set_fill_color(*self.brand_primary)
            self.set_text_color(*self.text_light)
            
            # Draw header row
            col_widths = [45, 25, 25, 25, 25, 25]
            header_texts = ["Performer", "Score", "Correct", "Wrong", "Skipped", "Penalty"]
            
            self.set_x(15)
            for i, text in enumerate(header_texts):
                self.cell(col_widths[i], 10, text, 1, 0, 'C', True)
            self.ln()
            
            # Draw rows for top performers
            for i, performer in enumerate(top_performers):
                # Alternate row colors
                if i % 2 == 0:
                    self.set_fill_color(240, 240, 250)  # Very light blue
                else:
                    self.set_fill_color(245, 245, 245)  # Light gray
                
                # Format the name
                try:
                    raw_name = str(performer.get('user_name', 'Unknown'))
                    # Check for non-Latin characters or emojis
                    has_non_latin = any(ord(c) > 127 for c in raw_name)
                    
                    if has_non_latin:
                        # Use a safe name for PDF
                        user_id = performer.get('user_id', '')
                        rank = performer.get('rank', '')
                        display_name = f"User{rank}_{str(user_id)[-4:]}"
                    else:
                        # Use cleaned version of the name
                        display_name = ''.join(c for c in raw_name if ord(c) < 128)[:25]
                    
                    # Add medal designation
                    if i == 0:
                        display_name = "GOLD: " + display_name
                    elif i == 1:
                        display_name = "SILVER: " + display_name
                    elif i == 2:
                        display_name = "BRONZE: " + display_name
                except:
                    display_name = f"User {i+1}"
                
                # Print row
                self.set_x(15)
                self.set_text_color(*self.text_dark)
                self.cell(col_widths[0], 10, display_name, 1, 0, 'L', True)
                
                # Add metrics with color-coded text
                metrics_data = [
                    performer.get("adjusted_score", 0),
                    performer.get("correct_answers", 0),
                    performer.get("wrong_answers", 0),
                    performer.get("skipped", 0),
                    performer.get("penalty", 0)
                ]
                
                for j, value in enumerate(metrics_data):
                    # Use color coding for the metrics
                    self.set_text_color(*metric_colors[j])
                    self.cell(col_widths[j+1], 10, str(value), 1, 0, 'C', True)
                
                self.ln()
            
            # Add average row as comparison benchmark
            self.set_fill_color(230, 230, 230)  # Light gray
            self.set_x(15)
            self.set_text_color(*self.brand_primary)
            self.set_font('Arial', 'BI', 10)
            self.cell(col_widths[0], 10, "AVERAGE (All Participants)", 1, 0, 'L', True)
            
            # Add average metrics
            avg_metrics = [
                round(avg_score, 1),
                round(avg_correct, 1),
                round(avg_wrong, 1),
                round(avg_skipped, 1),
                round(avg_penalty, 1)
            ]
            
            for j, value in enumerate(avg_metrics):
                self.set_text_color(*metric_colors[j])
                self.cell(col_widths[j+1], 10, str(value), 1, 0, 'C', True)
            
            self.ln(15)
            
            # Add detailed performance insights
            self.set_font('Arial', 'B', 12)
            self.set_text_color(*self.brand_primary)
            self.cell(0, 10, "Detailed Performance Insights:", 0, 1, 'L')
            
            self.set_font('Arial', '', 10)
            self.set_text_color(*self.text_dark)
            
            # Calculate and add insights
            insights = []
            
            # Insight 1: Topper's score vs average
            if top_performers:
                topper_score = top_performers[0].get("adjusted_score", 0)
                score_diff_pct = ((topper_score - avg_score) / max(1, avg_score)) * 100
                insights.append(f"- Top performer scored {round(score_diff_pct)}% higher than the quiz average")
            
            # Insight 2: Correct answer patterns
            if top_performers:
                top_correct = top_performers[0].get("correct_answers", 0)
                correct_diff = top_correct - avg_correct
                insights.append(f"- Top performers averaged {round(correct_diff, 1)} more correct answers than others")
            
            # Insight 3: Wrong answer patterns
            wrong_counts = [p.get("wrong_answers", 0) for p in leaderboard]
            if wrong_counts:
                max_wrong = max(wrong_counts)
                min_wrong = min(wrong_counts)
                insights.append(f"- Wrong answers ranged from {min_wrong} to {max_wrong} across all participants")
            
            # Insight 4: Skip patterns
            if top_performers:
                top_skipped = sum(p.get("skipped", 0) for p in top_performers) / len(top_performers)
                insights.append(f"- Top performers skipped an average of {round(top_skipped, 1)} questions")
            
            # Insight 5: Penalty impact
            if top_performers:
                top_penalty = sum(p.get("penalty", 0) for p in top_performers) / len(top_performers)
                insights.append(f"- Negative marking impact on top performers: {round(top_penalty, 1)} points")
            
            # Print the insights
            for insight in insights:
                self.multi_cell(0, 7, insight, 0, 'L')
            
            self.ln(5)
            
        except Exception as e:
            logger.error(f"Error in topper comparison: {e}")
            # If the fancy version fails, create a simple version
            self.ln(10)
            self.set_font('Arial', 'B', 12)
            self.set_text_color(0, 0, 0)
            self.cell(0, 10, "Top Performers", 0, 1, 'L')
            
            if leaderboard:
                top_performers = sorted(
                    leaderboard, 
                    key=lambda x: x.get("adjusted_score", 0), 
                    reverse=True
                )[:min(3, len(leaderboard))]
                
                for i, performer in enumerate(top_performers):
                    raw_name = str(performer.get('user_name', 'Unknown'))
                    # Check for non-Latin characters that would cause PDF problems
                    has_non_latin = any(ord(c) > 127 for c in raw_name)
                    
                    if has_non_latin:
                        # Use a safe name for PDF
                        user_id = performer.get('user_id', '')
                        rank = performer.get('rank', '')
                        name = f"User{rank}_{str(user_id)[-4:]}"
                    else:
                        # Use cleaned version of the name
                        name = ''.join(c for c in raw_name if ord(c) < 128)[:25]
                        
                    score = performer.get("adjusted_score", 0)
                    self.set_font('Arial', '', 10)
                    self.cell(0, 7, f"{i+1}. {name}: {score} points", 0, 1, 'L')
    
    def add_detailed_analytics(self, leaderboard):
        """Add detailed quiz performance analytics"""
        if not leaderboard:
            return
            
        try:
            # Add section title with icon and branded styling
            self.ln(15)
            self.set_font('Arial', 'B', 14)
            self.set_text_color(*self.brand_primary)
            self.cell(0, 10, "DETAILED QUIZ ANALYTICS", 0, 1, 'L')
            
            # Add decorative line under section title
            self.set_draw_color(*self.brand_secondary)
            self.set_line_width(0.3)
            self.line(15, self.get_y(), 130, self.get_y())
            self.ln(10)
            
            # Calculate performance metrics
            total_participants = len(leaderboard)
            
            # Score metrics
            scores = [p.get("adjusted_score", 0) for p in leaderboard]
            if scores:
                max_score = max(scores)
                min_score = min(scores)
                avg_score = sum(scores) / len(scores)
                median_score = sorted(scores)[len(scores)//2] if scores else 0
                
                # Participation metrics
                correct_answers = [p.get("correct_answers", 0) for p in leaderboard]
                wrong_answers = [p.get("wrong_answers", 0) for p in leaderboard]
                skipped = [p.get("skipped", 0) for p in leaderboard]
                
                # Calculate average metrics
                avg_correct = sum(correct_answers) / max(1, len(correct_answers))
                avg_wrong = sum(wrong_answers) / max(1, len(wrong_answers))
                avg_skipped = sum(skipped) / max(1, len(skipped))
                
                # Calculate performance distributions
                correct_percentage = avg_correct / (avg_correct + avg_wrong + avg_skipped) * 100 if (avg_correct + avg_wrong + avg_skipped) > 0 else 0
                wrong_percentage = avg_wrong / (avg_correct + avg_wrong + avg_skipped) * 100 if (avg_correct + avg_wrong + avg_skipped) > 0 else 0
                skipped_percentage = avg_skipped / (avg_correct + avg_wrong + avg_skipped) * 100 if (avg_correct + avg_wrong + avg_skipped) > 0 else 0
                
                # Create a visual analytics grid with KPIs
                # First row - Score Analytics
                self.set_font('Arial', 'B', 12)
                self.set_text_color(*self.brand_primary)
                self.cell(0, 10, "Score Analytics", 0, 1, 'L')
                
                # Create a row of KPI boxes
                box_width = 42
                box_height = 25
                margin = 4
                
                # Score Analytics row
                metrics = [
                    {"label": "HIGHEST SCORE", "value": f"{max_score}", "color": self.brand_accent},
                    {"label": "AVERAGE SCORE", "value": f"{avg_score:.1f}", "color": self.brand_secondary},
                    {"label": "MEDIAN SCORE", "value": f"{median_score}", "color": (100, 100, 150)},
                    {"label": "LOWEST SCORE", "value": f"{min_score}", "color": (200, 50, 50)}
                ]
                
                # Draw the first row of metrics
                self.set_y(self.get_y() + 5)
                start_x = 15
                
                for i, metric in enumerate(metrics):
                    x = start_x + (i * (box_width + margin))
                    self.set_xy(x, self.get_y())
                    
                    # Draw box with metric color
                    self.set_fill_color(*metric["color"])
                    self.rect(x, self.get_y(), box_width, box_height, style='F')
                    
                    # Add label
                    self.set_xy(x + 2, self.get_y() + 3)
                    self.set_font('Arial', 'B', 8)
                    self.set_text_color(*self.text_light)
                    self.cell(box_width - 4, 6, metric["label"], 0, 2, 'L')
                    
                    # Add value
                    self.set_xy(x + 2, self.get_y() + 2)
                    self.set_font('Arial', 'B', 14)
                    self.cell(box_width - 4, 8, metric["value"], 0, 0, 'L')
                
                # Move to next row
                self.ln(box_height + 15)
                
                # Performance Distribution row
                self.set_font('Arial', 'B', 12)
                self.set_text_color(*self.brand_primary)
                self.cell(0, 10, "Performance Distribution", 0, 1, 'L')
                
                # Draw performance distribution as a horizontal stacked bar
                bar_width = 170
                bar_height = 20
                self.set_y(self.get_y() + 5)
                
                # Calculate segment widths
                correct_width = (correct_percentage / 100) * bar_width
                wrong_width = (wrong_percentage / 100) * bar_width
                skipped_width = (skipped_percentage / 100) * bar_width
                
                # Draw the segments of the stacked bar
                start_x = 15
                
                # Correct answers segment (green)
                self.set_fill_color(*self.brand_accent)
                self.rect(start_x, self.get_y(), correct_width, bar_height, style='F')
                
                # Wrong answers segment (red)
                self.set_fill_color(200, 50, 50)
                self.rect(start_x + correct_width, self.get_y(), wrong_width, bar_height, style='F')
                
                # Skipped answers segment (gray)
                self.set_fill_color(150, 150, 150)
                self.rect(start_x + correct_width + wrong_width, self.get_y(), skipped_width, bar_height, style='F')
                
                # Add percentage labels to segments
                # Correct
                self.set_xy(start_x + (correct_width / 2) - 10, self.get_y() + 6)
                self.set_font('Arial', 'B', 9)
                self.set_text_color(*self.text_light)
                self.cell(20, 8, f"{correct_percentage:.1f}%", 0, 0, 'C')
                
                # Wrong
                if wrong_width > 15:  # Only add label if segment is wide enough
                    self.set_xy(start_x + correct_width + (wrong_width / 2) - 10, self.get_y())
                    self.cell(20, 8, f"{wrong_percentage:.1f}%", 0, 0, 'C')
                
                # Skipped
                if skipped_width > 15:  # Only add label if segment is wide enough
                    self.set_xy(start_x + correct_width + wrong_width + (skipped_width / 2) - 10, self.get_y())
                    self.cell(20, 8, f"{skipped_percentage:.1f}%", 0, 0, 'C')
                
                # Add legend below the bar
                self.ln(bar_height + 5)
                legend_y = self.get_y()
                legend_items = [
                    {"label": "Correct Answers", "color": self.brand_accent},
                    {"label": "Wrong Answers", "color": (200, 50, 50)},
                    {"label": "Skipped Questions", "color": (150, 150, 150)}
                ]
                
                # Draw legend items
                legend_width = 15
                legend_height = 5
                legend_spacing = 60
                
                for i, item in enumerate(legend_items):
                    x = start_x + (i * legend_spacing)
                    self.set_xy(x, legend_y)
                    
                    # Draw color box
                    self.set_fill_color(*item["color"])
                    self.rect(x, legend_y, legend_width, legend_height, style='F')
                    
                    # Add label
                    self.set_xy(x + legend_width + 2, legend_y)
                    self.set_font('Arial', '', 8)
                    self.set_text_color(*self.text_dark)
                    self.cell(40, 5, item["label"], 0, 0, 'L')
                
                self.ln(15)
                
                # Additional Quiz Insights
                self.set_font('Arial', 'B', 12)
                self.set_text_color(*self.brand_primary)
                self.cell(0, 10, "Quiz Insights", 0, 1, 'L')
                
                self.set_font('Arial', '', 10)
                self.set_text_color(*self.text_dark)
                
                insights = []
                
                # Insight 1: Participant performance
                if total_participants > 0:
                    above_avg = len([s for s in scores if s > avg_score])
                    above_avg_pct = (above_avg / total_participants) * 100
                    insights.append(f"- {above_avg} participants ({above_avg_pct:.1f}%) scored above average")
                
                # Insight 2: Score spread
                if scores and max_score > min_score:
                    score_spread = max_score - min_score
                    insights.append(f"- Score spread of {score_spread} points between highest and lowest")
                
                # Insight 3: Correct vs wrong ratio
                if avg_wrong > 0:
                    correct_wrong_ratio = avg_correct / max(1, avg_wrong)
                    insights.append(f"- Average correct to wrong answer ratio: {correct_wrong_ratio:.1f}")
                
                # Insight 4: Skipping behavior
                max_skipped = max(skipped) if skipped else 0
                insights.append(f"- Maximum questions skipped by a participant: {max_skipped}")
                
                # Print the insights
                for insight in insights:
                    self.multi_cell(0, 7, insight, 0, 'L')
                
            self.ln(5)
                
        except Exception as e:
            logger.error(f"Error in detailed analytics: {e}")
            # Fallback to simple analytics
            self.ln(10)
            self.set_font('Arial', 'B', 12)
            self.set_text_color(0, 0, 0)
            self.cell(0, 10, "Quiz Performance Analytics", 0, 1, 'L')
            
            self.set_font('Arial', '', 10)
            if leaderboard:
                scores = [p.get("adjusted_score", 0) for p in leaderboard]
                if scores:
                    self.cell(0, 7, f"Highest Score: {max(scores)}", 0, 1, 'L')
                    self.cell(0, 7, f"Average Score: {sum(scores)/len(scores):.1f}", 0, 1, 'L')
                    self.cell(0, 7, f"Lowest Score: {min(scores)}", 0, 1, 'L')
    
    def add_score_distribution(self, leaderboard):
        """Add score distribution graph with visual bar chart"""
        if not leaderboard:
            return
        
        try:
            # Add section title with icon and branded styling
            self.ln(15)
            self.set_font('Arial', 'B', 14)
            self.set_text_color(*self.brand_primary)
            self.cell(0, 10, "SCORE DISTRIBUTION", 0, 1, 'L')
            
            # Add decorative line under section title
            self.set_draw_color(*self.brand_secondary)
            self.set_line_width(0.3)
            self.line(15, self.get_y(), 100, self.get_y())
            self.ln(10)
            
            # Define score ranges with more intuitive labels
            score_ranges = {
                "Below 20": 0,
                "21-40": 0,
                "41-60": 0,
                "61-80": 0,
                "81-100": 0,
                "Above 100": 0
            }
            
            # Count participants in each score range
            max_count = 1  # Initialize to 1 to avoid division by zero
            for entry in leaderboard:
                score = entry.get("adjusted_score", 0)
                if score <= 20:
                    score_ranges["Below 20"] += 1
                elif score <= 40:
                    score_ranges["21-40"] += 1
                elif score <= 60:
                    score_ranges["41-60"] += 1
                elif score <= 80:
                    score_ranges["61-80"] += 1
                elif score <= 100:
                    score_ranges["81-100"] += 1
                else:
                    score_ranges["Above 100"] += 1
                    
                # Track maximum count for scaling
                max_count = max(max_count, max(score_ranges.values()))
            
            # Set up visual bar chart parameters
            chart_width = 140
            bar_height = 12
            max_bar_width = chart_width
            
            # Set initial position
            start_x = 30
            start_y = self.get_y()
            
            # Create color gradients for bars based on score range
            bar_colors = [
                (200, 50, 50),    # Red for lowest scores
                (220, 120, 50),   # Orange
                (230, 180, 50),   # Yellow
                (180, 200, 50),   # Light green
                (100, 180, 50),   # Green
                (50, 150, 180)    # Blue for highest scores
            ]
            
            # Draw reference grid lines (light gray)
            self.set_draw_color(200, 200, 200)  # Light gray
            self.set_line_width(0.1)
            
            # Vertical grid lines
            for i in range(1, 6):
                x = start_x + (i * max_bar_width / 5)
                self.line(x, start_y - 5, x, start_y + (len(score_ranges) * (bar_height + 5)) + 5)
            
            # Draw labels for grid lines (percentage)
            self.set_font('Arial', '', 7)
            self.set_text_color(150, 150, 150)
            for i in range(0, 6):
                x = start_x + (i * max_bar_width / 5)
                percentage = i * 20
                self.set_xy(x - 5, start_y - 10)
                self.cell(10, 5, f"{percentage}%", 0, 0, 'C')
            
            # Now draw the chart bars
            self.ln(5)
            
            # Set font for labels
            self.set_font('Arial', 'B', 9)
            self.set_text_color(*self.text_dark)
            
            # Draw each bar with its label
            for i, (range_name, count) in enumerate(score_ranges.items()):
                # Scale bar width based on max count
                scaled_width = (count / max_count) * max_bar_width
                
                # Draw range label
                y_pos = start_y + (i * (bar_height + 5))
                self.set_xy(15, y_pos + 2)
                self.cell(15, bar_height, range_name, 0, 0, 'L')
                
                # Draw bar with gradient fill
                if count > 0:  # Only draw if there are participants in this range
                    self.set_fill_color(*bar_colors[i])
                    self.set_draw_color(*self.brand_primary)
                    self.set_line_width(0.3)
                    self.rect(start_x, y_pos, scaled_width, bar_height, style='FD')
                    
                    # Add count label inside/beside the bar
                    label_x = min(start_x + scaled_width + 2, start_x + max_bar_width - 15)
                    self.set_xy(label_x, y_pos + 2)
                    self.set_text_color(80, 80, 80)
                    self.cell(15, bar_height, str(count), 0, 0, 'L')
            
            # Reset position and styling
            self.ln(bar_height * len(score_ranges) + 15)
            self.set_text_color(*self.text_dark)
            self.set_line_width(0.3)
            
            # Add explanatory note
            self.set_font('Arial', 'I', 8)
            self.set_text_color(100, 100, 100)
            self.cell(0, 5, "Note: Distribution shows number of participants in each score range", 0, 1, 'L')
            
        except Exception as e:
            # Fallback to simple text distribution if visual chart fails
            logger.error(f"Error creating score distribution chart: {e}")
            
            self.ln(10)
            self.set_font('Arial', 'B', 12)
            self.set_text_color(0, 51, 102)
            self.cell(0, 10, "Score Distribution (Simple View)", 0, 1, 'L')
            
            # Reset simple score ranges
            score_ranges = {
                "0-20": 0,
                "21-40": 0,
                "41-60": 0,
                "61-80": 0,
                "81-100": 0,
                "101+": 0
            }
            
            # Recount participants
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
            
            # Display simple text distribution
            self.set_font('Arial', '', 10)
            self.set_text_color(0, 0, 0)  # Black
            
            for range_name, count in score_ranges.items():
                # Use ASCII for compatibility
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
            logger.info("Adding topper comparison...")
            pdf.add_topper_comparison(leaderboard)
        except Exception as e:
            logger.error(f"Error adding topper comparison: {e}")
            # Continue anyway
            
        try:
            logger.info("Adding detailed analytics...")
            pdf.add_detailed_analytics(leaderboard)
        except Exception as e:
            logger.error(f"Error adding detailed analytics: {e}")
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
        
        # Pre-process leaderboard data to handle encoding issues
        try:
            logger.info("Pre-processing leaderboard data for encoding compatibility...")
            if leaderboard and isinstance(leaderboard, list):
                processed_leaderboard = []
                
                for entry in leaderboard:
                    # Check if entry is a dictionary before trying to copy
                    if isinstance(entry, dict):
                        clean_entry = entry.copy()
                    else:
                        # Handle non-dictionary entries
                        logger.warning(f"Leaderboard entry is not a dictionary: {type(entry)}")
                        clean_entry = {"user_name": str(entry)}
                    
                    # Handle username encoding issues
                    if 'user_name' in clean_entry:
                        raw_name = str(clean_entry.get('user_name', 'Unknown'))
                        
                        # Sanitize the name to ensure PDF compatibility
                        # Replace any problematic character using list comprehension
                        # This avoids modifying strings directly which can cause errors
                        safe_chars = []
                        for c in raw_name:
                            if ord(c) < 128:  # ASCII range
                                safe_chars.append(c)
                            else:
                                # Use appropriate replacements for some common characters
                                # or default to underscore
                                safe_chars.append('_')
                        
                        # Create a new string from the character list
                        safe_name = ''.join(safe_chars)
                        
                        # If name is empty after cleaning, use a fallback
                        if not safe_name or safe_name.isspace():
                            uid = str(clean_entry.get('user_id', ''))[-4:] if 'user_id' in clean_entry else ''
                            rank = clean_entry.get('rank', '')
                            safe_name = f"User_{rank}_{uid}"
                            
                        clean_entry['user_name'] = safe_name
                    
                    processed_leaderboard.append(clean_entry)
                
                # Use the processed data instead of original
                leaderboard = processed_leaderboard
                logger.info(f"Successfully pre-processed {len(leaderboard)} user names")
        except Exception as e:
            logger.error(f"Error pre-processing leaderboard: {e}")
            # Continue with original data
        
        # Try multiple output strategies to ensure the PDF works
        try:
            # Strategy 1: Standard output
            logger.info("Attempting PDF output with standard method...")
            pdf.output(filename, 'F')
            logger.info("PDF output completed successfully with standard method")
        except Exception as e:
            logger.error(f"Error in standard PDF output: {e}")
            
            # Strategy 2: Try binary mode
            try:
                logger.info("Trying binary output method...")
                # This sometimes helps with encoding issues
                pdf_content = pdf.output(dest='S').encode('latin-1')
                with open(filename, 'wb') as f:
                    f.write(pdf_content)
                logger.info("PDF output completed successfully with binary method")
            except Exception as e2:
                logger.error(f"Error in binary PDF output: {e2}")
                
                # Final fallback - create a simplified PDF without the problem
                logger.info("Creating simplified PDF as fallback...")
                
                # Use a clean, simple PDF with proper content
                simple_pdf = FPDF()
                simple_pdf.add_page()
                
                # Add title
                simple_pdf.set_font('Arial', 'B', 16)
                simple_pdf.cell(0, 10, f'Quiz {quiz_id} Results', 0, 1, 'C')
                simple_pdf.ln(5)
                
                # Add subtitle with title if available
                if title:
                    simple_pdf.set_font('Arial', 'I', 12)
                    simple_pdf.cell(0, 10, title, 0, 1, 'C')
                
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
                
                # Add a footer note with branding
                simple_pdf.ln(15)
                simple_pdf.set_font('Arial', 'B', 10)
                simple_pdf.set_text_color(60, 60, 150)  # Blue text
                simple_pdf.cell(0, 10, "PREMIUM QUIZ BOT RESULTS", 0, 1, 'C')
                
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
    
    # Import needed modules here to make sure they're available 
    import os
    
    # Make sure PDF directory exists
    try:
        os.makedirs(PDF_RESULTS_DIR, exist_ok=True)
    except Exception as e:
        logger.error(f"Error creating PDF directory: {e}")
    
    # Generate PDF results with error reporting
    try:
        pdf_file = generate_pdf_results(quiz_id)
        
        # Verify file exists and has content
        if pdf_file and os.path.exists(pdf_file) and os.path.getsize(pdf_file) > 0:
            logger.info(f"PDF generated successfully: {pdf_file}")
            return pdf_file
        else:
            logger.error(f"PDF generation failed or returned invalid file")
            return None
    except Exception as e:
        logger.error(f"Error in PDF generation: {e}")
        return None

async def handle_quiz_end_with_pdf(update, context, quiz_id, user_id, user_name, 
                                  total_questions, correct_answers, wrong_answers, 
                                  skipped, penalty, score, adjusted_score):
    """Handle quiz end with PDF generation and HTML interactive report"""
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
                # Import os module directly here to ensure it's available in this scope
                import os
                
                # Verify the file exists and has minimum size
                if os.path.exists(pdf_file):
                    file_size = os.path.getsize(pdf_file)
                    logger.info(f"Found PDF file: {pdf_file} with size {file_size} bytes")
                    
                    if file_size > 50:  # Lower threshold to 50 bytes to be less strict
                        # Try to verify PDF header but don't fail if it's not perfect
                        try:
                            with open(pdf_file, 'rb') as f:
                                file_header = f.read(5)
                                if file_header == b'%PDF-':
                                    logger.info(f"PDF header verified successfully")
                                else:
                                    logger.warning(f"PDF header not standard but will try to use anyway: {file_header}")
                            
                            # Consider valid if it exists and has reasonable size
                            file_valid = True
                            logger.info(f"PDF file considered valid based on size and existence")
                        except Exception as header_error:
                            logger.warning(f"Could not verify PDF header but will continue: {header_error}")
                            # Consider valid anyway if the file exists and has size
                            file_valid = True
                    else:
                        logger.error(f"PDF file too small (size: {file_size}): {pdf_file}")
                else:
                    logger.error(f"PDF file does not exist: {pdf_file}")
            except Exception as e:
                logger.error(f"Error verifying PDF file: {e}")
                # FAILSAFE: If there was an error in verification but the file may exist
                try:
                    import os
                    if pdf_file and os.path.exists(pdf_file) and os.path.getsize(pdf_file) > 0:
                        file_valid = True
                        logger.warning(f"Using PDF despite verification error: {pdf_file}")
                except Exception:
                    pass  # Don't add more errors if this failsafe also fails
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
                    
                # PDF results have been generated successfully
                # Send the PDF only, no success message
                
                                # HTML reports have been disabled in automatic mode
                # Users can generate HTML reports manually using the /htmlreport command
                # Example: /htmlreport [quiz_id]
                
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
    welcome_text = (
        "👋 Welcome to Negative Marking Quiz Bot!\n\n"
        "Create quizzes with advanced negative marking, import questions from multiple platforms "
        "(PDF, Text, TestBook), and share with customizable scoring systems. "
        "Share in groups and track detailed performance with PDF results, interactive HTML reports, and comprehensive statistics.\n\n"
        
        "Main commands:\n"
        "- /quiz - Start a quiz\n"
        "- /htmlreport QUIZ_ID - Generate interactive HTML report\n"
        "- /htmlinfo - Learn about HTML reports\n"
        "- /pdfinfo - Learn about PDF import\n"
        "- /features - See all features\n"
        "- /stats - View your performance stats"
    )
    
    # Create the "Join Our Channel" button with the URL
    keyboard = [
        [InlineKeyboardButton("🔔 Join Our Channel", url="https://t.me/NegativeMarkingTestbot")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_html(welcome_text, reply_markup=reply_markup)
    
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help message."""
    await start(update, context)

async def features_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show features message."""
    # Create a stylish formatted showcase matching the screenshot exactly
    features_text = ""
    
    # Main title - using the quote style from screenshot
    features_text += "| 📘 Features Showcase of Negative Marking Quiz Bot! 🚀 |\n\n"
    
    # Main features - using the blue diamond bullets from screenshot
    features_text += "🔹 Create questions from text just by providing a ✓ mark to the right options.\n"
    features_text += "🔹 Marathon Quiz Mode: Create unlimited questions for a never-ending challenge.\n"
    features_text += "🔹 Convert Polls to Quizzes: Simply forward polls (e.g., from @quizbot), and unnecessary elements like [1/100] will be auto-removed!\n"
    features_text += "🔹 Smart Filtering: Remove unwanted words (e.g., usernames, links) from forwarded polls.\n"
    features_text += "🔹 Skip, Pause & Resume ongoing quizzes anytime.\n"
    features_text += "🔹 Bulk Question Support via ChatGPT output.\n"
    features_text += "🔹 Negative Marking for accurate scoring.\n"
    features_text += "🔹 Edit Existing Quizzes with ease like shuffle title editing timer adding removing questions and many more.\n"
    features_text += "🔹 Quiz Analytics: View engagement, tracking how many users completed the quiz.\n"
    features_text += "🔹 Inline Query Support: Share quizzes directly in any chat, with percentile and percentage.\n"
    features_text += "🔹 Create Questions from TXT.\n"
    features_text += "🔹 Advance Mechanism with 99.99% uptime.\n"
    features_text += "🔹 Automated link and username removal from Poll's description and questions.\n"
    features_text += "🔹 Auto txt quiz creation from Wikipedia Britannica bbc news and 20+ articles sites.\n"
    
    # Latest updates section with styled header
    features_text += "\n| 🆕 Latest update new |\n\n"
    
    features_text += "🔹 Create Questions from Testbook App by test link.\n"
    features_text += "🔹 Auto clone from official quizbot.\n"
    features_text += "🔹 Create from polls/already finishrd quizzes in channels and all.\n"
    
    # Upcoming features section with rocket
    features_text += "\n| 🚀 Upcoming Features: |\n\n"
    
    features_text += "🔸 Advance Engagement saving + later on perspective.\n"
    features_text += "🔸 More optimizations for a smoother experience.\n"
    features_text += "🔸 Suprising Updates...\n"
    
    # Analytics section with chart icon
    features_text += "\n| 📊 Live Tracker & Analysis: |\n\n"
    
    features_text += "✅ Topper Comparisons\n"
    features_text += "✅ Detailed Quiz Performance Analytics\n"
    features_text += "✅ Interactive HTML Reports with Charts\n"
    features_text += "✅ Professional PDF Results\n"
    
    # Send the formatted message
    await update.message.reply_text(features_text)

# ---------- NEGATIVE MARKING COMMAND ADDITIONS ----------
async def extended_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display extended user statistics with penalty information."""
    user = update.effective_user
    stats = get_extended_user_stats(user.id)
    
    percentage = (stats["correct_answers"] / stats["total_answers"] * 100) if stats["total_answers"] > 0 else 0
    adjusted_percentage = (stats["adjusted_score"] / stats["total_answers"] * 100) if stats["total_answers"] > 0 else 0
    
    # Create visualization for performance metrics
    correct_bar = "🟢" * stats["correct_answers"] + "⚪" * stats["incorrect_answers"]
    if len(correct_bar) > 10:  # If too many questions, scale it down
        correct_ratio = stats["correct_answers"] / stats["total_answers"] if stats["total_answers"] > 0 else 0
        correct_count = round(correct_ratio * 10)
        incorrect_count = 10 - correct_count
        correct_bar = "🟢" * correct_count + "⚪" * incorrect_count
    
    # Generate score icon based on adjusted percentage
    if adjusted_percentage >= 80:
        score_icon = "🏆"  # Trophy for excellent performance
    elif adjusted_percentage >= 60:
        score_icon = "🌟"  # Star for good performance
    elif adjusted_percentage >= 40:
        score_icon = "🔶"  # Diamond for average performance
    elif adjusted_percentage >= 20:
        score_icon = "🔸"  # Small diamond for below average
    else:
        score_icon = "⚡"  # Lightning for needs improvement
    
    # Create a modern, visually appealing stats display
    stats_text = (
        f"<b>✨ PERFORMANCE ANALYTICS ✨</b>\n"
        f"<i>User: {user.first_name}</i>\n\n"
        
        f"<b>📈 QUIZ ACTIVITY</b>\n"
        f"- Questions Attempted: <b>{stats['total_answers']}</b>\n"
        f"- Performance Chart: {correct_bar}\n\n"
        
        f"<b>🎯 ACCURACY METRICS</b>\n"
        f"- Correct Responses: <b>{stats['correct_answers']}</b>\n"
        f"- Incorrect Responses: <b>{stats['incorrect_answers']}</b>\n"
        f"- Raw Success Rate: <b>{percentage:.1f}%</b>\n\n"
        
        f"<b>⚖️ NEGATIVE MARKING IMPACT</b>\n"
        f"- Penalty Points: <b>{stats['penalty_points']:.2f}</b>\n"
        f"- Raw Score: <b>{stats['raw_score']}</b>\n"
        f"- Adjusted Score: <b>{stats['adjusted_score']:.2f}</b>\n"
        f"- Adjusted Success: <b>{adjusted_percentage:.1f}%</b> {score_icon}\n\n"
    )
    
    # Add information about negative marking status with stylish formatting
    negative_marking_status = "enabled" if NEGATIVE_MARKING_ENABLED else "disabled"
    status_icon = "🟢" if NEGATIVE_MARKING_ENABLED else "🔴"
    stats_text += f"<i>{status_icon} Negative marking is currently {negative_marking_status}</i>"
    
    await update.message.reply_html(stats_text, disable_web_page_preview=True)

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
    # Clear any previous question data and conversation states
    context.user_data.clear()
    
    # Create a new question entry
    context.user_data["new_question"] = {}
    
    # Send welcome message with instructions
    await update.message.reply_html(
        "<b>✨ Create New Question ✨</b>\n\n"
        "First, send me the <b>question text</b>.\n\n"
        "<i>Example: What is the national bird of India?</i>"
    )
    
    logging.info(f"Add question started by user {update.effective_user.id}")
    
    # Move to the QUESTION state
    return QUESTION

async def add_question_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the question text and ask for options with correct answer marked."""
    # Store the question text
    if "new_question" not in context.user_data:
        context.user_data["new_question"] = {}
    
    context.user_data["new_question"]["question"] = update.message.text
    
    # Log the received question
    logging.info(f"User {update.effective_user.id} sent question: {update.message.text}")
    
    # Send a message asking for options with clear instructions
    await update.message.reply_html(
        "<b>📝 Question received!</b>\n\n"
        "Now, send me the <b>options with the correct answer marked with an asterisk (*)</b>.\n\n"
        "<i>Format each option on a separate line and mark the correct answer with an asterisk (*). Example:</i>\n\n"
        "(A) Peacock *\n"
        "(B) Sparrow\n"
        "(C) Parrot\n"
        "(D) Eagle"
    )
    
    # Return the next state - waiting for options
    return OPTIONS

async def add_question_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Parse options and automatically detect the correct answer with asterisk."""
    try:
        # Validate user_data state
        if "new_question" not in context.user_data:
            # Something went wrong, restart the flow
            await update.message.reply_html(
                "❌ <b>Sorry, there was an issue with your question data.</b>\n\n"
                "Please use /add to start over."
            )
            return ConversationHandler.END
            
        # Get options text and split into lines
        options_text = update.message.text
        options_lines = options_text.split('\n')
        
        # Log received options
        logging.info(f"User {update.effective_user.id} sent options: {options_lines}")
        
        # Initialize variables for parsing
        cleaned_options = []
        correct_answer = None
        
        # Process each option line
        for i, line in enumerate(options_lines):
            # Skip empty lines
            if not line.strip():
                continue
                
            # Look for asterisk marker
            if '*' in line:
                # Remove the asterisk and save the index as correct answer
                cleaned_line = line.replace('*', '').strip()
                correct_answer = i
            else:
                cleaned_line = line.strip()
            
            # Remove option prefix (A), (B), etc. if present
            if cleaned_line and cleaned_line[0] == '(' and ')' in cleaned_line[:4]:
                cleaned_line = cleaned_line[cleaned_line.find(')')+1:].strip()
            
            # Add to cleaned options
            if cleaned_line:
                cleaned_options.append(cleaned_line)
        
        # Check if we have at least 2 options
        if len(cleaned_options) < 2:
            await update.message.reply_html(
                "❌ <b>You need to provide at least 2 options.</b>\n\n"
                "Please send them again, one per line."
            )
            return OPTIONS
        
        # If no correct answer was marked or couldn't be detected
        if correct_answer is None:
            await update.message.reply_html(
                "❌ <b>I couldn't detect which answer is correct.</b>\n\n"
                "Please mark the correct answer with an asterisk (*) and try again.\n"
                "Example: (A) Peacock *"
            )
            return OPTIONS
        
        # Save the cleaned options and correct answer
        context.user_data["new_question"]["options"] = cleaned_options
        context.user_data["new_question"]["answer"] = correct_answer
        
        # Create a formatted display of the options with the correct one highlighted
        option_labels = ["A", "B", "C", "D", "E", "F"]
        options_preview = []
        
        for i, opt in enumerate(cleaned_options):
            if i == correct_answer:
                options_preview.append(f"({option_labels[i]}) <b>{opt}</b> ✓")
            else:
                options_preview.append(f"({option_labels[i]}) {opt}")
        
        options_display = "\n".join(options_preview)
        
        # Show categories for selection
        categories = [
            "General Knowledge", "Science", "History", "Geography", 
            "Entertainment", "Sports", "Other"
        ]
        
        # Create keyboard for category selection
        keyboard = []
        for category in categories:
            keyboard.append([InlineKeyboardButton(category, callback_data=f"category_{category}")])
        
        # Show the question summary and ask for category
        await update.message.reply_html(
            f"<b>✅ Options saved! Correct answer detected:</b>\n\n"
            f"<b>Question:</b> {context.user_data['new_question']['question']}\n\n"
            f"<b>Options:</b>\n{options_display}\n\n"
            f"Finally, select a <b>category</b> for this question:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Go to category selection state
        return CATEGORY
    except Exception as e:
        # Handle any unexpected errors
        logging.error(f"Error in add_question_options: {str(e)}")
        await update.message.reply_html(
            "❌ <b>Sorry, something went wrong while processing your options.</b>\n\n"
            "Please try again with /add command."
        )
        return ConversationHandler.END

async def add_question_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """This function is no longer needed but kept for compatibility."""
    # This step is now skipped since we detect the correct answer from the options input
    # Just in case this function gets called, forward to custom ID step
    keyboard = [
        [InlineKeyboardButton("Auto-generate ID", callback_data="auto_id")],
        [InlineKeyboardButton("Specify custom ID", callback_data="custom_id")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_html(
        "<b>Choose ID method:</b> How would you like to assign an ID to this question?",
        reply_markup=reply_markup
    )
    return CUSTOM_ID

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
    # Check if we're awaiting a custom ID from this user
    if not context.user_data.get("awaiting_custom_id", False):
        return CUSTOM_ID
        
    try:
        custom_id = int(update.message.text)
        context.user_data["custom_id"] = custom_id
        # Remove the awaiting flag
        context.user_data["awaiting_custom_id"] = False
        
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
    """Handle category selection and save the question."""
    try:
        # Get the callback query
        query = update.callback_query
        await query.answer()
        
        # Extract category from callback data
        category = query.data.replace("category_", "")
        
        # Log the selected category
        logging.info(f"User {query.from_user.id} selected category: {category}")
        
        # Validate that we have question data
        if "new_question" not in context.user_data:
            await query.edit_message_text(
                "❌ <b>Error: Question data not found. Please try again with /add</b>",
                parse_mode="HTML"
            )
            return ConversationHandler.END
        
        # Get the question data from user_data
        new_question = context.user_data["new_question"]
        new_question["category"] = category
        
        # Determine the question ID
        if context.user_data.get("custom_id"):
            question_id = context.user_data["custom_id"]
        else:
            question_id = get_next_question_id()
        
        # Add the question with the generated ID
        add_question_with_id(question_id, new_question)
        
        # Format the options for display
        options_formatted = "\n".join([f"({i+1}) {opt}" for i, opt in enumerate(new_question['options'])])
        
        # Create success message with all question details
        await query.edit_message_text(
            f"✅ <b>Question added successfully with ID: {question_id}</b>\n\n"
            f"<b>Question:</b> {new_question['question']}\n\n"
            f"<b>Options:</b>\n{options_formatted}\n\n"
            f"<b>Correct Answer:</b> {new_question['options'][new_question['answer']]}\n\n"
            f"<b>Category:</b> {category}",
            parse_mode="HTML"
        )
        
        # Clean up user data
        context.user_data.clear()  # Full cleanup
        
        # End the conversation
        return ConversationHandler.END
    except Exception as e:
        # Handle any unexpected errors
        logging.error(f"Error in category_callback: {str(e)}")
        try:
            await query.edit_message_text(
                "❌ <b>Sorry, something went wrong while saving your question.</b>\n\n"
                "Please try again with /add command.",
                parse_mode="HTML"
            )
        except:
            # In case we can't edit the original message
            await query.message.reply_html(
                "❌ <b>Sorry, something went wrong while saving your question.</b>\n\n"
                "Please try again with /add command."
            )
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current operation."""
    # Send a friendly cancellation message
    await update.message.reply_html(
        "<b>✅ Operation cancelled.</b>\n\n"
        "You can start over with /add or use other commands whenever you're ready."
    )
    
    # Clean up all user data
    context.user_data.clear()
    
    # End the conversation
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
    
    # Store penalties before resetting so we can use them for displaying scores
    user_penalties = {}
    
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
    
    # Get quiz ID from context if available
    quiz_id = quiz.get("quiz_id", "")
    # Get the quiz title (default if not specified)
    quiz_title = quiz.get("title", "Quiz")
    
    # Create results message using Telegram-style formatting like in the screenshot
    results_message = f"🏆 Quiz '{quiz_title}' has ended !\n\n"
    
    # Format results
    if final_scores:
        # Add the "Top Performers" header styled like in the screenshot
        results_message += "🎯 Top Performers: 💬\n\n"
        
        # Show top participants with the new format
        for i, data in enumerate(final_scores[:3]):  # Limit to top 3
            # Get user data
            name = data.get("name", f"Player {i+1}")
            correct = data.get("correct", 0)
            wrong = data.get("participation", 0) - data.get("correct", 0)  # Calculate wrong answers
            penalty = data.get("penalty", 0)
            adjusted = data.get("adjusted_score", correct)
            
            # Calculate percentages for display
            percentage = (correct / questions_count * 100) if questions_count > 0 else 0
            accuracy_percentage = (correct / data.get("participation", 1) * 100) if data.get("participation", 0) > 0 else 0
            
            # Personalized medal emoji for rank
            medal_emoji = ["🥇", "⏱️", "🏅"][i] if i < 3 else f"{i+1}."
            
            # Format the line with correct/wrong icons like in the screenshot
            results_message += (
                f"{medal_emoji} {name} | ✅ {correct} | ❌ {wrong} | 🎯 {adjusted:.2f} |\n"
                f"⏱️ {data.get('participation', 0)}s | 📊 {percentage:.2f}% | 🚀 {accuracy_percentage:.2f}%\n"
            )
            
            # Add separator line if not the last entry
            if i < min(2, len(final_scores) - 1):
                results_message += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    else:
        results_message += "No participants found for this quiz."
    
    # Send results
    await context.bot.send_message(
        chat_id=chat_id,
        text=results_message
    )
    
    # ENHANCED AUTO-RESET: Reset negative penalties after calculating and displaying results
    if NEGATIVE_MARKING_ENABLED:
        # Reset penalties for all participants after displaying results
        for user_data in final_scores:
            user_id = user_data.get("user_id")
            penalty = user_data.get("penalty", 0)
            if penalty > 0 and user_id:
                # Store the penalty value for reference before resetting
                logger.info(f"Auto-resetting negative penalties for user {user_id} after quiz completion. Previous penalty: {penalty:.2f}")
                reset_user_penalties(user_id)
    
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
    
    # Debug log message properties
    logger.info(f"Received forwarded message with attributes: {dir(message)}")
    
    # Check for poll in message
    # In Telegram API, polls can be in different message types
    has_poll = False
    poll = None
    
    # Check different ways a poll might be present in a message
    if hasattr(message, 'poll') and message.poll is not None:
        has_poll = True
        poll = message.poll
    elif hasattr(message, 'effective_attachment') and message.effective_attachment is not None:
        # Sometimes polls are in effective_attachment
        attachment = message.effective_attachment
        if hasattr(attachment, 'poll') and attachment.poll is not None:
            has_poll = True
            poll = attachment.poll
    
    if has_poll and poll is not None:
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

async def html_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show information about HTML report feature."""
    info_text = (
        "📊 <b>Interactive HTML Quiz Reports</b>\n\n"
        "The bot can generate interactive HTML reports for your quizzes with detailed analytics and charts.\n\n"
        "<b>Features:</b>\n"
        "✓ Interactive charts and graphs\n"
        "✓ Question-by-question analysis\n"
        "✓ Participant performance metrics\n"
        "✓ Complete leaderboard\n"
        "✓ Visual score distribution\n\n"
        "<b>How to use:</b>\n"
        "1. After a quiz completes, the bot automatically generates both PDF and HTML reports\n"
        "2. You can manually generate an HTML report for any quiz using:\n"
        "   <code>/htmlreport QUIZ_ID</code> (e.g., <code>/htmlreport 123</code>)\n"
        "3. Download the HTML file sent by the bot\n"
        "4. Open the file in any web browser to view the interactive dashboard\n\n"
        "<b>Note:</b> HTML reports provide an interactive experience compared to static PDF reports. They include clickable elements and dynamic charts for better analysis."
    )
    await update.message.reply_html(info_text, disable_web_page_preview=True)
    
async def inline_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help for inline features and how to troubleshoot inline issues."""
    # Get available quizzes
    all_questions = load_questions()
    quiz_ids = list(all_questions.keys())
    quiz_count = len(quiz_ids)
    example_id = quiz_ids[0] if quiz_count > 0 else "example_id"
    
    # Detailed help text with actual data
    help_text = (
        "🔍 <b>Inline Query Troubleshooting Guide</b>\n\n"
        f"<b>Available Quizzes:</b> {quiz_count}\n"
        f"<b>Quiz IDs:</b> {', '.join(quiz_ids[:5]) if quiz_count > 0 else 'None'}\n\n"
        "<b>How Inline Mode Works:</b>\n"
        "1. Type @your_bot_username in any chat\n"
        "2. Wait for quiz options to appear\n"
        "3. Select a quiz to share\n\n"
        "<b>Troubleshooting Tips:</b>\n"
        "• Make sure inline mode is enabled for your bot via @BotFather\n"
        "• Try sharing with empty query first (@your_bot_username + space)\n"
        "• Use the 'Share Quiz' button from quiz creation\n"
        f"• Try a specific quiz ID: @your_bot_username quiz_{example_id}\n\n"
        "<b>Test Commands:</b>\n"
        "• /quizid - shows all available quiz IDs\n"
        "• /stats - shows your active quizzes\n"
        f"• Test inline directly: @{context.bot.username}\n\n"
        "<b>If Still Not Working:</b>\n"
        "• Clear Telegram cache (Settings > Data and Storage > Storage Usage > Clear Cache)\n"
        "• Restart Telegram app\n"
        "• Make sure your bot is not in privacy mode (set via @BotFather)"
    )
    
    # Create custom keyboard with buttons to test inline
    keyboard = [
        [InlineKeyboardButton("🔍 Test Inline Mode", switch_inline_query="")],
        [InlineKeyboardButton(f"🔍 Test with Example ID", switch_inline_query=f"quiz_{example_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send the help text with buttons
    await update.message.reply_html(help_text, reply_markup=reply_markup)

async def html_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate an HTML report for a specific quiz ID"""
    try:
        # Check if the user provided a quiz ID
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "❌ Please provide a quiz ID. For example: /htmlreport 123"
            )
            return
        
        # Get the quiz ID from the args
        quiz_id = context.args[0]
        
        # Send a message to indicate we're working on it
        await update.message.reply_text(
            f"📊 *Generating HTML Report for Quiz {quiz_id}...*\n\n"
            f"This may take a moment depending on the size of the quiz data.",
            parse_mode="MARKDOWN"
        )
        
        # Make sure we have the quiz results
        quiz_results = get_quiz_results(quiz_id)
        if not quiz_results:
            await update.message.reply_text(
                f"❌ No results found for Quiz ID: {quiz_id}. Please check the ID and try again."
            )
            return
            
        # Log the quiz results for debugging
        logger.info(f"Found {len(quiz_results)} results for quiz ID {quiz_id}")
        
        # Define a direct HTML generator function instead of trying to import
        def generate_html_report_direct(quiz_id, title=None, questions_data=None, leaderboard=None, quiz_metadata=None):
            """
            Generate an HTML quiz results report directly
            
            Args:
                quiz_id: The ID of the quiz
                title: Optional title for the quiz
                questions_data: List of question objects
                leaderboard: List of participant results
                quiz_metadata: Additional quiz metadata
                
            Returns:
                str: Path to the generated HTML file
            """
            logger.info("Starting direct HTML generation...")
            try:
                # Make sure the HTML directory exists
                html_dir = "html_results"
                if not os.path.exists(html_dir):
                    os.makedirs(html_dir)
                    logger.info(f"Created HTML results directory: {html_dir}")
                
                # Generate timestamp for the filename
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                
                # Create the filename
                html_filename = f"quiz_{quiz_id}_results_{timestamp}.html"
                html_filepath = os.path.join(html_dir, html_filename)
                
                # Get quiz title
                if not title:
                    title = f"Quiz {quiz_id} Results"
                
                # Default quiz metadata if not provided
                if not quiz_metadata:
                    quiz_metadata = {
                        "total_questions": len(questions_data) if questions_data else 0,
                        "negative_marking": get_quiz_penalty(quiz_id),
                        "quiz_date": datetime.datetime.now().strftime("%Y-%m-%d"),
                        "description": f"Results for Quiz ID: {quiz_id}"
                    }
                
                # Default leaderboard if not provided
                if not leaderboard:
                    leaderboard = []
                    
                # Ensure all inputs are valid
                if not isinstance(leaderboard, list):
                    logger.error(f"Leaderboard is not a list: {type(leaderboard)}")
                    leaderboard = []
                    
                if not isinstance(questions_data, list):
                    logger.error(f"Questions data is not a list: {type(questions_data)}")
                    questions_data = []
                    
                # Filter out any non-dictionary entries and add debug logging
                sanitized_leaderboard = []
                
                # Add diagnostic logging for leaderboard data
                logger.info(f"Leaderboard data before sanitization: {leaderboard}")
                if len(leaderboard) > 0:
                    sample = leaderboard[0]
                    logger.info(f"Sample leaderboard entry type: {type(sample)}")
                    if isinstance(sample, dict):
                        logger.info(f"Sample leaderboard entry keys: {sample.keys()}")
                
                for p in leaderboard:
                    if isinstance(p, dict):
                        # Log user info for debugging
                        user_name = p.get("user_name", "N/A")
                        user_id = p.get("user_id", "N/A")
                        logger.info(f"Processing participant: {user_name} (ID: {user_id})")
                        sanitized_leaderboard.append(p)
                    else:
                        logger.warning(f"Skipping non-dictionary participant: {type(p)}")
                
                sanitized_questions = []
                for q in questions_data:
                    if isinstance(q, dict):
                        sanitized_questions.append(q.copy())  # Create a copy to avoid modifying original
                    else:
                        logger.warning(f"Skipping non-dictionary question: {type(q)}")
                
                logger.info(f"Generating HTML report with {len(sanitized_leaderboard)} participants and {len(sanitized_questions)} questions")
                
                # Create a basic HTML template with responsive design
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>{title}</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; line-height: 1.6; padding: 20px; max-width: 1200px; margin: 0 auto; }}
                        h1 {{ color: #4361ee; text-align: center; margin-bottom: 20px; }}
                        h2 {{ color: #3a0ca3; margin-top: 30px; border-bottom: 2px solid #f72585; padding-bottom: 10px; }}
                        .card {{ background: #fff; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); margin: 20px 0; padding: 20px; }}
                        .stats {{ display: flex; flex-wrap: wrap; gap: 15px; justify-content: space-between; }}
                        .stat-box {{ flex: 1; min-width: 150px; background: #f8f9fa; padding: 15px; border-radius: 6px; text-align: center; }}
                        .stat-value {{ font-size: 24px; font-weight: bold; color: #4361ee; margin: 10px 0; }}
                        .stat-label {{ font-size: 14px; color: #6c757d; }}
                        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                        th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #ddd; }}
                        th {{ background-color: #f2f2f2; }}
                        tr:hover {{ background-color: #f5f5f5; }}
                        .rank-1 {{ background-color: #ffd700; }}
                        .rank-2 {{ background-color: #c0c0c0; }}
                        .rank-3 {{ background-color: #cd7f32; }}
                        .question {{ margin-bottom: 20px; padding: 15px; background: #f8f9fa; border-radius: 6px; }}
                        .question-text {{ font-weight: bold; }}
                        .options {{ margin-left: 20px; }}
                        .correct {{ color: #198754; font-weight: bold; }}
                        .header {{ text-align: center; margin-bottom: 30px; }}
                        .footer {{ text-align: center; margin-top: 50px; padding: 20px; color: #6c757d; font-size: 14px; }}
                    </style>
                </head>
                <body>
                    <div class="header">
                        <h1>{title}</h1>
                        <p>Generated on {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
                    </div>
                    
                    <div class="card">
                        <h2>Quiz Overview</h2>
                """
                
                # Sort leaderboard by score
                sorted_participants = sorted(
                    sanitized_leaderboard, 
                    key=lambda x: x.get("adjusted_score", 0) if isinstance(x, dict) else 0, 
                    reverse=True
                )
                
                # Remove duplicate users based on user_id
                # This fixes the issue of the same user appearing multiple times in the leaderboard
                deduplicated_participants = []
                processed_users = set()  # Track processed users by ID
                
                for participant in sorted_participants:
                    user_id = participant.get("user_id", "")
                    
                    # Only add each user once based on user_id
                    if user_id and user_id not in processed_users:
                        processed_users.add(user_id)
                        deduplicated_participants.append(participant)
                
                # Use the deduplicated list for display
                sorted_leaderboard = deduplicated_participants
                
                # Now that we have deduplicated_participants, we can complete the HTML
                html_content += f"""
                        <div class="stats">
                            <div class="stat-box">
                                <div class="stat-label">Total Questions</div>
                                <div class="stat-value">{quiz_metadata.get("total_questions", 0)}</div>
                            </div>
                            <div class="stat-box">
                                <div class="stat-label">Total Participants</div>
                                <div class="stat-value">{len(deduplicated_participants)}</div>
                            </div>
                            <div class="stat-box">
                                <div class="stat-label">Negative Marking</div>
                                <div class="stat-value">{quiz_metadata.get("negative_marking", 0)}</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h2>Leaderboard</h2>
                        <table>
                            <tr>
                                <th>Rank</th>
                                <th>Name</th>
                                <th>Score</th>
                                <th>Correct</th>
                                <th>Wrong</th>
                            </tr>
                """
                
                # Add leaderboard rows
                for i, player in enumerate(sorted_leaderboard):
                    if not isinstance(player, dict):
                        continue
                    
                    rank_class = ""
                    if i == 0:
                        rank_class = "rank-1"
                    elif i == 1:
                        rank_class = "rank-2"
                    elif i == 2:
                        rank_class = "rank-3"
                    
                    name = player.get("user_name", f"Player {i+1}")
                    score = player.get("adjusted_score", 0)
                    correct = player.get("correct_answers", 0)
                    wrong = player.get("wrong_answers", 0)
                    
                    html_content += f"""
                            <tr class="{rank_class}">
                                <td>{i+1}</td>
                                <td>{name}</td>
                                <td>{score}</td>
                                <td>{correct}</td>
                                <td>{wrong}</td>
                            </tr>
                    """
                
                # Close leaderboard table
                html_content += """
                        </table>
                    </div>
                """
                
                # Add questions section if available
                if sanitized_questions and len(sanitized_questions) > 0:
                    html_content += """
                    <div class="card">
                        <h2>Questions</h2>
                    """
                    
                    for i, question in enumerate(sanitized_questions):
                        if not isinstance(question, dict):
                            continue
                        
                        q_text = question.get("question", "")
                        options = question.get("options", [])
                        answer_idx = question.get("answer", 0)
                        
                        html_content += f"""
                        <div class="question">
                            <div class="question-text">Q{i+1}. {q_text}</div>
                            <div class="options">
                                <ol type="A">
                        """
                        
                        # Add options
                        for j, option in enumerate(options):
                            is_correct = j == answer_idx
                            class_name = "correct" if is_correct else ""
                            correct_mark = "✓ " if is_correct else ""
                            
                            html_content += f"""
                                    <li class="{class_name}">{correct_mark}{option}</li>
                            """
                        
                        html_content += """
                                </ol>
                            </div>
                        </div>
                        """
                    
                    # Close questions section
                    html_content += """
                    </div>
                    """
                
                # Footer with branding
                html_content += """
                    <div class="footer">
                        <p>Generated by Telegram Quiz Bot with Negative Marking</p>
                        <p>Interactive HTML Report | All Rights Reserved</p>
                    </div>
                </body>
                </html>
                """
                
                # Write to file
                with open(html_filepath, "w", encoding="utf-8") as f:
                    f.write(html_content)
                
                logger.info(f"HTML report generated at: {html_filepath}")
                return html_filepath
                
            except Exception as e:
                logger.error(f"Error generating direct HTML report: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                return None
        
        # Create an HTML generator object with our direct function
        class HtmlGenerator:
            def generate_html_report(self, quiz_id, title=None, questions_data=None, leaderboard=None, quiz_metadata=None):
                return generate_enhanced_html_report(quiz_id, title, questions_data, leaderboard, quiz_metadata)
        
        # Use the direct generator
        html_generator = HtmlGenerator()
        logger.info("Using direct HTML generation function")
        
        # Get quiz questions - with safety measures
        try:
            questions_data = load_questions()
        except Exception as e:
            logger.error(f"Error loading questions: {e}")
            questions_data = {}
            
        # Handle both dictionary and list formats for questions
        quiz_questions = []
        try:
            # Make sure questions_data is a dictionary
            if isinstance(questions_data, dict):
                # Find questions that match the quiz ID
                for qid, q_data in questions_data.items():
                    if str(qid).startswith(str(quiz_id)):
                        # Create a completely new question object rather than modifying the original
                        if isinstance(q_data, dict):
                            # Each question becomes a new simple dict with only essential fields
                            quiz_questions.append({
                                "id": str(qid),
                                "question": q_data.get("question", ""),
                                "options": q_data.get("options", []),
                                "answer": q_data.get("answer", 0)
                            })
                        elif isinstance(q_data, list):
                            # Handle list of questions
                            for q in q_data:
                                if isinstance(q, dict):
                                    quiz_questions.append({
                                        "id": str(qid),
                                        "question": q.get("question", ""),
                                        "options": q.get("options", []),
                                        "answer": q.get("answer", 0)
                                    })
            else:
                logger.error(f"Questions data is not a dictionary: {type(questions_data)}")
        except Exception as e:
            logger.error(f"Error processing questions: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
        
        logger.info(f"Found {len(quiz_questions)} questions for quiz {quiz_id}")
        
        # Get quiz results
        quiz_results_data = get_quiz_results(quiz_id)
        
        # Extract participants from the quiz_results structure
        if isinstance(quiz_results_data, dict) and "participants" in quiz_results_data:
            # Get the participants list
            participants_list = quiz_results_data["participants"]
            
            # Make sure it's a list
            if isinstance(participants_list, list):
                # Process each participant to ensure data validity
                quiz_results = []
                for participant in participants_list:
                    if isinstance(participant, dict):
                        # Create a copy to avoid modifying the original
                        p_copy = participant.copy()
                        
                        # Ensure user_name is valid
                        if "user_name" in p_copy:
                            user_name = p_copy["user_name"]
                            if not isinstance(user_name, str):
                                p_copy["user_name"] = str(user_name)
                            
                            # Check for problematic username
                            if p_copy["user_name"].lower() == "participants":
                                user_id = p_copy.get("user_id", "unknown")
                                p_copy["user_name"] = f"User_{user_id}"
                                
                        quiz_results.append(p_copy)
                    elif participant is not None:
                        # Log but don't add non-dict participants
                        logger.warning(f"Skipping non-dictionary participant: {type(participant)}")
                        
                logger.info(f"Extracted and sanitized {len(quiz_results)} participants from quiz results")
            else:
                quiz_results = []
                logger.warning(f"Participants is not a list: {type(participants_list)}")
        else:
            quiz_results = []
            logger.warning(f"No participants found in quiz results or unexpected format: {type(quiz_results_data)}")
        
        # Print some diagnostics
        logger.info(f"Found {len(quiz_results)} participant results for quiz {quiz_id}")
        
        # Check if we have any data to generate a report
        if not quiz_questions and not quiz_results:
            await update.message.reply_text(
                f"❌ No data found for Quiz ID {quiz_id}. Please check the ID and try again."
            )
            return
        
        # Get total questions count
        total_questions = len(quiz_questions)
        if total_questions == 0 and quiz_results:
            # Try to get total questions from results if available
            for result in quiz_results:
                if "total_questions" in result:
                    total_questions = result["total_questions"]
                    break
        
        # Prepare quiz metadata
        quiz_metadata = {
            "total_questions": total_questions,
            "negative_marking": get_quiz_penalty(quiz_id) or 0,
            "quiz_date": datetime.datetime.now().strftime("%Y-%m-%d"),
            "description": f"Results for Quiz ID: {quiz_id} - Negative Marking: {get_quiz_penalty(quiz_id)} points per wrong answer"
        }
        
        # Process participant data for time displays and ensure required fields
        # Process participant data and ensure required fields
        processed_results = []
        for participant in quiz_results:
            # Create a copy of the participant dictionary to avoid modifying the original
            # Check that participant is a dictionary before copying
            if isinstance(participant, dict):
                participant_copy = participant.copy()
            else:
                # Handle non-dictionary participants
                logger.warning(f"Participant is not a dictionary: {type(participant)}")
                participant_copy = {
                    "user_id": "unknown",
                    "user_name": str(participant) if participant is not None else "Unknown"
                }
            
            # Ensure essential fields for HTML report
            if "time_taken" not in participant_copy:
                participant_copy["time_taken"] = 0  # Default
            if "user_name" not in participant_copy:
                participant_copy["user_name"] = f"User_{participant_copy.get('user_id', 'unknown')}"
            if "answers" not in participant_copy:
                participant_copy["answers"] = {}
                
            processed_results.append(participant_copy)
        
        # Use the processed results for further sanitization
        quiz_results = processed_results
        
        # Process data for HTML generation
        sanitized_results = []
        logger.info(f"Pre-cleaning quiz results, count: {len(quiz_results)}")
        for participant in quiz_results:
            if isinstance(participant, dict):
                # Clean up each participant record
                cleaned_participant = {
                    "user_id": participant.get("user_id", "unknown"),
                    "user_name": participant.get("user_name", "Anonymous"),
                    "correct_answers": participant.get("correct_answers", 0),
                    "wrong_answers": participant.get("wrong_answers", 0),
                    "time_taken": participant.get("time_taken", 0),
                    "adjusted_score": participant.get("adjusted_score", 0),
                    "raw_score": participant.get("correct_answers", 0)
                }
                sanitized_results.append(cleaned_participant)
            else:
                logger.warning(f"Skipping non-dictionary participant: {type(participant)}")
        logger.info(f"Post-cleaning quiz results, count: {len(sanitized_results)}")

        # Fix any potential string entries in questions
        sanitized_questions = []
        logger.info(f"Pre-cleaning questions, count: {len(quiz_questions)}")
        for question in quiz_questions:
            if isinstance(question, dict):
                # Clean up each question
                cleaned_question = {
                    "id": question.get("id", "unknown"),
                    "question": question.get("question", ""),
                    "options": question.get("options", []),
                    "answer": question.get("answer", 0)
                }
                sanitized_questions.append(cleaned_question)
            else:
                logger.warning(f"Skipping non-dictionary question: {type(question)}")
        logger.info(f"Post-cleaning questions, count: {len(sanitized_questions)}")
        
        # Generate HTML report with validated data
        try:
            html_file = html_generator.generate_html_report(
                quiz_id=quiz_id,
                title=f"Quiz {quiz_id} Interactive Results Analysis",
                questions_data=sanitized_questions,
                leaderboard=sanitized_results,
                quiz_metadata=quiz_metadata
            )
            
            logger.info(f"HTML report generated: {html_file}")
            
            # Check if the file was actually created
            if html_file and os.path.exists(html_file):
                # Get file size for verification
                file_size = os.path.getsize(html_file)
                logger.info(f"HTML file size: {file_size} bytes")
                
                if file_size > 100:  # Basic validation
                    # Send the HTML file
                    with open(html_file, 'rb') as file:
                        await context.bot.send_document(
                            chat_id=update.effective_chat.id,
                            document=file,
                            filename=f"Quiz_{quiz_id}_Interactive_Results.html",
                            caption=f"📈 *Interactive Quiz {quiz_id} Analysis*\n\nOpen this HTML file in any web browser for a detailed interactive dashboard with charts and statistics.\n\nTotal Participants: {len(quiz_results)}\nNegative Marking: {get_quiz_penalty(quiz_id)} points/wrong",
                            parse_mode="MARKDOWN"
                        )
                    
                    # Send success message
                    success_message = (
                        f"✅ Interactive HTML Results generated successfully!\n\n"
                        f"Open the HTML file in any web browser to view:\n"
                        f"- Interactive charts and graphs\n"
                        f"- Question-by-question analysis\n"
                        f"- Complete leaderboard\n"
                        f"- Performance metrics"
                    )
                    await update.message.reply_text(success_message)
                    return
                else:
                    logger.error(f"HTML file too small: {file_size} bytes")
                    await update.message.reply_text(
                        f"❌ HTML report seems invalid (file too small)."
                    )
                    return
            else:
                logger.error(f"HTML file not found or empty: {html_file}")
                await update.message.reply_text(
                    f"❌ HTML report generation failed: File not created."
                )
                return
                
        except Exception as e:
            logger.error(f"Error generating HTML report: {e}")
            import traceback
            logger.error(f"HTML error traceback: {traceback.format_exc()}")
            await update.message.reply_text(
                f"❌ Error generating HTML report: {str(e)[:100]}..."
            )
            return
            
    except Exception as e:
        logger.error(f"Error in HTML report command: {e}")
        await update.message.reply_text(
            f"❌ An error occurred: {str(e)}"
        )

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

# ====== /create command for quiz creation ======
async def create_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the process of creating a new quiz."""
    await update.message.reply_text("✅ Send the quiz name first.")
    return CREATE_NAME

async def create_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the quiz name input and ask for questions."""
    quiz_name = update.message.text
    # Store the quiz name in context
    context.user_data["create_quiz"] = {
        "name": quiz_name,
        "questions": [],
        "sections": False,
        "timer": 10,
        "negative_marking": 0,
        "type": "free",
        "creator": update.effective_user.username or f"user_{update.effective_user.id}"
    }
    
    await update.message.reply_text(
        f"✅ Quiz name set to: {quiz_name}\n\n"
        "Now send questions in the stated format, "
        "or try to send a quiz poll, pdf file or .txt file, send /cancel to stop "
        "creating quiz."
    )
    return CREATE_QUESTIONS

async def create_questions_file_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle file upload during quiz creation."""
    message = update.message
    quiz_data = context.user_data.get("create_quiz", {})
    
    # Handle .txt file upload
    if message.document and message.document.file_name.endswith('.txt'):
        # Ensure downloads directory exists
        ensure_directory("downloads")
        
        file_id = message.document.file_id
        file = await context.bot.get_file(file_id)
        file_path = f"downloads/{file_id}.txt"
        await file.download_to_drive(file_path)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Split into lines
            lines = content.strip().split('\n')
            
            # Extract questions using existing function
            questions = extract_questions_from_txt(lines)
            
            if questions:
                # Add quiz name to each question for better organization
                quiz_name = quiz_data.get("name", "Custom Quiz")
                for q in questions:
                    q["quiz_name"] = quiz_name
                
                # Add questions to the quiz
                current_questions = quiz_data.get("questions", [])
                current_questions.extend(questions)
                quiz_data["questions"] = current_questions
                context.user_data["create_quiz"] = quiz_data
                
                await update.message.reply_text(
                    f"✅ {len(questions)} questions processed from file! "
                    f"Total questions: {len(current_questions)}\n\n"
                    "Send the next question set or poll or type /done when finished or /cancel to cancel."
                )
                
                # Automatically ask for /done confirmation if this is the first file
                if len(current_questions) == len(questions):
                    await update.message.reply_text(
                        "Would you like to proceed with these questions? Type /done to continue to the next step."
                    )
                    
                return CREATE_QUESTIONS
            else:
                await update.message.reply_text(
                    "❌ No questions could be extracted from the file. Please check the format and try again."
                )
                return CREATE_QUESTIONS
                
        except Exception as e:
            logger.error(f"Error processing txt file: {e}")
            await update.message.reply_text(
                f"❌ Error processing file: {str(e)}"
            )
            return CREATE_QUESTIONS
    
    # Handle PDF file upload
    elif message.document and message.document.file_name.endswith('.pdf'):
        # Ensure downloads directory exists
        ensure_directory("downloads")
        
        file_id = message.document.file_id
        file = await context.bot.get_file(file_id)
        file_path = f"downloads/{file_id}.pdf"
        await file.download_to_drive(file_path)
        
        try:
            # Extract text from PDF
            text_list = extract_text_from_pdf(file_path)
            if not text_list:
                await update.message.reply_text("❌ Could not extract text from PDF file.")
                return CREATE_QUESTIONS
                
            # Parse questions
            questions = parse_questions_from_text(text_list)
            
            if questions:
                # Add quiz name to each question for better organization
                quiz_name = quiz_data.get("name", "Custom Quiz")
                for q in questions:
                    q["quiz_name"] = quiz_name
                
                # Add questions to the quiz
                current_questions = quiz_data.get("questions", [])
                current_questions.extend(questions)
                quiz_data["questions"] = current_questions
                context.user_data["create_quiz"] = quiz_data
                
                await update.message.reply_text(
                    f"✅ {len(questions)} questions processed from PDF! "
                    f"Total questions: {len(current_questions)}\n\n"
                    "Send the next question set or poll or type /done when finished or /cancel to cancel."
                )
                
                # Automatically ask for /done confirmation if this is the first file
                if len(current_questions) == len(questions):
                    await update.message.reply_text(
                        "Would you like to proceed with these questions? Type /done to continue to the next step."
                    )
                    
                return CREATE_QUESTIONS
            else:
                await update.message.reply_text(
                    "❌ No questions could be extracted from the PDF. Please check the format and try again."
                )
                return CREATE_QUESTIONS
                
        except Exception as e:
            logger.error(f"Error processing PDF file: {e}")
            await update.message.reply_text(
                f"❌ Error processing PDF file: {str(e)}"
            )
            return CREATE_QUESTIONS
    
    # Handle regular text input (could be a question or command)
    elif message.text:
        # Use a case-insensitive check for commands at the beginning of the message
        clean_text = message.text.strip().lower()
        
        # Debug logging for commands to trace issues
        if clean_text.startswith('/'):
            logger.info(f"Command detected in create_questions_file_received: {clean_text}")
            
        if clean_text.startswith('/done'):
            # Proceed to ask about sections
            if len(quiz_data.get("questions", [])) > 0:
                # Add logging
                logger.info(f"Moving to CREATE_SECTIONS state with {len(quiz_data.get('questions', []))} questions")
                
                await update.message.reply_text(
                    "Do you want section in your quiz? send yes/no"
                )
                return CREATE_SECTIONS
            else:
                await update.message.reply_text(
                    "❌ You need to add at least one question to create a quiz."
                )
                return CREATE_QUESTIONS
                
        elif clean_text.startswith('/cancel'):
            context.user_data.pop("create_quiz", None)
            await update.message.reply_text("❌ Quiz creation cancelled.")
            return ConversationHandler.END
    
    # For unrecognized input
    await update.message.reply_text(
        "Please send questions via text file, PDF, or type /done when finished or /cancel to cancel."
    )
    return CREATE_QUESTIONS

async def create_sections_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the sections selection (yes/no)."""
    response = update.message.text.lower()
    quiz_data = context.user_data.get("create_quiz", {})
    
    if response in ["yes", "y"]:
        quiz_data["sections"] = True
    else:
        quiz_data["sections"] = False
    
    context.user_data["create_quiz"] = quiz_data
    
    # Ask for timer
    await update.message.reply_text(
        "⏳ Enter the quiz timer in seconds (greater than 10 sec)."
    )
    return CREATE_TIMER

async def create_timer_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the timer input."""
    try:
        timer = int(update.message.text)
        if timer < 10:
            await update.message.reply_text(
                "❌ Timer must be at least 10 seconds. Please enter a value greater than 10."
            )
            return CREATE_TIMER
            
        quiz_data = context.user_data.get("create_quiz", {})
        quiz_data["timer"] = timer
        context.user_data["create_quiz"] = quiz_data
        
        # Ask for negative marking
        await update.message.reply_text(
            "📝 Please send the negative marking if you want to add else send 0.\n\n"
            "eg. Enter an integer, fraction (e.g., 1/3), or decimal (e.g., 0.25)."
        )
        return CREATE_NEGATIVE_MARKING
        
    except ValueError:
        await update.message.reply_text(
            "❌ Please enter a valid number for the timer."
        )
        return CREATE_TIMER

async def create_negative_marking_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the negative marking input."""
    value_str = update.message.text.strip()
    quiz_data = context.user_data.get("create_quiz", {})
    
    # Handle different formats of input
    try:
        if "/" in value_str:
            # Handle fraction format
            num, denom = value_str.split("/")
            value = float(num) / float(denom)
        elif value_str == "0" or value_str == "0.":
            value = 0.0
        else:
            value = float(value_str)
            
        quiz_data["negative_marking"] = value
        context.user_data["create_quiz"] = quiz_data
        
        # Ask for quiz type
        await update.message.reply_text(
            "📝 Please specify the quiz type (free or paid)."
        )
        return CREATE_TYPE
        
    except (ValueError, ZeroDivisionError):
        await update.message.reply_text(
            "❌ Please enter a valid value for negative marking (e.g., 0, 0.5, 1/2)."
        )
        return CREATE_NEGATIVE_MARKING

async def create_type_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the quiz type input and finalize quiz creation."""
    quiz_type = update.message.text.lower().strip()
    quiz_data = context.user_data.get("create_quiz", {})
    
    if quiz_type in ["free", "paid"]:
        quiz_data["type"] = quiz_type
    else:
        # Default to free if input is invalid
        quiz_data["type"] = "free"
    
    # Generate a unique quiz ID (5-character alphanumeric)
    import random
    import string
    quiz_id = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
    quiz_data["quiz_id"] = quiz_id
    
    # Save the quiz data
    all_questions = load_questions()
    
    # Add the quiz_id to each question
    for q in quiz_data["questions"]:
        q["quiz_id"] = quiz_id
        # Make sure all required fields are present
        if "question" not in q or not q["question"]:
            logger.warning(f"Question missing 'question' field: {q}")
        if "options" not in q or not q["options"]:
            logger.warning(f"Question missing 'options' field: {q}")
        if "answer" not in q or not q["answer"]:
            logger.warning(f"Question missing 'answer' field: {q}")
    
    # Store all questions for this quiz under the quiz_id key
    # This ensures all questions are stored together as a list under the quiz_id
    all_questions[quiz_id] = quiz_data["questions"]
    logger.info(f"Saving quiz with ID {quiz_id}: {len(quiz_data['questions'])} questions")
    
    # Debug: Check the structure of the saved questions
    logger.info(f"Quiz database now contains {len(all_questions)} quiz IDs")
    logger.info(f"Quiz IDs in database: {list(all_questions.keys())}")
    
    if quiz_id in all_questions:
        logger.info(f"Quiz ID '{quiz_id}' successfully added to database")
        logger.info(f"Question count for quiz '{quiz_id}': {len(all_questions[quiz_id])}")
    else:
        logger.error(f"CRITICAL ERROR: Quiz ID '{quiz_id}' NOT found in database after adding!")
    
    # Save all questions
    save_questions(all_questions)
    
    # Verify questions were saved correctly by reloading
    verification_questions = load_questions()
    if quiz_id in verification_questions:
        logger.info(f"Verification: Quiz ID '{quiz_id}' exists in database after save")
        logger.info(f"Verification: Question count: {len(verification_questions[quiz_id])}")
    else:
        logger.error(f"CRITICAL ERROR: Quiz ID '{quiz_id}' NOT found after save!")
    
    # Store any quiz-specific settings
    if quiz_data["negative_marking"] > 0:
        set_quiz_penalty(quiz_id, quiz_data["negative_marking"])
    
    # Prepare success message
    success_message = (
        "Quiz Created Successfully! 📚\n\n"
        f"📝 Quiz Name: {quiz_data['name']}\n"
        f"# Questions: {len(quiz_data['questions'])}\n"
        f"⏱️ Timer: {quiz_data['timer']} seconds\n"
        f"🆔 Quiz ID: {quiz_id}\n"
        f"💰 Type: {quiz_data['type']}\n"
        f"➖ -ve Marking: {quiz_data['negative_marking']:.2f}\n"
        f"👤 Creator: {quiz_data['creator']}"
    )
    
    # Create custom keyboard with buttons
    # Ensure quiz_id is a string without spaces or special characters
    safe_quiz_id = str(quiz_id).strip()
    
    # Create button callback data and verify it's valid
    button_callback = f"start_quiz_{safe_quiz_id}"
    logger.info(f"Button callback data: {button_callback}")
    
    keyboard = [
        [InlineKeyboardButton("🎯 Start Quiz Now", callback_data=button_callback)],
        [InlineKeyboardButton("🚀 Start Quiz in Group", switch_inline_query=f"quiz_{safe_quiz_id}")],
        [InlineKeyboardButton("🔗 Share Quiz", switch_inline_query="")],
        [InlineKeyboardButton("📋 Quiz ID", callback_data=f"dummy_action")]
    ]
    
    # Log the button creation
    logger.info(f"Created inline buttons with switch_inline_query values: 'quiz_{safe_quiz_id}' and empty string")
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(success_message, reply_markup=reply_markup)
    
    # Clear the creation data from context
    context.user_data.pop("create_quiz", None)
    return ConversationHandler.END

async def start_created_quiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the Start Quiz Now button click after quiz creation."""
    query = update.callback_query
    await query.answer()
    
    # Extract quiz ID from callback data
    callback_data = query.data.strip()
    logger.info(f"Received callback data: {callback_data}")
    
    # Make sure the callback data starts with the expected prefix
    if not callback_data.startswith("start_quiz_"):
        logger.error(f"Invalid callback data format: {callback_data}")
        await query.edit_message_text("❌ Invalid quiz start request. Please try again.")
        return
        
    # Extract quiz ID and ensure it's properly formatted
    quiz_id = callback_data.replace("start_quiz_", "").strip()
    logger.info(f"Extracted quiz ID: {quiz_id}")
    
    # Validate the quiz ID
    if not quiz_id:
        logger.error("Empty quiz ID extracted from callback data")
        await query.edit_message_text("❌ Missing quiz ID. Please try again.")
        return
    
    # Load questions for this quiz
    questions = []
    all_questions = load_questions()
    
    # Debug: Print the structure of the questions database
    logger.info(f"Quiz database contains {len(all_questions)} quiz IDs")
    logger.info(f"Available quiz IDs: {list(all_questions.keys())}")
    
    # Debug: Check if the quiz ID exists in the database
    if quiz_id in all_questions:
        logger.info(f"Found quiz ID '{quiz_id}' directly in the database")
    else:
        logger.info(f"Quiz ID '{quiz_id}' not found directly in database, will try alternative lookup")
    
    # FIXED APPROACH: First try to find quiz_id as a direct key in all_questions
    if quiz_id in all_questions:
        quiz_questions = all_questions[quiz_id]
        
        # Debug: Check the format of the quiz questions
        logger.info(f"Type of quiz_questions: {type(quiz_questions)}")
        
        # Handle both list and dict formats
        if isinstance(quiz_questions, list):
            questions = quiz_questions
            logger.info(f"Quiz questions is a list with {len(questions)} items")
        else:
            questions = [quiz_questions]
            logger.info(f"Quiz questions is not a list, converted to single-item list")
        
        logger.info(f"Found {len(questions)} questions directly using quiz_id key")
    else:
        # Fallback: Check if quiz_id is stored as a field inside each question
        logger.info(f"Searching for quiz_id={quiz_id} as a field in questions")
        for q_id, q_data in all_questions.items():
            if isinstance(q_data, dict) and q_data.get("quiz_id") == quiz_id:
                questions.append(q_data)
                logger.info(f"Found matching question in data for quiz_id={q_id}")
            elif isinstance(q_data, list):
                # Handle case where questions are stored as a list
                logger.info(f"Checking list of {len(q_data)} questions for quiz_id={q_id}")
                for question in q_data:
                    if isinstance(question, dict) and question.get("quiz_id") == quiz_id:
                        questions.append(question)
                        logger.info(f"Found matching question in list for quiz_id={q_id}")
        
        logger.info(f"Found {len(questions)} questions by searching quiz_id field")
    
    if not questions:
        logger.error(f"No questions found for quiz ID: {quiz_id}")
        logger.info(f"Available quiz IDs: {list(all_questions.keys())}")
        
        # Additional debug: Check for potentially similar IDs (case sensitivity or whitespace)
        for existing_id in all_questions.keys():
            if existing_id.lower() == quiz_id.lower():
                logger.info(f"Found potential case-insensitive match: '{existing_id}'")
            elif existing_id.strip() == quiz_id.strip():
                logger.info(f"Found potential whitespace-sensitive match: '{existing_id}'")
        
        await query.edit_message_text(
            "❌ No questions found for this quiz ID. The quiz may have been deleted."
        )
        return
    
    # Check negative marking settings for this quiz
    neg_value = get_quiz_penalty(quiz_id)
    
    # Update message to show loading
    await query.edit_message_text(
        f"⏳ Starting quiz with ID: {quiz_id}\n"
        f"Loading {len(questions)} questions..."
    )
    
    # Prepare a proper user ID and name for tracking
    user_id = update.effective_user.id
    user_name = update.effective_user.username or update.effective_user.first_name or f"User_{user_id}"
    
    # Add user to participants
    add_participant(user_id, user_name, update.effective_user.first_name)
    
    # Determine quiz title - try to find it in questions
    quiz_title = "Custom Quiz"
    if questions and isinstance(questions[0], dict):
        # Try to extract the quiz title from the first question's quiz metadata if available
        if "quiz_name" in questions[0]:
            quiz_title = questions[0]["quiz_name"]
        # Also try quiz_title field if present
        elif "quiz_title" in questions[0]:
            quiz_title = questions[0]["quiz_title"]
            
    # Create a new quiz session in chat_data
    chat_id = update.effective_chat.id
    context.chat_data["quiz"] = {
        "active": True,
        "questions": questions,
        "current_question": 0,
        "quiz_id": quiz_id,
        "title": quiz_title,
        "participants": {
            str(user_id): {
                "name": user_name,
                "correct": 0,
                "wrong": 0,
                "skipped": 0,
                "penalty": 0,
                "participation": 0
            }
        },
        "negative_marking": neg_value > 0,
        "neg_value": neg_value,
        "custom_timer": None  # Can be set to override default timing
    }
    
    # Send the first question
    await send_question(context, chat_id, 0)
    
    # Send confirmation message
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"✅ Quiz started! {len(questions)} questions will be asked.\n\n"
             f"{'❗ Negative marking is enabled for this quiz.' if neg_value > 0 else ''}"
    )

# ---------- TXT IMPORT COMMAND HANDLERS ----------
async def txtimport_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the text import process"""
    await update.message.reply_text(
        "📄 <b>Text File Import Wizard</b>\n\n"
        "Please upload a <b>.txt file</b> containing quiz questions.\n\n"
        "<b>File Format:</b>\n"
        "- Questions MUST end with a question mark (?) to be detected\n"
        "- Questions should start with 'Q1.' or '1.' format (e.g., 'Q1. What is...?')\n"
        "- Options should be labeled as A), B), C), D) with one option per line\n"
        "- Correct answer can be indicated with:\n"
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
    
    # Verify questions were saved correctly by reloading
    verification_questions = load_questions()
    if custom_id in verification_questions:
        logger.info(f"TXT Import: Quiz ID '{custom_id}' exists in database after save")
        logger.info(f"TXT Import: Question count: {len(verification_questions[custom_id])}")
        
        # Additional checks for data integrity
        if not isinstance(verification_questions[custom_id], list):
            logger.error(f"ERROR: Questions for '{custom_id}' are not stored as a list!")
        
        # Check each question has quiz_id field
        for q in verification_questions[custom_id]:
            if not isinstance(q, dict):
                logger.error(f"ERROR: Non-dictionary question in '{custom_id}': {type(q)}")
                continue
                
            if "quiz_id" not in q:
                logger.error(f"ERROR: Question missing quiz_id field in '{custom_id}'")
            elif q["quiz_id"] != custom_id:
                logger.error(f"ERROR: Question has wrong quiz_id: {q['quiz_id']} vs {custom_id}")
    else:
        logger.error(f"CRITICAL ERROR: Quiz ID '{custom_id}' NOT found after txt import!")
    
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

def add_questions_with_id(custom_id, questions_list):
    """
    Add questions with a custom ID
    Returns the number of questions added
    """
    try:
        # Ensure custom_id is treated as a string to avoid dictionary key issues
        custom_id = str(custom_id).strip()
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
                            # Ensure quiz_id is consistent
                            q['quiz_id'] = custom_id
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
        
        # Double check that all questions have the correct quiz_id field
        for q in questions[custom_id]:
            if isinstance(q, dict):
                q['quiz_id'] = custom_id
        
        # Save the updated questions
        logger.info(f"Saving updated questions dict with {len(questions)} IDs")
        save_questions(questions)
        
        # Verify that the questions were saved properly
        verification = load_questions()
        if custom_id not in verification:
            logger.error(f"CRITICAL ERROR: Questions not properly saved for ID {custom_id}")
        else:
            logger.info(f"Successfully saved {len(verification[custom_id])} questions for ID {custom_id}")
        
        return len(valid_questions)
    except Exception as e:
        logger.error(f"Error in add_questions_with_id: {str(e)}", exc_info=True)
        return 0

async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline queries for sharing quizzes."""
    query = update.inline_query.query.strip()
    results = []
    
    logger.info(f"Received inline query: '{query}' from user {update.effective_user.id}")
    logger.info(f"Inline query object: {update.inline_query}")
    
    # Enhanced debug for all incoming queries
    try:
        # Show available quizzes for any query
        all_questions = load_questions()
        logger.info(f"Database contains {len(all_questions)} quiz IDs: {list(all_questions.keys())}")
        
        # For empty queries, show all available quizzes (top 10)
        if not query:
            logger.info("Empty query, will show all available quizzes")
            count = 0
            for quiz_id, quiz_data in all_questions.items():
                if count >= 10:  # Limit to 10 results
                    break
                
                # Get quiz questions
                if isinstance(quiz_data, list):
                    questions = quiz_data
                else:
                    questions = [quiz_data]
                
                # Get quiz name
                quiz_name = "Quiz " + quiz_id
                if questions and isinstance(questions[0], dict):
                    if "quiz_name" in questions[0]:
                        quiz_name = questions[0]["quiz_name"]
                    elif "quiz_title" in questions[0]:
                        quiz_name = questions[0]["quiz_title"]
                
                # Check negative marking
                neg_value = get_quiz_penalty(quiz_id)
                neg_text = f"Negative: {neg_value}" if neg_value > 0 else "No negative marking"
                
                # Create result for this quiz
                result_content = f"📝 Quiz: {quiz_name}\n" \
                                f"🆔 ID: {quiz_id}\n" \
                                f"❓ Questions: {len(questions)}\n" \
                                f"⚠️ {neg_text}"
                
                # Create an inline result with start button
                keyboard = [
                    [InlineKeyboardButton("➡️ Start Quiz", callback_data=f"start_quiz_{quiz_id}")]
                ]
                
                # Generate unique ID for this result
                result_id = f"all_{quiz_id}_{count}"
                
                # Add this quiz to results
                results.append(
                    InlineQueryResultArticle(
                        id=result_id,
                        title=f"Quiz: {quiz_name}",
                        description=f"{len(questions)} questions • {neg_text}",
                        input_message_content=InputTextMessageContent(result_content),
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        thumb_url="https://img.icons8.com/color/48/000000/quiz.png"
                    )
                )
                count += 1
        
        # Process formatted queries like "quiz_ID" or "share_ID"
        elif query.startswith("quiz_") or query.startswith("share_"):
            # Extract quiz ID from query
            parts = query.split('_', 1)
            if len(parts) < 2:
                logger.error(f"Invalid format for query: {query}")
                return await update.inline_query.answer(results)
                
            action = parts[0]
            quiz_id = parts[1].strip()
            
            logger.info(f"Formatted inline query for {action} with quiz ID: '{quiz_id}'")
            
            # Load questions for this quiz using the same improved approach
            questions = []
            
            # First try direct key lookup
            if quiz_id in all_questions:
                quiz_questions = all_questions[quiz_id]
                
                # Handle both list and dict formats
                if isinstance(quiz_questions, list):
                    questions = quiz_questions
                else:
                    questions = [quiz_questions]
                    
                logger.info(f"Inline: Found {len(questions)} questions using direct key")
            else:
                # Fallback approach
                for q_id, q_data in all_questions.items():
                    if isinstance(q_data, dict) and q_data.get("quiz_id") == quiz_id:
                        questions.append(q_data)
                    elif isinstance(q_data, list):
                        for question in q_data:
                            if isinstance(question, dict) and question.get("quiz_id") == quiz_id:
                                questions.append(question)
                                
                logger.info(f"Inline: Found {len(questions)} questions by field search")
                
            if not questions:
                logger.error(f"Inline: No questions for quiz ID: '{quiz_id}'")
                logger.info(f"Available quiz IDs: {list(all_questions.keys())}")
                
                # Check for similar IDs
                for existing_id in all_questions.keys():
                    if existing_id.lower() == quiz_id.lower():
                        logger.info(f"Found potential case-insensitive match: '{existing_id}'")
                        # Use the matched ID instead
                        quiz_id = existing_id
                        if isinstance(all_questions[existing_id], list):
                            questions = all_questions[existing_id]
                        else:
                            questions = [all_questions[existing_id]]
                        logger.info(f"Using case-corrected ID '{existing_id}' with {len(questions)} questions")
                        break
                
                # If still no questions found
                if not questions:
                    # Create a "no results" message
                    results.append(
                        InlineQueryResultArticle(
                            id="not_found",
                            title="Quiz Not Found",
                            description=f"No quiz found with ID: {quiz_id}",
                            input_message_content=InputTextMessageContent(
                                f"❌ Quiz with ID '{quiz_id}' could not be found.\n\nPlease check the quiz ID and try again."
                            ),
                            thumb_url="https://img.icons8.com/color/48/000000/cancel--v1.png"
                        )
                    )
                    return await update.inline_query.answer(results)
                
            # Get quiz details
            quiz_name = "Custom Quiz"
            if questions and isinstance(questions[0], dict):
                if "quiz_name" in questions[0]:
                    quiz_name = questions[0]["quiz_name"]
                elif "quiz_title" in questions[0]:
                    quiz_name = questions[0]["quiz_title"]
                    
            # Check negative marking
            neg_value = get_quiz_penalty(quiz_id)
            neg_text = f"Negative Marking: {neg_value}" if neg_value > 0 else "No negative marking"
                    
            # Create response based on action type
            if action == "quiz" or action == "share":
                # Create an InlineQueryResult with button to start the quiz
                result_content = f"📝 Quiz: {quiz_name}\n" \
                                f"🆔 ID: {quiz_id}\n" \
                                f"❓ Questions: {len(questions)}\n" \
                                f"⚠️ {neg_text}"
                                
                keyboard = [
                    [InlineKeyboardButton("➡️ Start Quiz", callback_data=f"start_quiz_{quiz_id}")]
                ]
                
                # Create the result
                results.append(
                    InlineQueryResultArticle(
                        id=quiz_id,
                        title=f"Quiz: {quiz_name}",
                        description=f"{len(questions)} questions • {neg_text}",
                        input_message_content=InputTextMessageContent(result_content),
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        thumb_url="https://img.icons8.com/color/48/000000/quiz.png"
                    )
                )
        
        # Search for quizzes matching the query
        else:
            logger.info(f"Searching for quizzes matching query: '{query}'")
            count = 0
            for quiz_id, quiz_data in all_questions.items():
                if count >= 10:  # Limit to 10 results
                    break
                
                # Get quiz questions
                if isinstance(quiz_data, list):
                    questions = quiz_data
                else:
                    questions = [quiz_data]
                
                # Get quiz name
                quiz_name = "Quiz " + quiz_id
                if questions and isinstance(questions[0], dict):
                    if "quiz_name" in questions[0]:
                        quiz_name = questions[0]["quiz_name"]
                    elif "quiz_title" in questions[0]:
                        quiz_name = questions[0]["quiz_title"]
                
                # Check if query matches quiz ID or name
                if (query.lower() in quiz_id.lower() or 
                    query.lower() in quiz_name.lower()):
                    
                    # Check negative marking
                    neg_value = get_quiz_penalty(quiz_id)
                    neg_text = f"Negative: {neg_value}" if neg_value > 0 else "No negative marking"
                    
                    # Create result for this quiz
                    result_content = f"📝 Quiz: {quiz_name}\n" \
                                    f"🆔 ID: {quiz_id}\n" \
                                    f"❓ Questions: {len(questions)}\n" \
                                    f"⚠️ {neg_text}"
                    
                    # Create an inline result with start button
                    keyboard = [
                        [InlineKeyboardButton("➡️ Start Quiz", callback_data=f"start_quiz_{quiz_id}")]
                    ]
                    
                    # Generate unique ID for this result
                    result_id = f"search_{quiz_id}_{count}"
                    
                    # Add this quiz to results
                    results.append(
                        InlineQueryResultArticle(
                            id=result_id,
                            title=f"Quiz: {quiz_name}",
                            description=f"{len(questions)} questions • {neg_text}",
                            input_message_content=InputTextMessageContent(result_content),
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            thumb_url="https://img.icons8.com/color/48/000000/quiz.png"
                        )
                    )
                    count += 1
    except Exception as e:
        logger.error(f"Error in inline query handler: {str(e)}", exc_info=True)
        # Create error result
        results.append(
            InlineQueryResultArticle(
                id="error",
                title="Error Processing Query",
                description="An error occurred while processing your query",
                input_message_content=InputTextMessageContent(
                    f"❌ Error processing query: {str(e)}"
                ),
                thumb_url="https://img.icons8.com/color/48/000000/error--v1.png"
            )
        )
    
    # If no results found, show a helpful message
    if not results:
        results.append(
            InlineQueryResultArticle(
                id="no_results",
                title="No Quizzes Found",
                description="Try sharing a quiz from the bot or use quiz_ID format",
                input_message_content=InputTextMessageContent(
                    "To share a quiz, use:\n"
                    "1. The Share Quiz button after creating a quiz\n"
                    "2. Type @your_bot_username followed by quiz_ID\n"
                    "3. Type @your_bot_username to see all available quizzes"
                ),
                thumb_url="https://img.icons8.com/color/48/000000/info--v1.png"
            )
        )
        
    # Log the number of results
    logger.info(f"Returning {len(results)} inline query results")
    
    # Answer the inline query with a short cache time for testing
    await update.inline_query.answer(results, cache_time=5)

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # IMPORTANT: Register the inline query handler first so it has the highest priority
    application.add_handler(InlineQueryHandler(inline_query_handler))
    logger.info("Registered inline query handler with TOP priority for quiz sharing")
    
    # Basic command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("features", features_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("stop", stop_quiz_command))
    application.add_handler(CommandHandler("stats", stats_command))  # This calls extended_stats_command
    application.add_handler(CommandHandler("delete", delete_command))
    
    # NEGATIVE MARKING ADDITION: Add new command handlers
    application.add_handler(CommandHandler("negmark", negative_marking_settings))
    application.add_handler(CommandHandler("resetpenalty", reset_user_penalty_command))
    application.add_handler(CallbackQueryHandler(negative_settings_callback, pattern=r"^neg_mark_"))
    
    # Quiz creation conversation handler
    # Create a done handler function that reuses code from create_questions_file_received
    async def done_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle /done command explicitly during quiz creation."""
        quiz_data = context.user_data.get("create_quiz", {})
        logger.info(f"Explicit /done command handler with {len(quiz_data.get('questions', []))} questions")
        
        # Proceed to ask about sections
        if len(quiz_data.get("questions", [])) > 0:
            await update.message.reply_text(
                "Do you want section in your quiz? send yes/no"
            )
            return CREATE_SECTIONS
        else:
            await update.message.reply_text(
                "❌ You need to add at least one question to create a quiz."
            )
            return CREATE_QUESTIONS
    
    create_quiz_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("create", create_command)],
        states={
            CREATE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_name_received)],
            CREATE_QUESTIONS: [
                CommandHandler("done", done_command_handler),  # Explicit handler for /done command
                MessageHandler(filters.Document.ALL, create_questions_file_received),
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_questions_file_received),
            ],
            CREATE_SECTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_sections_received)
            ],
            CREATE_TIMER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_timer_received)
            ],
            CREATE_NEGATIVE_MARKING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_negative_marking_received)
            ],
            CREATE_TYPE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_type_received)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("done", done_command_handler),  # Also handle /done in fallbacks
        ],
    )
    application.add_handler(create_quiz_conv_handler)
    
    # PDF IMPORT ADDITION: Add new command handlers
    application.add_handler(CommandHandler("pdfinfo", pdf_info_command))
    application.add_handler(CommandHandler("quizid", quiz_with_id_command))
    
    # HTML Report Generation command handlers
    application.add_handler(CommandHandler("htmlreport", html_report_command))
    application.add_handler(CommandHandler("htmlinfo", html_info_command))
    
    # Inline mode help and troubleshooting
    application.add_handler(CommandHandler("inlinehelp", inline_help_command))

    # Add handler for negative marking selection callback
    application.add_handler(CallbackQueryHandler(negative_marking_callback, pattern=r"^negmark_"))
    
    # Add handler for created quiz start button callback
    application.add_handler(CallbackQueryHandler(start_created_quiz_callback, pattern=r"^start_quiz_"))
    
    # Add handler for dummy_action (ID button)
    application.add_handler(CallbackQueryHandler(
        lambda update, context: update.callback_query.answer(f"Copy this ID: {update.callback_query.message.text.split('ID:')[1].split('\n')[0].strip()}", show_alert=True),
        pattern=r"^dummy_action$"
    ))
    
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
    # Handle any forwarded message and check if it has a poll inside the handler
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
            CATEGORY: [CallbackQueryHandler(category_callback, pattern=r"^category_")]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
        per_user=True,
        per_message=False,
        name="add_question_conversation"
    )
    application.add_handler(add_question_handler)
    
    # Poll Answer Handler - CRITICAL for tracking all participants
    application.add_handler(PollAnswerHandler(poll_answer))
    
    # NOTE: Inline query handler is already registered at the beginning of the handlers list
    # No need to register it again here
    
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
        allow_reentry=True,  # Allow the conversation to be restarted
        per_user=True,
        per_message=False,
        name="txtimport_conversation"
    )
    application.add_handler(txtimport_handler)
    
    # Start the Bot
    application.run_polling()

if __name__ == "__main__":
    main()
