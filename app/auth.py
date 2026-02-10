from flask import Blueprint, render_template, redirect, url_for, request, jsonify
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from db import db, User, ApiToken, logger
from flask_login import LoginManager
from utils import sanitize_sensitive_data
from constants import BUILD_VERSION
from api_responses import success_response, error_response, handle_api_errors, ErrorCode
from repositories.user_repository import UserRepository
import os
import logging

# Retrieve main logger
logger = logging.getLogger("main")


def admin_account_created():
    """Check if at least one admin account exists"""
    return User.query.filter_by(admin_access=True).count() > 0


def unauthorized_json():
    response = login_manager.unauthorized()
    return error_response(
        error_code=ErrorCode.UNAUTHORIZED,
        message="Unauthorized",
        status_code=response.status_code,
        details={"location": response.location},
    )


def access_required(access: str):
    def _access_required(f):
        @wraps(f)
        def decorated_view(*args, **kwargs):
            if not admin_account_created():
                # Auth disabled if no admin exists, request ok
                return f(*args, **kwargs)

            # 1. Try Session Authentication (Browser)
            if current_user.is_authenticated:
                if not current_user.has_access(access):
                    return "Forbidden", 403
                return f(*args, **kwargs)

            # 2. Try Basic Authentication (API/Automation)
            if request.authorization:
                success, error, is_admin = basic_auth(request)
                if success:
                    if access == "admin" and not is_admin:
                        return "Forbidden", 403
                    return f(*args, **kwargs)

            # 3. Try Bearer Token Authentication
            token_valid, _, user_obj = check_api_token(request)
            if token_valid:
                # Check permissions using the user object linked to the token
                if not user_obj.has_access(access):
                    return "Forbidden", 403
                return f(*args, **kwargs)

            # 4. Public access check
            if access == "shop":
                from settings import load_settings

                settings = load_settings()
                if settings.get("shop", {}).get("public_profile", False):
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
                raise ValueError("Empty list used when requiring a role.")
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if require_all and not all(current_user.has_role(role) for role in roles):
                return "Forbidden", 403
            elif not require_all and not any(current_user.has_role(role) for role in roles):
                return "Forbidden", 403
            return f(*args, **kwargs)

        return decorated_view

    return _roles_required


def basic_auth(request):
    success = True
    error = ""
    is_admin = False

    auth = request.authorization
    if auth is None:
        success = False
        error = "Shop requires authentication."
        return success, error, is_admin

    username = auth.username
    password = auth.password
    user = User.query.filter_by(user=username).first()
    if user is None:
        success = False
        error = f'Unknown user "{username}".'

    elif not check_password_hash(user.password, password):
        success = False
        error = f'Incorrect password for user "{username}".'

    elif not user.has_shop_access():
        success = False
        error = f'User "{username}" does not have access to the shop.'

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

    token = ApiToken.query.filter_by(token=token_str).first()

    if token:
        # Update last used timestamp
        try:
            from utils import now_utc

            token.last_used = now_utc()
            db.session.commit()
        except:
            pass  # Don't fail auth just because of timestamp update error

        return True, None, token.user

    return False, "Invalid token", None


auth_blueprint = Blueprint("auth", __name__)

login_manager = LoginManager()
login_manager.login_view = "auth.login"


def create_or_update_user(username, password, admin_access=False, shop_access=False, backup_access=False):
    """
    Create a new user or update an existing user with the given credentials and access rights.
    """
    user = User.query.filter_by(user=username).first()
    try:
        hashed_pw = generate_password_hash(password, method="pbkdf2:sha256")
        if user:
            logger.info(f"Updating existing user {username}")
            user.admin_access = admin_access
            user.shop_access = shop_access
            user.backup_access = backup_access
            user.password = hashed_pw
        else:
            logger.info(f"Creating new user {username}")
            new_user = User(
                user=username,
                password=hashed_pw,
                admin_access=admin_access,
                shop_access=shop_access,
                backup_access=backup_access,
            )
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
    username = os.getenv(environment_name + "_NAME")
    password = os.getenv(environment_name + "_PASSWORD")
    if username and password:
        if admin:
            logger.info("Initializing an admin user from environment variable...")
            admin_access = True
            shop_access = True
            backup_access = True
        else:
            logger.info("Initializing a regular user from environment variable...")
            admin_access = False
            shop_access = True
            backup_access = False

        if not admin:
            existing_admin = admin_account_created()
            if not existing_admin and not admin_access:
                logger.error(f"Error creating user {username}, first account created must be admin")
                return

        create_or_update_user(username, password, admin_access, shop_access, backup_access)


def init_users(app):
    with app.app_context():
        # init users from ENV
        if os.environ.get("USER_ADMIN_NAME") is not None:
            init_user_from_environment(environment_name="USER_ADMIN", admin=True)
        if os.environ.get("USER_GUEST_NAME") is not None:
            init_user_from_environment(environment_name="USER_GUEST", admin=False)


@auth_blueprint.route("/login", methods=["GET", "POST"])
def login():
    # Import here to avoid circular dependency
    from app import limiter

    # Apply rate limiting: 20 login attempts per minute per IP (Increased for better UX)
    @limiter.limit("20 per minute")
    def _rate_limited_login():
        if request.method == "GET":
            next_url = request.args.get("next", "")
            if current_user.is_authenticated:
                return redirect(next_url if len(next_url) else "/")
            return render_template("login.html", title="Login", build_version=BUILD_VERSION)

        # login code goes here
        username = request.form.get("user")
        password = request.form.get("password")
        remember = bool(request.form.get("remember"))
        next_url = request.form.get("next", "")

        user = User.query.filter_by(user=username).first()

        # check if the user actually exists
        # take the user-supplied password, hash it, and compare it to the hashed password in the database
        if not user or not check_password_hash(user.password, password):
            logger.warning(f"Incorrect login for user {username}")
            return redirect(url_for("auth.login"))  # if the user doesn't exist or password is wrong, reload the page

        # if the above check passes, then we know the user has the right credentials
        logger.info(f"Sucessfull login for user {username}")
        login_user(user, remember=remember)

        return redirect(next_url if len(next_url) else "/")

    return _rate_limited_login()


@auth_blueprint.route("/profile")
@login_required
@access_required("backup")
def profile():
    return render_template("profile.html", build_version=BUILD_VERSION)


@auth_blueprint.route("/api/change_password", methods=["POST"])
@login_required
@handle_api_errors
def change_password():
    data = request.json
    current_password = data.get("current_password")
    new_password = data.get("new_password")
    confirm_password = data.get("confirm_password")

    if not current_password or not new_password or not confirm_password:
        return error_response(ErrorCode.VALIDATION_ERROR, message="Todos os campos são obrigatórios.")

    if new_password != confirm_password:
        return error_response(ErrorCode.VALIDATION_ERROR, message="As senhas não coincidem.")

    if not check_password_hash(current_user.password, current_password):
        return error_response(ErrorCode.UNAUTHORIZED, message="Senha atual incorreta.")

    current_user.password = generate_password_hash(new_password, method="pbkdf2:sha256")
    db.session.commit()
    logger.info(f"Senha alterada com sucesso para o usuário {current_user.user}")
    return success_response(message="Senha alterada com sucesso!")


@auth_blueprint.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")
