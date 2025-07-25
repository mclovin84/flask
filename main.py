from flask import Flask, request, jsonify
import os
import datetime
import json

app = Flask(__name__)


# 1. Health check endpoint (very useful for Railway!)
@app.route('/health')
def health():
    return "OK", 200


# 2. Dummy implementation of SignalWire webhooks
# You can expand these with your actual logic later.

@app.route('/log-screening', methods=['POST'])
def log_screening():
    """SignalWire calls this endpoint when your SWML says to log call screening."""
    data = request.json
    # You'd add code here to log to Google Sheets
    # For now, just print for debugging
    print("Screening data:", data)
    return jsonify({"status": "logged"})

@app.route('/recording-complete', methods=['POST'])
def recording_complete():
    """Called when a call recording is finished."""
    data = request.json if request.is_json else request.form
    print("Recording complete:", data)
    return jsonify({"status": "processed"})

@app.route('/check-blocklist', methods=['POST'])
def check_blocklist():
    """Checks if a number is on your blocklist (here, always responds 'not blocked')."""
    data = request.json
    caller_number = data.get('caller_number')
    # In real code, you'd check Google Sheets here!
    return jsonify({'response_blocked': 'false'})

@app.route('/log-event', methods=['POST'])
def log_event():
    data = request.json
    print("Event:", data)
    return jsonify({'status': 'logged'})


# 3. Home route (optional)
@app.route('/')
def index():
    return jsonify({"status": "success", "message": "Flask SignalWire Webhook Ready."})

if __name__ == '__main__':
    # Do NOT use debug=True in production
    app.run(port=int(os.environ.get("PORT", 5000)), host='0.0.0.0')
