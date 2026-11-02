"""PROTOTYPE server: the search-UI concepts plus a same-origin proxy to the real API. Throwaway.

    uv run python apps/web_prototype/serve.py   # http://localhost:8040/?variant=A
"""

from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse

HERE = Path(__file__).parent
API = "http://localhost:8020"
app = FastAPI()
client = httpx.AsyncClient(base_url=API, timeout=30)


@app.api_route("/api/{path:path}", methods=["GET", "POST"])
async def proxy(path: str, request: Request) -> Response:
    upstream = await client.request(request.method, f"/{path}", params=request.query_params,
                                    content=await request.body(),
                                    headers={"content-type": request.headers.get("content-type", "application/json")})
    return Response(upstream.content, upstream.status_code, media_type=upstream.headers.get("content-type"))


@app.get("/{name:path}")
async def static(name: str) -> FileResponse:
    file = (HERE / (name or "index.html")).resolve()
    return FileResponse(file if file.is_relative_to(HERE) and file.is_file() else HERE / "index.html")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8040)
