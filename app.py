from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import requests
import os
import uuid
import asyncpg
from datetime import datetime

app = FastAPI()

# Pega a URL do banco que o Railway injeta automaticamente
DATABASE_URL = os.getenv("DATABASE_URL")

async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS locations (
            id TEXT PRIMARY KEY,
            ip TEXT,
            lat REAL,
            lon REAL,
            city TEXT,
            region TEXT,
            country TEXT,
            isp TEXT,
            created_at TIMESTAMP
        )
    ''')
    await conn.close()

@app.on_event("startup")
async def startup():
    await init_db()

def get_ip_location(ip: str):
    try:
        resp = requests.get(f"http://ip-api.com/json/{ip}?fields=status,lat,lon,city,region,countryCode,isp", timeout=5)
        data = resp.json()
        if data.get("status") == "success":
            return {
                "lat": data["lat"],
                "lon": data["lon"],
                "city": data.get("city", ""),
                "region": data.get("region", ""),
                "country": data.get("countryCode", ""),
                "isp": data.get("isp", "")
            }
    except:
        pass
    return None

@app.get("/", response_class=HTMLResponse)
async def index():
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>Tracker</title></head>
    <body>
        <h1>Hello World</h1>
        <script>
            fetch('/track')
                .then(r => r.json())
                .then(data => console.log('Tracked:', data))
                .catch(err => console.log('Error:', err));
        </script>
    </body>
    </html>
    """
    return html

@app.get("/track")
async def track(request: Request):
    forwarded = request.headers.get("x-forwarded-for")
    client_ip = forwarded.split(",")[0].strip() if forwarded else request.client.host
    
    if client_ip in ["127.0.0.1", "localhost", "::1"]:
        client_ip = "8.8.8.8"
    
    loc_data = get_ip_location(client_ip)
    if not loc_data:
        return {"error": "localizacao nao encontrada"}
    
    conn = await asyncpg.connect(DATABASE_URL)
    record_id = str(uuid.uuid4())[:8]
    await conn.execute('''
        INSERT INTO locations (id, ip, lat, lon, city, region, country, isp, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    ''', record_id, client_ip, loc_data["lat"], loc_data["lon"],
        loc_data["city"], loc_data["region"], loc_data["country"],
        loc_data["isp"], datetime.utcnow())
    await conn.close()
    
    return {"id": record_id, "lat": loc_data["lat"], "lon": loc_data["lon"]}

@app.get("/admin")
async def admin():
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch('''
        SELECT id, ip, lat, lon, city, region, country, isp, created_at
        FROM locations ORDER BY created_at DESC LIMIT 50
    ''')
    await conn.close()
    
    html = "<h1>📍 Localizações capturadas</h1><table border='1'><tr><th>ID</th><th>IP</th><th>Lat</th><th>Lon</th><th>Cidade</th><th>Região</th><th>País</th><th>ISP</th><th>Data</th></tr>"
    for r in rows:
        html += f"<tr><td>{r['id']}</td><td>{r['ip']}</td><td>{r['lat']}</td><td>{r['lon']}</td><td>{r['city']}</td><td>{r['region']}</td><td>{r['country']}</td><td>{r['isp']}</td><td>{r['created_at']}</td></tr>"
    html += "</table>"
    return HTMLResponse(html)