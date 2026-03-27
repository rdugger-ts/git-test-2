import os
import json
import requests
import requests.exceptions
from thoughtspot_rest_api import *

gh_action_none = "{None}"

# Values passed into ENV from Workflow file, using GitHub Secrets and Workflow Variables
server = os.environ.get("TS_SERVER")
username = os.environ.get("TS_USERNAME")
secret_key = os.environ.get("TS_SECRET_KEY")
org_id = os.environ.get("ORG_ID")  # Set via retrieve_org_id_from_org_name.py setting environment

object_type = os.environ.get("OBJECT_TYPE")
object_filename = os.environ.get("OBJECT_FILENAME")
import_policy = os.environ.get("IMPORT_POLICY")
sync_or_async = os.environ.get("ASYNC")

# Define the directory names to link to the workflow
directories_for_objects = {
    "CONNECTION": ["connections"],
    "DATA_MODEL": ["tables", "models", "sql_views", "views"],
    "TABLE": ["tables"],
    "MODEL": ["models"],
    "LIVEBOARD": ["liveboards"],
    "ANSWER": ["answers"],
    "CONTENT": ["liveboards", "answers"],
}

ts: TSRestApiV2 = TSRestApiV2(server_url=server)

print("========== IMPORT START ==========")
print(f"TS_SERVER: {server}")
print(f"TS_USERNAME: {username}")
print(f"ORG_ID from env: {org_id}")
print(f"OBJECT_TYPE: {object_type}")
print(f"IMPORT_POLICY: {import_policy}")
print(f"ASYNC: {sync_or_async}")
print("==================================")

# Authenticate
try:
    auth_resp = ts.auth_token_full(
        username=username,
        secret_key=secret_key,
        validity_time_in_sec=3000,
        org_id=org_id,
    )
    ts.bearer_token = auth_resp["token"]

    print("Auth completed successfully.")
    print("Auth response:")
    print(json.dumps(auth_resp, indent=2))
except requests.exceptions.HTTPError as e:
    print("Authentication failed.")
    print(e)
    print(e.response.content)
    raise

# Read the directories for the objects specified
print(f"Getting directories for {object_type}")
directories_to_import = directories_for_objects[object_type]
tml_strings = []
tml_file_paths = []

for dir_name in directories_to_import:
    try:
        files_in_dir = os.listdir(dir_name)
        print(f"These files in directory {dir_name}:")
        print(files_in_dir)

        for filename in files_in_dir:
            # Skip files that aren't .tml
            if ".tml" in filename:
                full_file_path = f"{dir_name}/{filename}"
                try:
                    with open(full_file_path, mode="r") as f:
                        tml_str = f.read()
                        tml_strings.append(tml_str)
                        tml_file_paths.append(full_file_path)
                except Exception as e:
                    print(f"Failed reading file {full_file_path}: {e}")
    except FileNotFoundError as e:
        print("Directory doesn't exist, skipping")
        print(e)

if len(tml_strings) == 0:
    print("No TML to import, exiting")
    raise SystemExit(0)

print(f"TML files queued for import ({len(tml_file_paths)}):")
for path in tml_file_paths:
    print(f" - {path}")

# Import the TMLs
try:
    print(f"Importing {len(tml_strings)} TMLs using Import Policy {import_policy} via {sync_or_async}")

    if sync_or_async == "SYNC":
        results = ts.metadata_tml_import(
            metadata_tmls=tml_strings,
            import_policy=import_policy,
            create_new=False,
        )
    elif sync_or_async == "ASYNC":
        results = ts.metadata_tml_async_import(
            metadata_tmls=tml_strings,
            import_policy=import_policy,
            create_new=False,
        )
    else:
        raise ValueError(f"Invalid ASYNC value: {sync_or_async}")

    print("Import API completed successfully with following response:")
    print(json.dumps(results, indent=2))

except requests.exceptions.HTTPError as e:
    print("Import failed with HTTPError.")
    print(e)
    print(e.response.content)
    raise
except Exception as e:
    print("Import failed with unexpected error.")
    print(str(e))
    raise

# Summarize import results
print("========== IMPORT SUMMARY ==========")
ok_count = 0
error_count = 0
created_names = []
updated_names = []
error_entries = []

if isinstance(results, list):
    for item in results:
        response = item.get("response", {})
        status = response.get("status", {})
        header = response.get("header", {})
        action = response.get("action", "")
        status_code = status.get("status_code", "")

        if status_code == "OK":
            ok_count += 1
            obj_name = header.get("name", "<unknown>")
            obj_id = header.get("objId", "<unknown>")
            if action == "CREATE":
                created_names.append(f"{obj_name} ({obj_id})")
            elif action == "UPDATE":
                updated_names.append(f"{obj_name} ({obj_id})")
        else:
            error_count += 1
            error_entries.append(
                {
                    "request_index": item.get("request_index"),
                    "status_code": status.get("status_code"),
                    "error_code": status.get("error_code"),
                    "error_message": status.get("error_message"),
                }
            )

print(f"Successful items: {ok_count}")
print(f"Errored items: {error_count}")

if created_names:
    print("Created objects:")
    for name in created_names:
        print(f" - {name}")

if updated_names:
    print("Updated objects:")
    for name in updated_names:
        print(f" - {name}")

if error_entries:
    print("Errored objects:")
    print(json.dumps(error_entries, indent=2))

print("====================================")

# Optional post-import verification search
# This is primarily useful for CONNECTION imports where you want to confirm
# that the same token can immediately see what was just created.
# Optional post-import verification search using direct REST call
try:
    print("Running post-import verification search via direct REST call...")

    headers = {
        "Authorization": f"Bearer {ts.bearer_token}",
        "Content-Type": "application/json",
    }

    search_payload = {
        "metadata": [
            {
                "type": "DATA_SOURCE"
            }
        ],
        "record_size": 100
    }

    resp = requests.post(
        url=f"{server}/api/rest/2.0/metadata/search",
        headers=headers,
        json=search_payload,
        timeout=60,
    )

    print(f"Verification search HTTP status: {resp.status_code}")
    print("Verification search response:")
    print(json.dumps(resp.json(), indent=2))

except Exception as e:
    print("Post-import verification search failed with unexpected error.")
    print(str(e))

print("=========== IMPORT END ===========")
