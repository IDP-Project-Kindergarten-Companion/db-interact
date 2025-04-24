# --- db_interact_service/models.py ---
import datetime
from pymongo import MongoClient
from pymongo.uri_parser import parse_uri
from pymongo.errors import ConnectionFailure, OperationFailure
from flask import current_app, g
from bson import ObjectId # For handling MongoDB ObjectIDs

# --- Database Connection Handling ---

def get_db():
    """
    Opens a new database connection for the operational DB if there is
    none yet for the current application context. Returns the database object.
    """
    if 'operational_mongo_db' not in g:
        mongo_uri = current_app.config['MONGO_URI']
        try:
            uri_dict = parse_uri(mongo_uri)
            db_name = uri_dict.get('database')
            if not db_name:
                raise ValueError(f"Operational database name not found in MONGO_URI: {mongo_uri}")

            g.operational_mongo_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
            g.operational_mongo_client.admin.command('ismaster') # Check connection
            g.operational_mongo_db = g.operational_mongo_client[db_name]
            current_app.logger.info(f"Connected to operational DB: {db_name}")

        except ConnectionFailure as e:
             current_app.logger.error(f"Operational DB connection failed: {e}")
             g.operational_mongo_db = None
             raise ConnectionFailure(f"Could not connect to operational database: {e}")
        except ValueError as e:
             current_app.logger.error(f"Configuration error: {e}")
             g.operational_mongo_db = None
             raise ValueError(f"Configuration error: {e}")

    if g.operational_mongo_db is None:
        raise ConnectionFailure("Operational database connection previously failed in this context.")

    return g.operational_mongo_db

def close_db(e=None):
    """Closes the operational database connection."""
    client = g.pop('operational_mongo_client', None)
    if client is not None:
        client.close()
        current_app.logger.info("Closed operational DB connection.")
    g.pop('operational_mongo_db', None)


# --- Example CRUD Functions ---
# Add functions specific to your data models (activities, drawings, child profiles etc.)

def add_activity_record(activity_data: dict) -> str:
    """Adds a generic activity record to the 'activities' collection."""
    db = get_db()
    try:
        if 'created_at' not in activity_data:
            activity_data['created_at'] = datetime.datetime.utcnow()
        result = db.activities.insert_one(activity_data)
        return str(result.inserted_id)
    except OperationFailure as e:
        current_app.logger.error(f"Failed to add activity: {e}")
        raise

def get_activities_for_child(child_id: str, start_date: datetime.datetime = None, end_date: datetime.datetime = None) -> list[dict]:
    """Gets activity records for a specific child, optionally filtered by date."""
    db = get_db()
    query = {"child_id": child_id}
    # Add date filtering logic here...
    try:
        activities = list(db.activities.find(query).sort("created_at", -1))
        for activity in activities:
            activity['_id'] = str(activity['_id'])
        return activities
    except OperationFailure as e:
        current_app.logger.error(f"Failed to get activities: {e}")
        raise

# Add more functions for drawings, child profiles etc.
# def save_drawing_metadata(...)
# def get_drawings_for_child(...)
# def get_child_profile(...)
# def update_child_profile(...)

