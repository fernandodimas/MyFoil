"""
API Response Utilities - Standardized error handling and responses
Phase 3.1: Consistent API responses with error codes and messages
"""

from flask import jsonify
from functools import wraps
import logging
import traceback

logger = logging.getLogger(__name__)


# API Error Codes
class ErrorCode:
    SUCCESS = "SUCCESS"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    CONFLICT = "CONFLICT"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"


def success_response(data=None, message=None, status_code=200):
    """
    Standard success response format for API endpoints
    """
    response = {"code": ErrorCode.SUCCESS, "success": True}

    if data is not None:
        response["data"] = data

    if message:
        response["message"] = message

    return jsonify(response), status_code


def error_response(
    error_code=ErrorCode.INTERNAL_ERROR,
    message=None,
    details=None,
    status_code=400,
    log_error=True,
    include_traceback=False,
):
    """
    Standard error response format for API endpoints
    """
    response = {"code": error_code, "success": False}

    if message:
        response["message"] = message
    elif error_code == ErrorCode.NOT_FOUND:
        response["message"] = "Resource not found"
    elif error_code == ErrorCode.VALIDATION_ERROR:
        response["message"] = "Invalid request parameters"
    elif error_code == ErrorCode.INTERNAL_ERROR:
        response["message"] = "An unexpected error occurred"
    elif error_code == ErrorCode.UNAUTHORIZED:
        response["message"] = "Authentication required"
    elif error_code == ErrorCode.FORBIDDEN:
        response["message"] = "Access forbidden"
    elif error_code == ErrorCode.CONFLICT:
        response["message"] = "Resource conflict"
    elif error_code == ErrorCode.RATE_LIMIT_EXCEEDED:
        response["message"] = "Rate limit exceeded"

    if details:
        response["details"] = details

    if include_traceback:
        response["traceback"] = traceback.format_exc()

    if log_error and error_code in [ErrorCode.INTERNAL_ERROR, ErrorCode.VALIDATION_ERROR]:
        error_msg = f"{error_code}: {message} | Details: {details}"
        if include_traceback:
            logger.error(error_msg, exc_info=True)
        else:
            logger.error(error_msg)

    return jsonify(response), status_code


def handle_api_errors(f):
    """
    Decorator to standardize error handling for API endpoints
    Automatically catches exceptions and returns consistent error responses
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            return error_response(ErrorCode.VALIDATION_ERROR, message=str(e), status_code=400)
        except KeyError as e:
            return error_response(
                ErrorCode.VALIDATION_ERROR, message=f"Missing required parameter: {str(e)}", status_code=400
            )
        except FileNotFoundError as e:
            return error_response(ErrorCode.NOT_FOUND, message=str(e), status_code=404)
        except PermissionError as e:
            return error_response(ErrorCode.FORBIDDEN, message=str(e), status_code=403)
        except Exception as e:
            logger.error(f"Unhandled exception in {f.__name__}: {e}", exc_info=True)
            return error_response(
                ErrorCode.INTERNAL_ERROR,
                message="An unexpected error occurred",
                status_code=500,
                include_traceback=False,
            )

    return wrapper


def paginated_response(items, total, page, per_page, has_more=None):
    """
    Standard paginated response format for list endpoints
    """
    response = {
        "code": ErrorCode.SUCCESS,
        "success": True,
        "data": items,
        "pagination": {
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
        },
    }

    if has_more is not None:
        response["pagination"]["has_more"] = has_more
    else:
        response["pagination"]["has_more"] = page * per_page < total

    response["pagination"]["next_page"] = page + 1 if response["pagination"]["has_more"] else None
    response["pagination"]["prev_page"] = page - 1 if page > 1 else None

    return jsonify(response), 200


def validation_error_response(field, message):
    """
    Convenience function for validation errors
    """
    return error_response(
        ErrorCode.VALIDATION_ERROR,
        message=f"Validation failed for field: {field}",
        details={"field": field, "error": message},
        status_code=400,
    )


def not_found_response(resource_type, resource_id=None):
    """
    Convenience function for not found errors
    """
    if resource_id:
        message = f"{resource_type} with ID '{resource_id}' not found"
    else:
        message = f"{resource_type} not found"
    return error_response(ErrorCode.NOT_FOUND, message=message, status_code=404)


def internal_error_response(message=None, log_message=None):
    """
    Convenience function for internal server errors
    """
    if log_message:
        logger.error(log_message)
    return error_response(ErrorCode.INTERNAL_ERROR, message=message or "An unexpected error occurred", status_code=500)
