"""
Authentication Middleware - Decoradores e funções de autenticação
"""
from functools import wraps
from flask import request, jsonify, current_app
from flask_login import current_user
from settings import load_settings
import logging

logger = logging.getLogger('main')

def access_required(access_type):
    """Decorador para verificar acesso baseado no tipo"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({'error': 'Authentication required'}), 401

            if not current_user.has_access(access_type):
                return jsonify({'error': 'Access denied'}), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator

def tinfoil_access(f):
    """Decorador para acesso Tinfoil com verificação de host"""
    @wraps(f)
    def _tinfoil_access(*args, **kwargs):
        hauth_success = None
        auth_success = None
        request.verified_host = None

        # Host verification to prevent hotlinking
        # Tinfoil doesn't send Hauth for file grabs, only directories, so ignore get_game endpoints.
        host_verification = "/api/get_game" not in request.path and (request.is_secure or request.headers.get("X-Forwarded-Proto") == "https")
        if host_verification:
            app_settings = load_settings()
            request_host = request.host
            request_hauth = request.headers.get('Hauth')
            logger.info(f"Secure Tinfoil request from remote host {request_host}, proceeding with host verification.")
            shop_host = app_settings["shop"].get("host")
            shop_hauth = app_settings["shop"].get("hauth")
            if not shop_host:
                logger.error("Missing shop host configuration, Host verification is disabled.")

            elif request_host != shop_host:
                logger.warning(f"Incorrect URL referrer detected: {request_host}.")
                error = f"Incorrect URL `{request_host}`."
                hauth_success = False

            elif not shop_hauth:
                # Try authentication, if an admin user is logging in then set the hauth
                auth_success, auth_error, auth_is_admin = basic_auth(request)
                if auth_success and auth_is_admin:
                    from settings import set_shop_settings
                    shop_settings = app_settings['shop']
                    shop_settings['hauth'] = request_hauth
                    set_shop_settings(shop_settings)
                    logger.info(f"Successfully set Hauth value for host {request_host}.")
                    hauth_success = True
                else:
                    logger.warning(f"Hauth value not set for host {request_host}, Host verification is disabled. Connect to the shop from Tinfoil with an admin account to set it.")

            elif request_hauth != shop_hauth:
                logger.warning(f"Incorrect Hauth detected for host: {request_host}.")
                error = f"Incorrect Hauth for URL `{request_host}`."
                hauth_success = False

            else:
                hauth_success = True
                request.verified_host = shop_host

            if hauth_success is False:
                return tinfoil_error(error)

        # Now checking auth if shop is private
        app_settings = load_settings()
        if not app_settings['shop']['public']:
            # Shop is private
            if auth_success is None:
                # First check if user is logged in via session (Browser)
                if current_user.is_authenticated and current_user.has_access('shop'):
                    auth_success = True
                else:
                    # Fallback to Basic Auth (Tinfoil)
                    auth_success, auth_error, auth_is_admin = basic_auth(request)

            if not auth_success:
                return tinfoil_error(auth_error)
        # Auth success
        return f(*args, **kwargs)
    return _tinfoil_access

def basic_auth(request):
    """Autenticação básica HTTP"""
    from db import User
    import base64

    auth = request.headers.get('Authorization')
    if not auth or not auth.startswith('Basic '):
        return False, 'Missing or invalid authorization header', False

    try:
        credentials = base64.b64decode(auth[6:]).decode('utf-8')
        username, password = credentials.split(':', 1)
    except:
        return False, 'Invalid authorization header format', False

    user = User.query.filter_by(user=username).first()
    if user and user.password == password:  # In production, use proper password hashing
        return True, None, user.admin_access

    return False, 'Invalid username or password', False

def tinfoil_error(error):
    """Retornar erro formatado para Tinfoil"""
    return jsonify({
        'error': error
    })

def admin_required(f):
    """Decorador para acesso administrativo"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'Authentication required'}), 401

        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403

        return f(*args, **kwargs)
    return decorated_function

def shop_access_required(f):
    """Decorador para acesso à loja"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'Authentication required'}), 401

        if not current_user.has_shop_access():
            return jsonify({'error': 'Shop access required'}), 403

        return f(*args, **kwargs)
    return decorated_function