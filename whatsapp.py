from flask import Flask, request, jsonify
from twilio.rest import Client
from pyngrok import ngrok, conf
from dotenv import load_dotenv
import os, json, sqlite3

# Load environment variables
load_dotenv()

app = Flask(__name__)

# --------- CONFIG ----------
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN  = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_FROM = os.getenv('TWILIO_WHATSAPP_FROM')
PORT = int(os.getenv('PORT', 5000))
DB_FILE = "sent_log.db"
# ----------------------------

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# === Database setup ===
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sent_log (
            shipment_id TEXT,
            attribute_name TEXT,
            attribute_value TEXT,
            PRIMARY KEY (shipment_id, attribute_name)
        )
    """)
    conn.commit()
    conn.close()

def get_sent_value(shipment_id, attr):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT attribute_value FROM sent_log WHERE shipment_id=? AND attribute_name=?",
                (shipment_id, attr))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def save_sent_value(shipment_id, attr, value):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO sent_log (shipment_id, attribute_name, attribute_value)
        VALUES (?, ?, ?)
    """, (shipment_id, attr, value))
    conn.commit()
    conn.close()

init_db()

# === Ngrok start (free temporary URL) ===
def start_ngrok_and_get_url(port=PORT):
    conf.get_default().monitor_thread = False
    tunnel = ngrok.connect(port, "http")
    public_url = tunnel.public_url
    print(f"Ngrok public URL {public_url} - http://localhost:{port}")
    with open("ngrok_url.txt", "w") as f:
        f.write(public_url)
    return public_url

# === JSON search for specific attributes ===
def find_selected_attribute_dates(obj):
    target_keys = ["attributeDate1", "attributeDate2", "attributeDate6", "attributeDate7"]
    found = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in target_keys and isinstance(v, dict) and "value" in v:
                found[k] = v["value"]
            elif isinstance(v, (dict, list)):
                found.update(find_selected_attribute_dates(v))
    elif isinstance(obj, list):
        for item in obj:
            found.update(find_selected_attribute_dates(item))
    return found

# === Extract OTM payload ===
def extract_otm_payload(data):
    if "transactions" in data:
        items = data["transactions"].get("items", [])
        if items and "body" in items[0]:
            return items[0]["body"]
    elif "body" in data:
        return data["body"]
    return data

# === Flask routes ===
@app.route("/send-message", methods=["POST"])
def send_message():
    try:
        data = request.get_json(force=True)
    except Exception as e:
        print("JSON parse error", e)
        return jsonify({"status": "error", "message": "invalid JSON"}), 400

    payload = extract_otm_payload(data)
    print("Extracted payload", json.dumps(payload, indent=2))

    dates_found = find_selected_attribute_dates(payload)
    if not dates_found:
        return jsonify({"status": "error", "message": "No selected attributeDate fields"}), 400

    # --- Extract dynamic phone number and prepend +20 ---
    customer_phone = payload.get("attributeNumber7")
    if customer_phone is None:
        return jsonify({"status": "error", "message": "attributeNumber7 (phone) missing"}), 400

    try:
        customer_phone = str(int(float(customer_phone)))
    except Exception as e:
        print("Phone parse error", e)
        return jsonify({"status": "error", "message": "Invalid phone number format"}), 400

    customer_phone = f"+20{customer_phone}"
    phone_to_send = f"whatsapp:{customer_phone}"
    print("Phone to send", phone_to_send)

    shipment_id = str(payload.get("shipmentXid", payload.get("shipmentId", "unknown")))
    messages_sent = []

    custom_messages = {
        "attributeDate1": "Dear Customer, CUSTOMER ACTUAL ARRIVAL at {value}",
        "attributeDate2": "Dear Customer, CUSTOMER ACTUAL DEPARTURE at {value}",
        "attributeDate6": "Dear Customer, ACTUAL LOADING DATE at {value}",
        "attributeDate7": "Dear Customer, ACTUAL DISCHARGING DATE at {value}",
    }

    for attr, value in dates_found.items():
        prev_value = get_sent_value(shipment_id, attr)
        if prev_value == value:
            print(f"Skipping duplicate for {shipment_id} {attr}={value}")
            continue

        message_text = custom_messages.get(attr, f"{attr} updated {value}").replace("{value}", str(value))
        try:
            client.messages.create(
                body=message_text,
                from_=TWILIO_WHATSAPP_FROM,
                to=phone_to_send
            )
            messages_sent.append(message_text)
            save_sent_value(shipment_id, attr, value)
        except Exception as e:
            print("Twilio send error", e)
            return jsonify({"status": "error", "message": "Failed to send message"}), 500

    return jsonify({
        "status": "success",
        "messages_sent": messages_sent,
        "phone_sent": phone_to_send
    }), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/ngrok-url", methods=["GET"])
def get_ngrok_url():
    try:
        with open("ngrok_url.txt", "r") as f:
            url = f.read().strip()
        return jsonify({"ngrok_url": url}), 200
    except Exception:
        return jsonify({"ngrok_url": None}), 200

@app.route("/show-log", methods=["GET"])
def show_log():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT shipment_id, attribute_name, attribute_value FROM sent_log")
    rows = cur.fetchall()
    conn.close()
    return jsonify(rows)

if __name__ == "__main__":
    try:
        public_url = start_ngrok_and_get_url(PORT)
        print(f"\nYour POST endpoint {public_url}/send-message\n")
        print(f"View logs at {public_url}/show-log\n")
    except Exception as e:
        print("Ngrok error", e)

    app.run(host="0.0.0.0", port=PORT)
