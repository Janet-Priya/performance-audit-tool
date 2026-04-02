from fastapi import FastAPI
import asyncio

app = FastAPI(title="Target Microservice API", description="Simulated microservice for performance testing")

@app.get("/health")
async def health():
    return {"status": "ok", "message": "Service is healthy"}

@app.post("/login")
async def login():
    await asyncio.sleep(0.08)  # 80ms — change to 1.5 to simulate slow API for demo
    return {"token": "abc123xyz", "user_id": 42, "expires_in": 3600}

@app.get("/get-data")
async def get_data():
    await asyncio.sleep(0.15)  # 150ms
    return {"data": [1, 2, 3, 4, 5], "count": 5, "page": 1}

@app.get("/users")
async def get_users():
    await asyncio.sleep(0.03)  # 30ms
    return {"users": [
        {"id": 1, "name": "Alice", "email": "alice@example.com"},
        {"id": 2, "name": "Bob", "email": "bob@example.com"},
        {"id": 3, "name": "Charlie", "email": "charlie@example.com"},
    ]}

@app.post("/upload")
async def upload():
    await asyncio.sleep(0.4)  # 400ms — intentionally SLOW
    return {"uploaded": True, "file_id": "file_abc123", "size_bytes": 1024}

@app.get("/search")
async def search(q: str = "default"):
    await asyncio.sleep(0.2)  # 200ms
    return {"query": q, "results": [
        {"id": 1, "title": f"Result for {q} - Item 1"},
        {"id": 2, "title": f"Result for {q} - Item 2"},
    ], "total": 2}

@app.get("/notifications")
async def notifications():
    await asyncio.sleep(0.05)  # 50ms
    return {"notifications": [
        {"id": 1, "message": "Your report is ready", "read": False},
        {"id": 2, "message": "New user signed up", "read": True},
    ]}
