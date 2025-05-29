from app import db
from datetime import datetime

class User(db.Model):
    id = db.Column(db.String(50), primary_key=True)  # Spotify user ID
    display_name = db.Column(db.String(100))
    email = db.Column(db.String(120))
    image_url = db.Column(db.String(255))
    access_token = db.Column(db.Text)
    refresh_token = db.Column(db.Text)
    token_expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<User {self.display_name}>'
    
    def is_token_expired(self):
        """Check if the access token has expired"""
        if not self.token_expires_at:
            return True
        return datetime.utcnow() >= self.token_expires_at
