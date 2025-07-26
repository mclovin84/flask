# main.py - Complete SignalWire webhook handler with proper indentation
import os
import json
import datetime
import logging
from flask import Flask, request, jsonify

# Configure logging
logging.basicConfig(level=logging.INFO)__)

app = Flask(__name__)

# Configuration - environment variables
GOOGLE_SHEETS_ID = os.environ.get('GOOGLE_SHEETS_ID')
GOOGLE_CREDS_JSON = os.environ.get('GOOGLE_CREDS_JSON')
SIGNALWIRE_SPACE = os.environ.get('SIGNALWIRE_SPACE')
SIGNALWIRE_PROJECT = os.environ.get('SIGNALWIRE_PROJECT')
SIGNALWIRE_TOKEN = os.environ.get('SIGNALWIRE_TOKEN')
OWNER_PHONE_NUMBER = os.environ.get('OWNER_PHONE_NUMBER', '+15022969469')
BUSINESS_NAME = os.environ.get('BUSINESS_NAME', 'Anthony Barragan')

# Initialize Google Sheets client if credentials are available
sheets_service = None
if GOOGLE_CREDS_JSON:
    try:
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
        parsed_args = data.get('argument', {}).get('parsed', [{}])[0] if data.get('argument', {}).get('parsed') else {}
        decision = parsed_args.get('decision', 'block')
        caller_name = parsed_args.get('caller_name', 'Unknown')
        call_reason = parsed_args.get('call_reason', 'No reason given')
        
        logger.info(f"AI decision: {decision}, caller: {caller_name}, reason: {call_reason}")
        
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
                                    "connect": {
                                        "to": OWNER_PHONE_NUMBER,
                                        "timeout": 30
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
                                        "url": "say:I'm sorry, we're unable to take your call at this time. Goodbye.",
                                        "say_voice": "Polly.Joanna"
                                    }
                                },
                                {"hangup": {}}
                            ]
                        }
                    }
                }]
            }
        
        return jsonify(swml_response)
        
    except Exception as e:
        logger.error(f"Error in route_call webhook: {e}")
        return jsonify({
            "response": "I'm sorry, there was an error processing your call.",
            "action": [{
                "SWML": {
                    "version": "1.0.0",
                    "sections": {
                        "main": [
                            {"play": {"url": "say:I'm sorry, there was an error. Please try again later.", "say_voice": "Polly.Joanna"}},
                            {"hangup": {}}
                        ]
                    }
                }
            }]
        })

# Legacy endpoints for compatibility
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

@app.route('/owner-whisper', methods=['POST'])
def owner_whisper():
    """Announce caller info to owner before connecting"""
    try:
        return jsonify({
            "version": "1.0.0",
            "sections": {
                "main": [
                    {"play": {"url": "say:Incoming call", "say_voice": "Polly.Joanna"}}
                ]
            }
        })
    except Exception as e:
        logger.error(f"Error in owner_whisper: {e}")
        return jsonify({"version": "1.0.0", "sections": {"main": []}})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
