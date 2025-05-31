import json
import time
import logging
from typing import Dict, List, Any, Optional
from collections import Counter, defaultdict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ModelTierManager:
    """Manages different model tiers for optimal performance vs quality tradeoffs"""
    
    # Model tier definitions (fastest to most capable)
    LIGHTNING = 'gemini-1.5-flash'           # Lightning fast for ultra-simple tasks
    ULTRA_FAST = 'gemini-1.5-flash-8b'      # Ultra fast for simple tasks (8B model)
    FAST = 'gemini-2.0-flash-exp'           # Fast for standard tasks  
    BALANCED = 'gemini-2.5-flash-preview-05-20'  # Current model, balanced speed/quality
    PREMIUM = 'gemini-1.5-pro'              # High quality for complex analysis
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def get_model_for_task(self, task_type: str, user_preference: str = 'balanced') -> str:
        """Get optimal model for specific task type"""
        
        # Lightning tasks - ultra-simple pattern matching
        if task_type in ['instant_rec', 'pattern_match', 'quick_similarity']:
            return self.LIGHTNING
            
        # Ultra-fast tasks that don't require deep reasoning
        elif task_type in ['quick_analysis', 'genre_classification', 'mood_detection']:
            return self.ULTRA_FAST
            
        # Fast tasks that need some reasoning but not deep analysis
        elif task_type in ['recommendation_generation', 'track_similarity', 'basic_reasoning']:
            return self.FAST
            
        # Balanced tasks (default current behavior)
        elif task_type in ['full_recommendation', 'user_profiling']:
            return self.BALANCED
            
        # Premium tasks requiring deep analysis
        elif task_type in ['complex_analysis', 'psychological_profiling']:
            return self.PREMIUM
            
        # User preference override
        if user_preference == 'lightning':
            return self.LIGHTNING
        elif user_preference == 'speed':
            return self.FAST
        elif user_preference == 'quality':
            return self.PREMIUM
        else:
            return self.BALANCED

class SpotifyDataOptimizer:
    """Optimizes Spotify data for LLM processing by reducing token usage while preserving essential information"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def optimize_track_data(self, tracks: List[Dict], max_tracks: int = 30) -> List[Dict]:
        """Optimize track data by removing redundancy and keeping only essential fields"""
        if not tracks:
            return []
        
        # Remove duplicates based on track name + artist combination
        seen = set()
        unique_tracks = []
        
        for track in tracks[:max_tracks * 2]:  # Start with 2x to account for duplicates
            # Handle different track data structures
            if 'track' in track:  # Recently played format
                track_info = track['track']
            else:  # Top tracks format
                track_info = track
            
            # Create unique identifier
            track_id = f"{track_info['name'].lower()}||{track_info['artists'][0]['name'].lower()}"
            
            if track_id not in seen and len(unique_tracks) < max_tracks:
                seen.add(track_id)
                # Keep only essential fields
                optimized_track = {
                    'name': track_info['name'],
                    'artist': track_info['artists'][0]['name'],
                    'popularity': track_info.get('popularity', 0)
                }
                unique_tracks.append(optimized_track)
        
        return unique_tracks
    
    def optimize_artist_data(self, artists: List[Dict], max_artists: int = 15) -> List[Dict]:
        """Optimize artist data by keeping only essential fields and removing duplicates"""
        if not artists:
            return []
        
        seen = set()
        unique_artists = []
        
        for artist in artists[:max_artists * 2]:
            artist_name = artist['name'].lower()
            
            if artist_name not in seen and len(unique_artists) < max_artists:
                seen.add(artist_name)
                # Keep only essential fields
                optimized_artist = {
                    'name': artist['name'],
                    'genres': artist.get('genres', [])[:3],  # Limit to top 3 genres
                    'popularity': artist.get('popularity', 0)
                }
                unique_artists.append(optimized_artist)
        
        return unique_artists
    
    def extract_music_patterns(self, music_data: Dict) -> Dict[str, Any]:
        """Extract key patterns and insights from music data to reduce LLM processing"""
        patterns = {}
        
        # Genre analysis
        all_genres = []
        for artist_list in ['top_artists_last_month', 'top_artists_6_months', 'top_artists_all_time']:
            if artist_list in music_data:
                for artist in music_data[artist_list]:
                    all_genres.extend(artist.get('genres', []))
        
        genre_counts = Counter(all_genres)
        patterns['top_genres'] = dict(genre_counts.most_common(8))
        patterns['genre_diversity'] = len(set(all_genres))
        
        # Artist consistency analysis
        all_artists = []
        for track_list in ['recent_tracks', 'top_tracks_last_month', 'top_tracks_6_months', 'top_tracks_all_time']:
            if track_list in music_data:
                for track in music_data[track_list]:
                    all_artists.append(track['artist'])
        
        artist_counts = Counter(all_artists)
        patterns['favorite_artists'] = dict(artist_counts.most_common(10))
        patterns['artist_variety'] = len(set(all_artists))
        
        # Popularity patterns
        recent_popularities = [track.get('popularity', 0) for track in music_data.get('recent_tracks', [])]
        if recent_popularities:
            patterns['avg_popularity'] = sum(recent_popularities) / len(recent_popularities)
            patterns['mainstream_preference'] = patterns['avg_popularity'] > 60
        
        # Time-based evolution
        patterns['taste_evolution'] = self._analyze_taste_evolution(music_data)
        
        return patterns
    
    def _analyze_taste_evolution(self, music_data: Dict) -> Dict[str, Any]:
        """Analyze how music taste has evolved over time"""
        evolution = {}
        
        # Compare recent vs all-time artists
        recent_artists = set(track['artist'] for track in music_data.get('recent_tracks', []))
        alltime_artists = set(track['artist'] for track in music_data.get('top_tracks_all_time', []))
        
        evolution['consistency_score'] = len(recent_artists & alltime_artists) / max(len(alltime_artists), 1)
        evolution['exploring_new_artists'] = len(recent_artists - alltime_artists) > 5
        
        # Compare recent vs all-time genres
        recent_genres = set()
        for track in music_data.get('recent_tracks', []):
            # We'd need to map tracks to genres, simplified for now
            pass
        
        return evolution
    
    def create_optimized_music_summary(self, music_data: Dict) -> Dict[str, Any]:
        """Create a compact summary of music data optimized for LLM processing"""
        # Extract patterns first
        patterns = self.extract_music_patterns(music_data)
        
        # Create optimized summary
        summary = {
            'listening_summary': {
                'recent_track_count': len(music_data.get('recent_tracks', [])),
                'top_artists': list(patterns['favorite_artists'].keys())[:8],
                'dominant_genres': list(patterns['top_genres'].keys())[:6],
                'avg_popularity': round(patterns.get('avg_popularity', 50)),
                'taste_consistency': patterns['taste_evolution']['consistency_score']
            },
            'recent_favorites': music_data.get('recent_tracks', [])[:15],  # Most recent 15
            'core_preferences': {
                'top_tracks_sample': music_data.get('top_tracks_all_time', [])[:10],
                'genre_distribution': patterns['top_genres'],
                'mainstream_vs_niche': 'mainstream' if patterns.get('mainstream_preference', False) else 'eclectic'
            },
            'musical_evolution': patterns['taste_evolution'],
            'context': {
                'total_playlists': music_data.get('total_playlists', 0),
                'saved_tracks_count': len(music_data.get('saved_tracks', [])),
                'genre_diversity_score': patterns['genre_diversity'],
                'artist_variety_score': patterns['artist_variety']
            }
        }
        
        return summary

    def collect_optimized_spotify_data(self, spotify_client) -> Dict[str, Any]:
        """Collect optimized Spotify data with reduced API calls and data compression"""
        self.logger.info("Collecting optimized Spotify data...")
        
        try:
            # Collect only essential data with reduced limits
            self.logger.debug("Fetching recent tracks (30 instead of 150)...")
            recent_tracks = spotify_client.get_recently_played(limit=30) or {'items': []}
            
            self.logger.debug("Fetching top tracks for each time period (15 instead of 20)...")
            top_tracks_short = spotify_client.get_top_tracks(time_range='short_term', limit=15) or {'items': []}
            top_tracks_medium = spotify_client.get_top_tracks(time_range='medium_term', limit=15) or {'items': []}
            top_tracks_long = spotify_client.get_top_tracks(time_range='long_term', limit=15) or {'items': []}
            
            self.logger.debug("Fetching top artists for each time period (15 instead of 20)...")
            top_artists_short = spotify_client.get_top_artists(time_range='short_term', limit=15) or {'items': []}
            top_artists_medium = spotify_client.get_top_artists(time_range='medium_term', limit=15) or {'items': []}
            top_artists_long = spotify_client.get_top_artists(time_range='long_term', limit=15) or {'items': []}
            
            self.logger.debug("Fetching saved tracks (30 instead of 50)...")
            saved_tracks = spotify_client.get_saved_tracks(limit=30) or {'items': []}
            
            self.logger.debug("Fetching playlists (15 instead of 20)...")
            playlists = spotify_client.get_user_playlists(limit=15) or {'items': []}
            
            # Optimize the collected data using class methods
            optimized_data = {
                'recent_tracks': self.optimize_track_data(recent_tracks.get('items', []), max_tracks=20),
                'top_tracks_last_month': self.optimize_track_data(top_tracks_short.get('items', []), max_tracks=15),
                'top_tracks_6_months': self.optimize_track_data(top_tracks_medium.get('items', []), max_tracks=15),
                'top_tracks_all_time': self.optimize_track_data(top_tracks_long.get('items', []), max_tracks=15),
                'top_artists_last_month': self.optimize_artist_data(top_artists_short.get('items', []), max_artists=12),
                'top_artists_6_months': self.optimize_artist_data(top_artists_medium.get('items', []), max_artists=12),
                'top_artists_all_time': self.optimize_artist_data(top_artists_long.get('items', []), max_artists=12),
                'saved_tracks': self.optimize_track_data([item['track'] for item in saved_tracks.get('items', [])], max_tracks=20),
                'playlist_names': [playlist['name'] for playlist in playlists.get('items', []) if playlist.get('name')][:10],
                'total_playlists': len(playlists.get('items', []))
            }
            
            # Log optimization results
            original_size = (
                len(recent_tracks.get('items', [])) +
                len(top_tracks_short.get('items', [])) +
                len(top_tracks_medium.get('items', [])) +
                len(top_tracks_long.get('items', [])) +
                len(saved_tracks.get('items', []))
            )
            
            optimized_size = (
                len(optimized_data['recent_tracks']) +
                len(optimized_data['top_tracks_last_month']) +
                len(optimized_data['top_tracks_6_months']) +
                len(optimized_data['top_tracks_all_time']) +
                len(optimized_data['saved_tracks'])
            )
            
            compression_ratio = original_size / max(optimized_size, 1)
            
            self.logger.info(f"Data optimization complete: {original_size} -> {optimized_size} items ({compression_ratio:.2f}x compression)")
            
            return optimized_data
            
        except Exception as e:
            self.logger.error(f"Error collecting optimized Spotify data: {e}")
            # Return minimal data structure to prevent crashes
            return {
                'recent_tracks': [],
                'top_tracks_last_month': [],
                'top_tracks_6_months': [],
                'top_tracks_all_time': [],
                'top_artists_last_month': [],
                'top_artists_6_months': [],
                'top_artists_all_time': [],
                'saved_tracks': [],
                'playlist_names': [],
                'total_playlists': 0
            }


class HyperOptimizedLLMManager:
    """Ultra-fast LLM manager using tiered models for maximum performance"""
    
    def __init__(self, data_optimizer: SpotifyDataOptimizer):
        self.data_optimizer = data_optimizer
        self.model_tier_manager = ModelTierManager()
        self.logger = logging.getLogger(__name__)
        self.user_profile_cache = {}  # Cache user profiles
    
    def get_lightning_recommendation(self, music_data: Dict, gemini_api_key: str,
                                   session_adjustment: str = None, 
                                   recent_recommendations: List[str] = None,
                                   user_id: int = None) -> Dict[str, Any]:
        """Lightning-fast recommendation using cached profiles and fast AI model"""
        
        import google.generativeai as genai
        genai.configure(api_key=gemini_api_key)
        
        total_start = time.time()
        
        # Check if we have a cached profile for this user
        cached_profile = self.user_profile_cache.get(user_id) if user_id else None
        
        if cached_profile:
            self.logger.info("LIGHTNING MODE: Using cached user profile")
            user_profile = cached_profile
            profile_duration = 0.0
        else:
            # Quick profiling using fast model for speed
            self.logger.info("LIGHTNING MODE: Quick profile generation with fast model...")
            profile_start = time.time()
            
            # Use fast model for quick profiling
            fast_model = genai.GenerativeModel(self.model_tier_manager.FAST)
            
            # Enhanced summary with more context for better profiling
            top_artists = list(set([t['artist'] for t in music_data.get('recent_tracks', [])[:8]]))[:5]
            recent_tracks = [f"{t['name']} - {t['artist']}" for t in music_data.get('recent_tracks', [])[:5]]
            
            profile_prompt = f"""Analyze this user's music taste in 2-3 sentences with specific insights:

Recent listening: {', '.join(recent_tracks)}
Favorite artists: {', '.join(top_artists)}

Describe their musical preferences, mood patterns, and what type of songs they would love. Be specific about genres, energy levels, and emotional themes they prefer."""
            
            try:
                profile_response = fast_model.generate_content(profile_prompt)
                user_profile = profile_response.text.strip()
                # Cache the profile
                if user_id:
                    self.user_profile_cache[user_id] = user_profile
            except Exception as e:
                user_profile = f"User enjoys {', '.join(top_artists)} style music with diverse taste spanning multiple genres"
            
            profile_duration = time.time() - profile_start
        
        # Fast recommendation using optimized model for speed
        self.logger.info("LIGHTNING MODE: Fast recommendation generation...")
        rec_start = time.time()
        
        # Use fast model for speedy recommendations
        fast_model = genai.GenerativeModel(self.model_tier_manager.FAST)
        
        # Enhanced prompt for better recommendations
        avoid_part = f"\n\nRecently recommended (avoid these): {', '.join(recent_recommendations[:5])}" if recent_recommendations else ""
        session_part = f"\n\nCurrent mood/preference: {session_adjustment}" if session_adjustment else ""
        
        rec_prompt = f"""Based on this detailed user profile, recommend ONE perfect song:

USER MUSIC PROFILE:
{user_profile}

RECENT LISTENING CONTEXT:
{', '.join([f"{t['name']} by {t['artist']}" for t in music_data.get('recent_tracks', [])[:5]])}{session_part}{avoid_part}

Consider their established taste while suggesting something that will genuinely excite them. The song should be specific, real, and available on Spotify.

Respond with ONLY: "Song Title" by Artist Name"""
        
        rec_response = fast_model.generate_content(rec_prompt)
        recommendation = rec_response.text.strip()
        rec_duration = time.time() - rec_start
        
        total_duration = time.time() - total_start
        
        self.logger.info(f"FAST LIGHTNING COMPLETE: Total {total_duration:.2f}s (Profile: {profile_duration:.2f}s, Rec: {rec_duration:.2f}s)")
        
        return {
            'success': True,
            'recommendation': recommendation,
            'user_profile': user_profile,
            'stats': {
                'profile_duration': profile_duration,
                'rec_duration': rec_duration,
                'total_llm_duration': profile_duration + rec_duration,
                'models_used': [self.model_tier_manager.FAST],
                'approach': 'lightning_fast_quality',
                'cached_profile': cached_profile is not None
            }
        }
    
    def get_hyper_optimized_recommendation(self, music_data: Dict, gemini_api_key: str,
                                         session_adjustment: str = None, 
                                         recent_recommendations: List[str] = None,
                                         feedback_insights: List[Dict] = None,
                                         speed_preference: str = 'ultra_fast') -> Dict[str, Any]:
        """Get AI recommendation using hyper-optimized multi-tier approach"""
        
        import google.generativeai as genai
        genai.configure(api_key=gemini_api_key)
        
        total_start = time.time()
        
        # Step 1: Ultra-fast user profiling (2-3 seconds)
        self.logger.info("STEP 1: Ultra-fast user profiling...")
        profile_start = time.time()
        
        # Use ultra-fast model for quick analysis
        ultra_fast_model = genai.GenerativeModel(self.model_tier_manager.ULTRA_FAST)
        
        # Create micro-summary for profiling
        micro_summary = self._create_micro_summary(music_data)
        profile_prompt = self._build_profile_prompt(micro_summary)
        
        try:
            profile_response = ultra_fast_model.generate_content(profile_prompt)
            user_profile = profile_response.text.strip()
            profile_duration = time.time() - profile_start
            self.logger.info(f"User profiling complete: {profile_duration:.2f}s")
        except Exception as e:
            self.logger.warning(f"Ultra-fast profiling failed, using simplified profile: {e}")
            user_profile = self._create_fallback_profile(music_data)
            profile_duration = time.time() - profile_start
        
        # Step 2: Lightning-fast recommendation generation (1-2 seconds)
        self.logger.info("STEP 2: Lightning-fast recommendation generation...")
        rec_start = time.time()
        
        # Use fast model for recommendation
        fast_model = genai.GenerativeModel(self.model_tier_manager.FAST)
        
        # Build hyper-optimized recommendation prompt
        rec_prompt = self._build_hyper_optimized_rec_prompt(
            user_profile, micro_summary, session_adjustment, 
            recent_recommendations, feedback_insights
        )
        
        rec_response = fast_model.generate_content(rec_prompt)
        recommendation = rec_response.text.strip()
        rec_duration = time.time() - rec_start
        
        total_duration = time.time() - total_start
        
        self.logger.info(f"HYPER-OPTIMIZATION COMPLETE:")
        self.logger.info(f"  Profiling: {profile_duration:.2f}s")
        self.logger.info(f"  Recommendation: {rec_duration:.2f}s") 
        self.logger.info(f"  Total LLM Time: {total_duration:.2f}s")
        
        return {
            'recommendation': recommendation,
            'user_profile': user_profile,
            'optimization_stats': {
                'profile_duration': profile_duration,
                'rec_duration': rec_duration,
                'total_llm_duration': total_duration,
                'models_used': [self.model_tier_manager.ULTRA_FAST, self.model_tier_manager.FAST],
                'approach': 'hyper_optimized_multi_tier'
            }
        }
    
    def _create_micro_summary(self, music_data: Dict) -> Dict[str, Any]:
        """Create extremely compact summary for ultra-fast processing"""
        patterns = self.data_optimizer.extract_music_patterns(music_data)
        
        # Ultra-compact representation
        return {
            'top_artists': list(patterns['favorite_artists'].keys())[:5],
            'top_genres': list(patterns['top_genres'].keys())[:4],
            'recent_tracks': [f"{t['name']} - {t['artist']}" for t in music_data.get('recent_tracks', [])[:8]],
            'mainstream_score': patterns.get('avg_popularity', 50),
            'variety_score': patterns['artist_variety']
        }
    
    def _build_profile_prompt(self, micro_summary: Dict) -> str:
        """Build ultra-compact prompt for user profiling"""
        return f"""Analyze this music data in 3 sentences:

Recent: {', '.join(micro_summary['recent_tracks'])}
Artists: {', '.join(micro_summary['top_artists'])}
Genres: {', '.join(micro_summary['top_genres'])}
Mainstream score: {micro_summary['mainstream_score']}/100

Describe: 1) Musical taste type 2) Mood preference 3) Discovery style"""
    
    def _build_hyper_optimized_rec_prompt(self, user_profile: str, micro_summary: Dict,
                                        session_adjustment: str = None,
                                        recent_recommendations: List[str] = None,
                                        feedback_insights: List[Dict] = None) -> str:
        """Build ultra-optimized recommendation prompt"""
        
        session_part = f"\n🎯 SESSION MOOD: {session_adjustment}" if session_adjustment else ""
        avoid_part = f"\n❌ AVOID: {', '.join(recent_recommendations[:5])}" if recent_recommendations else ""
        
        return f"""🎵 USER: {user_profile}

🎶 RECENT FAVORITES: {', '.join(micro_summary['recent_tracks'])}
🎤 TOP ARTISTS: {', '.join(micro_summary['top_artists'])}
🎵 GENRES: {', '.join(micro_summary['top_genres'])}{session_part}{avoid_part}

Recommend ONE song: "Title" by Artist"""
    
    def _create_fallback_profile(self, music_data: Dict) -> str:
        """Create simple fallback profile if ultra-fast model fails"""
        patterns = self.data_optimizer.extract_music_patterns(music_data)
        top_genres = list(patterns['top_genres'].keys())[:3]
        mainstream = "mainstream" if patterns.get('avg_popularity', 50) > 60 else "indie"
        
        return f"User enjoys {', '.join(top_genres)} music with {mainstream} preferences. Moderate variety seeker."


class OptimizedLLMManager:
    """Optimized LLM manager that uses compressed data and efficient prompting"""
    
    def __init__(self, data_optimizer: SpotifyDataOptimizer):
        self.data_optimizer = data_optimizer
        self.logger = logging.getLogger(__name__)
    
    def get_optimized_recommendation(self, music_data: Dict, gemini_model, 
                                   session_adjustment: str = None, 
                                   recent_recommendations: List[str] = None,
                                   feedback_insights: List[Dict] = None) -> Dict[str, Any]:
        """Get AI recommendation using optimized single-call approach"""
        
        start_time = time.time()
        
        # Create optimized music summary
        self.logger.info("Creating optimized music summary...")
        music_summary = self.data_optimizer.create_optimized_music_summary(music_data)
        
        # Build compact, efficient prompt
        prompt = self._build_optimized_prompt(
            music_summary, session_adjustment, recent_recommendations, feedback_insights
        )
        
        prompt_size = len(prompt)
        self.logger.info(f"OPTIMIZED PROMPT SIZE: {prompt_size:,} characters (vs previous ~38K)")
        
        # Single LLM call for recommendation
        self.logger.info("Making single optimized LLM call...")
        llm_start = time.time()
        
        response = gemini_model.generate_content(prompt)
        
        llm_duration = time.time() - llm_start
        total_duration = time.time() - start_time
        
        self.logger.info(f"OPTIMIZED LLM COMPLETE - Duration: {llm_duration:.2f}s (Total: {total_duration:.2f}s)")
        
        return {
            'recommendation': response.text.strip(),
            'optimization_stats': {
                'prompt_size': prompt_size,
                'llm_duration': llm_duration,
                'total_duration': total_duration,
                'data_compression_ratio': prompt_size / 38000  # vs previous size
            }
        }
    
    def _build_optimized_prompt(self, music_summary: Dict, session_adjustment: str = None,
                              recent_recommendations: List[str] = None,
                              feedback_insights: List[Dict] = None) -> str:
        """Build an optimized, compact prompt for music recommendation"""
        
        # Session adjustment section
        session_section = ""
        if session_adjustment:
            session_section = f"\n🎯 SESSION PREFERENCE: {session_adjustment}\nPrioritize this preference while staying true to their established taste.\n"
        
        # Recent recommendations to avoid
        avoid_section = ""
        if recent_recommendations:
            avoid_section = f"\n❌ DO NOT RECOMMEND: {', '.join(recent_recommendations[:10])}\n"
        
        # Feedback insights (if available)
        feedback_section = ""
        if feedback_insights and len(feedback_insights) > 0:
            feedback_section = f"\n💭 PAST FEEDBACK: {json.dumps(feedback_insights[:3])}\n"
        
        prompt = f"""Recommend ONE song for this user based on their optimized music profile:{session_section}

🎵 LISTENING PROFILE:
• Recent listening: {music_summary['listening_summary']['recent_track_count']} tracks
• Core artists: {', '.join(music_summary['listening_summary']['top_artists'])}
• Dominant genres: {', '.join(music_summary['listening_summary']['dominant_genres'])}
• Popularity preference: {music_summary['listening_summary']['avg_popularity']}/100
• Taste consistency: {music_summary['listening_summary']['taste_consistency']:.2f}
• Style: {music_summary['core_preferences']['mainstream_vs_niche']}

🔥 RECENT FAVORITES (Last 15):
{json.dumps(music_summary['recent_favorites'])}

⭐ ALL-TIME CORE (Top 10):
{json.dumps(music_summary['core_preferences']['top_tracks_sample'])}

📊 MUSICAL DNA:
• Genres: {json.dumps(music_summary['core_preferences']['genre_distribution'])}
• Diversity score: {music_summary['context']['genre_diversity_score']} genres
• Artist variety: {music_summary['context']['artist_variety_score']} artists
• Evolution: {'Exploring new' if music_summary['musical_evolution']['exploring_new_artists'] else 'Consistent with favorites'}{feedback_section}{avoid_section}

🎯 TASK: Recommend ONE specific song that:
1. Matches their core taste but offers discovery potential
2. Fits their recent listening patterns and mood
3. Respects their mainstream/niche preference level
4. Is NOT in their recent history or previous recommendations

RESPOND WITH ONLY: "Song Title" by Artist Name"""
        
        return prompt


class DataCacheManager:
    """Manages caching of processed music data to avoid redundant API calls and processing"""
    
    def __init__(self, cache_duration_minutes: int = 10):
        self.cache = {}
        self.cache_timestamps = {}
        self.cache_duration = timedelta(minutes=cache_duration_minutes)
        self.logger = logging.getLogger(__name__)
    
    def get_cached_data(self, user_id: int, data_type: str) -> Optional[Dict]:
        """Get cached data if it's still valid"""
        cache_key = f"{user_id}_{data_type}"
        
        if cache_key in self.cache:
            if datetime.now() - self.cache_timestamps[cache_key] < self.cache_duration:
                self.logger.debug(f"Using cached {data_type} for user {user_id}")
                return self.cache[cache_key]
            else:
                # Cache expired, remove it
                del self.cache[cache_key]
                del self.cache_timestamps[cache_key]
        
        return None
    
    def cache_data(self, user_id: int, data_type: str, data: Dict):
        """Cache processed data"""
        cache_key = f"{user_id}_{data_type}"
        self.cache[cache_key] = data
        self.cache_timestamps[cache_key] = datetime.now()
        self.logger.debug(f"Cached {data_type} for user {user_id}")
    
    def clear_user_cache(self, user_id: int):
        """Clear all cache for a specific user"""
        keys_to_remove = [key for key in self.cache.keys() if key.startswith(f"{user_id}_")]
        for key in keys_to_remove:
            del self.cache[key]
            del self.cache_timestamps[key]
        self.logger.debug(f"Cleared cache for user {user_id}")
    
    def clear_expired_cache(self):
        """Clear all expired cache entries"""
        now = datetime.now()
        expired_keys = [
            key for key, timestamp in self.cache_timestamps.items()
            if now - timestamp >= self.cache_duration
        ]
        
        for key in expired_keys:
            del self.cache[key]
            del self.cache_timestamps[key]
        
        if expired_keys:
            self.logger.debug(f"Cleared {len(expired_keys)} expired cache entries")


# Global instances
data_optimizer = SpotifyDataOptimizer()
optimized_llm_manager = OptimizedLLMManager(data_optimizer)
hyper_optimized_llm_manager = HyperOptimizedLLMManager(data_optimizer)
cache_manager = DataCacheManager(cache_duration_minutes=15) 