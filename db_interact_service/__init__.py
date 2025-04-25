# --- db_interact_service/__init__.py ---
import logging
from flask import Flask
# Use relative imports within the package
from .config import Config
from .models import close_db
from .routes import data_bp, internal_bp

def create_app():
    """Factory function to create the DB Interact Flask application."""
    app = Flask(__name__)
    # Load configuration from the Config object
    app.config.from_object(Config)

    # Configure logging
    logging.basicConfig(level=logging.INFO)
    app.logger.info("DB Interact Service starting up...")
    app.logger.info(f"Attempting to connect to OPERATIONAL_MONGO_URI: {app.config.get('MONGO_URI')[:15]}...")

    # Register database teardown function from models.py
    app.teardown_appcontext(close_db)

    # Register the blueprints for the application
    app.register_blueprint(data_bp)
    app.register_blueprint(internal_bp)
    app.logger.info("Blueprints registered.")

    # Basic root route for health check
    @app.route('/')
    def index():
        try:
            from .models import get_db
            get_db() # Attempt connection
            return "DB Interact Service Running - DB Connection OK"
        except Exception as e:
            app.logger.error(f"Health check DB connection failed: {e}")
            # Return detailed error only if needed for debugging, might expose too much
            return f"DB Interact Service Running - DB Connection FAILED", 500

    app.logger.info("DB Interact Service application created.")
    return app
