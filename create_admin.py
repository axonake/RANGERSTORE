"""
Create Admin User Script
"""
import os
from dotenv import load_dotenv
load_dotenv()

from app import app, db, User

def create_admin():
    with app.app_context():
        # Check if admin exists
        admin = User.query.filter_by(username='admin').first()
        if admin:
            print("⚠️ Admin user already exists!")
            print(f"   Username: admin")
            print(f"   Email: {admin.email}")
            print(f"   Balance: ฿{admin.balance:,.2f}")
            return
        
        # Create admin user
        admin = User(
            username='admin',
            email='admin@lrgstore.com',
            is_admin=True,
            balance=100000.0
        )
        admin.set_password('admin123')  # Change this!
        
        db.session.add(admin)
        db.session.commit()
        
        print("✅ Admin user created!")
        print(f"   Username: admin")
        print(f"   Password: admin123")
        print(f"   Email: admin@lrgstore.com")
        print(f"   Balance: ฿100,000.00")
        print("\n⚠️ Please change the password immediately!")

if __name__ == '__main__':
    create_admin()
