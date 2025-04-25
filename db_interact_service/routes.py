# --- db_interact_service/routes.py ---

from flask import Blueprint, request, jsonify, g, current_app
from .decorators import token_required
# Import CRUD functions and authorization helpers from models
from .models import *
from pymongo.errors import OperationFailure
from bson import ObjectId # To validate ObjectIds if needed
import datetime
import traceback # For logging stack traces

# Create Blueprints:
# 'internal' for routes primarily called service-to-service
# 'data' for routes potentially exposed via API Gateway to frontend
internal_bp = Blueprint('internal', __name__, url_prefix='/internal')
data_bp = Blueprint('data', __name__, url_prefix='/data')


# --- Helper Function for Authorization ---
def check_child_access(child_id):
    """
    Checks if the current user (identified by token data in 'g')
    is authorized to access data related to the given child_id.
    Returns True if authorized, False otherwise.
    """
    user_id = getattr(g, 'current_user_id', None)
    user_role = getattr(g, 'current_user_role', None)

    # Basic validation of inputs
    if not user_id or not child_id:
        current_app.logger.warning("Authorization check failed: Missing user_id or child_id in request context or parameters.")
        return False

    # Attempt authorization checks, handle potential errors (e.g., invalid ObjectId)
    try:
        # Teachers/Supervisors check if they are linked to the child
        if user_role == 'teacher' and is_supervisor_of(user_id, child_id):
            return True
        # Parents check if they are linked to the child
        if user_role == 'parent' and is_parent_of(user_id, child_id):
            return True
        # Add other roles like 'admin' if needed
        # if user_role == 'admin':
        #    return True

    except Exception as e:
        # Log any error during the database check (e.g., invalid ID format passed to ObjectId)
        current_app.logger.error(f"Error during authorization check for child {child_id}, user {user_id}: {e}")
        return False # Deny access if checks fail due to error

    # Deny access if none of the conditions are met
    current_app.logger.warning(f"Authorization denied for user {user_id} (role: {user_role}) on child {child_id}")
    return False

# --- Internal Children Routes (Called by other services) ---

@internal_bp.route('/children', methods=['POST'])
@token_required # Ensure caller service provides a valid token
def handle_create_child():
    """
    (Internal) Creates a new child record.
    Expects the calling service (e.g., child-profile-service) to have
    verified that the user performing the action (whose ID is in the token)
    is a parent.
    """
    user_id = g.current_user_id # The parent performing the action
    user_role = g.current_user_role # Role from token

    # Optional safety check (can be removed if calling service guarantees role)
    if user_role != 'parent':
         return jsonify({"message": "Unauthorized: Only parents can initiate child creation"}), 403

    data = request.get_json()
    # Validate required fields passed from the calling service
    if not data or not data.get('name') or not data.get('birthday'):
        return jsonify({"message": "Missing required fields from calling service: name, birthday"}), 400

    try:
        # Pass the validated parent_id from the token to link the child
        child_id = create_child_record(data, parent_id=user_id)
        current_app.logger.info(f"Child record created with ID: {child_id} by parent {user_id}")
        return jsonify({"message": "Child record created", "child_id": child_id}), 201
    except ValueError as e: # Catches validation errors from model
        return jsonify({"message": f"Failed to create child: {e}"}), 400
    except OperationFailure as e: # Catch database errors
        current_app.logger.error(f"Database error creating child: {e}")
        return jsonify({"message": f"Database error: {e}"}), 500
    except Exception as e:
        current_app.logger.error(f"Unexpected error creating child: {e}\n{traceback.format_exc()}")
        return jsonify({"message": "An internal server error occurred"}), 500

@internal_bp.route('/children/<child_id>', methods=['PUT'])
@token_required # Ensure caller service provides a valid token
def handle_update_child(child_id):
    """
    (Internal) Updates child details (group, allergies, notes, name, birthday).
    Expects the calling service (e.g., child-profile-service) to have
    verified that the user performing the action has permission to update this child.
    """
    # The calling service MUST verify permissions before calling this.
    data = request.get_json()
    if not data:
        return jsonify({"message": "Missing request body"}), 400

    try:
        # Validate child_id format before proceeding
        ObjectId(child_id)
        success = update_child_details(child_id, data)
        if success:
            current_app.logger.info(f"Child details updated for ID: {child_id}")
            return jsonify({"message": "Child details updated"}), 200
        else:
            # Check if child exists to differentiate between not found and no valid fields
            if get_child_by_id(child_id):
                 current_app.logger.warning(f"Update failed for child {child_id}: No valid fields or data unchanged.")
                 return jsonify({"message": "No valid fields provided for update or update failed"}), 400
            else:
                 current_app.logger.warning(f"Update failed for child {child_id}: Child not found.")
                 return jsonify({"message": "Child not found"}), 404
    except ValueError as e: # Catches validation errors from model
        return jsonify({"message": f"Failed to update child: {e}"}), 400
    except OperationFailure as e: # Catch database errors
        current_app.logger.error(f"Database error updating child {child_id}: {e}")
        return jsonify({"message": f"Database error: {e}"}), 500
    except Exception as e: # Catch ObjectId errors etc.
        current_app.logger.error(f"Unexpected error updating child {child_id}: {e}\n{traceback.format_exc()}")
        return jsonify({"message": "An internal server error occurred"}), 500

@internal_bp.route('/children/<child_id>/link-supervisor', methods=['PUT'])
@token_required # Ensure caller service provides a valid token
def handle_link_supervisor(child_id):
    """
    (Internal) Links a supervisor to a child.
    Expects the calling service (e.g., child-profile-service) to have
    verified the linking code and that the user in the token is a supervisor.
    """
    # Calling service verifies the linking code and supervisor role.
    data = request.get_json()
    supervisor_id = data.get('supervisor_id') if data else None

    if not supervisor_id:
        return jsonify({"message": "Missing supervisor_id in request body"}), 400

    try:
        # Validate IDs before attempting link
        ObjectId(child_id)
        ObjectId(supervisor_id)
        success = link_supervisor_to_child(child_id, supervisor_id)
        if success:
             # Note: success just means child was found. Supervisor might have already been linked.
             current_app.logger.info(f"Supervisor link updated for child {child_id}, supervisor {supervisor_id}")
             return jsonify({"message": "Supervisor link updated successfully"}), 200
        else:
             # This likely means the child_id was invalid
             current_app.logger.warning(f"Failed to link supervisor: Child not found with ID {child_id}")
             return jsonify({"message": "Child not found"}), 404
    except ValueError as e: # Catches validation errors from model
         return jsonify({"message": f"Failed to link supervisor: {e}"}), 400
    except OperationFailure as e: # Catch database errors
        current_app.logger.error(f"Database error linking supervisor for child {child_id}: {e}")
        return jsonify({"message": f"Database error: {e}"}), 500
    except Exception as e: # Catch ObjectId errors etc.
        current_app.logger.error(f"Unexpected error linking supervisor for child {child_id}: {e}\n{traceback.format_exc()}")
        return jsonify({"message": "An internal server error occurred"}), 500


# --- Internal Activity Routes (Called by other services) ---

@internal_bp.route('/activities', methods=['POST'])
@token_required # Ensure caller service provides a valid token
def handle_add_activity():
    """
    (Internal) Adds a new activity record.
    Expects the calling service (e.g., activities-log-service) to have
    verified the user is a supervisor linked to the child.
    """
    # Calling service (activities-log) MUST verify supervisor role and link to child.
    data = request.get_json()
    # Basic validation
    if not data or not data.get('child_id') or not data.get('type') or not data.get('details'):
         return jsonify({"message": "Missing required fields: child_id, type, details"}), 400

    # Add who logged the activity (user ID from token)
    data['logged_by'] = g.current_user_id

    try:
        activity_id = add_activity_record(data)
        current_app.logger.info(f"Activity record created with ID: {activity_id} for child {data.get('child_id')} by user {g.current_user_id}")
        return jsonify({"message": "Activity added successfully", "activity_id": activity_id}), 201
    except ValueError as e: # Catches validation errors from model
        return jsonify({"message": f"Failed to add activity: {e}"}), 400
    except OperationFailure as e: # Catch database errors
        current_app.logger.error(f"Database error adding activity: {e}")
        return jsonify({"message": f"Database error: {e}"}), 500
    except Exception as e:
        current_app.logger.error(f"Unexpected error adding activity: {e}\n{traceback.format_exc()}")
        return jsonify({"message": "An internal server error occurred"}), 500


# --- Data Routes (Potentially Exposed via Gateway) ---

@data_bp.route('/children/<child_id>', methods=['GET'])
@token_required # Token needed
def handle_get_child_data(child_id):
    """Gets details for a specific child (requires authorization check)."""
    # Authorization check: Is the requesting user allowed to see this child?
    if not check_child_access(child_id):
        # Logged inside check_child_access
        return jsonify({"message": "Forbidden: You do not have access to this child's data"}), 403

    try:
        child = get_child_by_id(child_id)
        if child:
            return jsonify(child), 200
        else:
            # Log if child not found after authorization check (unlikely but possible)
            current_app.logger.warning(f"Child {child_id} not found during GET request by authorized user {g.current_user_id}")
            return jsonify({"message": "Child not found"}), 404
    except Exception as e:
        current_app.logger.error(f"Error getting child {child_id}: {e}\n{traceback.format_exc()}")
        return jsonify({"message": "An internal server error occurred"}), 500

@data_bp.route('/children', methods=['GET'])
@token_required # Token needed
def handle_get_children_list_data():
    """Gets a list of children associated with the current user (parent or supervisor)."""
    user_id = g.current_user_id
    user_role = g.current_user_role
    children_list = []

    try:
        if user_role == 'parent':
            children_list = get_children_for_parent(user_id)
        elif user_role == 'teacher':
            children_list = get_children_for_supervisor(user_id)
        # Add logic for other roles (e.g., admin) if needed
        else:
            # Handle unexpected roles if necessary
             current_app.logger.warning(f"User {user_id} with unexpected role '{user_role}' attempted to list children.")
             return jsonify({"message": "Invalid user role for this operation"}), 403


        return jsonify(children_list), 200
    except Exception as e:
        current_app.logger.error(f"Error getting children list for user {user_id}: {e}\n{traceback.format_exc()}")
        return jsonify({"message": "An internal server error occurred"}), 500

@data_bp.route('/activities', methods=['GET'])
@token_required # Token needed
def handle_get_activities_data():
    """Gets activities for a specific child, with optional filters (requires authorization)."""
    child_id = request.args.get('child_id')
    activity_type = request.args.get('type') # Optional filter (e.g., 'meal', 'sleep', 'drawing')
    start_date_str = request.args.get('start_date') # Optional filter YYYY-MM-DD
    end_date_str = request.args.get('end_date')     # Optional filter YYYY-MM-DD

    if not child_id:
        return jsonify({"message": "Missing required query parameter: child_id"}), 400

    # --- Authorization Check ---
    if not check_child_access(child_id):
        # Logged inside check_child_access
        return jsonify({"message": "Forbidden: You do not have access to this child's activities"}), 403

    # --- Date Parsing ---
    start_date = None
    end_date = None
    try:
        if start_date_str:
            # Parse date string, assume start of the day
            start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d')
        if end_date_str:
            # Parse date string and add one day to make range exclusive of the end date
            # e.g., end_date=2023-10-27 means include up to 2023-10-26 23:59:59...
            end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d') + datetime.timedelta(days=1)
    except ValueError:
        return jsonify({"message": "Invalid date format. Use YYYY-MM-DD."}), 400

    try:
        # Call model function with validated parameters
        activities = get_activities_for_child(child_id, activity_type, start_date, end_date)
        return jsonify(activities), 200
    except ValueError as e: # Catches validation errors from model (e.g., invalid child_id format)
         return jsonify({"message": f"Failed to get activities: {e}"}), 400
    except OperationFailure as e: # Catch database errors
        current_app.logger.error(f"Database error getting activities for child {child_id}: {e}")
        return jsonify({"message": f"Database error: {e}"}), 500
    except Exception as e:
        current_app.logger.error(f"Unexpected error getting activities for child {child_id}: {e}\n{traceback.format_exc()}")
        return jsonify({"message": "An internal server error occurred"}), 500

@data_bp.route('/activities/<activity_id>', methods=['DELETE'])
@token_required # Token needed
def handle_delete_activity(activity_id):
    """Deletes a specific activity record (requires authorization)."""
    user_id = g.current_user_id
    user_role = g.current_user_role

    # --- Authorization ---
    # 1. Basic role check: Only teachers/supervisors can delete
    if user_role != 'teacher':
        return jsonify({"message": "Forbidden: Only supervisors can delete activities"}), 403

    try:
        # 2. Get the activity to find the associated child_id
        # Use the specific model function for this
        activity = get_activity_by_id(activity_id)
        if not activity:
            return jsonify({"message": "Activity not found"}), 404

        child_id = activity.get('child_id') # Should be string from _serialize_doc
        if not child_id:
             # This shouldn't happen if data integrity is maintained
             current_app.logger.error(f"Activity {activity_id} is missing child_id!")
             return jsonify({"message": "Internal data error: Activity missing child link"}), 500

        # 3. Check if the supervisor (user_id from token) is linked to that child
        if not is_supervisor_of(user_id, child_id):
            # Log the specific authorization failure
            current_app.logger.warning(f"Authorization failed: Supervisor {user_id} attempted to delete activity {activity_id} for child {child_id} they do not supervise.")
            return jsonify({"message": "Forbidden: You are not authorized to modify activities for this child"}), 403

        # --- Deletion ---
        # 4. If authorized, attempt deletion using the model function
        deleted = delete_activity_record(activity_id)
        if deleted:
            current_app.logger.info(f"Activity {activity_id} deleted by supervisor {user_id}")
            return jsonify({"message": "Activity deleted successfully"}), 200
        else:
            # This could happen if the activity was deleted between the check and the delete call,
            # or if the activity_id format was valid but didn't match anything.
            # The model function already logged a warning if it didn't find the doc.
            return jsonify({"message": "Activity not found or already deleted"}), 404

    except ValueError as e: # Catches validation errors from model functions
        return jsonify({"message": f"Error processing delete request: {e}"}), 400
    except OperationFailure as e: # Catch database errors
        current_app.logger.error(f"Database error deleting activity {activity_id}: {e}")
        return jsonify({"message": f"Database error: {e}"}), 500
    except Exception as e:
        current_app.logger.error(f"Unexpected error deleting activity {activity_id}: {e}\n{traceback.format_exc()}")
        return jsonify({"message": "An internal server error occurred"}), 500

# Add routes for Drawings similarly if needed, although they are handled
# via the /activities endpoint with type='drawing' based on current models.
# Example: GET /data/activities?child_id=...&type=drawing

