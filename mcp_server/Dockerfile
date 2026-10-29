# Multi-stage production container for Cloud Run
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY models.py mcp_server/models.py
COPY server.py mcp_server/server.py
COPY __init__.py mcp_server/__init__.py

EXPOSE 8080

# Run with uvicorn
CMD ["python", "-m", "uvicorn", "mcp_server.server:app", "--host", "0.0.0.0", "--port", "8080"]
