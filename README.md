# Spotify AI Music Discovery Platform

An intelligent music discovery platform that uses AI to provide personalized music recommendations based on your Spotify listening habits.

## Features

- **Spotify Integration**: Connect with your Spotify account for seamless music control
- **AI-Powered Recommendations**: Get personalized song suggestions using Google Gemini AI
- **Music Taste Analysis**: Deep insights into your musical preferences and listening patterns
- **Interactive Feedback**: Help the AI learn your preferences through feedback
- **Playlist Creation**: Generate AI-curated playlists based on your taste
- **Real-time Playback Control**: Play, pause, and control music directly from the platform
- **🎯 Smart Music Recommendations**: AI analyzes your listening patterns to suggest perfect tracks
- **⚡ Lightning Mode**: Ultra-fast recommendations with advanced optimization
- **🎨 Psychological Music Profiling**: Deep insights into your musical personality  
- **🎼 AI Playlist Creation**: Generate curated playlists with custom themes
- **💬 Conversational Feedback**: Natural language interaction with your AI music assistant
- **📊 Performance Analytics**: Real-time metrics and optimization insights
- **🔄 Enhanced Duplicate Prevention**: Advanced tracking system prevents repetitive recommendations

## Tech Stack

- **Backend**: Flask (Python)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **AI**: Google Gemini 1.5 Flash
- **Authentication**: Spotify OAuth 2.0
- **Frontend**: HTML, CSS, JavaScript
- **Deployment**: Gunicorn WSGI server

## Environment Variables Required

```env
# Spotify API Credentials
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret

# Google AI
GOOGLE_API_KEY=your_google_gemini_api_key

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

### 5. Set Up Google AI
1. Go to [Google AI Studio](https://aistudio.google.com/)
2. Create an API key for Gemini
3. Add it to your environment variables

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

## Troubleshooting

### Spotify Playlist Creation Error (403 - Insufficient Client Scope)

If you encounter a "403 - Insufficient client scope" error when creating playlists, this is a known intermittent issue with Spotify's API. Here's how to resolve it:

#### Immediate Solutions:
1. **Re-authenticate**: Log out and log back in to refresh your Spotify permissions
2. **Wait and retry**: The issue often resolves itself within a few hours
3. **Check Spotify status**: This may be a temporary API issue on Spotify's side

#### For Developers:
- Ensure your app includes these scopes: `playlist-modify-public`, `playlist-modify-private`, `playlist-read-private`
- The error often occurs due to intermittent issues with Spotify's scope validation
- Monitor the logs for detailed error information

#### Why This Happens:
This is a known issue in Spotify's API that affects many developers. The problem is intermittent and typically resolves without any code changes required.

## Enhanced Recommendation Tracking System

### Intelligent Duplicate Prevention
Spotifai now features a sophisticated tracking system that prevents the AI from suggesting the same tracks repeatedly:

#### Key Features:
- **Time-based tracking**: Monitors recommendations over configurable time periods (24-72 hours)
- **Artist frequency analysis**: Prevents over-recommending the same artists
- **Cross-method tracking**: Considers recommendations from individual suggestions, playlists, and lightning mode
- **Smart validation**: Checks for exact duplicates and artist overuse before making suggestions
- **Enhanced prompts**: LLM receives detailed context about recent recommendations and diversity requirements

#### Database Enhancements:
- `session_adjustment`: Stores user's session-specific preferences
- `recommendation_method`: Tracks the source (standard, lightning, playlist)  
- `was_played`: Records if user actually played the recommendation
- `last_played_at` & `play_count`: Tracks engagement metrics
- Time-based queries with automatic cleanup

#### Benefits:
- **Better Discovery**: More diverse recommendations that avoid repetition
- **Improved User Experience**: Fresher suggestions that respect listening patterns
- **Smart Context**: AI understands what you've heard recently and adjusts accordingly
- **Artist Diversity**: Prevents over-recommending favorite artists while maintaining taste alignment 