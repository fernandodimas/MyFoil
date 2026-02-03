
print("DEBUG: Starting script...")
import os
import sys
import logging

# Force stdout flushing
sys.stdout.reconfigure(line_buffering=True)

print("DEBUG: Importing app...")
from app import app, db
print("DEBUG: App imported.")

from auth import create_or_update_user, User
print("DEBUG: Auth imported.")

# Configure logging to stdout
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

def test_create_admin():
    print("DEBUG: Entering test function...")
    with app.app_context():
        try:
            # Check existing users
            print("DEBUG: Querying existing users...")
            count = User.query.count()
            print(f"Existing users: {count}")
            
            # Try to create 'admin' user
            username = "admin"
            password = "password123"
            
            print(f"Creating user {username}...")
            create_or_update_user(username, password, admin_access=True, shop_access=True, backup_access=True)
            
            user = User.query.filter_by(user=username).first()
            if user:
                print(f"SUCCESS: User {user.user} created with ID {user.id}")
                print(f"Admin Access: {user.admin_access}")
                print(f"Password Hash: {user.password[:20]}...")
            else:
                print("FAILURE: User not found after creation attempt.")
                
        except Exception as e:
            print(f"ERROR: Failed to create user. Exception: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_create_admin()
