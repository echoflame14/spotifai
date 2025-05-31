import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class TruncatingFormatter(logging.Formatter):
    def __init__(self, fmt=None, datefmt=None, max_length=200):
        super().__init__(fmt, datefmt)
        self.max_length = max_length

    def format(self, record):
        if isinstance(record.msg, str) and len(record.msg) > self.max_length:
            original_length = len(record.msg)
            record.msg = f"{record.msg[:self.max_length]}... [truncated, total length: {original_length} chars]"
        return super().format(record)

# Configure logging
logger = logging.getLogger('app')
logger.setLevel(logging.DEBUG)

# Create console handler with custom formatter
console_handler = logging.StreamHandler()
console_formatter = TruncatingFormatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    max_length=200
)
console_handler.setFormatter(console_formatter)

# Create file handler with custom formatter
file_handler = logging.FileHandler('app.log')
file_formatter = TruncatingFormatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    max_length=200
)
file_handler.setFormatter(file_formatter)

# Add handlers to logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# Log environment variables at startup
logger.debug('=== Environment Variables ===')
logger.debug(f'SPOTIFY_CLIENT_ID: {os.environ.get("SPOTIFY_CLIENT_ID", "Not set")}')
logger.debug(f'SPOTIFY_CLIENT_SECRET: {"Present" if os.environ.get("SPOTIFY_CLIENT_SECRET") else "Not set"}')
logger.debug(f'SPOTIFY_REDIRECT_URI: {os.environ.get("SPOTIFY_REDIRECT_URI", "Not set")}')
logger.debug(f'SESSION_SECRET: {"Present" if os.environ.get("SESSION_SECRET") else "Not set"}')
logger.debug('==========================')

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# Create the app
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SESSION_SECRET", "dev-secret-key")
app.config["DEBUG"] = True  # Enable debug mode
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///spotify_clone.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Configure session for storing OAuth tokens
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False

# Initialize the app with the extension
db.init_app(app)

# Set Flask logger to DEBUG
app.logger.setLevel(logging.DEBUG)

# Import routes after app creation to avoid circular imports
with app.app_context():
    # Import models so their tables are created
    import models  # noqa: F401
    
    # Create all tables
    db.create_all()
    
    # Import and register routes
    import routes  # noqa: F401

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)  # Enable debug mode in run configuration
