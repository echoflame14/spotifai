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
    
    # Relationships
    recommendations = db.relationship('Recommendation', backref='user', lazy=True)
    feedback_entries = db.relationship('UserFeedback', backref='user', lazy=True)
    
    def __repr__(self):
        return f'<User {self.display_name}>'
    
    def is_token_expired(self):
        """Check if the access token has expired"""
        if not self.token_expires_at:
            return True
        return datetime.utcnow() >= self.token_expires_at


class Recommendation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), db.ForeignKey('user.id'), nullable=False)
    track_name = db.Column(db.String(255), nullable=False)
    artist_name = db.Column(db.String(255), nullable=False)
    track_uri = db.Column(db.String(255), nullable=False)
    album_name = db.Column(db.String(255))
    ai_reasoning = db.Column(db.Text)
    psychological_analysis = db.Column(db.Text)
    listening_data_snapshot = db.Column(db.Text)  # JSON of user data at recommendation time
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Feedback relationship
    feedback_entries = db.relationship('UserFeedback', backref='recommendation', lazy=True)

    def __repr__(self):
        return f'<Recommendation {self.track_name} by {self.artist_name}>'


class UserFeedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), db.ForeignKey('user.id'), nullable=False)
    recommendation_id = db.Column(db.Integer, db.ForeignKey('recommendation.id'), nullable=False)
    feedback_text = db.Column(db.Text, nullable=False)
    sentiment = db.Column(db.String(20))  # positive, negative, neutral
    ai_processed_feedback = db.Column(db.Text)  # AI analysis of the feedback
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<UserFeedback {self.id}: {self.sentiment}>'
