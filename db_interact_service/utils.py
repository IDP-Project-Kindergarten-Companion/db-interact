from bson import ObjectId


# --- Helper to convert ObjectIds in documents ---
def serialize_doc(doc):
    """Converts ObjectId fields to string for JSON serialization."""
    if not doc:
        return doc
    # Convert main _id
    if '_id' in doc and isinstance(doc['_id'], ObjectId):
        doc['_id'] = str(doc['_id'])
    # Convert ObjectIds in parent_ids list
    if 'parent_ids' in doc and isinstance(doc['parent_ids'], list):
        doc['parent_ids'] = [str(pid) for pid in doc.get('parent_ids', []) if isinstance(pid, ObjectId)]
    # Convert ObjectIds in supervisor_ids list
    if 'supervisor_ids' in doc and isinstance(doc['supervisor_ids'], list):
        doc['supervisor_ids'] = [str(sid) for sid in doc.get('supervisor_ids', []) if isinstance(sid, ObjectId)]
    # Convert child_id if present (e.g., in activity docs)
    if 'child_id' in doc and isinstance(doc['child_id'], ObjectId):
        doc['child_id'] = str(doc['child_id'])
    # Convert logged_by if present (e.g., in activity docs)
    if 'logged_by' in doc and isinstance(doc['logged_by'], ObjectId):
        doc['logged_by'] = str(doc['logged_by'])
    # Add more conversions here if other fields store ObjectIds
    return doc