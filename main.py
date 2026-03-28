from fastapi import FastAPI, Request
import httpx, os, json

app = FastAPI()

# Configurações do PocketBase (já existentes)
PB_URL = os.getenv("POCKETBASE_URL", "")
PB_EMAIL = os.getenv("POCKETBASE_EMAIL", "")
PB_PASS = os.getenv("POCKETBASE_PASSWORD", "")

# Configurações da Evolution API (novas)
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "")   # Ex: http://evolution-api:8080
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")   # Sua chave de API
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "") # Nome da instância (se necessário)

async def get_token():
    async with httpx.AsyncClient() as c:
        r = await c.post(
            f"{PB_URL}/api/collections/_superusers/auth-with-password",
            json={"identity": PB_EMAIL, "password": PB_PASS}
        )
        if r.status_code == 200:
            print("[AUTH OK]")
            return r.json()["token"]
        print(f"[AUTH FAIL] {r.status_code}")
        return None

@app.get("/health")
async def health():
    return {"status": "ok"}

# Endpoint existente: recebe webhooks da Evolution e salva no PocketBase
@app.post("/webhook")
async def webhook(request: Request):
    try:
        body = await request.json()
    except:
        return {"error": "JSON invalido"}

    event = body.get("event", "unknown")
    data = body.get("data", {})
    key = data.get("key", {})
    message = data.get("message", {})

    telefone = key.get("remoteJid", "").replace("@s.whatsapp.net", "")
    from_me = key.get("fromMe", False)
    tipo = "enviada" if from_me else "recebida"
    texto = (
        message.get("conversation")
        or message.get("extendedTextMessage", {}).get("text")
        or "[midia]"
    )

    print(f"[WEBHOOK] {event}")
    print(f"[MSG] {tipo} | {telefone} | {texto[:50]}")

    token = await get_token()
    if not token:
        return {"error": "Auth falhou"}

    record = {
        "telefone": telefone,
        "mensagem": texto,
        "tipo": tipo,
        "evento": event,
        "payload_raw": json.dumps(body)[:2000]
    }

    async with httpx.AsyncClient() as c:
        r = await c.post(
            f"{PB_URL}/api/collections/mensagens/records",
            json=record,
            headers={"Authorization": f"Bearer {token}"}
        )

    if r.status_code in [200, 201]:
        rid = r.json().get("id", "?")
        print(f"[SAVED] {rid}")
        return {"success": True, "record_id": rid}

    print(f"[PB ERROR] {r.status_code}: {r.text}")
    return {"error": "Falha ao salvar"}

# NOVO ENDPOINT: recebe webhooks do PocketBase e envia para a Evolution
@app.post("/pocketbase-webhook")
async def pocketbase_webhook(request: Request):
    try:
        body = await request.json()
    except:
        return {"error": "JSON invalido"}

    record = body.get("record", {})
    action = body.get("action", "")

    telefone = record.get("telefone", "").replace("@s.whatsapp.net", "")
    mensagem = record.get("mensagem", "")

    if not telefone or not mensagem:
        return {"error": "Campos telefone ou mensagem não encontrados"}

    print(f"[POCKETBASE] Ação: {action} | Telefone: {telefone} | Msg: {mensagem[:50]}")

    # URL correta para Evolution API v2
    evolution_url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }
    
    # Garante que o número está no formato correto (só dígitos)
    numero_limpo = ''.join(filter(str.isdigit, telefone))
    
    payload = {
        "number": numero_limpo,
        "text": mensagem
    }

    print(f"[DEBUG] URL: {evolution_url}")
    print(f"[DEBUG] Número: {numero_limpo}")

    async with httpx.AsyncClient() as c:
        try:
            response = await c.post(evolution_url, json=payload, headers=headers, timeout=10.0)
            
            if response.status_code == 200 or response.status_code == 201:
                print("[EVOLUTION] Mensagem enviada com sucesso")
                return {"success": True, "evolution_response": response.json()}
            else:
                print(f"[EVOLUTION] Erro: {response.status_code} - {response.text}")
                return {"error": f"Erro ao enviar mensagem: {response.status_code}", "details": response.text}
        except Exception as e:
            print(f"[EVOLUTION] Exceção: {str(e)}")
            return {"error": f"Exceção ao conectar: {str(e)}"}
