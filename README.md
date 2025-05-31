# Spotify AI Music Discovery Platform

An intelligent music discovery platform that uses AI to provide personalized music recommendations based on your Spotify listening habits.

## Features

- **Spotify Integration**: Connect with your Spotify account for seamless music control
- **AI-Powered Recommendations**: Get personalized song suggestions using Google Gemini AI
- **Music Taste Analysis**: Deep insights into your musical preferences and listening patterns
- **Interactive Feedback**: Help the AI learn your preferences through feedback
- **Playlist Creation**: Generate AI-curated playlists based on your taste
- **Real-time Playback Control**: Play, pause, and control music directly from the platform

## Tech Stack

- **Backend**: Flask (Python)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **AI**: Google Gemini 1.5 Flash (user-provided API key)
- **Authentication**: Spotify OAuth 2.0
- **Frontend**: HTML, CSS, JavaScript
- **Deployment**: Gunicorn WSGI server

## Environment Variables Required

```env
# Spotify API Credentials
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret

# Database
DATABASE_URL=postgresql://username:password@host:port/database

# Security
SESSION_SECRET=your_random_session_secret
```

## Setup Instructions

### 1. Clone the Repository
```bash
git clone https://github.com/echoflame14/spotifai.git
cd spotifai
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Set Environment Variables
Create a `.env` file with the required environment variables (see `.env.example`).

### 4. Set Up Spotify App
1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Add redirect URI: `http://localhost:5000/callback` (for local) or your production URL
4. Copy Client ID and Client Secret to your environment variables

### 5. Get Your Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com/)
2. Create an API key for Gemini
3. Add your API key in the app's AI Settings section after logging in

### 6. Run the Application
```bash
python main.py
```

## Deployment

This application is optimized for deployment on various platforms:

### Replit Deployment
- Configure environment variables in Replit Secrets
- The app will automatically deploy with the included configuration

### Other Platforms (Heroku, Railway, etc.)
- Ensure environment variables are properly configured
- The app uses Gunicorn for production-ready deployment
- PostgreSQL database required

## File Structure

```
├── app.py              # Flask app initialization
├── main.py             # Application entry point
├── models.py           # Database models
├── routes.py           # Application routes and logic
├── spotify_client.py   # Spotify API client
├── static/             # Static assets (CSS, JS, images)
├── templates/          # HTML templates
└── requirements.txt    # Python dependencies
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is open source and available under the MIT License. 