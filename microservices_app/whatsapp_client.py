import requests
from config import ACCESS_TOKEN, GRAPH_API_URL


def send_whatsapp_message(to, text):
    """
    Sends a plain text WhatsApp message to `to` (a phone number, no '+',
    e.g. '5218126293873' — same format WhatsApp gave us in the incoming
    payload's 'from' field).
    """
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }

    response = requests.post(GRAPH_API_URL, headers=headers, json=payload)
    print(f"Sent message -> status {response.status_code}: {response.text}")
    return response
