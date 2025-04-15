FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

# Set working directory
WORKDIR /app

# Install system dependencies & Hindi OCR model
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    tesseract-ocr \
    tesseract-ocr-hin \
    libtesseract-dev \
    wget \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Ensure hin.traineddata is available (optional but safe)
RUN mkdir -p /usr/share/tesseract-ocr/5/tessdata && \
    wget -O /usr/share/tesseract-ocr/5/tessdata/hin.traineddata \
    https://github.com/tesseract-ocr/tessdata/raw/main/hin.traineddata

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of your bot project
COPY . .

# Default CMD
CMD ["python", "main.py"]
