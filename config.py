import os
from dotenv import load_dotenv

# .env dosyasındaki ortam değişkenlerini yükle
basedir = os.path.abspath(os.path.dirname(__file__))
dotenv_path = os.path.join(basedir, '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    print("Warning: .env file not found. Using default or environment-set configurations.")

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY') or 'you-will-never-guess'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
    GEMINI_API_KEY  = os.environ.get('GEMINI_API_KEY')
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or os.path.join(basedir, 'uploads')
    CHROMA_DB_PATH = os.environ.get('CHROMA_DB_PATH') or os.path.join(basedir, 'chroma_data')

    # Ensure instance and upload folders exist
    INSTANCE_FOLDER_PATH = os.path.join(basedir, 'instance')
    if not os.path.exists(INSTANCE_FOLDER_PATH):
        os.makedirs(INSTANCE_FOLDER_PATH)
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    if not os.path.exists(CHROMA_DB_PATH) and CHROMA_DB_PATH: # CHROMA_DB_PATH might be empty if not set
        os.makedirs(CHROMA_DB_PATH)


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    FLASK_DEBUG = True # Ensure Flask's reloader and debugger are active

class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:' # Use in-memory SQLite for tests
    WTF_CSRF_ENABLED = False # Disable CSRF for tests

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    FLASK_DEBUG = False
    # Add any production-specific settings here, e.g., logging, security headers

# Dictionary to access configurations by name
config_by_name = dict(
    dev=DevelopmentConfig,
    test=TestingConfig,
    prod=ProductionConfig,
    default=DevelopmentConfig
)

# Helper function to get the current configuration
def get_config():
    config_name = os.getenv('FLASK_ENV', 'default')
    return config_by_name.get(config_name, DevelopmentConfig)
