"""
MyFoil - Custom Exceptions and Exception Handlers
"""
import structlog
from flask import jsonify
from werkzeug.exceptions import HTTPException

logger = structlog.get_logger('exceptions')


class MyFoilException(Exception):
    """Base exception for MyFoil"""
    def __init__(self, message: str, code: str = "MYFOIL_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)

    def to_dict(self):
        return {
            'error': True,
            'code': self.code,
            'message': self.message
        }


class DatabaseException(MyFoilException):
    """Database-related exceptions"""
    def __init__(self, message: str):
        super().__init__(message, code="DATABASE_ERROR")
        logger.error(f"Database error: {message}")


class TitleDBException(MyFoilException):
    """TitleDB-related exceptions"""
    def __init__(self, message: str):
        super().__init__(message, code="TITLEDAB_ERROR")
        logger.error(f"TitleDB error: {message}")


class FileException(MyFoilException):
    """File-related exceptions"""
    def __init__(self, message: str):
        super().__init__(message, code="FILE_ERROR")
        logger.error(f"File error: {message}")


class ValidationException(MyFoilException):
    """Validation-related exceptions"""
    def __init__(self, message: str):
        super().__init__(message, code="VALIDATION_ERROR")
        logger.warning(f"Validation error: {message}")


class AuthenticationException(MyFoilException):
    """Authentication-related exceptions"""
    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, code="AUTH_ERROR")
        logger.warning(f"Authentication error: {message}")


class AuthorizationException(MyFoilException):
    """Authorization-related exceptions"""
    def __init__(self, message: str = "Access denied"):
        super().__init__(message, code="FORBIDDEN")
        logger.warning(f"Authorization error: {message}")


def register_exception_handlers(app):
    """Register exception handlers with Flask app"""
    
    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        """Handle HTTP exceptions"""
        return jsonify({
            'error': True,
            'code': e.name.upper().replace(' ', '_'),
            'message': e.description
        }), e.code
    
    @app.errorhandler(MyFoilException)
    def handle_myfoil_exception(e):
        """Handle MyFoil custom exceptions"""
        return jsonify(e.to_dict()), 400
    
    @app.errorhandler(DatabaseException)
    def handle_database_exception(e):
        """Handle database exceptions"""
        return jsonify(e.to_dict()), 500
    
    @app.errorhandler(TitleDBException)
    def handle_titledb_exception(e):
        """Handle TitleDB exceptions"""
        return jsonify(e.to_dict()), 502
    
    @app.errorhandler(ValidationException)
    def handle_validation_exception(e):
        """Handle validation exceptions"""
        return jsonify(e.to_dict()), 400
    
    @app.errorhandler(AuthenticationException)
    def handle_auth_exception(e):
        """Handle authentication exceptions"""
        return jsonify(e.to_dict()), 401
    
    @app.errorhandler(AuthorizationException)
    def handle_authorization_exception(e):
        """Handle authorization exceptions"""
        return jsonify(e.to_dict()), 403
    
    @app.errorhandler(Exception)
    def handle_generic_exception(e):
        """Handle all other exceptions"""
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        return jsonify({
            'error': True,
            'code': 'INTERNAL_ERROR',
            'message': 'An unexpected error occurred'
        }), 500
