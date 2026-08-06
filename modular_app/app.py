import threading
from flask import Flask, request, jsonify

from config import VERIFY_TOKEN
from conversation import handle_message
from pipeline_sync import procesar_nuevo_pipeline_item

app = Flask(__name__)


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """
    Meta calls this once, with GET, when you click 'Verify and save'
    in the dashboard. It sends three query params:
      - hub.mode          (should be 'subscribe')
      - hub.verify_token  (should match VERIFY_TOKEN)
      - hub.challenge     (a random number we must echo back)
    If everything matches, we return hub.challenge as plain text
    and Meta considers the webhook verified.
    """
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("Webhook verified successfully!")
        return challenge, 200
    else:
        print("Webhook verification failed.")
        return "Verification failed", 403


@app.route("/webhook", methods=["POST"])
def receive_message():
    """
    Meta calls this with POST every time something happens: an incoming
    message, a delivery receipt, a read receipt, etc. We only care about
    actual incoming text messages -- status updates (sent/delivered/read)
    are expected and frequent, so we quietly ignore them instead of
    logging each one.
    """
    data = request.get_json()

    try:
        entry = data["entry"][0]
        change = entry["changes"][0]["value"]
        message = change["messages"][0]
        sender = message["from"]
        text_body = message["text"]["body"]

        print(f"Message from {sender}: {text_body}")

        # Run in the background instead of blocking here. Our own retry
        # loops (Estatus verification, etc.) can take many seconds --
        # if we don't respond to Meta quickly, it assumes delivery failed
        # and RE-SENDS the same message, causing duplicate processing.
        threading.Thread(target=handle_message, args=(sender, text_body)).start()

    except (KeyError, IndexError):
        # Not a text message (delivery/read receipt, etc.) -- nothing to do.
        pass

    # Respond immediately -- the real work happens in the background thread.
    return jsonify({"status": "received"}), 200


@app.route("/webhook/pipeline", methods=["POST"])
def pipeline_webhook():
    """
    Monday calls this whenever a new item is created on the Pipeline board.
    On FIRST registering the webhook, Monday sends a one-time payload like
    {"challenge": "some_string"} and expects us to echo it straight back --
    that's how Monday confirms we actually own this URL (its own version of
    Meta's GET-based handshake).
    """
    data = request.get_json()

    if "challenge" in data:
        return jsonify({"challenge": data["challenge"]}), 200

    try:
        event = data["event"]
        if event.get("type") == "create_pulse":
            pipeline_item_id = event["pulseId"]
            nombre_proyecto = event["pulseName"]
            print(f"New Pipeline item: {nombre_proyecto!r} (id={pipeline_item_id})")
            threading.Thread(
                target=procesar_nuevo_pipeline_item,
                args=(pipeline_item_id, nombre_proyecto),
            ).start()
    except (KeyError, TypeError) as e:
        print(f"Unrecognized Pipeline webhook payload shape: {e}")

    return jsonify({"status": "received"}), 200


if __name__ == "__main__":
    app.run(port=5000, debug=True)
