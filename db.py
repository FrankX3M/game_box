import sqlite3
import logging
import os

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Директория для данных (совместима с Docker)
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Путь к базе данных
DB_NAME = os.path.join(DATA_DIR, "scores.db")

def init_db():
    """Initialize the database and create tables if they don't exist."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    # Create scores table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS scores (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            points INTEGER DEFAULT 0,
            balance INTEGER DEFAULT 100
        )
    ''')
    
    # Create transactions table to track all balance changes
    cur.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            amount INTEGER,
            type TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info(f"Database initialized successfully at {DB_NAME}")

def add_win(user_id, username, amount_won):
    """Add a win to a user's record and update their balance."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    try:
        # Get current balance
        cur.execute('SELECT balance FROM scores WHERE user_id = ?', (user_id,))
        row = cur.fetchone()
        old_balance = row[0] if row else 100
        
        # Update or insert user record
        cur.execute('SELECT * FROM scores WHERE user_id = ?', (user_id,))
        if cur.fetchone():
            cur.execute('''
                UPDATE scores
                SET points = points + 1,
                    balance = balance + ?,
                    username = ?
                WHERE user_id = ?
            ''', (amount_won, username, user_id))
        else:
            cur.execute('''
                INSERT INTO scores (user_id, username, points, balance)
                VALUES (?, ?, 1, ?)
            ''', (user_id, username, 100 + amount_won))
        
        # Log the transaction
        cur.execute('''
            INSERT INTO transactions (user_id, username, amount, type)
            VALUES (?, ?, ?, 'win')
        ''', (user_id, username, amount_won))
        
        # Get new balance
        cur.execute('SELECT balance FROM scores WHERE user_id = ?', (user_id,))
        new_balance = cur.fetchone()[0]
        
        conn.commit()
        logger.info(f"Win recorded for user {user_id}: +{amount_won} coins. Balance: {old_balance} → {new_balance}")
    except Exception as e:
        conn.rollback()
        logger.error(f"Error recording win: {str(e)}")
    finally:
        conn.close()

def deduct_bet(user_id, username, amount):
    """Deduct a bet amount from user's balance."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    try:
        # Get current balance
        cur.execute('SELECT balance FROM scores WHERE user_id = ?', (user_id,))
        row = cur.fetchone()
        old_balance = row[0] if row else 100
        
        # Update or insert user record
        if row:
            new_balance = old_balance - amount
            cur.execute('UPDATE scores SET balance = ?, username = ? WHERE user_id = ?', 
                       (new_balance, username, user_id))
        else:
            new_balance = 100 - amount
            cur.execute('INSERT INTO scores (user_id, username, points, balance) VALUES (?, ?, 0, ?)', 
                       (user_id, username, new_balance))
        
        # Log the transaction
        cur.execute('''
            INSERT INTO transactions (user_id, username, amount, type)
            VALUES (?, ?, ?, 'bet')
        ''', (user_id, username, -amount))
        
        conn.commit()
        logger.info(f"Bet deducted for user {user_id}: -{amount} coins. Balance: {old_balance} → {new_balance}")
    except Exception as e:
        conn.rollback()
        logger.error(f"Error deducting bet: {str(e)}")
    finally:
        conn.close()
    
    return new_balance

def get_balance(user_id):
    """Get user's current balance."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    try:
        cur.execute('SELECT balance FROM scores WHERE user_id = ?', (user_id,))
        row = cur.fetchone()
        balance = row[0] if row else 100
        logger.info(f"Retrieved balance for user {user_id}: {balance} coins")
        return balance
    except Exception as e:
        logger.error(f"Error getting balance: {str(e)}")
        return 100
    finally:
        conn.close()

def get_leaderboard():
    """Get top 10 players by number of wins."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    try:
        cur.execute('SELECT username, points FROM scores ORDER BY points DESC LIMIT 10')
        rows = cur.fetchall()
        return rows
    except Exception as e:
        logger.error(f"Error getting leaderboard: {str(e)}")
        return []
    finally:
        conn.close()

def get_transaction_history(user_id, limit=10):
    """Get transaction history for a user."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    try:
        cur.execute('''
            SELECT amount, type, timestamp 
            FROM transactions 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (user_id, limit))
        return cur.fetchall()
    except Exception as e:
        logger.error(f"Error getting transaction history: {str(e)}")
        return []
    finally:
        conn.close()