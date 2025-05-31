#!/usr/bin/env python3
"""
Database migration script for enhanced recommendations
Adds new fields to support the enhanced recommendation system with audio features and quality metrics.
"""

import os
import sys
from datetime import datetime

# Add the project directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import Recommendation, UserAnalysis
from sqlalchemy import text

def migrate_database():
    """Migrate database to support enhanced recommendations"""
    
    print("🔄 Starting enhanced recommendations database migration...")
    
    with app.app_context():
        try:
            # Check if we need to add new columns
            print("📊 Checking database schema...")
            
            # Check Recommendation table
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            
            # Get current columns for Recommendation table
            recommendation_columns = [col['name'] for col in inspector.get_columns('recommendation')]
            print(f"Current recommendation columns: {recommendation_columns}")
            
            # Add missing columns to Recommendation table
            if 'confidence_score' not in recommendation_columns:
                print("➕ Adding confidence_score column to Recommendation table...")
                try:
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE recommendation ADD COLUMN confidence_score FLOAT'))
                        conn.commit()
                except Exception as e:
                    print(f"Error adding confidence_score: {e}")
                    # Try with different syntax for SQLite
                    try:
                        with db.engine.connect() as conn:
                            conn.execute(text('ALTER TABLE recommendation ADD confidence_score REAL'))
                            conn.commit()
                    except Exception as e2:
                        print(f"Second attempt failed: {e2}")
                        raise e2
            
            if 'match_score' not in recommendation_columns:
                print("➕ Adding match_score column to Recommendation table...")
                try:
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE recommendation ADD COLUMN match_score FLOAT'))
                        conn.commit()
                except Exception as e:
                    print(f"Error adding match_score: {e}")
                    # Try with different syntax for SQLite
                    try:
                        with db.engine.connect() as conn:
                            conn.execute(text('ALTER TABLE recommendation ADD match_score REAL'))
                            conn.commit()
                    except Exception as e2:
                        print(f"Second attempt failed: {e2}")
                        raise e2
            
            # Check UserAnalysis table
            if 'user_analysis' in inspector.get_table_names():
                analysis_columns = [col['name'] for col in inspector.get_columns('user_analysis')]
                print(f"Current user_analysis columns: {analysis_columns}")
                
                if 'analysis_ready' not in analysis_columns:
                    print("➕ Adding analysis_ready column to UserAnalysis table...")
                    try:
                        with db.engine.connect() as conn:
                            conn.execute(text('ALTER TABLE user_analysis ADD COLUMN analysis_ready BOOLEAN DEFAULT 0'))
                            conn.commit()
                    except Exception as e:
                        print(f"Error adding analysis_ready: {e}")
                        # Try with different syntax for SQLite
                        try:
                            with db.engine.connect() as conn:
                                conn.execute(text('ALTER TABLE user_analysis ADD analysis_ready INTEGER DEFAULT 0'))
                                conn.commit()
                        except Exception as e2:
                            print(f"Second attempt failed: {e2}")
                            raise e2
            else:
                print("📋 UserAnalysis table not found - will be created on first use")
            
            print("✅ Database migration completed successfully!")
            print("\n📈 Enhanced recommendation features now available:")
            print("   • Audio features analysis for recommendations")
            print("   • Confidence and match scoring")
            print("   • Enhanced psychological profiling")
            print("   • Comprehensive listening pattern analysis")
            print("   • Up to 50 recent tracks analysis (vs 20 previously)")
            print("   • Multi-timeframe top artists/tracks analysis")
            print("   • Playlist and library context awareness")
            
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    return True

def verify_migration():
    """Verify that the migration was successful"""
    
    print("\n🔍 Verifying migration...")
    
    with app.app_context():
        try:
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            
            # Check Recommendation table
            recommendation_columns = [col['name'] for col in inspector.get_columns('recommendation')]
            required_rec_columns = ['confidence_score', 'match_score']
            
            missing_rec_columns = [col for col in required_rec_columns if col not in recommendation_columns]
            if missing_rec_columns:
                print(f"❌ Missing columns in Recommendation table: {missing_rec_columns}")
                return False
            else:
                print(f"✅ All required Recommendation columns present: {required_rec_columns}")
            
            # Check UserAnalysis table if it exists
            if 'user_analysis' in inspector.get_table_names():
                analysis_columns = [col['name'] for col in inspector.get_columns('user_analysis')]
                if 'analysis_ready' not in analysis_columns:
                    print("❌ Missing analysis_ready column in UserAnalysis table")
                    return False
                else:
                    print("✅ UserAnalysis analysis_ready column present")
            else:
                print("📋 UserAnalysis table will be created on first use")
            
            print("✅ Migration verification successful!")
            
            return True
            
        except Exception as e:
            print(f"❌ Verification failed: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    print("Enhanced Recommendations Database Migration")
    print("="*50)
    
    # Run migration
    if migrate_database():
        # Verify migration
        if verify_migration():
            print("\n🎉 Enhanced recommendations are ready to use!")
            print("\nKey improvements:")
            print("• 2.5x more recent tracks analyzed (50 vs 20)")
            print("• Audio features analysis for deeper insights")
            print("• Confidence scoring for recommendation quality")
            print("• Enhanced psychological profiling")
            print("• Multi-timeframe artist/track analysis")
            print("• Comprehensive listening behavior analysis")
        else:
            print("\n⚠️  Migration completed but verification failed")
            sys.exit(1)
    else:
        print("\n❌ Migration failed")
        sys.exit(1) 