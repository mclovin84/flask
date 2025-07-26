import os
import json
import datetime
import logging
from flask import Flask, request, jsonify

from google.oauth2 import service_account
from googleapiclient.discovery import build
from twilio.rest import Client
import openai

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ---------- ENVIRONMENT ----------
GOOGLE_SHEETS_ID   = os.environ.get('GOOGLE_SHEETS_ID')
GOOGLE_CREDS_JSON  = os.environ.get('GOOGLE_CREDS_JSON')
OPENAI_API_KEY     = os.environ.get('OPENAI_API_KEY')
SIGNALWIRE_PROJECT = os.environ.get('SIGNALWIRE_PROJECT')
SIGNALWIRE_SPACE   = os.environ.get('SIGNALWIRE_SPACE')
SIGNALWIRE_TOKEN   = os.environ.get('SIGNALWIRE_TOKEN')
OWNER_PHONE_NUMBER = os.environ.get('OWNER_PHONE_NUMBER', '+15022969469')
OWNER_SMS          = os.environ.get('OWNER_SMS')
BUSINESS_NAME      = os.environ.get('BUSINESS_NAME', 'Anthony Barragan')

# ---------- GOOGLE SHEETS INIT ----------
sheets_service = None
BLOCKLIST, ALLOWLIST = set(), set()
try:
    creds = service_account.Credentials.from_service_account_info(
        json.loads(GOOGLE_CREDS_JSON),
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    sheets_service = build('sheets', 'v4', credentials=creds)
    logger.info("Google Sheets API initialized.")
except Exception as e:
    logger.warning(f"Google Sheets integration failed: {e}")

def refresh_lists():
    global BLOCKLIST, ALLOWLIST
    if sheets_service and GOOGLE_SHEETS_ID:
        try:
            bl_vals = sheets_service.spreadsheets().values().get(
                spreadsheetId=GOOGLE_SHEETS_ID, range="Blocklist!A:A"
            ).execute().get("values", [])
            BLOCKLIST = set(num[0] for num in bl_vals if num)
            al_vals = sheets_service.spreadsheets().values().get(
                spreadsheetId=GOOGLE_SHEETS_ID, range="Allowlist!A:A"
            ).execute().get("values", [])
            ALLOWLIST = set(num[0] for num in al_vals if num)
        except Exception as e:
            logger.warning("Block/allow list fetch failed: %s", e)
refresh_lists()

# ---------- SIGNALWIRE (Twilio-compatible) CLIENT ----------
sw_client = None
try:
    sw_client = Client(
        SIGNALWIRE_PROJECT, SIGNALWIRE_TOKEN,
        signalwire_space=SIGNALWIRE_SPACE  # This is correct for modern signalwire SDKs
    )
except Exception as e:
    logger.warning(f"SignalWire client error: {e}")

# ---------- OPENAI ----------
try:
    openai.api_key = OPENAI_API_KEY
except Exception as e:
    logger.warning("OpenAI not configured: %s", e)

def ai_screening(transcript):
    prompt = (
        "You are a call screening assistant. "
        "Based on this transcript, should the call be transferred, blocked, or sent to voicemail? "
        "Reply as JSON: {'decision':'transfer/block/voicemail','caller_name':'','call_reason':''}\n"
        f"Transcript: {transcript}"
    )
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": prompt}],
            max_tokens=150,
            temperature=0
        )
        data = json.loads(resp.choices[0].message.content.strip())
        return data
    except Exception as e:
        logger.warning("OpenAI screening error: %s", e)
        return {"decision": "voicemail", "caller_name": "Unknown", "call_reason": transcript[:40]}

def log_to_sheet(tab, row):
    if sheets_service and GOOGLE_SHEETS_ID:
        try:
            sheets_service.spreadsheets().values().append(
                spreadsheetId=GOOGLE_SHEETS_ID,
                range=f"{tab}!A:Z",
                valueInputOption='RAW',
                body={'values': [row]}
            ).execute()
        except Exception as e:
            logger.warning("Sheet logging error: %s", e)

def send_notification(msg):
    if OWNER_SMS and sw_client:
        try:
            sw_client.messages.create(
                to=OWNER_SMS, from_=OWNER_PHONE_NUMBER, body=msg[:1600]
            )
        except Exception as e:
            logger.warning("SMS notification failed: %s", e)

@app.route('/health')
def health():
    return "OK", 200

@app.route('/')
def index():
    return {"message": "Dynamic SignalWire Webhook Ready", "status": "success"}

@app.route("/callflow", methods=["POST"])
def callflow():
    refresh_lists()
    data = request.get_json(force=True) or {}
    call_sid = data.get("call_sid", "")
    from_num = data.get("from", "")
    dt = datetime.datetime.utcnow().isoformat()

    # Block/Allow logic
    if from_num in BLOCKLIST:
        log_to_sheet("CallLog", [dt, call_sid, from_num, "blocked", "", "blocklist"])
        return jsonify({
            "version": "1.0.0",
            "sections": {"main": [
                {"play": {"url": "say:Your number is blocked. Goodbye.", "say_voice": "Polly.Joanna"}},
                {"hangup": {}}
            ]}
        })
    elif from_num in ALLOWLIST:
        log_to_sheet("CallLog", [dt, call_sid, from_num, "transferred", "", "allowlist"])
        return jsonify({
            "version": "1.0.0",
            "sections": {"main": [
                {"play": {"url": "say:Please hold, connecting you now.", "say_voice": "Polly.Joanna"}},
                {"connect": {"to": OWNER_PHONE_NUMBER, "timeout": 30}},
                {"hangup": {}}
            ]}
        })
    else:
        # Ask, then record, then AI
        return jsonify({
            "version": "1.0.0",
            "sections": {"main": [
                {"play": {"url": "say:Please state your name and reason for calling after the beep.", "say_voice": "Polly.Joanna"}},
                {"record": {
                    "beep": True,
                    "format": "mp3",
                    "max_length": 45,
                    "action": {
                        "url": "https://flask-production-41f4.up.railway.app/process-recording",
                        "method": "POST",
                        "params": {
                            "call_sid": call_sid,
                            "from": from_num,
                        }
                    }
                }}
            ]}
        })

@app.route("/process-recording", methods=["POST"])
def process_recording():
    # Try form, then JSON
    form = request.form or {}
    json_body = (request.get_json(force=True) or {}) if not form else {}
    rec_url = form.get("RecordingUrl") or json_body.get("RecordingUrl", "")
    from_number = form.get("from") or json_body.get("from", "")
    call_sid = form.get("call_sid") or json_body.get("call_sid", "")
    dt = datetime.datetime.utcnow().isoformat()

    transcript = f"Recording is at {rec_url} (add STT integration for AI)."
    ai_result = ai_screening(transcript)
    decision = ai_result.get("decision", "voicemail")
    caller_name = ai_result.get("caller_name", "Unknown")
    call_reason = ai_result.get("call_reason", "")

    log_to_sheet("CallLog", [dt, call_sid, from_number, decision, caller_name, call_reason, rec_url])
    if decision == "transfer":
        send_notification(f"Incoming call from {caller_name}: {call_reason}")

    if decision == "transfer":
        return jsonify({
            "version": "1.0.0",
            "sections": {"main": [
                {"play": {"url": f"say:Thank you {caller_name}, connecting you now.", "say_voice": "Polly.Joanna"}},
                {"connect": {"to": OWNER_PHONE_NUMBER, "timeout": 30}},
                {"hangup": {}}
            ]}
        })
    elif decision == "block":
        return jsonify({
            "version": "1.0.0",
            "sections": {"main": [
                {"play": {"url": "say:We're unable to take your call. Goodbye.", "say_voice": "Polly.Joanna"}},
                {"hangup": {}}
            ]}
        })
    else:
        return jsonify({
            "version": "1.0.0",
            "sections": {"main": [
                {"play": {"url": "say:Please leave a voicemail after the beep.", "say_voice": "Polly.Joanna"}},
                {"record": {
                    "beep": True,
                    "format": "mp3",
                    "max_length": 180,
                    "action": {
                        "url": "https://flask-production-41f4.up.railway.app/log-voicemail",
                        "method": "POST",
                        "params": {
                            "call_sid": call_sid,
                            "from": from_number,
                            "caller_name": caller_name or from_number
                        }
                    }
                }},
                {"hangup": {}}
            ]}
        })

@app.route("/log-voicemail", methods=["POST"])
def log_voicemail():
    form = request.form or {}
    json_body = (request.get_json(force=True) or {}) if not form else {}
    rec_url = form.get("RecordingUrl") or json_body.get("RecordingUrl", "")
    from_number = form.get("from") or json_body.get("from", "")
    call_sid = form.get("call_sid") or json_body.get("call_sid", "")
    caller_name = form.get("caller_name") or json_body.get("caller_name") or from_number or ""
    dt = datetime.datetime.utcnow().isoformat()
    log_to_sheet("Voicemail", [dt, call_sid, from_number, caller_name, rec_url])
    send_notification(f"Voicemail from {caller_name or from_number}: {rec_url}")
    return jsonify({"status": "processed"})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
