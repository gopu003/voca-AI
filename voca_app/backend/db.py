import sqlite3
import time
import os
from datetime import datetime

class DatabaseManager:
    """Manages SQLite database for storing VocaAI history"""
    
    def __init__(self, db_path="voca_history.db"):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self.init_db()

    def init_db(self):
        """Initialize the database and create tables if they don't exist"""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.cursor = self.conn.cursor()
            
            # Create logs table
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS activity_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,  -- 'SIGN' or 'VOICE'
                    content TEXT NOT NULL,
                    language TEXT,
                    timestamp REAL,
                    formatted_time TEXT
                )
            ''')
            self.conn.commit()
            print(f"Database initialized at {self.db_path}")
        except Exception as e:
            print(f"Database Initialization Error: {e}")

    def add_entry(self, event_type, content, language="en-US"):
        """Add a new entry to the logs"""
        if not content:
            return
            
        try:
            timestamp = time.time()
            formatted_time = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            
            self.cursor.execute('''
                INSERT INTO activity_logs (event_type, content, language, timestamp, formatted_time)
                VALUES (?, ?, ?, ?, ?)
            ''', (event_type, content, language, timestamp, formatted_time))
            self.conn.commit()
            # print(f"DB: Saved {event_type} - {content[:20]}...")
        except Exception as e:
            print(f"DB Save Error: {e}")

    def get_recent_history(self, limit=50):
        """Retrieve recent history logs"""
        try:
            self.cursor.execute('''
                SELECT event_type, content, formatted_time 
                FROM activity_logs 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (limit,))
            return self.cursor.fetchall()
        except Exception as e:
            print(f"DB Fetch Error: {e}")
            return []

    def clear_history(self):
        """Clear all history"""
        try:
            self.cursor.execute('DELETE FROM activity_logs')
            self.conn.commit()
        except Exception as e:
            print(f"DB Clear Error: {e}")

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
