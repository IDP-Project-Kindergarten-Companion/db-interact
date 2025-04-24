# --- db_interact_service/decorators.py ---

import os
from functools import wraps
from flask import request, jsonify, current_app, g
import jwt

def token_required(f):
    """
    Decorator for DB Interact Service routes.
    Ensures a valid ACCESS JWT is present, validates it using the shared secret,
    and loads user info ('user_id', 'role') into Flask's 'g' object.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(" ")[1]

        if not token:
            return jsonify({"message": "Token is missing!"}), 401

        try:
            jwt_secret = current_app.config.get('JWT_SECRET_KEY')
            jwt_algo = current_app.config.get('JWT_ALGORITHM', 'HS256')

            if not jwt_secret:
                current_app.logger.critical("JWT_SECRET_KEY is not configured in DB Interact Service!")
                return jsonify({"message": "Server configuration error"}), 500

            payload = jwt.decode(
                token,
                jwt_secret,
                algorithms=[jwt_algo],
                # Optional: Validate audience/issuer
            )

            if payload.get("type") != "access":
                return jsonify({"message": "Invalid token type provided (expected access)"}), 401

            g.current_user_id = payload.get("sub")
            g.current_user_role = payload.get("role")

            if g.current_user_id is None or g.current_user_role is None:
                 current_app.logger.warning("Token payload missing 'sub' or 'role'.")
                 return jsonify({"message": "Invalid token payload"}), 401

        except jwt.ExpiredSignatureError:
            return jsonify({"message": "Access token has expired!"}), 401
        except jwt.InvalidTokenError as e:
            current_app.logger.warning(f"Invalid access token received: {e}")
            return jsonify({"message": "Access token is invalid!"}), 401
        except Exception as e:
            current_app.logger.error(f"Unexpected error decoding token: {e}", exc_info=True)
            return jsonify({"message": "Error processing token"}), 500

        return f(*args, **kwargs)

    return decorated_function
