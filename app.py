from flask import Flask, jsonify, request
from datetime import datetime, timedelta
import json
import os
import threading
import time
import requests

app = Flask(__name__)

# GitHub raw URL to load UID storage JSON (read-only)
GITHUB_UID_JSON_URL = 'https://raw.githubusercontent.com/ffwlxd/FFwlxd-time/main/uid_storage.json'

# Local fallback file path for saving
STORAGE_FILE = 'uid_storage_local.json'

# Lock for thread-safe access
storage_lock = threading.Lock()

# Function to load UIDs from GitHub (read-only)
def load_uids():
    try:
        response = requests.get(GITHUB_UID_JSON_URL)
        response.raise_for_status()
        content = response.text.strip()
        return json.loads(content) if content else {}
    except Exception as e:
        print(f"Failed to load UID data from GitHub: {e}")
        return {}

# Function to save UIDs locally
def save_uids(uids):
    try:
        with open(STORAGE_FILE, 'w') as file:
            json.dump(uids, file, default=str)
    except Exception as e:
        print(f"Failed to save UIDs locally: {e}")

# Periodic cleanup of expired UIDs
def cleanup_expired_uids():
    while True:
        with storage_lock:
            uids = load_uids()
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            expired_uids = [uid for uid, exp_time in uids.items() if exp_time != 'permanent' and exp_time <= current_time]
            for uid in expired_uids:
                try:
                    requests.get(f"https://ffwlxd-add-api.vercel.app/remove/{uid}?key=ffwlx")
                    print(f"Deleted expired UID: {uid}")
                except Exception as e:
                    print(f"Failed to remove UID {uid}: {e}")
                del uids[uid]
            save_uids(uids)
        time.sleep(1)

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_expired_uids, daemon=True)
cleanup_thread.start()

# Add UID API
@app.route('/add_uid', methods=['GET'])
def add_uid():
    uid = request.args.get('uid')
    time_value = request.args.get('time')
    time_unit = request.args.get('type')  # days, months, years, seconds
    permanent = request.args.get('permanent', 'false').lower() == 'true'

    if not uid:
        return jsonify({'error': 'Missing parameter: uid'}), 400

    if permanent:
        expiration_time = 'permanent'
        try:
            requests.get(f"https://ffwlxd-add-api.vercel.app/add/{uid}?key=ffwlx")
        except Exception as e:
            print(f"Failed to add UID {uid}: {e}")
    else:
        if not time_value or not time_unit:
            return jsonify({'error': 'Missing parameters: time or type'}), 400
        try:
            time_value = int(time_value)
        except ValueError:
            return jsonify({'error': 'Invalid time value'}), 400

        now = datetime.now()
        if time_unit == 'days':
            expiration_time = now + timedelta(days=time_value)
        elif time_unit == 'months':
            expiration_time = now + timedelta(days=time_value * 30)
        elif time_unit == 'years':
            expiration_time = now + timedelta(days=time_value * 365)
        elif time_unit == 'seconds':
            expiration_time = now + timedelta(seconds=time_value)
        else:
            return jsonify({'error': 'Invalid type. Use "days", "months", "years", or "seconds".'}), 400

        expiration_time = expiration_time.strftime('%Y-%m-%d %H:%M:%S')
        try:
            requests.get(f"https://ffwlxd-add-api.vercel.app/add/{uid}?key=ffwlx")
        except Exception as e:
            print(f"Failed to add UID {uid}: {e}")

    with storage_lock:
        uids = load_uids()
        uids[uid] = expiration_time
        save_uids(uids)

    return jsonify({
        'uid': uid,
        'expires_at': expiration_time if not permanent else 'never'
    })

# Check time left for UID
@app.route('/get_time/<string:uid>', methods=['GET'])
def check_time(uid):
    with storage_lock:
        uids = load_uids()
        if uid not in uids:
            return jsonify({'error': 'UID not found'}), 404

        expiration_time = uids[uid]
        if expiration_time == 'permanent':
            return jsonify({
                'uid': uid,
                'status': 'permanent',
                'message': 'This UID will never expire.'
            })

        expiration_time = datetime.strptime(expiration_time, '%Y-%m-%d %H:%M:%S')
        now = datetime.now()

        if now > expiration_time:
            return jsonify({'error': 'UID has expired'}), 400

        remaining = expiration_time - now
        days = remaining.days
        hours, rem = divmod(remaining.seconds, 3600)
        minutes, seconds = divmod(rem, 60)

        return jsonify({
            'uid': uid,
            'remaining_time': {
                'days': days,
                'hours': hours,
                'minutes': minutes,
                'seconds': seconds
            }
        })

# Run Flask app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=50022, debug=True)