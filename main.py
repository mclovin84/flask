# main.py - Complete SignalWire webhook handler with proper timeout configuration
import os
import json
import datetime
import logging
from flask import Flask, request, jsonify
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration - environment variables
GOOGLE_SHEETS_ID = os.environ.get('GOOGLE_SHEETS_ID')
GOOGLE_CREDS_JSON = os.environ.get('GOOGLE_CREDS_JSON')
SIGNALWIRE_SPACE = os.environ.get('SIGNALWIRE_SPACE')
SIGNALWIRE_PROJECT = os.environ.get('SIGNALWIRE_PROJECT')
SIGNALWIRE_TOKEN = os.environ.get('SIGNALWIRE_TOKEN')
OWNER_PHONE_NUMBER = os.environ.get('OWNER_PHONE_NUMBER', '+15022969469')
OWNER_SMS = os.environ.get('OWNER_SMS')
OWNER_EMAIL = os.environ.get('OWNER_EMAIL')
BUSINESS_NAME = os.environ.get('BUSINESS_NAME', 'Anthony Barragan')

# Initialize Google Sheets client if credentials are available
sheets_service = None
if GOOGLE_:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        
        creds = service_account.Credentials.from_service_account_info(
            json.loads(GOOGLE_CREDS_JSON),
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        sheets_service = build('sheets', 'v4', credentials=creds)
        logger.info("Google Sheets service initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Google Sheets: {e}")

# Initialize SignalWire client if credentials are available
sw_client = None
if SIGNALWIRE_PROJECT and SIGNALWIRE_TOKEN and SIGNALWIRE_SPACE:
    try:
        from twilio.rest import Client
        sw_client = Client(SIGNALWIRE_PROJECT, SIGNALWIRE_TOKEN, 
                          signalwire_space_url=f'{SIGNALWIRE_SPACE}.signalwire.com')
        logger.info("SignalWire client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize SignalWire client: {e}")

# Simple blocklist cache
BLOCKLIST = set()
ALLOWLIST = set()

def load_blocklist():
    """Load blocklist from Google Sheets"""
    global BLOCKLIST, ALLOWLIST
    try:
        if sheets_service and GOOGLE_SHEETS_ID:
            # Load blocklist
            result = sheets_service.spreadsheets().values().get(
                spreadsheetId=GOOGLE_SHEETS_ID,
                range='Blocklist!A:A'
            ).execute()
            values = result.get('values', [])
            BLOCKLIST = set([row[0] for row in values if row])
            
            # Load allowlist
            result = sheets_service.spreadsheets().values().get(
                spreadsheetId=GOOGLE_SHEETS_ID,
                range='Allowlist!A:A'
            ).execute()
            values = result.get('values', [])
            ALLOWLIST = set([row[0] for row in values if row])
            
            logger.info(f"Loaded {len(BLOCKLIST)} blocked numbers and {len(ALLOWLIST)} allowed numbers")
    except Exception as e:
        logger.error(f"Error loading blocklist: {e}")

# Load blocklist on startup
load_blocklist()

# Health check endpoint
@app.route('/health', methods=['GET'])
def health():
    return "OK", 200

# Root endpoint
@app.route('/')
def index():
    return jsonify({"status": "success", "message": "Flask SignalWire Webhook Ready."})

# Blocklist checking endpoint
@app.route('/check-blocklist', methods=['POST'])
def check_blocklist():
    """Check if caller is on blocklist"""
    try:
        data = request.json
        caller_number = data.get('caller_number', '')
        
        logger.info(f"Checking blocklist for number: {caller_number}")
        
        # Check exact match in blocklist
        if caller_number in BLOCKLIST:
            logger.info(f"Number {caller_number} is blocked")
            return jsonify({
                'response_blocked': 'true', 
                'block_reason': 'blocklist'
            })
        
        # Check allowlist for VIP callers
        if caller_number in ALLOWLIST:
            logger.info(f"Number {caller_number} is on allowlist")
            return jsonify({
                'response_blocked': 'false', 
                'is_known_caller': 'true',
                'allow_reason': 'allowlist'
            })
        
        logger.info(f"Number {caller_number} is not blocked")
        return jsonify({'response_blocked': 'false'})
        
    except Exception as e:
        logger.error(f"Error in check_blocklist: {e}")
        return jsonify({'response_blocked': 'false'})

# SWAIG function webhook for call routing decisions
@app.route('/route-call', methods=['POST'])
def route_call():
    """Handle AI agent's call routing decision via SWAIG webhook"""
    try:
        data = request.json
        logger.info(f"Route call webhook received: {data}")
        
        # Extract the function call data
        function_name = data.get('function', '')
        argument = data.get('argument', {})
        
        # Get the parsed arguments
        parsed_args = argument.get('parsed', [{}])[0] if argument.get('parsed') else {}
        decision = parsed_args.get('decision', 'block')
        caller_name = parsed_args.get('caller_name', 'Unknown')
        call_reason = parsed_args.get('call_reason', 'No reason given')
        
        logger.info(f"AI decision: {decision}, caller: {caller_name}, reason: {call_reason}")
        
        # Log the screening result
        log_screening_result(data, decision, caller_name, call_reason)
        
        # Return appropriate SWML response based on decision
        if decision == 'transfer':
            swml_response = {
                "response": f"Thank you {caller_name}, I'm connecting you now.",
                "action": [{
                    "SWML": {
                        "version": "1.0.0",
                        "sections": {
                            "main": [
                                {
                                    "play": {
                                        "url": f"say:Please hold while I connect you to {BUSINESS_NAME}.",
                                        "say_voice": "Polly.Joanna"
                                    }
                                },
                                {
                                    "play": {
                                        "url": "https://github.com/mclovin84/flask/raw/main/Fly%20with%20Me.mp3",
                                        "loop": 0
                                    }
                                },
                                {
                                    "connect": {
                                        "to": OWNER_PHONE_NUMBER,
                                        "timeout": 30,
                                        "confirm": f"https://{request.host}/owner-whisper"
                                    }
                                },
                                {"hangup": {}}
                            ]
                        }
                    }
                }]
            }
        elif decision == 'voicemail':
            swml_response = {
                "response": "I'll direct you to voicemail.",
                "action": [{
                    "SWML": {
                        "version": "1.0.0",
                        "sections": {
                            "main": [
                                {
                                    "play": {
                                        "url": f"say:{BUSINESS_NAME} is unavailable. Please leave a message after the beep.",
                                        "say_voice": "Polly.Joanna"
                                    }
                                },
                                {
                                    "record": {
                                        "beep": True,
                                        "format": "mp3",
                                        "max_length": 180,
                                        "finish_on_key": "#",
                                        "action": {
                                            "url": f"https://{request.host}/voicemail-complete",
                                            "method": "POST"
                                        }
                                    }
                                },
                                {
                                    "play": {
                                        "url": "say:Thank you for your message. Goodbye.",
                                        "say_voice": "Polly.Joanna"
                                    }
                                },
                                {"hangup": {}}
                            ]
                        }
                    }
                }]
            }
        else:  # block or default
            swml_response = {
                "response": "I'm sorry, we're unable to take your call at this time.",
                "action": [{
                    "SWML": {
                        "version": "1.0.0",
                        "sections": {
                            "main": [
                                {
                                    "play": {
                                        "url": "say:I'm sorry, we're unable to take your call at this time. If you believe this is an error, please try again later. Goodbye.",
                                        "say_voice": "Polly.Joanna"
                                    }
                                },
                                {"hangup": {}}
                            ]
                        }
                    }
                }]
            }
        
        logger.info(f"Returning SWML response for decision: {decision}")
        return jsonify(swml_response)
        
    except Exception as e:
        logger.error(f"Error in route_call webhook: {e}")
        # Return a safe fallback response
        return jsonify({
            "response": "I'm sorry, there was an error processing your call.",
            "action": [{
                "SWML": {
                    "version": "1.0.0",
                    "sections": {
                        "main": [
                            {
                                "play": {
                                    "url": "say:I'm sorry, there was an error. Please try again later.",
                                    "say_voice": "Polly.Joanna"
                                }
                            },
                            {"hangup": {}}
                        ]
                    }
                }
            }]
        })

# Owner whisper announcement when transferring calls
@app.route('/owner-whisper', methods=['POST'])
def owner_whisper():
    """Announce caller info to owner before connecting"""
    try:
        data = request.json or request.form
        logger.info(f"Owner whisper data: {data}")
        
        # Try to get caller info from various possible sources
        caller_name = data.get('caller_name', 'Unknown caller')
        call_reason = data.get('call_reason', 'No reason given')
        caller_number = data.get('from', data.get('caller_number', 'Unknown number'))
        
        # Create whisper announcement
        whisper_message = f"Call from {caller_name} about {call_reason}"
        
        # Return SWML for whisper announcement
        whisper_swml = {
            "version": "1.0.0",
            "sections": {
                "main": [
                    {
                        "play": {
                            "url": f"say:{whisper_message}",
                            "say_voice": "Polly.Joanna"
                        }
                    }
                ]
            }
        }
        
        return jsonify(whisper_swml)
        
    except Exception as e:
        logger.error(f"Error in owner_whisper: {e}")
        return jsonify({
            "version": "1.0.0",
            "sections": {
                "main": [
                    {
                        "play": {
                            "url": "say:Incoming call",
                            "say_voice": "Polly.Joanna"
                        }
                    }
                ]
            }
        })

# Voicemail completion handler
@app.route('/voicemail-complete', methods=['POST'])
def voicemail_complete():
    """Handle completed voicemail recording"""
    try:
        data = request.json or request.form
        logger.info(f"Voicemail completed: {data}")
        
        recording_url = data.get('RecordingUrl', '')
        call_sid = data.get('call_sid', data.get('CallSid', ''))
        duration = data.get('RecordingDuration', '0')
        
        # Log voicemail to Google Sheets
        if sheets_service and GOOGLE_SHEETS_ID:
            values = [[
                datetime.datetime.utcnow().isoformat(),
                call_sid,
                data.get('caller_name', 'Unknown'),
                data.get('call_reason', 'Voicemail'),
                recording_url,
                f"Duration: {duration} seconds"
            ]]
            
            try:
                sheets_service.spreadsheets().values().append(
                    spreadsheetId=GOOGLE_SHEETS_ID,
                    range='Voicemail!A:F',
                    valueInputOption='RAW',
                    body={'values': values}
                ).execute()
                logger.info("Voicemail logged to Google Sheets")
            except Exception as e:
                logger.error(f"Failed to log voicemail: {e}")
        
        # Send notification if configured
        if OWNER_SMS and sw_client:
            try:
                message = f"📧 New voicemail received\nDuration: {duration} seconds\nRecording: {recording_url}"
                sw_client.messages.create(
                    to=OWNER_SMS,
                    from_=os.environ.get('NOTIFICATION_NUMBER', OWNER_PHONE_NUMBER),
                    body=message
                )
                logger.info("Voicemail SMS notification sent")
            except Exception as e:
                logger.error(f"Failed to send SMS notification: {e}")
        
        return jsonify({'status': 'processed'})
        
    except Exception as e:
        logger.error(f"Error processing voicemail: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Generic event logging endpoint
@app.route('/log-event', methods=['POST'])
def log_event():
    """Log generic call events"""
    try:
        data = request.json
        logger.info(f"Logging event: {data}")
        
        if sheets_service and GOOGLE_SHEETS_ID:
            values = [[
                datetime.datetime.utcnow().isoformat(),
                data.get('call_sid', ''),
                data.get('event', 'unknown'),
                json.dumps(data)
            ]]
            
            sheets_service.spreadsheets().values().append(
                spreadsheetId=GOOGLE_SHEETS_ID,
                range='EventLog!A:D',
                valueInputOption='RAW',
                body={'values': values}
            ).execute()
        
        return jsonify({'status': 'logged'})
        
    except Exception as e:
        logger.error(f"Error logging event: {e}")
        return jsonify({'status': 'error'})

# Helper function to log screening results
def log_screening_result(webhook_data, decision, caller_name, call_reason):
    """Log AI screening results to Google Sheets"""
    try:
        if sheets_service and GOOGLE_SHEETS_ID:
            # Extract call information from webhook data
            call_info = webhook_data.get('call', {}) if isinstance(webhook_data.get('call'), dict) else {}
            
            values = [[
                datetime.datetime.utcnow().isoformat(),
                webhook_data.get('call_id', call_info.get('call_id', '')),
                call_info.get('from', ''),
                call_info.get('to', ''),
                decision,
                caller_name,
                call_reason,
                '', # spam_confidence placeholder
                json.dumps(webhook_data)[:500]  # truncated webhook data
            ]]
            
            sheets_service.spreadsheets().values().append(
                spreadsheetId=GOOGLE_SHEETS_ID,
                range='CallLog!A:I',
                valueInputOption='RAW',
                body={'values': values}
            ).execute()
            
            logger.info(f"Screening result logged: {decision} for {caller_name}")
            
    except Exception as e:
        logger.error(f"Failed to log screening result: {e}")

# Legacy endpoints for compatibility (simplified versions)
@app.route('/log-screening', methods=['POST'])
def log_screening():
    """Legacy endpoint for logging screening results"""
    try:
        data = request.json
        logger.info(f"Legacy screening log: {data}")
        return jsonify({'status': 'logged'})
    except Exception as e:
        logger.error(f"Error in legacy log-screening: {e}")
        return jsonify({'status': 'error'})

@app.route('/recording-complete', methods=['POST'])
def recording_complete():
    """Handle completed call recording"""
    try:
        data = request.json or request.form
        logger.info(f"Recording completed: {data}")
        return jsonify({'status': 'processed'})
    except Exception as e:
        logger.error(f"Error processing recording: {e}")
        return jsonify({'status': 'error'})

@app.route('/ai-context', methods=['POST'])
def ai_context():
    """Provide dynamic context to AI agent"""
    try:
        data = request.json
        context = {
            'business_hours': datetime.datetime.now().hour >= 9 and datetime.datetime.now().hour < 17,
            'current_time': datetime.datetime.now().isoformat()
        }
        return jsonify({'context': json.dumps(context)})
    except Exception as e:
        logger.error(f"Error providing AI context: {e}")
        return jsonify({'context': '{}'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
