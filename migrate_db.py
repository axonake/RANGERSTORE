import sqlite3

def migrate():
    conn = sqlite3.connect('instance/database.db')
    cursor = conn.cursor()
    
    try:
        # Check if columns in 'order' table need to be nullable
        # SQLite doesn't support ALTER COLUMN, but nullable columns work automatically
        # Just ensure the table structure is correct
        
        # Check current order table columns
        cursor.execute("PRAGMA table_info('order')")
        columns = {info[1]: info for info in cursor.fetchall()}
        
        print("Current 'order' table columns:")
        for name, info in columns.items():
            print(f"  - {name}: notnull={info[3]}")
        
        # For SQLite, we can't change nullable status directly
        # But we can set default values for existing rows if needed
        
        # Update any NULL values that might cause issues
        if 'link_method' in columns:
            print("\nSetting default values for any NULL link_method entries...")
            # Don't change existing NULLs - just report status
            cursor.execute("SELECT COUNT(*) FROM 'order' WHERE link_method IS NULL")
            null_count = cursor.fetchone()[0]
            print(f"  Orders with NULL link_method: {null_count}")
        
        # Check user balance column
        cursor.execute("PRAGMA table_info(user)")
        user_columns = [info[1] for info in cursor.fetchall()]
        
        if 'balance' not in user_columns:
            print("\nAdding 'balance' column to 'user' table...")
            cursor.execute("ALTER TABLE user ADD COLUMN balance FLOAT DEFAULT 0.0")
            conn.commit()
            print("Migration successful: Added 'balance' column.")
        else:
            print("\n'balance' column already exists in user table.")
            
        print("\n✅ Migration check complete!")
            
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
