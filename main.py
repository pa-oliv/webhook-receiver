cat > /etc/dokploy/compose/programa-webhookreceiver-xoqzsc/code/main.py << 'EOF'
from fastapi import FastAPI, Request
import os
import json
import urllib.request
import urllib.error

app = FastAPI()

# Configurações
PB_URL = os.getenv("POCKETBASE_URL")
PB_EMAIL = os.getenv("POCKETBASE_EMAIL")
PB_PASSWORD = os.getenv("POCKETBASE_PASSWORD")
ZEROCLAW_TOKEN = os.getenv("ZEROCLAW_TOKEN")
ZEROCLAW_URL = "http://10.0.1.13:42617"

def authenticate_pocketbase():
    """Autentica no PocketBase e retorna o token"""
    try:
        data = json.dumps({
            "identity": PB_EMAIL,
            "password": PB_PASSWORD
        }).encode()
        
        req = urllib.request.Request(
            f"{PB_URL}/api/collections/_superusers/auth-with-password",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        response = urllib.request.urlopen(req, timeout=10)
        result = json.loads(response.read().decode())
        print("[AUTH OK]")
        return result.get("token")
    except Exception as e:
        print(f"[AUTH FAIL] {e}")
        return None

def save_to_pocketbase(token, phone, message, message_type="text"):
    """Salva mensagem no PocketBase"""
    try:
        data = json.dumps({
            "telefone": phone,
            "conteudo": message,
            "tipo": message_type
        }).encode()
        
        req = urllib.request.Request(
            f"{PB_URL}/api/collections/mensagens/records",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": token
            },
            method="POST"
        )
        
        response = urllib.request.urlopen(req, timeout=10)
        result = json.loads(response.read().decode())
        record_id = result.get("id")
        print(f"[SAVED] {record_id}")
        return record_id
    except Exception as e:
        print(f"[SAVE FAIL] {e}")
        return None

def ask_zeroclaw(message):
    """Envia mensagem para ZeroClaw e retorna resposta da IA"""
    try:
        data = json.dumps({"message": message}).encode()
        
        req = urllib.request.Request(
            f"{ZEROCLAW_URL}/webhook",
            data=data,
            headers={
                "Authorization": f"Bearer {ZEROCLAW_TOKEN}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        
        response = urllib.request.urlopen(req, timeout=30)
        result = json.loads(response.read().decode())
        ai_response = result.get("response", "")
        print(f"[ZEROCLAW OK] {len(ai_response)} caracteres")
        return ai_response
    except Exception as e:
        print(f"[ZEROCLAW FAIL] {e}")
        return None

@app.post("/webhook")
async def receive_webhook(request: Request):
    body = await request.json()
    event = body.get("event")
    
    # Ignorar eventos irrelevantes
    if event in ["connection.update", "contacts.update"]:
        print(f"[IGNORADO] evento: {event}")
        return {"ignored": True, "event": event}
    
    print(f"[WEBHOOK] {event}")
    
    # Processar apenas messages.upsert
    if event == "messages.upsert":
        try:
            msg_data = body["data"]["messages"][0]
            phone = msg_data["key"]["remoteJid"].split("@")[0]
            
            # Detectar tipo de mensagem
            if "conversation" in msg_data["message"]:
                message = msg_data["message"]["conversation"]
                msg_type = "text"
            elif "extendedTextMessage" in msg_data["message"]:
                message = msg_data["message"]["extendedTextMessage"]["text"]
                msg_type = "text"
            else:
                message = "[midia]"
                msg_type = "media"
            
            print(f"[MSG] recebida | {phone} | {message}")
            
            # 1. Salvar no PocketBase
            token = authenticate_pocketbase()
            if token:
                save_to_pocketbase(token, phone, message, msg_type)
            
            # 2. Processar com ZeroClaw (APENAS SE FOR TEXTO)
            if msg_type == "text" and message != "[midia]":
                ai_response = ask_zeroclaw(message)
                if ai_response:
                    print(f"[IA RESPOSTA] {ai_response[:100]}...")  # Mostra só primeiros 100 chars
                    # TODO: Aqui vai enviar para WhatsApp depois
            
            return {"status": "processed"}
            
        except Exception as e:
            print(f"[ERROR] {e}")
            return {"error": str(e)}
    
    return {"status": "ok"}

@app.get("/")
def read_root():
    return {"status": "webhook-receiver running", "zeroclaw": "integrated"}
EOF
