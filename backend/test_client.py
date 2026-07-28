from fastapi.testclient import TestClient
from app.main import app
import traceback
import sys

sys.stdout = open('test_output.log', 'w', encoding='utf-8')
sys.stderr = sys.stdout

try:
    with TestClient(app, raise_server_exceptions=True) as client:
        print("Starting tests...")
        response = client.post("/v1/conversations", json={"customer_ref": "CUST-1", "channel": "web"})
        print("Start:", response.status_code, response.json())
        data = response.json()
        token = data["session_token"]
        conv_id = data["conversation_id"]

        print("Sending message...")
        response2 = client.post(
            f"/v1/conversations/{conv_id}/messages", 
            json={"message": "I need a card replacement"},
            headers={"Authorization": f"Bearer {token}"}
        )
        print("Message:", response2.status_code)
        try:
            print(response2.json())
        except:
            print(response2.text)
except Exception as e:
    print("FATAL ERROR:")
    traceback.print_exc(file=sys.stdout)
