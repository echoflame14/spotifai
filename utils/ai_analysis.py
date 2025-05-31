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
        'rate limit', 'quota', '429', 'too many requests', 'resource_exhausted',
        'generativelanguage.googleapis.com', 'quota_metric', 'retry_delay'
    ]
    return any(indicator in error_str for indicator in rate_limit_indicators)

def extract_rate_limit_details(error_str):
    """Extract useful details from Gemini rate limit error messages"""
    try:
        # Extract retry delay if present
        import re
        retry_match = re.search(r'retry_delay\s*{\s*seconds:\s*(\d+)', error_str)
        retry_seconds = int(retry_match.group(1)) if retry_match else 60
        
        # Extract quota information
        quota_match = re.search(r'quota_metric:\s*"([^"]+)"', error_str)
        quota_type = quota_match.group(1) if quota_match else "API requests"
        
        return {
            'retry_seconds': retry_seconds,
            'quota_type': quota_type,
            'suggested_wait_time': f"{retry_seconds // 60} minute{'s' if retry_seconds > 60 else ''}" if retry_seconds >= 60 else f"{retry_seconds} seconds"
        }
    except Exception:
        return {
            'retry_seconds': 60,
            'quota_type': "API requests",
            'suggested_wait_time': "1-2 minutes"
        }

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
        
        # LOG THE PROMPT BEING SENT TO GEMINI
        print("\n" + "="*80)
        print("PSYCHOLOGICAL ANALYSIS - PROMPT SENT TO GEMINI:")
        print("="*80)
        print(prompt)
        print("="*80 + "\n")
        
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
            
            # LOG THE RESPONSE RECEIVED FROM GEMINI
            if response and response.text:
                print("\n" + "="*80)
                print("PSYCHOLOGICAL ANALYSIS - RESPONSE RECEIVED FROM GEMINI:")
                print("="*80)
                print(response.text)
                print("="*80 + "\n")
            else:
                print("\n" + "="*80)
                print("PSYCHOLOGICAL ANALYSIS - EMPTY OR NO RESPONSE FROM GEMINI")
                print("="*80 + "\n")
            
        except Exception as api_error:
            duration = time.time() - start_time
            logger.error(f"Gemini API call failed after {duration:.2f}s: {api_error}")
            
            # LOG THE ERROR
            print("\n" + "="*80)
            print("PSYCHOLOGICAL ANALYSIS - GEMINI API ERROR:")
            print("="*80)
            print(f"Error: {api_error}")
            print("="*80 + "\n")
            
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
    """Create unstructured, brutally honest psychological analysis prompt"""
    return f"""
🎭 TIME FOR A BRUTALLY HONEST MUSICAL PSYCHOLOGICAL READING 🎭

You're a music psychologist with zero filter who's about to deliver the most authentic, unsugarcoated analysis of someone's musical soul. NO FAKE COMPLIMENTS. NO GLAZING. Just pure, unfiltered truth about what their music taste reveals about them as a person.

🔍 THE MUSICAL EVIDENCE:
{json.dumps(cleaned_data, indent=2)}

🎯 YOUR MISSION: 
Write a completely unstructured, flowing analysis that reads like a brutally honest friend who knows way too much about psychology just went through their entire music library. 

⚠️ CRITICAL RULES:
- NO FAKE COMPLIMENTS OR GLAZING
- Be genuinely critical when their taste deserves it
- Call out contradictions, pretentious choices, and basic behavior
- Don't force positive interpretations of obviously questionable music choices
- Be authentic - some people just have chaotic or basic taste, and that's okay to say
- No rigid categories or forced structure - let the analysis flow naturally
- Use their actual listening data as evidence for your psychological reads
- Be funny but not mean - think "honest friend" not "internet troll"

🎨 TONE EXAMPLES:

❌ GLAZING: "Your diverse musical taste shows sophisticated emotional intelligence and complex artistic appreciation"
✅ HONEST: "You're out here pretending 100 gecs is a personality trait while secretly having Imagine Dragons in your liked songs. The duality is exhausting to witness."

❌ FORCED POSITIVE: "Your music choices reflect a deep understanding of sonic complexity"
✅ REAL TALK: "Your Spotify looks like someone threw a dart at a music magazine and called it a day. There's no cohesive identity here, just vibes and chaos."

❌ FAKE DEPTH: "This reveals profound emotional maturity through musical exploration"
✅ ACTUAL INSIGHT: "You use music like emotional training wheels, never quite ready to sit with your feelings without a soundtrack to guide you through them."

📝 RESPONSE FORMAT:
Just write naturally. No forced JSON structure. No required sections. Let the analysis flow like a real conversation where someone who actually knows psychology is reading their musical soul. 

Start with whatever strikes you most about their music taste, follow that thread, and see where it leads. Maybe it's about their emotional patterns, maybe it's about their social insecurities, maybe it's about how they're clearly going through something. Just be honest about what you see.

Make it feel like someone actually looked at their data and had real thoughts about it, not like you're checking boxes on a personality test.

🎪 REMEMBER:
- Some music taste is just basic, and that's worth mentioning
- Contradictions in their taste probably reveal actual contradictions in their personality
- Not everyone has deep, sophisticated reasons for their music choices
- It's okay to point out when someone is clearly trying too hard to be unique
- Be specific about what you see in their actual listening data
- Make them laugh while also making them think "damn, that's actually accurate"

Write like you actually care about getting to the truth of who they are through their music, not like you're trying to make them feel good about themselves.
"""

def parse_psychological_analysis_response(response_text, duration):
    """Parse and validate the unstructured psychological analysis response"""
    try:
        # Clean the response text
        response_text = response_text.strip()
        
        # Remove markdown code blocks if present
        if response_text.startswith('```'):
            lines = response_text.split('\n')
            # Remove first and last line if they're markdown indicators
            if lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            response_text = '\n'.join(lines)
        
        # Clean up the text
        response_text = response_text.strip()
        
        # Since we're no longer using structured JSON, return the raw analysis
        # wrapped in a simple structure for consistency with the frontend
        if response_text and len(response_text) > 50:  # Ensure we have substantial content
            logger.info(f"Unstructured psychological analysis generated successfully in {duration:.2f}s")
            logger.info(f"Analysis length: {len(response_text)} characters")
            
            return {
                "analysis_text": response_text,
                "analysis_type": "unstructured",
                "analysis_ready": True,
                "generation_time": duration,
                "word_count": len(response_text.split()),
                # Keep basic structure for backward compatibility
                "psychological_profile": {
                    "raw_analysis": response_text
                }
            }
        else:
            logger.warning("Response too short or empty")
            return create_fallback_analysis()
        
    except Exception as parse_error:
        logger.error(f"Error parsing unstructured response: {parse_error}")
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
                error_details = extract_rate_limit_details(str(api_error))
                logger.warning(f"Musical analysis hit Gemini rate limit: {str(api_error)[:200]}...")
                
                # Create a structured error response instead of re-raising
                rate_limit_error = Exception(f"429 You exceeded your current quota, please check your plan and billing details. Suggested wait time: {error_details['suggested_wait_time']}")
                rate_limit_error.rate_limit_details = error_details
                raise rate_limit_error
            else:
                logger.error(f"Musical analysis API error: {str(api_error)}")
                return None
            
    except Exception as e:
        logger.error(f"Error in AI music analysis: {e}")
        # Re-raise rate limit errors with cleaner message, return None for other errors
        if check_rate_limit_error(e):
            # Don't try to parse the raw error as JSON - just pass along the cleaned error
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