# --- db_interact_service/run.py ---

# Import the factory function from the package directory
from db_interact_service import create_app

# Create the app instance using the factory
app = create_app()

# This block is primarily for local development using 'python run.py'
# It's typically NOT used when running via Docker with 'flask run' or gunicorn
if __name__ == '__main__':
    # Use a different port than auth_service (e.g., 5001) for local testing
    # Host 0.0.0.0 makes it accessible on the network
    # Set debug=False for production/docker environments
    app.run(host='0.0.0.0', port=5001, debug=True)
