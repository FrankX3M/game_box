FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY *.py .
COPY image.png .

# Создаем непривилегированного пользователя для запуска бота
RUN useradd -m botuser
USER botuser

# Запускаем бота
CMD ["python", "main.py"]