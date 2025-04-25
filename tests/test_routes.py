# tests/test_integration.py
import pytest
import requests
import time
import uuid # To generate unique usernames/emails for each run
import os # To read environment variables for URLs
from bson import ObjectId # To create valid/invalid ObjectIds for testing
import datetime # <--- Added import for datetime

# --- Configuration ---
AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://localhost:8081")
# --- Use port 8082 as confirmed by user ---
DB_INTERACT_URL = os.environ.get("DB_INTERACT_URL", "http://localhost:8082")
# --- End Port Correction ---

# --- Test Data ---
# Use functions to generate unique data for each test run
def generate_unique_user(role="parent"):
    """Generates unique user data for testing."""
    unique_id = str(uuid.uuid4())[:8] # Short unique ID
    if role == "parent":
        return {
            "username": f"pytest_parent_{unique_id}",
            "password": "password123",
            "role": "parent",
            "email": f"pytest_parent_{unique_id}@example.com",
            "first_name": "PytestParent",
            "last_name": unique_id
        }
    else: # teacher
        return {
            "username": f"pytest_teacher_{unique_id}",
            "password": "password456",
            "role": "teacher",
            "email": f"pytest_teacher_{unique_id}@example.com",
            "first_name": "PytestTeacher",
            "last_name": unique_id
        }

CHILD_DATA_TEMPLATE = {
    "name": "Pytest Child",
    "birthday": "2022-02-20", # Ensure YYYY-MM-DD format
    "group": "Testers",
    "allergies": ["Flaky Tests"],
    "notes": "Needs stable environment"
}
ACTIVITY_DATA_TEMPLATE = {
    "type": "sleep", # Example type
    "details": {
        "duration_minutes": 60,
        "quality": "restful",
        "notes": "Dreaming of passing tests."
    }
    # child_id and logged_by will be added dynamically
}

# --- Fixtures for Setup Steps (Session Scoped) ---

@pytest.fixture(scope="session")
def http_session():
    """Provides a requests session for making HTTP calls."""
    with requests.Session() as session:
        session.headers.update({"Content-Type": "application/json"})
        yield session

@pytest.fixture(scope="session")
def test_users(http_session):
    """Registers a parent and teacher user ONCE for the test session."""
    print("\nSetting up test users (session scope)...")
    parent_data = generate_unique_user("parent")
    teacher_data = generate_unique_user("teacher")

    # Register Parent
    try:
        reg_parent_response = http_session.post(f"{AUTH_SERVICE_URL}/auth/register", json=parent_data, timeout=10)
        reg_parent_response.raise_for_status() # Raise exception for 4xx/5xx
        assert reg_parent_response.status_code == 201, f"Parent registration unexpected status: {reg_parent_response.status_code}"
    except requests.exceptions.RequestException as e:
        # Check if it failed because user already exists (status 409)
        if isinstance(e, requests.exceptions.HTTPError) and e.response.status_code == 409:
            print(f"Parent user {parent_data['username']} likely already exists.")
        else:
            pytest.fail(f"Parent registration failed: {e}")
    except Exception as e:
         pytest.fail(f"Parent registration failed with unexpected error: {e}")


    # Register Teacher
    try:
        reg_teacher_response = http_session.post(f"{AUTH_SERVICE_URL}/auth/register", json=teacher_data, timeout=10)
        reg_teacher_response.raise_for_status()
        assert reg_teacher_response.status_code == 201, f"Teacher registration unexpected status: {reg_teacher_response.status_code}"
    except requests.exceptions.RequestException as e:
        if isinstance(e, requests.exceptions.HTTPError) and e.response.status_code == 409:
             print(f"Teacher user {teacher_data['username']} likely already exists.")
        else:
            pytest.fail(f"Teacher registration failed: {e}")
    except Exception as e:
         pytest.fail(f"Teacher registration failed with unexpected error: {e}")


    print(f"Test users registered or already exist (Parent: {parent_data['username']}, Teacher: {teacher_data['username']}).")
    # Return the data used, including passwords, for login fixture
    return {"parent": parent_data, "teacher": teacher_data}

# Fixture to register and login a SECOND parent for authorization tests
@pytest.fixture(scope="session")
def second_parent_user(http_session):
    """Registers and logs in a second parent user."""
    print("\nSetting up second parent user...")
    parent_data_2 = generate_unique_user("parent")

    # Register Second Parent
    try:
        reg_response = http_session.post(f"{AUTH_SERVICE_URL}/auth/register", json=parent_data_2, timeout=10)
        reg_response.raise_for_status()
        assert reg_response.status_code == 201
    except requests.exceptions.RequestException as e:
        if isinstance(e, requests.exceptions.HTTPError) and e.response.status_code == 409:
            print(f"Second parent user {parent_data_2['username']} likely already exists.")
        else:
            pytest.fail(f"Second parent registration failed: {e}")
    except Exception as e:
         pytest.fail(f"Second parent registration failed with unexpected error: {e}")

    # Login Second Parent
    login_data = {"username": parent_data_2["username"], "password": parent_data_2["password"]}
    login_response = http_session.post(f"{AUTH_SERVICE_URL}/auth/login", json=login_data)
    assert login_response.status_code == 200, f"Second parent login failed: {login_response.text}"
    login_json = login_response.json()
    token = login_json.get("access_token")
    user_id = login_json.get("user_id")
    assert token and user_id, "Second parent login response missing token or user_id"
    print(f"Second parent logged in. User ID: {user_id}")
    return {"token": token, "id": user_id}


# Function scope might be better for login if tokens expire during long test runs,
# but session scope is okay if tests are fast and token expiry is long enough.
@pytest.fixture(scope="session")
def logged_in_users(test_users, http_session):
    """Logs in the registered test users ONCE and returns tokens/IDs."""
    print("\nLogging in test users (session scope)...")
    tokens = {}
    user_ids = {}

    # Login Parent
    parent_login_data = {"username": test_users["parent"]["username"], "password": test_users["parent"]["password"]}
    parent_login_response = http_session.post(f"{AUTH_SERVICE_URL}/auth/login", json=parent_login_data)
    assert parent_login_response.status_code == 200, f"Parent login failed: {parent_login_response.text}"
    parent_login_json = parent_login_response.json()
    tokens["parent"] = parent_login_json.get("access_token")
    user_ids["parent"] = parent_login_json.get("user_id")
    assert tokens["parent"] and user_ids["parent"], "Parent login response missing token or user_id"
    print(f"Parent logged in. User ID: {user_ids['parent']}")

    # Login Teacher
    teacher_login_data = {"username": test_users["teacher"]["username"], "password": test_users["teacher"]["password"]}
    teacher_login_response = http_session.post(f"{AUTH_SERVICE_URL}/auth/login", json=teacher_login_data)
    assert teacher_login_response.status_code == 200, f"Teacher login failed: {teacher_login_response.text}"
    teacher_login_json = teacher_login_response.json()
    tokens["teacher"] = teacher_login_json.get("access_token")
    user_ids["teacher"] = teacher_login_json.get("user_id")
    assert tokens["teacher"] and user_ids["teacher"], "Teacher login response missing token or user_id"
    print(f"Teacher logged in. User ID: {user_ids['teacher']}")

    return {"tokens": tokens, "ids": user_ids}


# --- Fixtures with FUNCTION Scope ---
# These will run for EACH test function that uses them

@pytest.fixture(scope="function") # Changed scope
def created_child_id(logged_in_users, http_session):
    """Creates a child record using the parent token for EACH test."""
    print("\nCreating child record (function scope)...")
    parent_token = logged_in_users["tokens"]["parent"]
    headers = {"Authorization": f"Bearer {parent_token}"}

    response = http_session.post(f"{DB_INTERACT_URL}/internal/children", headers=headers, json=CHILD_DATA_TEMPLATE)
    assert response.status_code == 201, f"Child creation failed: {response.status_code} - {response.text}"
    child_data = response.json()
    child_id = child_data.get("child_id")
    assert child_id, "Child creation response missing child_id"
    print(f"Child created for test. ID: {child_id}")
    # No yield needed, just return the ID for this function's run
    return child_id

@pytest.fixture(scope="function") # Changed scope
def linked_child_supervisor(created_child_id, logged_in_users, http_session):
    """Links the test supervisor to the created child for EACH test and VERIFIES."""
    print("\nLinking supervisor (function scope)...")
    teacher_token = logged_in_users["tokens"]["teacher"]
    teacher_id = logged_in_users["ids"]["teacher"]
    parent_token = logged_in_users["tokens"]["parent"] # Need a token to verify
    headers_teacher = {"Authorization": f"Bearer {teacher_token}"}
    headers_parent = {"Authorization": f"Bearer {parent_token}"}
    link_data = {"supervisor_id": teacher_id}
    link_endpoint = f"/internal/children/{created_child_id}/link-supervisor"
    # Use the /data endpoint for verification as it includes authorization checks
    child_data_endpoint = f"/data/children/{created_child_id}"

    # --- Attempt Link ---
    response_link = http_session.put(f"{DB_INTERACT_URL}{link_endpoint}", headers=headers_teacher, json=link_data)
    assert response_link.status_code == 200, f"Supervisor linking PUT request failed: {response_link.text}"
    print("Supervisor link API call successful.")

    # --- Verification Step ---
    print("Verifying supervisor link by fetching child data...")
    # It might take a very short time for the update to be fully consistent in the DB
    time.sleep(0.5)
    response_verify = http_session.get(f"{DB_INTERACT_URL}{child_data_endpoint}", headers=headers_parent) # Use parent token to fetch
    assert response_verify.status_code == 200, f"Verification fetch failed: {response_verify.status_code} - {response_verify.text}"
    child_data = response_verify.json()
    supervisor_ids = child_data.get("supervisor_ids", [])
    assert isinstance(supervisor_ids, list), f"supervisor_ids is not a list: {supervisor_ids}"
    assert teacher_id in supervisor_ids, f"Teacher ID {teacher_id} not found in supervisor_ids {supervisor_ids} after linking"
    print(f"Supervisor link VERIFIED for test. Teacher ID {teacher_id} found in supervisor_ids.")

    # Return child_id for dependency chain within this function's scope
    return created_child_id

@pytest.fixture(scope="function") # Changed scope
def created_activity_id(linked_child_supervisor, logged_in_users, http_session):
    """Adds an activity record for the child using the teacher token for EACH test."""
    print("\nAdding activity record (function scope)...")
    child_id = linked_child_supervisor # Use the child ID from the linked fixture for this function run
    teacher_token = logged_in_users["tokens"]["teacher"]
    headers = {"Authorization": f"Bearer {teacher_token}"}

    # Prepare activity data, ensuring child_id is included
    activity_data = ACTIVITY_DATA_TEMPLATE.copy()
    activity_data["child_id"] = child_id
    # Note: 'logged_by' is added by the route handler using g.current_user_id

    response = http_session.post(f"{DB_INTERACT_URL}/internal/activities", headers=headers, json=activity_data)
    assert response.status_code == 201, f"Activity creation failed: {response.status_code} - {response.text}"
    activity_response_data = response.json()
    activity_id = activity_response_data.get("activity_id")
    assert activity_id, "Activity creation response missing activity_id"
    print(f"Activity created for test. ID: {activity_id}")
    # Return the activity ID for this function's run
    return activity_id


# --- Test Functions ---
# These tests now implicitly use the function-scoped fixtures, ensuring
# the child is created and supervisor linked before each test runs.

def test_get_child_data(logged_in_users, linked_child_supervisor, http_session):
    """Verify both parent and teacher can get child data AFTER linking."""
    print("\nTesting GET /data/children/{child_id}...")
    parent_token = logged_in_users["tokens"]["parent"]
    teacher_token = logged_in_users["tokens"]["teacher"]
    # Get the child_id specific to this test run from the fixture
    child_id = linked_child_supervisor
    endpoint = f"/data/children/{child_id}"

    # Test as Parent
    headers_parent = {"Authorization": f"Bearer {parent_token}"}
    response_parent = http_session.get(f"{DB_INTERACT_URL}{endpoint}", headers=headers_parent)
    assert response_parent.status_code == 200, f"Parent failed to get child data: {response_parent.text}"
    parent_child_data = response_parent.json()
    assert parent_child_data["_id"] == child_id
    assert parent_child_data["name"] == CHILD_DATA_TEMPLATE["name"]
    print("Get child data as Parent: OK")

    # Test as Teacher (Should pass now)
    headers_teacher = {"Authorization": f"Bearer {teacher_token}"}
    response_teacher = http_session.get(f"{DB_INTERACT_URL}{endpoint}", headers=headers_teacher)
    assert response_teacher.status_code == 200, f"Teacher failed to get child data: {response_teacher.text}"
    teacher_child_data = response_teacher.json()
    assert teacher_child_data["_id"] == child_id
    print("Get child data as Teacher: OK")

def test_get_children_list(logged_in_users, linked_child_supervisor, http_session):
    """Verify parent and teacher get the created child in their lists AFTER linking."""
    print("\nTesting GET /data/children...")
    parent_token = logged_in_users["tokens"]["parent"]
    teacher_token = logged_in_users["tokens"]["teacher"]
    # Get the child_id specific to this test run from the fixture
    child_id = linked_child_supervisor
    endpoint = "/data/children"

    # Test as Parent
    headers_parent = {"Authorization": f"Bearer {parent_token}"}
    response_parent = http_session.get(f"{DB_INTERACT_URL}{endpoint}", headers=headers_parent)
    assert response_parent.status_code == 200
    parent_children = response_parent.json()
    assert isinstance(parent_children, list)
    # Check if *any* child in the list matches the ID created for *this test run*
    assert any(child['_id'] == child_id for child in parent_children), f"Created child {child_id} not found in parent's list {parent_children}"
    print("Get children list as Parent: OK")

    # Test as Teacher (Should pass now)
    headers_teacher = {"Authorization": f"Bearer {teacher_token}"}
    response_teacher = http_session.get(f"{DB_INTERACT_URL}{endpoint}", headers=headers_teacher)
    assert response_teacher.status_code == 200
    teacher_children = response_teacher.json()
    assert isinstance(teacher_children, list)
    # Check if *any* child in the list matches the ID created for *this test run*
    assert any(child['_id'] == child_id for child in teacher_children), f"Created child {child_id} not found in teacher's list {teacher_children}"
    print("Get children list as Teacher: OK")

def test_get_activities(logged_in_users, linked_child_supervisor, created_activity_id, http_session):
    """Verify parent and teacher can get activities, including filtering."""
    print("\nTesting GET /data/activities...")
    parent_token = logged_in_users["tokens"]["parent"]
    teacher_token = logged_in_users["tokens"]["teacher"]
    # Get IDs specific to this test run from fixtures
    child_id = linked_child_supervisor
    activity_id = created_activity_id
    endpoint = f"/data/activities?child_id={child_id}"

    # Test as Parent
    headers_parent = {"Authorization": f"Bearer {parent_token}"}
    response_parent = http_session.get(f"{DB_INTERACT_URL}{endpoint}", headers=headers_parent)
    assert response_parent.status_code == 200
    parent_activities = response_parent.json()
    assert isinstance(parent_activities, list)
    assert any(act['_id'] == activity_id for act in parent_activities), f"Created activity {activity_id} not found in parent's get: {parent_activities}"
    print("Get activities as Parent: OK")

    # Test as Teacher
    headers_teacher = {"Authorization": f"Bearer {teacher_token}"}
    response_teacher = http_session.get(f"{DB_INTERACT_URL}{endpoint}", headers=headers_teacher)
    assert response_teacher.status_code == 200
    teacher_activities = response_teacher.json()
    assert isinstance(teacher_activities, list)
    assert any(act['_id'] == activity_id for act in teacher_activities), f"Created activity {activity_id} not found in teacher's get: {teacher_activities}"
    print("Get activities as Teacher: OK")

    # Test Filtering (as Teacher) - Use the type from ACTIVITY_DATA_TEMPLATE
    activity_type = ACTIVITY_DATA_TEMPLATE['type']
    endpoint_filtered = f"/data/activities?child_id={child_id}&type={activity_type}"
    response_filtered = http_session.get(f"{DB_INTERACT_URL}{endpoint_filtered}", headers=headers_teacher)
    assert response_filtered.status_code == 200
    filtered_activities = response_filtered.json()
    assert isinstance(filtered_activities, list)
    assert len(filtered_activities) > 0, f"No activities found when filtering for type '{activity_type}'"
    assert all(act['type'] == activity_type for act in filtered_activities), "Filtering by type returned activities of wrong type"
    assert any(act['_id'] == activity_id for act in filtered_activities), "Created activity not found when filtering by correct type"
    print(f"Get activities filtered by type '{activity_type}': OK")

    # Test filtering by a type that wasn't added
    wrong_activity_type = 'meal' if activity_type != 'meal' else 'behavior'
    endpoint_filtered_wrong = f"/data/activities?child_id={child_id}&type={wrong_activity_type}"
    response_filtered_wrong = http_session.get(f"{DB_INTERACT_URL}{endpoint_filtered_wrong}", headers=headers_teacher)
    assert response_filtered_wrong.status_code == 200
    assert response_filtered_wrong.json() == [], f"Filtering by wrong type '{wrong_activity_type}' should return empty list"
    print(f"Get activities filtered by wrong type '{wrong_activity_type}': OK")


def test_delete_activity_permissions_and_verify(logged_in_users, linked_child_supervisor, created_activity_id, http_session):
    """Verify parent cannot delete, teacher can delete, and verify deletion."""
    print("\nTesting DELETE /data/activities/{activity_id} permissions...")
    parent_token = logged_in_users["tokens"]["parent"]
    teacher_token = logged_in_users["tokens"]["teacher"]
    # Get IDs specific to this test run from fixtures
    child_id = linked_child_supervisor
    activity_id = created_activity_id
    endpoint = f"/data/activities/{activity_id}"

    # Attempt Delete as Parent (Should Fail 403)
    print("Attempting delete as Parent...")
    headers_parent = {"Authorization": f"Bearer {parent_token}"}
    response_parent_delete = http_session.delete(f"{DB_INTERACT_URL}{endpoint}", headers=headers_parent)
    assert response_parent_delete.status_code == 403, f"Parent deletion did not fail with 403: {response_parent_delete.status_code} - {response_parent_delete.text}"
    print("Delete as Parent: Forbidden (OK)")

    # Attempt Delete as Teacher (Should Succeed 200)
    print("Attempting delete as Teacher...")
    headers_teacher = {"Authorization": f"Bearer {teacher_token}"}
    response_teacher_delete = http_session.delete(f"{DB_INTERACT_URL}{endpoint}", headers=headers_teacher)
    assert response_teacher_delete.status_code == 200, f"Teacher deletion failed: {response_teacher_delete.text}"
    print("Delete as Teacher: OK")

    # Verify Deletion by trying to get activities again (Should be empty list for that activity)
    print("Verifying deletion...")
    time.sleep(0.5) # Give DB a moment
    verify_endpoint = f"/data/activities?child_id={child_id}"
    response_verify = http_session.get(f"{DB_INTERACT_URL}{verify_endpoint}", headers=headers_teacher)
    assert response_verify.status_code == 200
    activities_after_delete = response_verify.json()
    assert isinstance(activities_after_delete, list)
    assert not any(act['_id'] == activity_id for act in activities_after_delete), f"Deleted activity {activity_id} still found in list: {activities_after_delete}"
    print("Verify deletion: OK (Activity no longer listed)")

# --- New Tests ---

def test_update_child_details(logged_in_users, linked_child_supervisor, http_session):
    """Test updating allowed child details via internal endpoint."""
    print("\nTesting PUT /internal/children/{child_id}...")
    # Use teacher token as an example authorized caller (though permissions are assumed checked by calling service)
    teacher_token = logged_in_users["tokens"]["teacher"]
    child_id = linked_child_supervisor
    headers = {"Authorization": f"Bearer {teacher_token}"}
    endpoint = f"/internal/children/{child_id}"
    update_payload = {
        "group": "Butterflies",
        "notes": "Updated notes for test.",
        "allergies": ["Pollen", "Flaky Tests"], # Overwrite allergies
        "invalid_field": "should_be_ignored" # This field should not be updated
    }

    response_update = http_session.put(f"{DB_INTERACT_URL}{endpoint}", headers=headers, json=update_payload)
    assert response_update.status_code == 200, f"Update child failed: {response_update.text}"
    assert response_update.json()["message"] == "Child details updated"
    print("Update API call: OK")

    # Verify the update by fetching the data again
    time.sleep(0.5)
    response_verify = http_session.get(f"{DB_INTERACT_URL}/data/children/{child_id}", headers=headers) # Use teacher token to fetch
    assert response_verify.status_code == 200
    updated_data = response_verify.json()
    assert updated_data["group"] == "Butterflies"
    assert updated_data["notes"] == "Updated notes for test."
    assert updated_data["allergies"] == ["Pollen", "Flaky Tests"]
    assert "invalid_field" not in updated_data # Ensure only allowed fields were updated
    print("Verify child update: OK")

def test_get_activities_date_filter(logged_in_users, linked_child_supervisor, http_session):
    """Test getting activities with date range filtering."""
    print("\nTesting GET /data/activities with date filters...")
    teacher_token = logged_in_users["tokens"]["teacher"]
    child_id = linked_child_supervisor
    headers = {"Authorization": f"Bearer {teacher_token}"}

    # Note: This test assumes activities might exist across different dates.
    # A more robust test would explicitly create activities with specific dates first.
    # For now, we just test the endpoint's response to date parameters.

    # Test date range including only the second activity (Example dates)
    start_date = "2025-04-21"
    end_date = "2025-04-23" # Exclusive, so includes 21st and 22nd
    endpoint = f"/data/activities?child_id={child_id}&start_date={start_date}&end_date={end_date}"
    response = http_session.get(f"{DB_INTERACT_URL}{endpoint}", headers=headers)
    assert response.status_code == 200, f"Request with date filter failed: {response.text}"
    activities = response.json()
    assert isinstance(activities, list)
    # Cannot assert exact content without creating specific dated activities first
    print(f"Get activities with date filter ({start_date} to {end_date}): OK (Status 200 received)")

    # Test date range including no activities
    start_date_no = "2026-01-01" # A date likely in the future
    endpoint_no = f"/data/activities?child_id={child_id}&start_date={start_date_no}"
    response_no = http_session.get(f"{DB_INTERACT_URL}{endpoint_no}", headers=headers)
    assert response_no.status_code == 200, f"Request with future date filter failed: {response_no.text}"
    assert response_no.json() == [], "Date filter for future should return empty list"
    print(f"Get activities with date filter ({start_date_no} onwards): OK (Empty list)")


def test_get_non_existent_child(logged_in_users, http_session):
    """Test getting data for a child ID that does not exist."""
    print("\nTesting GET /data/children/{invalid_id}...")
    parent_token = logged_in_users["tokens"]["parent"]
    headers = {"Authorization": f"Bearer {parent_token}"}
    invalid_id = str(ObjectId()) # Generate a valid format but non-existent ID
    endpoint = f"/data/children/{invalid_id}"

    response = http_session.get(f"{DB_INTERACT_URL}{endpoint}", headers=headers)
    # --- Corrected Assertion ---
    # Expect 403 (Forbidden because auth check runs first and fails for non-existent ID)
    # or 404 (if route logic changes to check existence first)
    assert response.status_code in [403, 404], f"Expected 403 or 404 for non-existent child, got {response.status_code}"
    if response.status_code == 403:
        assert "Forbidden" in response.json().get("message", "")
        print("Get non-existent child: Forbidden (OK - Auth check failed)")
    else: # 404
        assert "Child not found" in response.json().get("message", "")
        print("Get non-existent child: Not Found (OK - Existence check failed)")
    # --- End Correction ---


def test_delete_non_existent_activity(logged_in_users, http_session):
    """Test deleting an activity ID that does not exist."""
    print("\nTesting DELETE /data/activities/{invalid_id}...")
    teacher_token = logged_in_users["tokens"]["teacher"]
    headers = {"Authorization": f"Bearer {teacher_token}"}
    invalid_id = str(ObjectId()) # Generate a valid format but non-existent ID
    endpoint = f"/data/activities/{invalid_id}"

    response = http_session.delete(f"{DB_INTERACT_URL}{endpoint}", headers=headers)
    # Expect 404 because the pre-check in the route (get_activity_by_id) fails
    assert response.status_code == 404, f"Expected 404 for deleting non-existent activity, got {response.status_code}"
    assert "Activity not found" in response.json().get("message", "")
    print("Delete non-existent activity: Not Found (OK)")

def test_unauthorized_access(logged_in_users, second_parent_user, created_child_id, http_session):
    """Test that a user cannot access data they are not linked to."""
    print("\nTesting unauthorized access...")
    # Use the token of the second parent, who is NOT linked to the created child
    unauthorized_token = second_parent_user["token"]
    child_id = created_child_id # Child created by the first parent
    headers = {"Authorization": f"Bearer {unauthorized_token}"}

    # Attempt to get child data
    print("Attempting GET /data/children/{child_id} as unauthorized parent...")
    endpoint_child = f"/data/children/{child_id}"
    response_child = http_session.get(f"{DB_INTERACT_URL}{endpoint_child}", headers=headers)
    assert response_child.status_code == 403, f"Expected 403 for unauthorized child access, got {response_child.status_code}"
    assert "Forbidden" in response_child.json().get("message", "")
    print("Unauthorized child access: Forbidden (OK)")

    # Attempt to get activities data
    print("Attempting GET /data/activities?child_id=... as unauthorized parent...")
    endpoint_activities = f"/data/activities?child_id={child_id}"
    response_activities = http_session.get(f"{DB_INTERACT_URL}{endpoint_activities}", headers=headers)
    assert response_activities.status_code == 403, f"Expected 403 for unauthorized activity access, got {response_activities.status_code}"
    assert "Forbidden" in response_activities.json().get("message", "")
    print("Unauthorized activity access: Forbidden (OK)")

