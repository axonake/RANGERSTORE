# Flask Configuration
import os

# Load .env file if exists (for local development)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, use system env vars

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'line-ranger-store-secret-key-2024'
    
    # Database Configuration
    # Uses DATABASE_URL from environment (Supabase PostgreSQL)
    DATABASE_URL = os.environ.get('DATABASE_URL')
    
    # Convert to SQLAlchemy format with psycopg (v3) driver
    if DATABASE_URL:
        # Handle various postgres:// formats
        if DATABASE_URL.startswith('postgres://'):
            DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql+psycopg://', 1)
        elif DATABASE_URL.startswith('postgresql://'):
            DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg://', 1)
    
    SQLALCHEMY_DATABASE_URI = DATABASE_URL or 'sqlite:///database.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Engine options for PostgreSQL
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    
    # ADB Configuration for MuMu Player
    ADB_PATH = os.environ.get('ADB_PATH') or r'F:\Program Files\Netease\MuMuPlayer\nx_main\adb.exe'
    
    # Game Configuration
    PACKAGE_NAME = 'com.linecorp.LGRGS'
    TARGET_FILENAME = '_LINE_COCOS_PREF_KEY.xml'
    TARGET_PATH = f'/data/data/{PACKAGE_NAME}/shared_prefs/{TARGET_FILENAME}'
    
    # TrueMoney Wallet Configuration
    TW_MERCHANT_PHONE = os.environ.get('TW_MERCHANT_PHONE') or "0631351022"
    
    # File upload settings
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'images')
    PRODUCTS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'products')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'xml'}
