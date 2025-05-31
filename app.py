import os
import logging
from dotenv import load_dotenv
from flask import Flask
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import timedelta

# Load environment variables from .env file
load_dotenv()

# Set up logging for debugging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///spotify_clone.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Configure session for Railway production environment
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)

# Production session cookie settings for Railway
if 'railway.app' in os.environ.get('RAILWAY_PUBLIC_DOMAIN', ''):
    # Production settings for Railway
    app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS only
    app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent XSS
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Allow cross-site for OAuth
    app.config['SESSION_COOKIE_DOMAIN'] = None  # Auto-detect domain
    app.logger.info("Configured session for Railway production environment")
else:
    # Development settings
    app.config['SESSION_COOKIE_SECURE'] = False  # Allow HTTP in dev
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.logger.info("Configured session for development environment")

# Import models and initialize the db
from models import db

# Initialize the app with the extension
db.init_app(app)

# Import models explicitly so they're available for routes
import models  # noqa: F401

# Create tables
with app.app_context():
    db.create_all()

# Import and register modular routes
from routes import register_routes
register_routes(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
