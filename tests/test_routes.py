# tests/test_integration.py
import pytest
import requests
import time
import uuid # To generate unique usernames/emails for each run

# --- Test Data ---
# Use functions to generate unique data for each test run
def generate_unique_user(role="parent"):
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
    "birthday": "2022-02-20",
    "group": "Testers",
    "allergies": ["Flaky Tests"],
    "notes": "Needs stable environment"
}
ACTIVITY_DATA_TEMPLATE = {
    "type": "sleep",
    "details": {
        "duration_minutes": 60,
        "quality": "restful",
        "notes": "Dreaming of passing tests."
    }
}

# --- Fixtures for Setup Steps (Session Scoped) ---

@pytest.fixture(scope="session")
def test_users(auth_service_url, http_session):
    """Registers a parent and teacher user for the test session."""
    print("\nSetting up test users...")
    parent_data = generate_unique_user("parent")
    teacher_data = generate_unique_user("teacher")

    # Register Parent
    reg_parent_response = http_session.post(f"{auth_service_url}/auth/register", json=parent_data)
    assert reg_parent_response.status_code in [201, 409], f"Parent registration failed: {reg_parent_response.text}" # Allow 409 if already exists from previous failed run

    # Register Teacher
    reg_teacher_response = http_session.post(f"{auth_service_url}/auth/register", json=teacher_data)
    assert reg_teacher_response.status_code in [201, 409], f"Teacher registration failed: {reg_teacher_response.text}"

    print("Test users registered (or already exist).")
    # Return the data used, including passwords, for login fixture
    return {"parent": parent_data, "teacher": teacher_data}

@pytest.fixture(scope="session")
def logged_in_users(test_users, auth_service_url, http_session):
    """Logs in the registered test users and returns tokens/IDs."""
    print("\nLogging in test users...")
    tokens = {}
    user_ids = {}

    # Login Parent
    parent_login_data = {"username": test_users["parent"]["username"], "password": test_users["parent"]["password"]}
    parent_login_response = http_session.post(f"{auth_service_url}/auth/login", json=parent_login_data)
    assert parent_login_response.status_code == 200, f"Parent login failed: {parent_login_response.text}"
    parent_login_json = parent_login_response.json()
    tokens["parent"] = parent_login_json.get("access_token")
    user_ids["parent"] = parent_login_json.get("user_id")
    assert tokens["parent"] and user_ids["parent"], "Parent login response missing token or user_id"
    print(f"Parent logged in. User ID: {user_ids['parent']}")

    # Login Teacher
    teacher_login_data = {"username": test_users["teacher"]["username"], "password": test_users["teacher"]["password"]}
    teacher_login_response = http_session.post(f"{auth_service_url}/auth/login", json=teacher_login_data)
    assert teacher_login_response.status_code == 200, f"Teacher login failed: {teacher_login_response.text}"
    teacher_login_json = teacher_login_response.json()
    tokens["teacher"] = teacher_login_json.get("access_token")
    user_ids["teacher"] = teacher_login_json.get("user_id")
    assert tokens["teacher"] and user_ids["teacher"], "Teacher login response missing token or user_id"
    print(f"Teacher logged in. User ID: {user_ids['teacher']}")

    return {"tokens": tokens, "ids": user_ids}


@pytest.fixture(scope="session")
def created_child_id(logged_in_users, db_interact_url, http_session):
    """Creates a child record using the parent token."""
    print("\nCreating child record...")
    parent_token = logged_in_users["tokens"]["parent"]
    headers = {"Authorization": f"Bearer {parent_token}"}

    response = http_session.post(f"{db_interact_url}/internal/children", headers=headers, json=CHILD_DATA_TEMPLATE)
    assert response.status_code == 201, f"Child creation failed: {response.text}"
    child_id = response.json().get("child_id")
    assert child_id, "Child creation response missing child_id"
    print(f"Child created. ID: {child_id}")
    return child_id

@pytest.fixture(scope="session")
def linked_child_supervisor(created_child_id, logged_in_users, db_interact_url, http_session):
    """Links the test supervisor to the created child."""
    print("\nLinking supervisor...")
    teacher_token = logged_in_users["tokens"]["teacher"]
    teacher_id = logged_in_users["ids"]["teacher"]
    headers = {"Authorization": f"Bearer {teacher_token}"}
    link_data = {"supervisor_id": teacher_id}
    endpoint = f"/internal/children/{created_child_id}/link-supervisor"

    response = http_session.put(f"{db_interact_url}{endpoint}", headers=headers, json=link_data)
    assert response.status_code == 200, f"Supervisor linking failed: {response.text}"
    print("Supervisor linked.")
    # Return child_id for dependency chain if needed, though created_child_id already provides it
    return created_child_id

@pytest.fixture(scope="session")
def created_activity_id(linked_child_supervisor, logged_in_users, db_interact_url, http_session):
    """Adds an activity record for the child using the teacher token."""
    print("\nAdding activity record...")
    child_id = linked_child_supervisor # Get child_id from previous fixture
    teacher_token = logged_in_users["tokens"]["teacher"]
    headers = {"Authorization": f"Bearer {teacher_token}"}

    activity_data = ACTIVITY_DATA_TEMPLATE.copy()
    activity_data["child_id"] = child_id

    response = http_session.post(f"{db_interact_url}/internal/activities", headers=headers, json=activity_data)
    assert response.status_code == 201, f"Activity creation failed: {response.text}"
    activity_id = response.json().get("activity_id")
    assert activity_id, "Activity creation response missing activity_id"
    print(f"Activity created. ID: {activity_id}")
    return activity_id


# --- Test Functions ---

def test_get_child_data(logged_in_users, created_child_id, db_interact_url, http_session):
    """Verify both parent and teacher can get child data."""
    print("\nTesting GET /data/children/{child_id}...")
    parent_token = logged_in_users["tokens"]["parent"]
    teacher_token = logged_in_users["tokens"]["teacher"]
    endpoint = f"/data/children/{created_child_id}"

    # Test as Parent
    headers_parent = {"Authorization": f"Bearer {parent_token}"}
    response_parent = http_session.get(f"{db_interact_url}{endpoint}", headers=headers_parent)
    assert response_parent.status_code == 200, f"Parent failed to get child data: {response_parent.text}"
    assert response_parent.json()["_id"] == created_child_id
    assert response_parent.json()["name"] == CHILD_DATA_TEMPLATE["name"]
    print("Get child data as Parent: OK")

    # Test as Teacher
    headers_teacher = {"Authorization": f"Bearer {teacher_token}"}
    response_teacher = http_session.get(f"{db_interact_url}{endpoint}", headers=headers_teacher)
    assert response_teacher.status_code == 200, f"Teacher failed to get child data: {response_teacher.text}"
    assert response_teacher.json()["_id"] == created_child_id
    print("Get child data as Teacher: OK")

def test_get_children_list(logged_in_users, created_child_id, db_interact_url, http_session):
    """Verify parent and teacher get the created child in their lists."""
    print("\nTesting GET /data/children...")
    parent_token = logged_in_users["tokens"]["parent"]
    teacher_token = logged_in_users["tokens"]["teacher"]
    endpoint = "/data/children"

    # Test as Parent
    headers_parent = {"Authorization": f"Bearer {parent_token}"}
    response_parent = http_session.get(f"{db_interact_url}{endpoint}", headers=headers_parent)
    assert response_parent.status_code == 200
    parent_children = response_parent.json()
    assert isinstance(parent_children, list)
    assert any(child['_id'] == created_child_id for child in parent_children), "Created child not found in parent's list"
    print("Get children list as Parent: OK")

    # Test as Teacher
    headers_teacher = {"Authorization": f"Bearer {teacher_token}"}
    response_teacher = http_session.get(f"{db_interact_url}{endpoint}", headers=headers_teacher)
    assert response_teacher.status_code == 200
    teacher_children = response_teacher.json()
    assert isinstance(teacher_children, list)
    assert any(child['_id'] == created_child_id for child in teacher_children), "Created child not found in teacher's list"
    print("Get children list as Teacher: OK")

def test_get_activities(logged_in_users, created_child_id, created_activity_id, db_interact_url, http_session):
    """Verify parent and teacher can get activities, including filtering."""
    print("\nTesting GET /data/activities...")
    parent_token = logged_in_users["tokens"]["parent"]
    teacher_token = logged_in_users["tokens"]["teacher"]
    endpoint = f"/data/activities?child_id={created_child_id}"

    # Test as Parent
    headers_parent = {"Authorization": f"Bearer {parent_token}"}
    response_parent = http_session.get(f"{db_interact_url}{endpoint}", headers=headers_parent)
    assert response_parent.status_code == 200
    parent_activities = response_parent.json()
    assert isinstance(parent_activities, list)
    assert any(act['_id'] == created_activity_id for act in parent_activities), "Created activity not found in parent's get"
    print("Get activities as Parent: OK")

    # Test as Teacher
    headers_teacher = {"Authorization": f"Bearer {teacher_token}"}
    response_teacher = http_session.get(f"{db_interact_url}{endpoint}", headers=headers_teacher)
    assert response_teacher.status_code == 200
    teacher_activities = response_teacher.json()
    assert isinstance(teacher_activities, list)
    assert any(act['_id'] == created_activity_id for act in teacher_activities), "Created activity not found in teacher's get"
    print("Get activities as Teacher: OK")

    # Test Filtering (as Teacher)
    endpoint_filtered = f"/data/activities?child_id={created_child_id}&type=sleep"
    response_filtered = http_session.get(f"{db_interact_url}{endpoint_filtered}", headers=headers_teacher)
    assert response_filtered.status_code == 200
    filtered_activities = response_filtered.json()
    assert isinstance(filtered_activities, list)
    assert all(act['type'] == 'sleep' for act in filtered_activities), "Filtering by type failed"
    assert any(act['_id'] == created_activity_id for act in filtered_activities), "Created activity not found when filtering by correct type"
    print("Get activities filtered by type: OK")

    endpoint_filtered_wrong = f"/data/activities?child_id={created_child_id}&type=meal"
    response_filtered_wrong = http_session.get(f"{db_interact_url}{endpoint_filtered_wrong}", headers=headers_teacher)
    assert response_filtered_wrong.status_code == 200
    assert response_filtered_wrong.json() == [], "Filtering by wrong type should return empty list"
    print("Get activities filtered by wrong type: OK")


def test_delete_activity_permissions_and_verify(logged_in_users, created_child_id, created_activity_id, db_interact_url, http_session):
    """Verify parent cannot delete, teacher can delete, and verify deletion."""
    print("\nTesting DELETE /data/activities/{activity_id} permissions...")
    parent_token = logged_in_users["tokens"]["parent"]
    teacher_token = logged_in_users["tokens"]["teacher"]
    endpoint = f"/data/activities/{created_activity_id}"

    # Attempt Delete as Parent (Should Fail 403)
    print("Attempting delete as Parent...")
    headers_parent = {"Authorization": f"Bearer {parent_token}"}
    response_parent_delete = http_session.delete(f"{db_interact_url}{endpoint}", headers=headers_parent)
    assert response_parent_delete.status_code == 403, f"Parent deletion did not fail with 403: {response_parent_delete.status_code}"
    print("Delete as Parent: Forbidden (OK)")

    # Attempt Delete as Teacher (Should Succeed 200)
    print("Attempting delete as Teacher...")
    headers_teacher = {"Authorization": f"Bearer {teacher_token}"}
    response_teacher_delete = http_session.delete(f"{db_interact_url}{endpoint}", headers=headers_teacher)
    assert response_teacher_delete.status_code == 200, f"Teacher deletion failed: {response_teacher_delete.text}"
    print("Delete as Teacher: OK")

    # Verify Deletion by trying to get activities again (Should be empty list)
    print("Verifying deletion...")
    time.sleep(0.5) # Give DB a moment
    verify_endpoint = f"/data/activities?child_id={created_child_id}"
    response_verify = http_session.get(f"{db_interact_url}{verify_endpoint}", headers=headers_teacher)
    assert response_verify.status_code == 200
    activities_after_delete = response_verify.json()
    assert isinstance(activities_after_delete, list)
    assert not any(act['_id'] == created_activity_id for act in activities_after_delete), "Deleted activity still found in list"
    print("Verify deletion: OK (Activity no longer listed)")

