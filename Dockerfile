
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .

RUN python -m pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Expose API and Streamlit ports
EXPOSE 8000 8501

# Start FastAPI and Streamlit
CMD ["sh", "-c", "python -m uvicorn app.api:app --host 0.0.0.0 --port 8000 & exec python -m streamlit run app/ui.py --server.address 0.0.0.0 --server.port 8501"]
