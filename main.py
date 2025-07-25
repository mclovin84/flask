# main.py - Complete webhook handler with Google Sheets
import os
import json
import datetime
import logging
from flask import Flask, request, jsonify
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
GOOGLE_SHEETS_ID = '18QnbWC6pko43ySkhKjTtuSoZyL6cpXxzFe88wCMo9R8'
GOOGLE_CREDS_JSON = os.environ.get('GOOGLE_CREDS_JSON')

# Initialize Google Sheets
sheets_service = None
if GOOGLE_CREDS_JSON:
    try:
        creds = service_account.Credentials.from_service_account_info(
            json.loads(GOOGLE_CREDS_JSON),
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        sheets_service = build('sheets', 'v4', credentials=creds)
        logger.info("Google Sheets connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect to Google Sheets: {e}")

# Cache for blocklist (refresh periodically in production)
BLOCKLIST = set()
ALLOWLIST = set()

def load_lists():
    """Load block/allow lists from Google Sheets"""
    global BLOCKLIST, ALLOWLIST
    if not sheets_service:
        return
    
    try:
        # Load blocklist
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=GOOGLE_SHEETS_ID,
            range='Blocklist!A2:A'  # Skip header row
        ).execute()
        values = result.get('values', [])
        BLOCKLIST = {row[0] for row in values if row}
        
        # Load allowlist
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=GOOGLE_SHEETS_ID,
            range='Allowlist!A2:A'  # Skip header row
        ).execute()
        values = result.get('values', [])
        ALLOWLIST = {row[0] for row in values if row}
        
        logger.info(f"Loaded {len(BLOCKLIST)} blocked numbers, {len(ALLOWLIST)} allowed numbers")
    except Exception as e:
        logger.error(f"Error loading lists: {e}")

# Load lists on startup
load_lists()

@app.route('/check-blocklist', methods=['POST'])
def check_blocklist():
    """Check if caller is on blocklist"""
    data = request.json
    caller_number = data.get('caller_number', '')
    
    # Reload lists (in production, cache this)
    load_lists()
    
    if caller_number in BLOCKLIST:
        return jsonify({'response_blocked': 'true', 'block_reason': 'blocklist'})
    
    return jsonify({'response_blocked': 'false'})

@app.route('/ai-context', methods=['POST'])
def ai_context():
    """Provide dynamic context to AI agent"""
    return jsonify({'context': '{}'})

@app.route('/log-screening', methods=['POST'])
def log_screening():
    """Log AI screening results to Google Sheets"""
    data = request.json
    
    # Log to console
    logger.info(f"Screening: {data.get('screening_result')} for {data.get('from')}")
    
    # Log to Google Sheets
    if sheets_service:
        try:
            values = [[
                datetime.datetime.utcnow().isoformat(),
                data.get('call_sid', ''),
                data.get('from', ''),
                data.get('to', ''),
                data.get('screening_result', ''),
                data.get('caller_name', ''),
                data.get('call_reason', ''),
                data.get('spam_confidence', ''),
                data.get('ai_transcript', '')[:500]  # Limit transcript length
            ]]
            
            sheets_service.spreadsheets().values().append(
                spreadsheetId=GOOGLE_SHEETS_ID,
                range='CallLog!A:I',
                valueInputOption='RAW',
                body={'values': values}
            ).execute()
            
            logger.info("Logged to Google Sheets successfully")
        except Exception as e:
            logger.error(f"Failed to log to Sheets: {e}")
    
    return jsonify({'status': 'logged'})

@app.route('/recording-complete', methods=['POST'])
def recording_complete():
    """Handle completed call recording"""
    data = request.form
    call_sid = data.get('call_sid', '')
    recording_url = data.get('RecordingUrl', '')
    recording_duration = data.get('RecordingDuration', '')
    
    logger.info(f"Recording completed for call {call_sid}")
    
    # Log to EventLog
    if sheets_service:
        try:
            values = [[
                datetime.datetime.utcnow().isoformat(),
                call_sid,
                'recording_complete',
                json.dumps({
                    'url': recording_url,
                    'duration': recording_duration
                })
            ]]
            
            sheets_service.spreadsheets().values().append(
                spreadsheetId=GOOGLE_SHEETS_ID,
                range='EventLog!A:D',
                valueInputOption='RAW',
                body={'values': values}
            ).execute()
        except Exception as e:
            logger.error(f"Failed to log recording: {e}")
    
    return jsonify({'status': 'processed'})

@app.route('/voicemail-complete', methods=['POST'])
def voicemail_complete():
    """Handle completed voicemail recording"""
    data = request.form
    call_sid = data.get('call_sid', '')
    caller_number = data.get('from', '')
    caller_name = data.get('caller_name', 'Unknown')
    call_reason = data.get('call_reason', 'No reason given')
    recording_url = data.get('RecordingUrl', '')
    
    logger.info(f"Voicemail from {caller_number}")
    
    # Log to Voicemail tab
    if sheets_service:
        try:
            values = [[
                datetime.datetime.utcnow().isoformat(),
                call_sid,
                f"{caller_name} ({caller_number})",
                call_reason,
                recording_url,
                'Transcript pending'  # You can add transcription later
            ]]
            
            sheets_service.spreadsheets().values().append(
                spreadsheetId=GOOGLE_SHEETS_ID,
                range='Voicemail!A:F',
                valueInputOption='RAW',
                body={'values': values}
            ).execute()
        except Exception as e:
            logger.error(f"Failed to log voicemail: {e}")
    
    return jsonify({'status': 'processed'})

@app.route('/log-event', methods=['POST'])
def log_event():
    """Generic event logging"""
    data = request.json
    
    logger.info(f"Event: {data.get('event')} for call {data.get('call_sid')}")
    
    # Log to EventLog
    if sheets_service:
        try:
            values = [[
                datetime.datetime.utcnow().isoformat(),
                data.get('call_sid', ''),
                data.get('event', ''),
                json.dumps(data)
            ]]
            
            sheets_service.spreadsheets().values().append(
                spreadsheetId=GOOGLE_SHEETS_ID,
                range='EventLog!A:D',
                valueInputOption='RAW',
                body={'values': values}
            ).execute()
        except Exception as e:
            logger.error(f"Failed to log event: {e}")
    
    return jsonify({'status': 'logged'})

@app.route('/owner-whisper', methods=['POST'])
def owner_whisper():
    """Announce caller info when owner answers"""
    headers = request.headers
    caller_name = headers.get('X-Caller-Name', 'Unknown')
    call_reason = headers.get('X-Call-Reason', 'No reason given')
    
    whisper_swml = {
        "version": "1.0.0",
        "sections": {
            "main": [
                {
                    "play": {
                        "url": f"say:{caller_name} calling about {call_reason}",
                        "voice": "en-US-Neural2-F"
                    }
                },
                {
                    "return": {}
                }
            ]
        }
    }
    
    return jsonify(whisper_swml)

@app.route('/', methods=['GET'])
def home():
    """Health check endpoint"""
    status = {
        'status': 'running',
        'message': 'SignalWire webhook handler',
        'google_sheets': 'connected' if sheets_service else 'not connected',
        'blocklist_count': len(BLOCKLIST),
        'allowlist_count': len(ALLOWLIST)
    }
    return jsonify(status)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))