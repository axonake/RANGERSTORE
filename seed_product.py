from app import app, db, User, Product, ProductStock
from werkzeug.security import generate_password_hash

def seed():
    with app.app_context():
        # Create User
        if not User.query.filter_by(username='user2').first():
            u = User(username='user2', role='user', balance=500.0)
            u.set_password('pass1234')
            db.session.add(u)
            print("Created user2")
            
        # Create Product
        if not Product.query.filter_by(name='Test Product').first():
            p = Product(name='Test Product', description='Description', price=100.0)
            db.session.add(p)
            db.session.flush()
            
            # Create Stocks
            s1 = ProductStock(product_id=p.id, xml_file='dummy1.xml', is_sold=False)
            s2 = ProductStock(product_id=p.id, xml_file='dummy2.xml', is_sold=False)
            db.session.add(s1)
            db.session.add(s2)
            
            print("Created Test Product with 2 stocks")
            
        db.session.commit()
        print("Seed complete")

if __name__ == '__main__':
    seed()
