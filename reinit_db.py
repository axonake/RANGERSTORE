import os
from app import app, db

def reinit_db():
    print("Re-initializing database...")
    if os.path.exists('instance/site.db'):
        os.remove('instance/site.db') # Assuming sqlite, but user switched to postgres
        print("Deleted sqlite file if exists")

    # For postgres or just general alchemy:
    with app.app_context():
        # Drop all tables
        db.drop_all()
        print("Dropped all tables")
        
        # Create all
        db.create_all()
        print("Created all tables")
        
        # Create Admin
        from app import User
        from werkzeug.security import generate_password_hash
        
        admin = User(
            username='admin', 
            password=generate_password_hash('admin123'), 
            role='admin',
            balance=100000.0
        )
        db.session.add(admin)
        db.session.commit()
        print("Created admin user")

if __name__ == "__main__":
    reinit_db()
