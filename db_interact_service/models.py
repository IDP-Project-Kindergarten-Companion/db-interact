# --- db_interact_service/models.py ---
import datetime
from pymongo import MongoClient
from pymongo.uri_parser import parse_uri
from pymongo.errors import ConnectionFailure, OperationFailure, DuplicateKeyError
from flask import current_app, g
from bson import ObjectId # For handling MongoDB ObjectIDs
import logging # Use standard logging
from .utils import serialize_doc

# --- Database Connection Handling ---

def get_db():
    """
    Opens a new database connection for the operational DB if there is
    none yet for the current application context. Returns the database object.
    Handles connection pooling implicitly via MongoClient.
    """
    # Check if connection object already exists for this context
    if 'operational_mongo_db' not in g:
        mongo_uri = current_app.config['MONGO_URI']
        try:
            # Parse URI to get database name
            uri_dict = parse_uri(mongo_uri)
            db_name = uri_dict.get('database')
            if not db_name:
                raise ValueError(f"Operational database name not found in MONGO_URI: {mongo_uri}")

            # Create client and store client and db object in Flask's 'g'
            # Add a server selection timeout for quicker failure detection
            g.operational_mongo_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
            # The ismaster command is cheap and does not require auth.
            # It forces the client to connect and check server status.
            g.operational_mongo_client.admin.command('ismaster')
            g.operational_mongo_db = g.operational_mongo_client[db_name]
            current_app.logger.info(f"Connected to operational DB: {db_name}")

        except ConnectionFailure as e:
             # Handle connection error during initialization
             current_app.logger.error(f"Operational DB connection failed: {e}")
             g.operational_mongo_db = None # Mark as None if connection failed
             raise ConnectionFailure(f"Could not connect to operational database: {e}")
        except ValueError as e:
             # Handle configuration errors (e.g., missing db name)
             current_app.logger.error(f"Configuration error: {e}")
             g.operational_mongo_db = None
             raise ValueError(f"Configuration error: {e}")
        except Exception as e:
             # Catch other potential errors during client initialization
             current_app.logger.error(f"Unexpected error during DB client initialization: {e}", exc_info=True)
             g.operational_mongo_db = None
             raise ConnectionFailure(f"Unexpected error connecting to operational database: {e}")


    # Check if connection failed on a previous attempt within the same context
    if g.operational_mongo_db is None:
        # This prevents using a None object if connection failed earlier in the request
        raise ConnectionFailure("Operational database connection previously failed in this context.")

    # Return the database object
    return g.operational_mongo_db

def close_db(e=None):
    """Closes the operational database connection by closing the client."""
    # Pop the client from 'g' to ensure it's removed
    client = g.pop('operational_mongo_client', None)
    # Close the client if it exists (this handles connection pooling)
    if client is not None:
        client.close()
        current_app.logger.info("Closed operational DB client connection.")
    # Also pop the db object just in case
    g.pop('operational_mongo_db', None)


# --- Children CRUD Functions ---

def create_child_record(child_data: dict, parent_id: str) -> str:
    """Creates a new child record in the 'children' collection, associating the initial parent."""
    db = get_db()
    try:
        # Validate parent_id format before using it
        parent_obj_id = ObjectId(parent_id)

        # Prepare child document with necessary fields
        new_child = {
            "name": child_data.get("name"),
            "birthday": child_data.get("birthday"), # Store as string YYYY-MM-DD or datetime object
            "group": child_data.get("group"),
            "allergies": child_data.get("allergies", []), # Default to empty list if not provided
            "notes": child_data.get("notes", ""),       # Default to empty string if not provided
            "parent_ids": [parent_obj_id],              # Link initial parent ObjectId
            "supervisor_ids": [],                       # Initialize empty list for supervisors
            "created_at": datetime.datetime.utcnow()    # Record creation timestamp
        }
        # Basic validation for required fields
        if not new_child["name"] or not new_child["birthday"]:
            raise ValueError("Missing required fields: name and birthday")
        # Add more validation as needed (e.g., birthday format)

        # Insert the new child document into the 'children' collection
        result = db.children.insert_one(new_child)
        # Return the string representation of the new ObjectId
        return str(result.inserted_id)
    except OperationFailure as e:
        # Handle potential MongoDB operation errors (e.g., network issues, write concerns)
        current_app.logger.error(f"Database error creating child record: {e}")
        raise # Re-raise database errors to be handled by the route
    except (ValueError, TypeError) as e:
        # Handle validation errors (missing fields, bad data types)
        current_app.logger.error(f"Validation error during child creation: {e}")
        raise ValueError(f"Invalid data for child creation: {e}")
    except Exception as e: # Catch ObjectId conversion errors etc.
        current_app.logger.error(f"Unexpected error processing child creation: {e}", exc_info=True)
        # Re-raise as ValueError for consistency in route handling
        raise ValueError(f"Error processing child creation: {e}")


def get_child_by_id(child_id: str) -> dict | None:
    """Gets a child document from the 'children' collection by its ID string."""
    db = get_db()
    try:
        # Convert string ID to ObjectId for querying
        obj_id = ObjectId(child_id)
        child = db.children.find_one({"_id": obj_id})
        # Serialize the document (convert ObjectIds to strings) before returning
        return serialize_doc(child)
    except Exception as e: # Handles invalid ObjectId format or other errors
        current_app.logger.warning(f"Error finding child by ID {child_id}: {e}")
        return None

def update_child_details(child_id: str, update_data: dict) -> bool:
    """Updates specific allowed fields of a child's profile in the 'children' collection."""
    db = get_db()
    # Define fields that are allowed to be updated via this function
    allowed_updates = ["group", "allergies", "notes", "name", "birthday"]
    update_payload = {"$set": {}}
    updated = False

    # Build the $set payload only with allowed fields present in update_data
    for key, value in update_data.items():
        if key in allowed_updates:
            # Add specific validation here if needed (e.g., check birthday format)
            update_payload["$set"][key] = value
            updated = True

    # If no valid fields were provided for update, return False
    if not updated:
        current_app.logger.info(f"No valid fields provided for updating child {child_id}")
        return False

    try:
        obj_id = ObjectId(child_id)
        # Perform the update operation
        result = db.children.update_one({"_id": obj_id}, update_payload)
        # Return True if a document was found (matched_count > 0)
        return result.matched_count > 0
    except OperationFailure as e:
        current_app.logger.error(f"Database error updating child details {child_id}: {e}")
        raise
    except Exception as e: # Invalid ObjectId format or other error
        current_app.logger.warning(f"Error updating child details {child_id}: {e}")
        return False

def link_supervisor_to_child(child_id: str, supervisor_id: str) -> bool:
    """Adds a supervisor ID (as ObjectId) to a child's supervisor_ids list if not already present."""
    db = get_db()
    try:
        child_obj_id = ObjectId(child_id)
        supervisor_obj_id = ObjectId(supervisor_id)
        # Use $addToSet to add the supervisor ID only if it doesn't already exist in the array
        # This prevents duplicates automatically.
        result = db.children.update_one(
            {"_id": child_obj_id},
            {"$addToSet": {"supervisor_ids": supervisor_obj_id}}
        )
        # Return True if the child document was found (matched_count > 0)
        # modified_count will be 0 if the supervisor was already in the set.
        return result.matched_count > 0
    except OperationFailure as e:
        current_app.logger.error(f"Database error linking supervisor {supervisor_id} to child {child_id}: {e}")
        raise
    except Exception as e: # Invalid ObjectId format or other error
        current_app.logger.warning(f"Error linking supervisor: {e}")
        return False

# --- Authorization Helper Functions ---

def is_parent_of(user_id: str, child_id: str) -> bool:
    """Checks if the user_id is listed in the child's parent_ids."""
    db = get_db()
    try:
        child_obj_id = ObjectId(child_id)
        user_obj_id = ObjectId(user_id)
        # Efficiently check for existence using count_documents (or find_one with projection)
        count = db.children.count_documents({"_id": child_obj_id, "parent_ids": user_obj_id})
        return count > 0
    except Exception as e: # Invalid ObjectId format or other DB error
        current_app.logger.error(f"Error checking parent relationship (user: {user_id}, child: {child_id}): {e}")
        return False

def is_supervisor_of(user_id: str, child_id: str) -> bool:
    """Checks if the user_id is listed in the child's supervisor_ids."""
    db = get_db()
    try:
        child_obj_id = ObjectId(child_id)
        user_obj_id = ObjectId(user_id)
        # Efficiently check for existence
        count = db.children.count_documents({"_id": child_obj_id, "supervisor_ids": user_obj_id})
        return count > 0
    except Exception as e: # Invalid ObjectId format or other DB error
        current_app.logger.error(f"Error checking supervisor relationship (user: {user_id}, child: {child_id}): {e}")
        return False

# --- Functions to get associated children ---

def get_children_for_parent(parent_id: str) -> list[dict]:
    """Gets basic info (_id, name) for children associated with a parent."""
    db = get_db()
    try:
        parent_obj_id = ObjectId(parent_id)
        # Find children where parent_id is in the parent_ids array
        # Project only the _id and name fields for efficiency
        children_cursor = db.children.find(
            {"parent_ids": parent_obj_id},
            {"_id": 1, "name": 1} # Projection: only return ID and name
        )
        # Serialize the results (_id to string)
        children_list = [serialize_doc(child) for child in children_cursor]
        return children_list
    except Exception as e: # Invalid ObjectId format or other DB error
        current_app.logger.error(f"Error getting children for parent {parent_id}: {e}")
        return []

def get_children_for_supervisor(supervisor_id: str) -> list[dict]:
    """Gets basic info (_id, name) for children associated with a supervisor."""
    db = get_db()
    try:
        supervisor_obj_id = ObjectId(supervisor_id)
        # Find children where supervisor_id is in the supervisor_ids array
        # Project only _id and name
        children_cursor = db.children.find(
            {"supervisor_ids": supervisor_obj_id},
            {"_id": 1, "name": 1} # Projection
        )
        # Serialize the results
        children_list = [serialize_doc(child) for child in children_cursor]
        return children_list
    except Exception as e: # Invalid ObjectId format or other DB error
        current_app.logger.error(f"Error getting children for supervisor {supervisor_id}: {e}")
        return []


# --- Activities CRUD Functions (Includes Drawings as type='drawing') ---

def add_activity_record(activity_data: dict) -> str:
    """
    Adds a generic activity record (meal, sleep, behavior, drawing, etc.)
    to the 'activities' collection.
    """
    db = get_db()
    try:
        # --- Validation ---
        required_fields = ['child_id', 'type', 'details', 'logged_by']
        missing = [field for field in required_fields if not activity_data.get(field)]
        if missing:
            raise ValueError(f"Missing required fields for activity: {', '.join(missing)}")

        # Validate ObjectId formats
        child_obj_id = ObjectId(activity_data['child_id'])
        logged_by_obj_id = ObjectId(activity_data['logged_by'])

        # Ensure details is a dictionary (or handle other types if needed)
        if not isinstance(activity_data['details'], dict):
             raise ValueError("Activity 'details' must be an object/dictionary")

        # Add specific validation based on type if necessary
        activity_type = activity_data['type']
        if activity_type == 'drawing':
            if not activity_data['details'].get('image_url'):
                 raise ValueError("Missing 'image_url' in details for drawing activity")
        # Add more type-specific validations here...

        # --- Preparation ---
        # Ensure creation timestamp is set
        if 'created_at' not in activity_data:
            activity_data['created_at'] = datetime.datetime.utcnow()

        # Ensure IDs are stored as ObjectIds
        activity_data['child_id'] = child_obj_id
        activity_data['logged_by'] = logged_by_obj_id

        # --- Insertion ---
        result = db.activities.insert_one(activity_data)
        return str(result.inserted_id)

    except OperationFailure as e:
        current_app.logger.error(f"Database error adding activity: {e}")
        raise # Re-raise DB errors
    except (ValueError, TypeError) as e: # Catch validation and ObjectId errors
        current_app.logger.error(f"Validation error adding activity: {e}")
        raise ValueError(f"Invalid data for activity creation: {e}") # Re-raise as ValueError
    except Exception as e:
        current_app.logger.error(f"Unexpected error adding activity: {e}", exc_info=True)
        raise ValueError(f"Unexpected error processing activity: {e}")


def get_activities_for_child(child_id: str, activity_type: str = None, start_date: datetime.datetime = None, end_date: datetime.datetime = None) -> list[dict]:
    """
    Gets activity records for a specific child from the 'activities' collection,
    optionally filtered by activity type and date range.
    """
    db = get_db()
    try:
        # Validate child_id format first
        obj_id = ObjectId(child_id)
        query = {"child_id": obj_id} # Query using ObjectId

        # Add optional filters to the query
        if activity_type:
            # Allow filtering by a list of types if needed in future
            if isinstance(activity_type, list):
                 query["type"] = {"$in": activity_type}
            else:
                 query["type"] = activity_type

        # Build date range filter
        date_filter = {}
        if start_date:
            date_filter["$gte"] = start_date
        if end_date:
            # Ensure end_date is exclusive ($lt)
            date_filter["$lt"] = end_date
        if date_filter:
            query["created_at"] = date_filter

        # Execute query and sort by creation time descending (newest first)
        activities_cursor = db.activities.find(query).sort("created_at", -1)

        # Serialize results before returning
        return [serialize_doc(activity) for activity in activities_cursor]

    except OperationFailure as e:
        current_app.logger.error(f"Database error getting activities for child {child_id}: {e}")
        raise # Re-raise DB errors
    except Exception as e: # Invalid ObjectId or other error
        current_app.logger.error(f"Error getting activities for child {child_id}: {e}")
        # Re-raise as ValueError for consistency
        raise ValueError(f"Invalid parameters for getting activities: {e}")

def get_activity_by_id(activity_id: str) -> dict | None:
    """Gets a single activity document by its ID."""
    db = get_db()
    try:
        obj_id = ObjectId(activity_id)
        activity = db.activities.find_one({"_id": obj_id})
        return serialize_doc(activity) # Serialize before returning
    except Exception as e: # Invalid ObjectId format or DB error
        current_app.logger.warning(f"Error finding activity by ID {activity_id}: {e}")
        return None

def delete_activity_record(activity_id: str) -> bool:
    """
    Deletes a single activity record from the 'activities' collection by its ID.
    Returns True if an activity was deleted, False otherwise.
    """
    db = get_db()
    try:
        obj_id = ObjectId(activity_id)
        # Perform the delete operation
        result = db.activities.delete_one({"_id": obj_id})
        # Check if a document was actually deleted
        if result.deleted_count > 0:
            current_app.logger.info(f"Deleted activity record with ID: {activity_id}")
            return True
        else:
            # Activity ID was valid format, but no document found
            current_app.logger.warning(f"Attempted to delete non-existent activity: {activity_id}")
            return False
    except OperationFailure as e:
        current_app.logger.error(f"Database error deleting activity {activity_id}: {e}")
        raise # Re-raise DB errors
    except Exception as e: # Invalid ObjectId format or other error
        current_app.logger.error(f"Error deleting activity {activity_id}: {e}")
        # Treat invalid ID format as non-existent for deletion purposes
        return False

