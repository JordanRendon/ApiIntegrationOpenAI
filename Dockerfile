FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY controller.py .
COPY openai_service.py .
COPY .env .

EXPOSE 8000

CMD ["python", "main.py"]

