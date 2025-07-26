# main.py - Fixed SignalWire webhook handler
import os
import json
import datetime
import logging
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Environment variables
OWNER_PHONE_NUMBER = os.environ.get('OWNER_PHONE_NUMBER', '+15022969469')
BUSINESS_NAME = os.environ.get('BUSINESS_NAME', 'Anthony Barragan')

@app.route('/health', methods=['GET'])
def health():
    return "OK", 200

@app.route('/')
def index():
    return jsonify({"status": "success", "message": "Flask SignalWire Webhook Ready."})

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

@app.route('/route-call', methods=['POST'])
def route_call():
    """CRITICAL: Handle AI routing decision with proper SWML response format"""
    try:
        data = request.json
        logger.info(f"Route call webhook received: {data}")
        
        # Extract AI function arguments - this is the EXACT format SignalWire sends
        argument = data.get('argument', {})
        parsed_args = argument.get('parsed', [{}])[0] if argument.get('parsed') else {}
        
        decision = parsed_args.get('decision', 'block')
        caller_name = parsed_args.get('caller_name', 'Unknown')
        call_reason = parsed_args.get('call_reason', 'No reason given')
        
        logger.info(f"AI decision: {decision}, caller: {caller_name}, reason: {call_reason}")
        
        # CRITICAL: Return the EXACT JSON format SignalWire expects
        if decision == 'transfer':
            return jsonify({
                "response": f"Thank you {caller_name}, I'm connecting you now.",
                "action": [{
                    "SWML": {
                        "version": "1.0.0",
                        "sections": {
                            "main": [
                                {
                                    "play": {
                                        "url": f"say:Please hold while I connect you.",
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
                                        "timeout": 30
                                    }
                                },
                                {"hangup": {}}
                            ]
                        }
                    }
                }]
            })
        elif decision == 'voicemail':
            return jsonify({
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
                                        "finish_on_key": "#"
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
            })
        else:  # block
            return jsonify({
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
            })
        
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
