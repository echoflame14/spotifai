"""
Routes package for Spotifai application.

This package contains all route handlers organized by functionality:
- auth: Authentication and OAuth routes
- dashboard: Main dashboard and music control
- ai: AI recommendations and analysis
- playlist: Playlist creation and management
- api: API endpoints
"""

from flask import Blueprint

# Import all route modules
from .auth import auth_bp
from .dashboard import dashboard_bp
from .ai import ai_bp
from .playlist import playlist_bp
from .api import api_bp

def register_routes(app):
    """Register all route blueprints with the Flask app"""
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(playlist_bp)
    app.register_blueprint(api_bp) 