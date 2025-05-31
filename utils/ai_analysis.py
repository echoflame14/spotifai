"""
AI Analysis utilities for music taste and recommendations.

This module handles all AI-powered analysis functionality using Gemini.
"""

import json
import time
import threading
import queue
from datetime import datetime
from flask import session
import google.generativeai as genai
import logging
from spotify_data_cleaner import extract_essential_music_context

logger = logging.getLogger(__name__)

def log_llm_timing(operation_name):
    """Decorator to log LLM operation timing"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            logger.info(f"LLM OPERATION START: {operation_name}")
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                logger.info(f"LLM OPERATION SUCCESS: {operation_name} - Duration: {duration:.2f}s")
                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.error(f"LLM OPERATION FAILED: {operation_name} - Duration: {duration:.2f}s - Error: {str(e)}")
                raise
        return wrapper
    return decorator

def configure_gemini(api_key):
    """Configure Gemini API with proper error handling"""
    try:
        # Clear any previous configuration
        try:
            genai.configure(api_key="")
        except:
            pass
        
        # Configure with new API key
        genai.configure(api_key=api_key)
        logger.info("Gemini API configured successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to configure Gemini API: {e}")
        return False

def check_rate_limit_error(error):
    """Check if an error is related to rate limiting"""
    error_str = str(error).lower()
    rate_limit_indicators = [
        'rate limit', 'quota', '429', 'too many requests', 'resource_exhausted'
    ]
    return any(indicator in error_str for indicator in rate_limit_indicators)

@log_llm_timing("psychological_analysis")
def generate_ultra_detailed_psychological_analysis(comprehensive_music_data, gemini_api_key):
    """Use Gemini 1.5 Flash to generate extremely comprehensive psychological and musical insights"""
    try:
        if not configure_gemini(gemini_api_key):
            return None
        
        # STEP 1: Clean the Spotify data using programmatic cleaning
        logger.info("STEP 1: Cleaning Spotify data with programmatic cleaner...")
        cleaned_data = extract_essential_music_context(comprehensive_music_data)
        
        if not cleaned_data:
            logger.error("Failed to clean Spotify data")
            return None
        
        logger.info("STEP 1 COMPLETE: Data programmatically cleaned and reduced for psychological analysis")
        
        # Use stable 1.5 Flash model
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            logger.info("Gemini 1.5 Flash model initialized successfully for psychological analysis")
        except Exception as model_error:
            logger.error(f"Failed to initialize Gemini model: {model_error}")
            return None
        
        # STEP 2: Generate psychological analysis using cleaned data
        logger.info("STEP 2: Generating psychological analysis with programmatically cleaned data...")
        
        prompt = create_psychological_analysis_prompt(cleaned_data)
        
        logger.info("Generating ultra-detailed psychological music analysis with Gemini 1.5 Flash...")
        start_time = time.time()
        
        try:
            # Use timeout for the API call
            result_queue = queue.Queue()
            
            def generate_with_timeout():
                try:
                    response = model.generate_content(prompt)
                    result_queue.put(('success', response))
                except Exception as e:
                    result_queue.put(('error', e))
            
            # Start generation in a separate thread
            thread = threading.Thread(target=generate_with_timeout)
            thread.daemon = True
            thread.start()
            
            # Wait for result with timeout
            thread.join(timeout=20)  # 20 second timeout
            
            if thread.is_alive():
                logger.warning("Psychological analysis timed out after 20 seconds")
                return None
            
            try:
                result_type, result = result_queue.get_nowait()
                if result_type == 'error':
                    raise result
                response = result
            except queue.Empty:
                logger.error("No result received from generation thread")
                return None
                
            duration = time.time() - start_time
            logger.info(f"Gemini API call completed in {duration:.2f}s")
            
        except Exception as api_error:
            duration = time.time() - start_time
            logger.error(f"Gemini API call failed after {duration:.2f}s: {api_error}")
            return None
        
        if response and response.text:
            return parse_psychological_analysis_response(response.text, duration)
        else:
            logger.warning("Empty response from ultra-detailed psychological analysis")
            return None
            
    except Exception as e:
        logger.error(f"Error in ultra-detailed psychological analysis: {e}", exc_info=True)
        return None

def create_psychological_analysis_prompt(cleaned_data):
    """Create comprehensive prompt for psychological analysis"""
    return f"""
You are an expert music psychologist and data analyst. Analyze this CLEANED and FOCUSED Spotify listening data to create a comprehensive psychological profile.

CLEANED LISTENING DATA (technical metadata programmatically removed):
{json.dumps(cleaned_data, indent=2)}

Create an extremely detailed psychological analysis covering ALL sections below. Be specific with examples from their actual listening data.

ANALYSIS REQUIREMENTS:

1. **CORE PSYCHOLOGICAL PROFILE**
   - Personality traits revealed through music choices
   - Emotional patterns and coping mechanisms
   - Cognitive preferences and thinking styles
   - Risk tolerance and openness to new experiences
   - Social vs. solitary listening patterns

2. **MUSICAL IDENTITY ANALYSIS**
   - Musical sophistication level and complexity preferences
   - Genre loyalty vs. exploration patterns
   - Artist discovery behavior and risk-taking
   - Mainstream vs. underground positioning
   - Cultural identity markers in music choices
   - Generational musical influences

3. **LISTENING BEHAVIOR PSYCHOLOGY**
   - Mood regulation patterns through music
   - Energy level management preferences
   - Concentration and focus music patterns
   - Social context preferences (party vs. personal)
   - Temporal listening habits and routines
   - Replay behavior and emotional attachment patterns

4. **GENRE EVOLUTION & GROWTH PATTERNS**
   - Musical journey and evolution over time
   - Comfort zone vs. exploration balance
   - Seasonal or cyclical preferences
   - Life event impact on musical taste
   - Prediction of future musical directions

5. **ARTIST RELATIONSHIP PATTERNS**
   - Loyalty vs. novelty-seeking balance
   - Fan behavior and dedication levels
   - Discovery pathway preferences
   - Artist popularity comfort zones
   - International vs. domestic preferences

6. **DEEP MUSICAL INSIGHTS**
   - Lyrical vs. instrumental preferences
   - Production style preferences
   - Era and vintage preferences
   - Technical complexity appreciation
   - Collaborative vs. solo artist preferences

7. **EMOTIONAL INTELLIGENCE MARKERS**
   - Emotional range in musical choices
   - Maturity indicators in taste evolution
   - Stress response musical patterns
   - Celebration and joy expression through music
   - Introspection and contemplation preferences

8. **PREDICTIVE BEHAVIORAL INSIGHTS**
   - Likely music discovery methods
   - Recommended genres for exploration
   - Optimal recommendation timing
   - Social sharing likelihood
   - Concert attendance probability

Respond with a detailed JSON object:
{{
    "psychological_profile": {{
        "core_personality": "[Detailed analysis of personality traits with specific examples from their data]",
        "emotional_patterns": "[Deep dive into emotional regulation and expression through music]",
        "cognitive_style": "[Analysis of thinking patterns revealed through musical choices]",
        "social_tendencies": "[Social vs. private listening patterns and implications]",
        "life_phase_indicators": "[What their music reveals about their current life stage]"
    }},
    "musical_identity": {{
        "sophistication_level": "[Assessment of musical knowledge and complexity appreciation]",
        "exploration_style": "[How they discover and adopt new music]",
        "cultural_positioning": "[Their place in musical culture and communities]",
        "authenticity_markers": "[What reveals their genuine vs. social music preferences]",
        "identity_evolution": "[How their musical identity has changed over time]"
    }},
    "listening_psychology": {{
        "mood_regulation": "[How they use music for emotional management]",
        "energy_management": "[Music choices for different energy states]",
        "focus_patterns": "[Music for concentration, work, relaxation]",
        "ritual_behaviors": "[Repeated listening patterns and their meanings]",
        "attachment_style": "[How they form emotional connections to music]"
    }},
    "growth_trajectory": {{
        "evolution_pattern": "[Their musical journey and development over time]",
        "future_predictions": "[Likely future musical directions based on patterns]",
        "exploration_readiness": "[How open they are to new musical experiences]",
        "influence_susceptibility": "[How external factors affect their musical choices]"
    }},
    "behavioral_insights": {{
        "recommendation_optimal_timing": "[Best times and contexts for music recommendations]",
        "discovery_preferences": "[How they prefer to find new music]",
        "social_sharing_likelihood": "[Probability and style of sharing music with others]",
        "purchase_behavior": "[Likelihood of buying music, merch, or concert tickets]",
        "playlist_creation_style": "[How they organize and curate their music]"
    }},
    "summary_insights": {{
        "key_findings": ["[5-7 most important insights about this user]"],
        "unique_traits": ["[3-5 things that make this user's taste unique]"],
        "recommendation_strategy": "[Optimal approach for recommending music to this user]",
        "psychological_type": "[Overall psychological archetype this user represents]"
    }},
    "analysis_confidence": {{
        "data_richness": "[Assessment of how much data was available for analysis]",
        "insight_confidence": "[Confidence level in the psychological insights]",
        "prediction_reliability": "[How reliable the behavioral predictions are]"
    }},
    "analysis_ready": true
}}

CRITICAL INSTRUCTIONS:
- Be extremely specific and use actual data points from their listening history
- Mention specific artists, genres, and patterns you observe
- Connect musical choices to psychological theories and behavioral science
- Provide actionable insights for music recommendations
- Be honest about data limitations and confidence levels
- Keep each section substantive (3-5 sentences minimum per field)
- Use psychological and musicological terminology appropriately
- Ground insights in the actual data provided, not generalizations
"""

def parse_psychological_analysis_response(response_text, duration):
    """Parse and validate the psychological analysis response"""
    try:
        # Clean the response text
        response_text = response_text.strip()
        
        # Remove markdown code blocks if present
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        elif response_text.startswith('```'):
            response_text = response_text[3:]
        
        # Additional cleaning - remove any extra whitespace and fix common JSON issues
        response_text = response_text.strip()
        
        # Find and extract complete JSON
        json_start = response_text.find('{')
        if json_start != -1:
            # Find the matching closing brace
            brace_count = 0
            json_end = -1
            for i, char in enumerate(response_text[json_start:], json_start):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = i + 1
                        break
            
            if json_end != -1:
                json_text = response_text[json_start:json_end]
                logger.info(f"Extracted JSON length: {len(json_text)} characters")
                
                # Additional JSON cleaning before parsing
                json_text = json_text.replace('\n', ' ').replace('\r', ' ')
                # Fix common JSON issues like trailing commas and unescaped quotes
                import re
                json_text = re.sub(r',\s*}', '}', json_text)  # Remove trailing commas
                json_text = re.sub(r',\s*]', ']', json_text)  # Remove trailing commas in arrays
                
                try:
                    insights_json = json.loads(json_text)
                    logger.info(f"Ultra-detailed psychological analysis generated successfully in {duration:.2f}s")
                    logger.info(f"Analysis includes {len(insights_json)} main sections with deep psychological insights")
                    return insights_json
                except json.JSONDecodeError as json_error:
                    logger.error(f"Failed to parse extracted JSON: {json_error}")
                    logger.error(f"JSON text (first 1000 chars): {json_text[:1000]}")
                    
                    # Try to fix specific JSON issues
                    try:
                        # Handle unescaped quotes in strings more aggressively
                        # Last resort: use regex to find and replace problematic quotes
                        fixed_json = re.sub(r'(?<!")([^"\\])"(?![",\]}])', r'\1\\"', json_text)
                        insights_json = json.loads(fixed_json)
                        logger.info("Successfully parsed JSON after fixing quotes")
                        return insights_json
                    except Exception as repair_error:
                        logger.warning(f"JSON repair attempts failed: {repair_error}, using fallback analysis")
                        # Return fallback response
                        return create_fallback_analysis()
        
        logger.error("Could not find complete JSON in response")
        return create_fallback_analysis()
        
    except Exception as parse_error:
        logger.error(f"Error parsing response: {parse_error}")
        return create_fallback_analysis()

def create_fallback_analysis():
    """Create fallback analysis when parsing fails"""
    return {
        "psychological_profile": {
            "core_personality": "Analysis completed but JSON parsing failed. User shows diverse musical taste with strong emotional connections.",
            "emotional_patterns": "Complex emotional regulation through music, mixing experimental and familiar elements.",
            "cognitive_style": "Open to new experiences while maintaining emotional anchors in familiar music.",
            "social_tendencies": "Balances mainstream and underground preferences.",
            "life_phase_indicators": "Active exploration phase with established core preferences."
        },
        "musical_identity": {
            "sophistication_level": "Shows appreciable musical knowledge and openness to variety.",
            "exploration_style": "Balanced approach between familiar favorites and new discoveries.",
            "cultural_positioning": "Engages with both popular and alternative musical cultures.",
            "authenticity_markers": "Personal music choices reflect genuine emotional connections.",
            "identity_evolution": "Continuous musical growth and taste development evident."
        },
        "listening_psychology": {
            "mood_regulation": "Uses music actively for emotional management and expression.",
            "energy_management": "Selects music appropriately for different energy states and activities.",
            "focus_patterns": "Music serves multiple functional purposes in daily life.",
            "ritual_behaviors": "Developed consistent patterns in music listening habits.",
            "attachment_style": "Forms meaningful connections with specific tracks and artists."
        },
        "growth_trajectory": {
            "evolution_pattern": "Shows evidence of musical taste evolution over time.",
            "future_predictions": "Likely to continue exploring within established preference framework.",
            "exploration_readiness": "Open to new musical experiences while maintaining core preferences.",
            "influence_susceptibility": "Balanced between personal taste and external musical influences."
        },
        "behavioral_insights": {
            "recommendation_optimal_timing": "Recommendations work best when aligned with current listening mood.",
            "discovery_preferences": "Prefers discovering music through personal exploration and trusted sources.",
            "social_sharing_likelihood": "Moderate likelihood of sharing music discoveries with others.",
            "purchase_behavior": "Shows engagement patterns suggesting music investment behavior.",
            "playlist_creation_style": "Likely creates playlists based on mood and activity contexts."
        },
        "summary_insights": {
            "key_findings": [
                "User demonstrates diverse musical taste with emotional depth",
                "Shows balance between exploration and familiarity in music choices",
                "Music serves multiple functional and emotional purposes",
                "Active engagement with both mainstream and alternative music",
                "Continuous evolution in musical preferences and discovery"
            ],
            "unique_traits": [
                "Balanced approach to musical exploration and familiarity",
                "Strong emotional connection to music choices",
                "Functional use of music for mood and energy regulation"
            ],
            "recommendation_strategy": "Focus on emotionally resonant tracks that balance familiar elements with new discoveries.",
            "psychological_type": "Emotionally-driven music explorer with balanced taste preferences."
        },
        "analysis_confidence": {
            "data_richness": "Sufficient data available for basic insights, though JSON parsing encountered issues.",
            "insight_confidence": "Medium confidence - based on fallback analysis due to parsing limitations.",
            "prediction_reliability": "Moderate reliability - general patterns observed but detailed analysis unavailable."
        },
        "analysis_ready": True,
        "parsing_issue": True,
        "fallback_used": True
    }

@log_llm_timing("musical_analysis")
def generate_ai_music_analysis(music_data, gemini_api_key):
    """Use Gemini AI to generate detailed music taste insights"""
    try:
        if not configure_gemini(gemini_api_key):
            return None
            
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
Analyze this user's comprehensive Spotify listening data and provide detailed musical expertise insights.

MUSIC DATA:
{json.dumps(music_data, indent=2)}

Respond ONLY with a JSON object in this exact format:
{{
    "genre_mastery": {{
        "primary_expertise": "[Detailed analysis of their main genre expertise and sophistication level. Include specific genres they've mastered and their depth of knowledge]"
    }},
    "artist_dynamics": {{
        "loyalty_patterns": "[Analysis of how they relate to artists - are they loyal fans or explorers? Do they follow artists' entire discographies or cherry-pick hits?]"
    }},
    "musical_sophistication": {{
        "technical_appreciation": "[Assessment of their ability to appreciate musical complexity, production quality, instrumentation, etc. Are they casual listeners or do they notice technical details?]"
    }},
    "listening_contexts": {{
        "primary_contexts": "[Analysis of when and how they listen to music - for focus, energy, mood regulation, social settings, etc.]"
    }},
    "insights_summary": {{
        "unique_taste_markers": [
            "[First unique aspect of their musical taste]",
            "[Second unique aspect of their musical taste]",
            "[Third unique aspect of their musical taste]",
            "[Fourth unique aspect of their musical taste]",
            "[Fifth unique aspect of their musical taste]"
        ]
    }},
    "analysis_ready": true
}}

Guidelines:
- Be specific and use actual data from their listening history
- Mention specific artists, genres, and patterns you observe
- Each section should be 2-3 detailed sentences
- Focus on musical expertise and sophistication rather than personality
- Use technical music terms appropriately
- Be insightful about their musical journey and evolution
- The unique_taste_markers should be specific, actionable insights
"""
        
        logger.info("Generating AI music taste analysis...")
        
        try:
            response = model.generate_content(prompt)
            
            if response and response.text:
                # Parse the JSON response
                import re
                
                # Extract JSON from the response
                json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
                if json_match:
                    insights_json = json.loads(json_match.group())
                    logger.info("AI music analysis generated successfully")
                    return insights_json
                else:
                    logger.warning("Could not extract JSON from AI response")
                    return None
            else:
                logger.warning("Empty response from AI music analysis")
                return None
        
        except Exception as api_error:
            # Check for rate limit errors
            if check_rate_limit_error(api_error):
                logger.warning(f"Musical analysis hit Gemini rate limit: {str(api_error)}")
                # Re-raise the error so it can be handled by the calling function
                raise api_error
            else:
                logger.error(f"Musical analysis API error: {str(api_error)}")
                return None
            
    except Exception as e:
        logger.error(f"Error in AI music analysis: {e}")
        # Re-raise rate limit errors, return None for other errors
        if check_rate_limit_error(e):
            raise e
        return None

def generate_basic_insights(spotify_client):
    """Generate basic insights without AI analysis"""
    try:
        # Get basic music data
        recent_tracks = spotify_client.get_recently_played(limit=20) or {'items': []}
        top_artists_short = spotify_client.get_top_artists(time_range='short_term', limit=10) or {'items': []}
        
        # Extract basic stats
        recent_track_count = len(recent_tracks.get('items', []))
        top_artists_count = len(top_artists_short.get('items', []))
        
        # Extract top genres from artists
        genres = set()
        for artist in top_artists_short.get('items', [])[:5]:
            genres.update(artist.get('genres', []))
        
        # Get top artists names
        top_artist_names = [artist['name'] for artist in top_artists_short.get('items', [])[:3]]
        
        # Get recent track info
        recent_track_names = [item['track']['name'] for item in recent_tracks.get('items', [])[:3]]
        
        return {
            'recent_tracks': {
                'count': recent_track_count,
                'examples': recent_track_names,
                'description': f"Analyzed {recent_track_count} recent listening sessions"
            },
            'top_artists': {
                'count': top_artists_count,
                'examples': top_artist_names,
                'description': f"Identified {len(top_artist_names)} core artists in your rotation"
            },
            'genres': {
                'count': len(genres),
                'examples': list(genres)[:3],
                'description': f"Discovered {len(genres)} distinct musical genres in your taste"
            },
            'analysis_ready': False
        }
    except Exception as e:
        logger.error(f"Error generating basic insights: {e}")
        return {
            'recent_tracks': {
                'count': 0,
                'examples': [],
                'description': "Analyzing your listening patterns..."
            },
            'top_artists': {
                'count': 0,
                'examples': [],
                'description': "Understanding your artist preferences..."
            },
            'genres': {
                'count': 0,
                'examples': [],
                'description': "Mapping your musical landscape..."
            },
            'analysis_ready': False
        } 