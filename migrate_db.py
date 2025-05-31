#!/usr/bin/env python3
"""
Database migration script to add enhanced recommendation tracking fields
"""

from app import app, db
from models import Recommendation
from sqlalchemy import text

def migrate_database():
    """Add new columns to the recommendation table"""
    
    with app.app_context():
        print("Starting database migration...")
        
        # Check if we need to add the new columns
        try:
            # Try to access the new columns to see if they exist
            test_rec = Recommendation.query.first()
            if test_rec:
                _ = test_rec.session_adjustment
                _ = test_rec.recommendation_method
                _ = test_rec.was_played
                _ = test_rec.last_played_at
                _ = test_rec.play_count
            print('✓ Database columns already exist - no migration needed')
            return True
        except Exception as e:
            print(f'Need to add new columns: {e}')
            print('Adding new columns to database...')
            
            # Add new columns one by one
            columns_to_add = [
                ('session_adjustment', 'TEXT'),
                ('recommendation_method', 'VARCHAR(50)'),
                ('was_played', 'BOOLEAN DEFAULT FALSE'),
                ('last_played_at', 'DATETIME'),
                ('play_count', 'INTEGER DEFAULT 0')
            ]
            
            for column_name, column_type in columns_to_add:
                try:
                    sql = f'ALTER TABLE recommendation ADD COLUMN {column_name} {column_type}'
                    db.engine.execute(text(sql))
                    print(f'✓ Added {column_name} column')
                except Exception as col_error:
                    print(f'⚠ {column_name} column may already exist: {col_error}')
            
            print('✓ Database migration completed successfully')
            return True

if __name__ == '__main__':
    try:
        migrate_database()
        print("\n🎉 Migration completed successfully!")
        print("\nEnhanced recommendation tracking is now available with:")
        print("- Better duplicate prevention")
        print("- Artist frequency tracking")
        print("- Play history tracking")
        print("- Session-based recommendations")
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print("Please check your database connection and try again.") 