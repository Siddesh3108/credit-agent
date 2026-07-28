import json
import urllib.request
import urllib.error

print("Creating conversation...")
req = urllib.request.Request("http://127.0.0.1:8000/v1/conversations", 
                              data=json.dumps({"customer_ref": "CUST-3", "channel": "web"}).encode(),
                              headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())
token = data["session_token"]
conv_id = data["conversation_id"]
print(f"Auth token: {token}, Conv id: {conv_id}")

print("Sending message...")
try:
    req2 = urllib.request.Request(f"http://127.0.0.1:8000/v1/conversations/{conv_id}/messages", 
                                  data=json.dumps({"message": "I need a card replacement"}).encode(),
                                  headers={"Content-Type": "application/json", "Host": "localhost", "Authorization": f"Bearer {token}"})
    resp2 = urllib.request.urlopen(req2)
    print(resp2.read())
except urllib.error.HTTPError as e:
    print(f"HTTPError: {e.code}")
    print(e.read().decode())
