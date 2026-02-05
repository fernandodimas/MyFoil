from flask import Blueprint, render_template, redirect, url_for, request, jsonify
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from db import *
from flask_login import LoginManager
from utils import sanitize_sensitive_data
from constants import BUILD_VERSION

import logging

# Retrieve main logger
logger = logging.getLogger('main')

def admin_account_created():
    return len(User.query.filter_by(admin_access=True).all())

def unauthorized_json():
    response = login_manager.unauthorized()
    resp = {
        'success': False,
        'status_code': response.status_code,
        'location': response.location
    }
    return jsonify(resp)

def access_required(access: str):
    def _access_required(f):
        @wraps(f)
        def decorated_view(*args, **kwargs):
            if not admin_account_created():
                # Auth disabled, request ok
                return f(*args, **kwargs)

            # 1. Try Session Authentication (Browser)
            if current_user.is_authenticated:
                if not current_user.has_access(access):
                    return 'Forbidden', 403
                return f(*args, **kwargs)

            # 2. Try Basic Authentication (API/Automation)
            if request.authorization:
                success, error, is_admin = basic_auth(request)
                if success:
                    if access == 'admin' and not is_admin:
                         return 'Forbidden', 403
                    return f(*args, **kwargs)

            # 3. Try Bearer Token Authentication
            token_valid, _, user_obj = check_api_token(request)
            if token_valid:
                # Check permissions using the user object linked to the token
                if not user_obj.has_access(access):
                    return 'Forbidden', 403
                return f(*args, **kwargs)
            
            # 4. Public access check
            if access == 'shop':
                from settings import load_settings
                settings = load_settings()
                if settings.get('shop/public_profile', False):
                     return f(*args, **kwargs)

            # 5. Failed
            return login_manager.unauthorized()
        return decorated_view
    return _access_required


def roles_required(roles: list, require_all=False):
    def _roles_required(f):
        @wraps(f)
        def decorated_view(*args, **kwargs):
            if not roles:
                raise ValueError('Empty list used when requiring a role.')
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if require_all and not all(current_user.has_role(role) for role in roles):
                return 'Forbidden', 403
            elif not require_all and not any(current_user.has_role(role) for role in roles):
                return 'Forbidden', 403
            return f(*args, **kwargs)

        return decorated_view

    return _roles_required

def basic_auth(request):
    success = True
    error = ''
    is_admin = False

    auth = request.authorization
    if auth is None:
        success = False
        error = 'Shop requires authentication.'
        return success, error, is_admin

    username = auth.username
    password = auth.password
    else:
        is_admin = user.has_admin_access()
    return success, error, is_admin

def check_api_token(request):
    """
    Validate Bearer token from Authorization header.
    Returns: (success, error, user_object)
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return False, "Missing or invalid token", None
    
    token_str = auth_header.split(" ")[1]
    
    # We need to import ApiToken inside here or rely on 'from db import *' at top
    # Assuming 'ApiToken' is available via 'from db import *'
    token = ApiToken.query.filter_by(token=token_str).first()
    
    if token:
        # Update last used timestamp
        try:
            from utils import now_utc
            token.last_used = now_utc()
            db.session.commit()
        except:
            pass # Don't fail auth just because of timestamp update error
            
        return True, None, token.user
        
    return False, "Invalid token", None

auth_blueprint = Blueprint('auth', __name__)

login_manager = LoginManager()
login_manager.login_view = 'auth.login'

def create_or_update_user(username, password, admin_access=False, shop_access=False, backup_access=False):
    """
    Create a new user or update an existing user with the given credentials and access rights.
    """
    user = User.query.filter_by(user=username).first()
    try:
        if user:
            logger.info(f'Updating existing user {username}')
            user.admin_access = admin_access
            user.shop_access = shop_access
            user.backup_access = backup_access
            user.password = generate_password_hash(password, method='pbkdf2:sha256')
        else:
            logger.info(f'Creating new user {username}')
            new_user = User(user=username, password=generate_password_hash(password, method='pbkdf2:sha256'), admin_access=admin_access, shop_access=shop_access, backup_access=backup_access)
            db.session.add(new_user)
        db.session.commit()
    except Exception as e:
        logger.error(f"Error saving user {username}: {e}")
        db.session.rollback()
        raise e

def init_user_from_environment(environment_name, admin=False):
    """
    allow to init some user from environment variable to init some users without using the UI
    """
    username = os.getenv(environment_name + '_NAME')
    password = os.getenv(environment_name + '_PASSWORD')
    if username and password:
        if admin:
            logger.info('Initializing an admin user from environment variable...')
            admin_access = True
            shop_access = True
            backup_access = True
        else:
            logger.info('Initializing a regular user from environment variable...')
            admin_access = False
            shop_access = True
            backup_access = False

        if not admin:
            existing_admin = admin_account_created()
            if not existing_admin and not admin_access:
                logger.error(f'Error creating user {username}, first account created must be admin')
                return

        create_or_update_user(username, password, admin_access, shop_access, backup_access)

def init_users(app):
    with app.app_context():
        # init users from ENV
        if os.environ.get('USER_ADMIN_NAME') is not None:
            init_user_from_environment(environment_name="USER_ADMIN", admin=True)
        if os.environ.get('USER_GUEST_NAME') is not None:
            init_user_from_environment(environment_name="USER_GUEST", admin=False)

@auth_blueprint.route("/login", methods=["GET", "POST"])
def login():
    # Import here to avoid circular dependency
    from app import limiter
    
    # Apply rate limiting: 20 login attempts per minute per IP (Increased for better UX)
    @limiter.limit("20 per minute")
    def _rate_limited_login():
        if request.method == "GET":
            next_url = request.args.get('next', '')
            if current_user.is_authenticated:
                return redirect(next_url if len(next_url) else '/')
            return render_template('login.html', title='Login', build_version=BUILD_VERSION)
            
        # login code goes here
        username = request.form.get('user')
        password = request.form.get('password')
        remember = bool(request.form.get('remember'))
        next_url = request.form.get('next', '')

        user = User.query.filter_by(user=username).first()

        # check if the user actually exists
        # take the user-supplied password, hash it, and compare it to the hashed password in the database
        if not user or not check_password_hash(user.password, password):
            logger.warning(f'Incorrect login for user {username}')
            return redirect(url_for('auth.login')) # if the user doesn't exist or password is wrong, reload the page

        # if the above check passes, then we know the user has the right credentials
        logger.info(f'Sucessfull login for user {username}')
        login_user(user, remember=remember)

        return redirect(next_url if len(next_url) else '/')
    
    return _rate_limited_login()

@auth_blueprint.route('/profile')
@login_required
@access_required('backup')
def profile():
    return render_template('profile.html', build_version=BUILD_VERSION)

@auth_blueprint.route('/api/users')
@access_required('admin')
def get_users():
    all_users = [
        dict(db_user._mapping)
        for db_user in db.session.query(User.id, User.user, User.admin_access, User.shop_access, User.backup_access).all()
    ]
    return jsonify(all_users)

@auth_blueprint.route('/api/user', methods=['DELETE'])
@login_required
@access_required('admin')
def delete_user():
    success = True
    data = request.json
    user_id = data['user_id']
    try:
        User.query.filter_by(id=user_id).delete()
        db.session.commit()
        logger.info(f'Successfully deleted user with id {user_id}.')
    except Exception as e:
        logger.error(f'Could not delete user with id {user_id}: {e}')
        success = False

    resp = {
        'success': success
    } 
    return jsonify(resp)

@auth_blueprint.route('/api/user', methods=['POST'])
@auth_blueprint.route('/api/user/signup', methods=['POST'])
@access_required('admin')
def signup_post():
    # Import here to avoid circular dependency
    from app import limiter
    
    # Rate limit: 10 signups per hour (prevent mass account creation)
    @limiter.limit("10 per hour")
    def _rate_limited_signup():
        signup_success = True
        data = request.json

        username = data['user']
        password = data['password']
        admin_access = data['admin_access']
        if admin_access:
            shop_access = True
            backup_access = True
        else:
            shop_access = data['shop_access']
            backup_access = data['backup_access']

        user = User.query.filter_by(user=username).first() # if this returns a user, then the user already exists in database
        
        if user: # if a user is found, we want to redirect back to signup page so user can try again
            logger.error(f'Error creating user {username}, user already exists')
            # Todo redirect to incoming page or return success: false
            return redirect(url_for('auth.signup'))
        
        existing_admin = admin_account_created()
        if not existing_admin and not admin_access:
            logger.error(f'Error creating user {username}, first account created must be admin')
            resp = {
                'success': False,
                'status_code': 400,
                'location': '/settings',
            } 
            return jsonify(resp)

        # Log sanitized request data
        logger.info(f'Creating new user: {username} with sanitized data: {sanitize_sensitive_data(data)}')

        # create a new user with the form data. Hash the password so the plaintext version isn't saved.
        try:
            create_or_update_user(username, password, admin_access, shop_access, backup_access)
        except Exception as e:
            logger.error(f"Signup failed: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
        
        logger.info(f'Successfully created user {username}.')

        resp = {
            'success': signup_success
        } 

        if not existing_admin and admin_access:
            logger.debug('First admin account created')
            resp['status_code'] = 302,
            resp['location'] = '/settings'
        
        return jsonify(resp)
    
    return _rate_limited_signup()


@auth_blueprint.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/')