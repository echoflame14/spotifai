#!/usr/bin/env python3
"""
Database migration script to add enhanced recommendation tracking fields
"""

from app import app, db
from models import Recommendation
from sqlalchemy import text, inspect

def migrate_database():
    """Add new columns to the recommendation table"""
    
    with app.app_context():
        print("Starting database migration...")
        
        # Check if we need to add the new columns
        try:
            # Check which columns exist in the recommendation table
            inspector = inspect(db.engine)
            existing_columns = [col['name'] for col in inspector.get_columns('recommendation')]
            
            required_columns = ['session_adjustment', 'recommendation_method', 'was_played', 'last_played_at', 'play_count']
            missing_columns = [col for col in required_columns if col not in existing_columns]
            
            if not missing_columns:
                print('✓ All required database columns already exist - no migration needed')
                return True
            
            print(f'Missing columns: {missing_columns}')
            print('Adding missing columns to database...')
            
            # Add missing columns one by one
            column_definitions = {
                'session_adjustment': 'TEXT',
                'recommendation_method': 'VARCHAR(50)',
                'was_played': 'BOOLEAN DEFAULT 0',
                'last_played_at': 'DATETIME',
                'play_count': 'INTEGER DEFAULT 0'
            }
            
            for column_name in missing_columns:
                column_type = column_definitions[column_name]
                try:
                    sql = text(f'ALTER TABLE recommendation ADD COLUMN {column_name} {column_type}')
                    with db.engine.connect() as connection:
                        connection.execute(sql)
                        connection.commit()
                    print(f'✓ Added {column_name} column')
                except Exception as col_error:
                    print(f'⚠ Failed to add {column_name} column: {col_error}')
            
            print('✓ Database migration completed successfully')
            return True
            
        except Exception as e:
            print(f'Migration error: {e}')
            print('Attempting to recreate table schema...')
            
            try:
                # Force recreate all tables if migration fails
                db.drop_all()
                db.create_all()
                print('✓ Database schema recreated successfully')
                return True
            except Exception as recreate_error:
                print(f'Failed to recreate schema: {recreate_error}')
                return False

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