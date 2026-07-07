import os
import base64
import json
import re
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

def main():
    print("Loading environment configuration...")
    load_dotenv()
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        print("Error: MONGO_URI not found in environment/.env file.")
        return

    html_path = os.path.join("templates", "academic_calendar.html")
    if not os.path.exists(html_path):
        print(f"Error: Could not find {html_path}")
        return

    print("Reading academic_calendar.html...")
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    print("Extracting base64-encoded events...")
    # Matches: const EVENTS = JSON.parse(atob("..."));
    match = re.search(r'const\s+EVENTS\s*=\s*JSON\.parse\(atob\(\"([^\"]+)\"\)\)', content)
    if not match:
        # Fallback to single quotes if needed
        match = re.search(r"const\s+EVENTS\s*=\s*JSON\.parse\(atob\(\'([^\'\x22]+)\'\)\)", content)

    if not match:
        print("Error: Could not locate EVENTS constant in the template file.")
        return

    b64_data = match.group(1)
    print("Decoding base64 string...")
    try:
        decoded_bytes = base64.b64decode(b64_data)
        decoded_str = decoded_bytes.decode("utf-8")
        events_list = json.loads(decoded_str)
    except Exception as e:
        print(f"Error decoding base64 data: {e}")
        return

    print(f"Successfully decoded {len(events_list)} events.")

    print("Connecting to MongoDB...")
    client = MongoClient(mongo_uri)
    db = client.get_database()

    print("Creating backup of existing events collection...")
    existing_count = db.events.count_documents({})
    if existing_count > 0:
        # Backup
        backup_name = f"events_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        print(f"Backing up {existing_count} existing events to '{backup_name}'...")
        db[backup_name].insert_many(list(db.events.find({})))

    print("Clearing events collection...")
    db.events.delete_many({})

    print("Inserting academic calendar events...")
    mongo_docs = []
    for item in events_list:
        doc = {
            "event_name": item.get("n", "Academic Event"),
            "description": f"Academic Calendar Event ({item.get('c')}). Faculty: {item.get('f') or 'N/A'}. Department: {item.get('d') or 'N/A'}. Campus: {item.get('p') or 'N/A'}.",
            "school": item.get("f", ""),
            "department": item.get("d", ""),
            "event_type": item.get("c", ""),
            "venue": item.get("v", ""),
            "event_date": item.get("s", ""),
            "end_date": item.get("e", ""),
            "event_time": "All Day",
            "coordinator": item.get("co", ""),
            "sub_category": item.get("sub", ""),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        mongo_docs.append(doc)

    if mongo_docs:
        res = db.events.insert_many(mongo_docs)
        print(f"Successfully inserted {len(res.inserted_ids)} academic calendar events.")
    else:
        print("No events found to insert.")

    print("Done!")

if __name__ == "__main__":
    main()
