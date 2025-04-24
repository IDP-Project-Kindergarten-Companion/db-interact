# --- db_interact_service/routes.py ---

from flask import Blueprint, request, jsonify, g, current_app
from .decorators import token_required
from .models import add_activity_record, get_activities_for_child # Import CRUD functions
from pymongo.errors import OperationFailure
from bson import ObjectId
import datetime

# Create a single Blueprint for all data interaction routes for now
db_bp = Blueprint('database', __name__, url_prefix='/data') # Example prefix

# --- Activity Routes ---

@db_bp.route('/activities', methods=['POST'])
@token_required
def add_activity():
    """Adds a new activity record."""
    user_role = g.current_user_role
    if user_role != 'teacher': # Example authorization
        return jsonify({"message": "Unauthorized: Only supervisors can add activities"}), 403

    data = request.get_json()
    if not data or not data.get('child_id') or not data.get('type'):
        return jsonify({"message": "Missing required fields: child_id, type"}), 400
    try:
        ObjectId(data['child_id']) # Validate ID format
    except Exception:
        return jsonify({"message": "Invalid child_id format"}), 400

    try:
        activity_id = add_activity_record(data)
        return jsonify({"message": "Activity added successfully", "activity_id": activity_id}), 201
    except OperationFailure as e:
        return jsonify({"message": f"Database error: {e}"}), 500
    except Exception as e:
        current_app.logger.error(f"Error adding activity: {e}", exc_info=True)
        return jsonify({"message": "An internal server error occurred"}), 500

@db_bp.route('/activities', methods=['GET'])
@token_required
def get_activities():
    """Gets activities for a specific child."""
    user_id = g.current_user_id
    user_role = g.current_user_role
    child_id = request.args.get('child_id')

    if not child_id:
        return jsonify({"message": "Missing required query parameter: child_id"}), 400
    try:
        ObjectId(child_id) # Validate ID format
    except Exception:
        return jsonify({"message": "Invalid child_id format"}), 400

    # --- Authorization Placeholder ---
    # Add real logic here to check if the user (parent/teacher)
    # is allowed to view data for this child_id.
    is_authorized = True # Replace with real check!
    if not is_authorized:
         return jsonify({"message": "Unauthorized to view activities for this child"}), 403
    # --- End Authorization Placeholder ---

    # Add date filtering logic if needed based on request args

    try:
        activities = get_activities_for_child(child_id) # Add date args if implemented
        return jsonify(activities), 200
    except OperationFailure as e:
        return jsonify({"message": f"Database error: {e}"}), 500
    except Exception as e:
        current_app.logger.error(f"Error getting activities: {e}", exc_info=True)
        return jsonify({"message": "An internal server error occurred"}), 500

# --- Add Routes for Drawings ---
# @db_bp.route('/drawings', methods=['POST'])
# @token_required
# def add_drawing(): ...

# @db_bp.route('/drawings', methods=['GET'])
# @token_required
# def get_drawings(): ...

# --- Add Routes for Child Profiles ---
# @db_bp.route('/profiles', methods=['POST']) ...
# @db_bp.route('/profiles/<child_id>', methods=['GET']) ...
# @db_bp.route('/profiles/<child_id>', methods=['PUT']) ...

