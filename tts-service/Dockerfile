FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY templates ./templates
COPY static ./static
RUN useradd --create-home app && mkdir -p storage && chown app storage
USER app
ENV PYTHONUNBUFFERED=1
# Render đặt PORT; AZURE_SPEECH_KEY và AZURE_SPEECH_REGION đặt trong dashboard Render
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
