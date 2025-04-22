#!/bin/bash

# Проверяем наличие Docker и Docker Compose
if ! command -v docker &> /dev/null; then
    echo "Docker не установлен. Пожалуйста, установите Docker."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "Docker Compose не установлен. Пожалуйста, установите Docker Compose."
    exit 1
fi

# Создаем директорию для данных, если она не существует
mkdir -p data
echo "Директория для данных создана: ./data/"

# Собираем и запускаем контейнер
echo "Запуск бота в Docker-контейнере..."
docker-compose up --build -d

echo "Бот запущен! Для просмотра логов используйте команду:"
echo "docker logs game_box_bot -f"