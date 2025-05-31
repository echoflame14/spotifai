#!/usr/bin/env python3
"""
Database migration script to add enhanced recommendation tracking fields
"""

from app import app, db
from models import Recommendation
from sqlalchemy import text, inspect

def migrate_database():
    """Add new columns to the recommendation and user tables"""
    
    with app.app_context():
        print("Starting database migration...")
        
        # Check if we need to add the new columns to recommendation table
        try:
            # Check which columns exist in the recommendation table
            inspector = inspect(db.engine)
            existing_columns = [col['name'] for col in inspector.get_columns('recommendation')]
            
            required_columns = ['session_adjustment', 'recommendation_method', 'was_played', 'last_played_at', 'play_count']
            missing_columns = [col for col in required_columns if col not in existing_columns]
            
            if missing_columns:
                print(f'Missing recommendation columns: {missing_columns}')
                print('Adding missing columns to recommendation table...')
                
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
                        print(f'✓ Added {column_name} column to recommendation table')
                    except Exception as col_error:
                        print(f'⚠ Failed to add {column_name} column: {col_error}')
            else:
                print('✓ All required recommendation table columns already exist')
            
            # Check if we need to add the used_loading_phrases column to user table
            user_columns = [col['name'] for col in inspector.get_columns('user')]
            
            if 'used_loading_phrases' not in user_columns:
                print('Adding used_loading_phrases column to user table...')
                try:
                    sql = text('ALTER TABLE user ADD COLUMN used_loading_phrases TEXT')
                    with db.engine.connect() as connection:
                        connection.execute(sql)
                        connection.commit()
                    print('✓ Added used_loading_phrases column to user table')
                except Exception as col_error:
                    print(f'⚠ Failed to add used_loading_phrases column: {col_error}')
            else:
                print('✓ used_loading_phrases column already exists in user table')
            
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
        print("\nEnhanced features now available:")
        print("- Better duplicate prevention")
        print("- Artist frequency tracking")
        print("- Play history tracking")
        print("- Session-based recommendations")
        print("- Loading phrase repetition prevention")
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print("Please check your database connection and try again.") 