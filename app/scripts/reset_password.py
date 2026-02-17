
import sys
import os
import argparse
import logging

# Add parent directory to path so we can import app modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

import app
from db import db
from auth import create_or_update_user, User

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def reset_password(username, password):
    """Reset password for a given user."""
    logger.info(f"Attempting to reset password for user: {username}")
    
    with app.create_app().app_context():
        try:
            # Check if user exists
            user_obj = User.query.filter_by(user=username).first()
            if not user_obj:
                logger.warning(f"User '{username}' not found. Creating new user.")
            
            # Update/Create user
            # Preserve existing permissions if user exists, otherwise default to False (safe)
            # Or should we default to Admin if creating? Let's assume Admin for recovery script.
            admin = user_obj.admin_access if user_obj else True
            shop = user_obj.shop_access if user_obj else True
            backup = user_obj.backup_access if user_obj else True
            
            create_or_update_user(
                username=username, 
                password=password, 
                admin_access=admin, 
                shop_access=shop, 
                backup_access=backup
            )
            
            logger.info("Password updated successfully.")
            return True
            
        except Exception as e:
            logger.error(f"Failed to reset password: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description="Reset user password")
    parser.add_argument("username", help="Username to reset")
    parser.add_argument("password", help="New password")
    
    args = parser.parse_args()
    
    if reset_password(args.username, args.password):
        print("SUCCESS")
        sys.exit(0)
    else:
        print("FAILURE")
        sys.exit(1)

if __name__ == "__main__":
    main()
