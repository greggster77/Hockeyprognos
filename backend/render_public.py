import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
GATEWAY_URL = os.getenv("HOCKEY_GATEWAY_URL", "").rstrip("/")
GATEWAY_TOKEN = os.getenv("HOCKEY_GATEWAY_TOKEN", "")

app = FastAPI(title="Hockeyprognos Public")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/{path:path}")
async def proxy_api(path: str, request: Request):
    if not GATEWAY_URL or not GATEWAY_TOKEN:
        raise HTTPException(503, "Gateway not configured")

    url = f"{GATEWAY_URL}/api/{path}"

    if request.url.query:
        url += "?" + request.url.query

    try:
        async with httpx.AsyncClient(timeout=35) as client:
            upstream = await client.get(
                url,
                headers={
                    "X-Gateway-Token": GATEWAY_TOKEN,
                    "Accept": "application/json",
                },
                follow_redirects=False,
            )

        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get(
                "content-type", "application/json"
            ),
            headers={"Cache-Control": "no-store"},
        )
    except httpx.RequestError:
        raise HTTPException(502, "Gateway unavailable")

# Webbappen serveras efter API-rutterna
app.mount(
    "/",
    StaticFiles(directory=str(ROOT / "web"), html=True),
    name="web",
)
