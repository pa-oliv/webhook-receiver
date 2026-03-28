from fastapi import FastAPI, Request
import httpx, os, json

app = FastAPI()

PB_URL = os.getenv("POCKETBASE_URL", "")
PB_EMAIL = os.getenv("POCKETBASE_EMAIL", "")
PB_PASS = os.getenv("POCKETBASE_PASSWORD", "")

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