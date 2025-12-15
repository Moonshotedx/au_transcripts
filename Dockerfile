# Dockerfile for AU Transcripts Streamlit Application
# Optimized for WeasyPrint PDF generation with required system libraries

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Set working directory
WORKDIR /app

# Install system dependencies for WeasyPrint and other libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    # WeasyPrint dependencies
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    # Font support
    fonts-liberation \
    fonts-dejavu-core \
    # Build tools (for some Python packages)
    gcc \
    libpq-dev \
    # Clean up
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY grade_card_generator.py .
COPY generate_transcript.py .
COPY enhanced_transcript_template.html .
COPY enhanced_transcript_styles.css .

# Copy modules
COPY db/ ./db/
COPY r2/ ./r2/

# Copy assets (templates, fonts, etc.)
COPY assets/ ./assets/
COPY ["Grade Card Template.pdf", "./"]
COPY ["Grade Point Table.pdf", "./"]

# Create output directories
RUN mkdir -p gradecards transcripts

# Expose Streamlit port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Run Streamlit app
CMD ["streamlit", "run", "app.py"]
