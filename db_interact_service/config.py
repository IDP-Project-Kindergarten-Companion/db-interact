# --- db_interact_service/config.py ---
import os
from dotenv import load_dotenv

load_dotenv() # Load .env file from the top-level db_interact_service directory

class Config:
    """Application configuration class for DB Interact Service."""
    SECRET_KEY = os.environ.get('DB_INTERACT_SECRET_KEY', 'a_fallback_secret_for_db_interact')

    # --- IMPORTANT ---
    # This MUST point to your OPERATIONAL MongoDB database.
    # It will be provided by docker-compose.
    # Use a distinct name like 'littlesteps_db' or 'operational_db'.
    MONGO_URI = os.environ.get('OPERATIONAL_MONGO_URI', 'mongodb://localhost:27017/littlesteps_db')

    # --- IMPORTANT ---
    # This MUST be the SAME secret key used by auth_service to SIGN tokens.
    # It will be provided by docker-compose using the same env var name.
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'default_jwt_secret_key_needs_change')
    JWT_ALGORITHM = "HS256" # Must match auth_service

    # Optional: Define expected audience/issuer if used in JWTs
    # JWT_AUDIENCE = 'urn:myapp:api'
    # JWT_ISSUER = 'urn:myapp:auth'
