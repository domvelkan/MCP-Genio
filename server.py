from __future__ import annotations

import hmac
import json
import logging
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("genio-mcp")

APP_NAME = "MCP-Genio"
API_TOKEN = os.getenv("GENIO_MCP_TOKEN", "").strip()
COMFYUI_URL = os.getenv("COMFYUI_URL", "").rstrip("/")
N8N_URL = os.getenv("N8N_URL", "").rstrip("/")
N8N_API_KEY = os.getenv("N8N_API_KEY", "").strip()
N8N_WEBHOOK_BASE = os.getenv("N8N_WEBHOOK_BASE", "").rstrip("/")
N8N_ALLOWED_WORKFLOWS = {
    item.strip() for item in os.getenv("N8N_ALLOWED_WORKFLOWS", "").split(",") if item.strip()
}
HERMES_HEALTH_URL = os.getenv("HERMES_HEALTH_URL", "").strip()

mcp = FastMCP(
    APP_NAME,
    instructions="Integração controlada com ComfyUI e n8n. Dispare apenas workflows autorizados. Nunca exponha segredos."
)

def required(name: str, value: str) -> str:
    if not value:
        raise RuntimeError(f"Configuração ausente: {name}")
    return value

async def get_json(url: str, headers: dict[str, str] | None = None, timeout: float = 15) -> Any:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

async def post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None,
                    timeout: float = 30) -> Any:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()

def n8n_headers() -> dict[str, str]:
    return {"X-N8N-API-KEY": required("N8N_API_KEY", N8N_API_KEY)}

@mcp.tool()
async def system_status() -> dict[str, Any]:
    """Mostra configuração e acessibilidade dos serviços, sem revelar tokens."""
    result: dict[str, Any] = {
        "service": APP_NAME,
        "comfyui_configured": bool(COMFYUI_URL),
        "n8n_configured": bool(N8N_URL and N8N_API_KEY),
        "allowed_workflow_count": len(N8N_ALLOWED_WORKFLOWS),
        "hermes_health_configured": bool(HERMES_HEALTH_URL),
    }
    targets = {
        "comfyui": (f"{COMFYUI_URL}/system_stats" if COMFYUI_URL else "", None),
        "n8n": (f"{N8N_URL}/healthz" if N8N_URL else "", n8n_headers() if N8N_URL and N8N_API_KEY else None),
        "hermes": (HERMES_HEALTH_URL, None),
    }
    for name, (url, headers) in targets.items():
        if not url:
            result[name] = "not_configured"
            continue
        try:
            async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
                response = await client.get(url, headers=headers)
                result[name] = "reachable" if response.is_success else f"http_{response.status_code}"
        except Exception as exc:
            logger.info("%s health check failed (%s)", name, type(exc).__name__)
            result[name] = "unreachable"
    return result

@mcp.tool()
async def comfyui_queue_status() -> dict[str, Any]:
    """Consulta a fila atual do ComfyUI."""
    return await get_json(f"{required('COMFYUI_URL', COMFYUI_URL)}/queue")

@mcp.tool()
async def comfyui_history(prompt_id: str) -> dict[str, Any]:
    """Consulta o histórico do ComfyUI para um prompt ID."""
    if not prompt_id or len(prompt_id) > 200 or any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in prompt_id
    ):
        raise ValueError("prompt_id inválido")
    data = await get_json(f"{required('COMFYUI_URL', COMFYUI_URL)}/history/{prompt_id}")
    return data if isinstance(data, dict) else {"result": data}

@mcp.tool()
async def comfyui_submit_workflow(workflow: dict[str, Any], client_id: str | None = None) -> dict[str, Any]:
    """Enfileira workflow JSON no ComfyUI; envie somente workflows revisados."""
    base = required("COMFYUI_URL", COMFYUI_URL)
    if not isinstance(workflow, dict) or not workflow:
        raise ValueError("workflow deve ser um objeto JSON não vazio")
    if len(json.dumps(workflow, ensure_ascii=False).encode("utf-8")) > 1_000_000:
        raise ValueError("workflow excede o limite de 1 MB")
    payload: dict[str, Any] = {"prompt": workflow}
    if client_id:
        if len(client_id) > 128 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in client_id):
            raise ValueError("client_id inválido")
        payload["client_id"] = client_id
    result = await post_json(f"{base}/prompt", payload)
    return result if isinstance(result, dict) else {"result": result}

@mcp.tool()
async def n8n_list_allowed_workflows() -> dict[str, Any]:
    """Lista apenas workflows cujos IDs estão na allowlist configurada."""
    base = required("N8N_URL", N8N_URL)
    _ = required("N8N_API_KEY", N8N_API_KEY)
    if not N8N_ALLOWED_WORKFLOWS:
        return {"workflows": [], "message": "Nenhum workflow permitido; configure N8N_ALLOWED_WORKFLOWS."}
    data = await get_json(f"{base}/api/v1/workflows?limit=250", headers=n8n_headers())
    rows = data.get("data", []) if isinstance(data, dict) else []
    allowed = [w for w in rows if str(w.get("id", "")) in N8N_ALLOWED_WORKFLOWS]
    return {"workflows": [{"id": str(w.get("id")), "name": w.get("name"), "active": w.get("active")} for w in allowed]}

@mcp.tool()
async def n8n_trigger_allowed_workflow(workflow_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Chama webhook n8n por identificador permitido; nunca aceita URL do chamador."""
    if workflow_id not in N8N_ALLOWED_WORKFLOWS:
        raise ValueError("workflow_id não está na allowlist")
    base = required("N8N_WEBHOOK_BASE", N8N_WEBHOOK_BASE)
    if any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-." for c in workflow_id):
        raise ValueError("workflow_id inválido")
    result = await post_json(f"{base}/{workflow_id}", payload or {}, timeout=60)
    return result if isinstance(result, dict) else {"result": result}

class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        if len(API_TOKEN) < 32:
            return JSONResponse({"error": "server_auth_not_configured"}, status_code=503)
        supplied = request.headers.get("authorization", "")
        expected = f"Bearer {API_TOKEN}"
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            return JSONResponse({"error": "unauthorized"}, status_code=401,
                                headers={"WWW-Authenticate": "Bearer"})
        return await call_next(request)

@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> Response:
    return JSONResponse({"ok": True, "service": APP_NAME})

app = mcp.streamable_http_app(host="0.0.0.0")
app.add_middleware(BearerAuthMiddleware)

if __name__ == "__main__":
    if len(API_TOKEN) < 32:
        raise SystemExit("Defina GENIO_MCP_TOKEN com pelo menos 32 caracteres.")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
