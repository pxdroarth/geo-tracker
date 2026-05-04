 
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import create_engine, Column, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import uuid
import os
import requests

app = FastAPI()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("DATABASE_URL não configurada")

engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)

class Location(Base):
    __tablename__ = "locations"
    id = Column(String, primary_key=True)
    ip = Column(String)
    lat = Column(Float)
    lon = Column(Float)
    city = Column(String)
    region = Column(String)
    country = Column(String)
    isp = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)

def get_ip_location(ip: str):
    """Usa ip-api.com (gratuito, sem chave, 45 req/min)"""
    try:
        resp = requests.get(f"http://ip-api.com/json/{ip}?fields=status,lat,lon,city,region,countryCode,isp", timeout=5)
        data = resp.json()
        if data.get("status") == "success":
            return {
                "lat": data["lat"],
                "lon": data["lon"],
                "city": data.get("city"),
                "region": data.get("region"),
                "country": data.get("countryCode"),
                "isp": data.get("isp")
            }
    except Exception as e:
        print(f"Erro IP geolocation: {e}")
    return None

@app.get("/", response_class=HTMLResponse)
async def index():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Tracker</title>
        <style>
            body { font-family: monospace; padding: 2rem; text-align: center; }
            .hidden { display: none; }
        </style>
    </head>
    <body>
        <h1>Hello World</h1>
        <p>Redirecionando...</p>
        <script>
            fetch('/track')
                .then(r => r.json())
                .then(data => {
                    console.log('Location tracked:', data);
                    document.body.innerHTML = '<h1>Hello World</h1><p>Status: OK</p>';
                })
                .catch(err => {
                    document.body.innerHTML = '<h1>Hello World</h1><p>Erro: ' + err + '</p>';
                });
        </script>
    </body>
    </html>
    """
    return html

@app.get("/track")
async def track(request: Request):
    # Pega IP real (Render usa proxy)
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host
    
    # Se for IP local ou de teste, usa um público
    if client_ip in ["127.0.0.1", "localhost", "::1"]:
        client_ip = "8.8.8.8"  # IP de exemplo
    
    loc_data = get_ip_location(client_ip)
    
    if not loc_data:
        return JSONResponse({"error": "Não foi possível localizar"}, status_code=404)
    
    db = SessionLocal()
    record_id = str(uuid.uuid4())[:8]
    new_loc = Location(
        id=record_id,
        ip=client_ip,
        lat=loc_data["lat"],
        lon=loc_data["lon"],
        city=loc_data["city"],
        region=loc_data["region"],
        country=loc_data["country"],
        isp=loc_data.get("isp")
    )
    db.add(new_loc)
    db.commit()
    db.close()
    
    return {
        "id": record_id,
        "ip": client_ip,
        "lat": loc_data["lat"],
        "lon": loc_data["lon"],
        "city": loc_data["city"],
        "region": loc_data["region"],
        "country": loc_data["country"]
    }

@app.get("/admin/locations")
async def list_locations():
    db = SessionLocal()
    locs = db.query(Location).order_by(Location.created_at.desc()).limit(100).all()
    db.close()
    return [
        {
            "id": l.id,
            "ip": l.ip,
            "lat": l.lat,
            "lon": l.lon,
            "city": l.city,
            "region": l.region,
            "country": l.country,
            "created_at": l.created_at.isoformat()
        }
        for l in locs
    ]