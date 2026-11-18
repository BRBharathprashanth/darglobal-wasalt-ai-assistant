
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .

RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn app.api:app --host 0.0.0.0 --port 8000 & exec python -m streamlit run app/ui.py --server.address 0.0.0.0 --server.port ${PORT:-8501}"]
