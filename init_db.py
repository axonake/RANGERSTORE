"""
Database Initialization Script
Creates all tables in PostgreSQL/Supabase
"""
import os
from dotenv import load_dotenv
load_dotenv()

from app import app, db

def init_db():
    with app.app_context():
        print("🔌 Connecting to database...")
        print(f"   URL: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")
        
        print("\n📦 Creating tables...")
        db.create_all()
        
        print("\n✅ Database initialized successfully!")
        print("\nTables created:")
        print("  - user")
        print("  - product")
        print("  - order")
        print("  - top_up")

if __name__ == '__main__':
    init_db()
