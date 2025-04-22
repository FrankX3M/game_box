import asyncio
import random
import logging
from dotenv import load_dotenv  # Add this import
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from db import init_db, add_win, get_leaderboard, get_balance, deduct_bet, get_transaction_history


load_dotenv()  # Add this line
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot token and configuration
TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    logger.error("TELEGRAM_TOKEN not found in environment variables!")
print(TOKEN)
print(type(TOKEN))

# Директория для данных (совместима с Docker)
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Game economics - увеличенная сложность для большего драйва
MOVE_COST = 15      # Увеличена стоимость хода (было 10)
WIN_AMOUNT = 80     # Немного увеличен выигрыш (было 70)
GRID_SIZE = 4       # Увеличен размер сетки до 4x4 (было 3x3)
GAME_TIMEOUT = 180  # Уменьшено время на игру (было 300 сек)

# Initialize bot and dispatcher
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Game state storage
games = {}

def generate_keyboard(chat_id, game):
    """Generate the game keyboard with current state."""
    buttons = []
    for i in range(GRID_SIZE):
        row = []
        for j in range(GRID_SIZE):
            cell_id = f"{i}_{j}"
            if cell_id in game["opened"]:
                # Opened cell - show X or target
                text = "❌" if cell_id != game["target"] else "🍆"
                row.append(InlineKeyboardButton(text=text, callback_data="noop"))
            else:
                # Closed cell - show box
                row.append(InlineKeyboardButton(
                    text="📦", 
                    callback_data=f"open:{chat_id}:{cell_id}"
                ))
        buttons.append(row)
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard

def start_new_game(chat_id):
    """Initialize a new game for the given chat_id."""
    # Random target position (row_col format)
    target = f"{random.randint(0, GRID_SIZE-1)}_{random.randint(0, GRID_SIZE-1)}"
    games[chat_id] = {
        "target": target,         # The position of the winning cell
        "opened": set(),          # Set of already opened cells
        "active": True,           # Game status flag
        "moves": 0,               # Count moves made
        "total_spent": 0          # Total coins spent
    }
    logger.info(f"New game started for chat {chat_id}. Target: {target}")

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    """Handle /start command."""
    await message.answer(
        "Привет! Вот доступные команды:\n"
        "/play - начать игру\n"
        "/balance - проверить баланс\n"
        "/history - история транзакций\n"
        "/stats - статистика побед\n\n"
        "📋 Правила игры:\n"
        f"- За каждый ход списывается {MOVE_COST} монет\n"
        f"- Если найдёшь хуй в коробке - получишь {WIN_AMOUNT} монет\n"
        f"- Игра идет на сетке {GRID_SIZE}x{GRID_SIZE}, что делает её сложнее\n"
        f"- У тебя {GAME_TIMEOUT//60} минут на игру, потом она сбрасывается\n"
        "- Будь внимателен! Открывая больше ячеек, ты рискуешь потерять больше монет"
    )

@dp.message(Command("play"))
async def play_handler(message: types.Message):
    """Handle /play command - start a new game."""
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        username = message.from_user.full_name
        
        logger.info(f"Play command from user {user_id} ({username}) in chat {chat_id}")

        # Check user balance - make sure they have at least enough for one move
        balance = get_balance(user_id)
        if balance < MOVE_COST:
            await message.answer(f"У тебя недостаточно монет! Нужно хотя бы {MOVE_COST}, а у тебя {balance}.")
            return
        
        # Start new game
        start_new_game(chat_id)
        
        # Send game message with keyboard
        await message.answer(
            f"🎲 Найди хуй в коробке!\nСтоимость хода: {MOVE_COST} монет.\nВыигрыш: {WIN_AMOUNT} монет.\n\n💰 Текущий баланс: {balance} монет",
            reply_markup=generate_keyboard(chat_id, games[chat_id])
        )
        
        # Set game timeout
        asyncio.create_task(game_timeout(chat_id))
    except Exception as e:
        logger.error(f"Error in play handler: {str(e)}")
        await message.answer(f"Произошла ошибка: {str(e)}")

async def game_timeout(chat_id, timeout=GAME_TIMEOUT):
    """Clean up game after timeout."""
    await asyncio.sleep(timeout)
    if chat_id in games and games[chat_id]["active"]:
        game_info = games.pop(chat_id)
        logger.info(f"Game for chat {chat_id} timed out and was removed. Moves: {game_info['moves']}, Spent: {game_info['total_spent']}")
        try:
            await bot.send_message(
                chat_id=chat_id, 
                text=f"⏰ Время игры истекло! Ты потратил {game_info['total_spent']} монет за {game_info['moves']} ходов, но так и не нашел приз."
            )
        except:
            pass

@dp.callback_query(F.data.startswith("open"))
async def open_cell(callback: types.CallbackQuery):
    """Handle cell opening callback."""
    try:
        # Parse callback data
        parts = callback.data.split(":")
        if len(parts) != 3:
            await callback.answer("Неверный формат данных")
            return
            
        _, chat_id_str, cell_id = parts
        try:
            chat_id = int(chat_id_str)
        except ValueError:
            await callback.answer("Неверный формат ID чата")
            return
        
        user_id = callback.from_user.id
        username = callback.from_user.full_name
            
        # Get game state
        game = games.get(chat_id)
        if not game:
            await callback.answer("Игра не найдена")
            return
            
        if not game["active"]:
            await callback.answer("Игра уже завершена")
            return

        if cell_id in game["opened"]:
            await callback.answer("Эта ячейка уже открыта")
            return
            
        # Check if user has enough balance for this move
        balance = get_balance(user_id)
        if balance < MOVE_COST:
            await callback.answer(f"Недостаточно монет! У тебя {balance}, нужно {MOVE_COST}.")
            return
            
        # Deduct cost for this move
        old_balance = balance
        new_balance = deduct_bet(user_id, username, MOVE_COST)
        
        # Update game stats
        game["moves"] += 1
        game["total_spent"] += MOVE_COST
        
        # Open the cell
        game["opened"].add(cell_id)
        logger.info(f"Cell {cell_id} opened in chat {chat_id} at cost of {MOVE_COST} coins")

        # Check if it's a winning cell
        if cell_id == game["target"]:
            # Player won
            game["active"] = False
            
            # Add win amount
            old_balance = new_balance  # Balance after move cost deduction
            add_win(user_id, username, WIN_AMOUNT)
            new_balance = get_balance(user_id)
            
            # Create winning message
            total_spent = game["total_spent"]
            profit = WIN_AMOUNT - total_spent
            profit_text = f"+{profit}" if profit > 0 else f"{profit}"
            
            win_msg = (
                f"💥 *{username}* нашёл хуй в коробке и выиграл {WIN_AMOUNT} монет!\n"
                f"Потрачено: {total_spent} монет за {game['moves']} ходов\n"
                f"Чистая прибыль: {profit_text} монет\n\n"
                f"💰 Баланс: {old_balance} → {new_balance} монет (+{WIN_AMOUNT})"
            )
            
            logger.info(f"User {user_id} won {WIN_AMOUNT} coins. Moves: {game['moves']}, Spent: {total_spent}, Profit: {profit}")
            
            # Show the winning in the current keyboard
            await callback.message.edit_text(
                f"🎲 Найди хуй в коробке!\nСтоимость хода: {MOVE_COST} монет.\nВыигрыш: {WIN_AMOUNT} монет.\n\n💰 Баланс: {old_balance} → {new_balance} монет",
                reply_markup=generate_keyboard(chat_id, game)
            )
            
            # Send winning message
            await callback.message.answer(win_msg, parse_mode="Markdown")
            
            # Start a new game automatically if enough coins
            if new_balance >= MOVE_COST:
                # Start new game
                start_new_game(chat_id)
                
                # Send new game message
                await callback.message.answer(
                    f"🎲 Начинаем новую игру!\nСтоимость хода: {MOVE_COST} монет.\nВыигрыш: {WIN_AMOUNT} монет.\n\n💰 Текущий баланс: {new_balance} монет",
                    reply_markup=generate_keyboard(chat_id, games[chat_id])
                )
                
                # Set timeout
                asyncio.create_task(game_timeout(chat_id))
            else:
                await callback.message.answer(
                    f"У тебя недостаточно монет для новой игры! Нужно хотя бы {MOVE_COST}, а у тебя {new_balance}."
                )
        else:
            # Player missed - update message showing balance change and opened cell
            bad_luck_msgs = [
                "Мимо! Продолжай искать.",
                "Не угадал! Ищи дальше.",
                "Пусто! Может в другой коробке?",
                "Ничего! Продолжай поиск.",
                "Нет! Попробуй еще."
            ]
            
            await callback.answer(f"{random.choice(bad_luck_msgs)} Списано {MOVE_COST} монет.")
            
            # Calculate potential profit/loss
            potential_profit = WIN_AMOUNT - game["total_spent"]
            profit_text = f"Потенциальная прибыль: +{potential_profit}" if potential_profit > 0 else f"Текущий убыток: {potential_profit}"
            
            # Update message with new balance info and moves count
            game_info = (
                f"🎲 Найди хуй в коробке!\n"
                f"Стоимость хода: {MOVE_COST} монет.\n"
                f"Выигрыш: {WIN_AMOUNT} монет.\n"
                f"Ходов сделано: {game['moves']}\n"
                f"{profit_text}\n\n"
                f"💰 Баланс: {old_balance} → {new_balance} монет (-{MOVE_COST})"
            )
            
            # Calculate remaining unopened cells
            total_cells = GRID_SIZE * GRID_SIZE
            remaining = total_cells - len(game["opened"])
            
            # If too many cells opened (>75%), add hint about remaining cells
            if remaining <= total_cells * 0.25:
                game_info += f"\n\n⚠️ Осталось всего {remaining} ячеек!"
            
            await callback.message.edit_text(
                game_info,
                reply_markup=generate_keyboard(chat_id, game)
            )
    except Exception as e:
        logger.error(f"Error in open_cell handler: {str(e)}")
        await callback.answer(f"Произошла ошибка: {str(e)}")

@dp.message(Command("stats"))
async def stats(message: types.Message):
    """Handle /stats command."""
    leaderboard = get_leaderboard()
    if not leaderboard:
        await message.answer("Пока никто не выигрывал 😶")
        return

    text = "🏆 *Статистика побед:*\n"
    for name, points in leaderboard:
        text += f"{name}: {points}\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("balance"))
async def balance(message: types.Message):
    """Handle /balance command."""
    bal = get_balance(message.from_user.id)
    await message.answer(f"💰 Твой баланс: {bal} монет.")

@dp.message(Command("history"))
async def history(message: types.Message):
    """Handle /history command - show transaction history."""
    user_id = message.from_user.id
    transactions = get_transaction_history(user_id, limit=10)
    
    if not transactions:
        await message.answer("У тебя пока нет истории транзакций.")
        return
    
    text = "📊 *История последних транзакций:*\n\n"
    for amount, type_tx, timestamp in transactions:
        symbol = "➕" if amount > 0 else "➖"
        abs_amount = abs(amount)
        type_text = "выигрыш" if type_tx == "win" else "ставка"
        text += f"{timestamp[:16]} | {symbol} {abs_amount} монет | {type_text}\n"
    
    await message.answer(text, parse_mode="Markdown")

async def main():
    """Main function to start the bot."""
    try:
        # Initialize database
        init_db()
        logger.info("Database initialized")
        
        # Start the bot
        logger.info("Starting bot polling...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Error in main function: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())