from __future__ import annotations

import hmac
import json
import logging
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.background import BackgroundTask
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
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
TELEGRAM_ALLOWED_CHAT_IDS = {
    item.strip() for item in os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",") if item.strip()
}
AI_PROVIDER = os.getenv("AI_PROVIDER", "openrouter").strip().lower()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "").strip()
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "").strip()

mcp = FastMCP(
    APP_NAME,
    instructions=(
        "Cockpit operacional do Andaris. Integra provedores de IA, ComfyUI e n8n. "
        "Dispare somente workflows revisados e autorizados. Nunca exponha segredos."
    ),
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


async def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: float = 30,
) -> Any:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        if not response.content:
            return {"ok": True, "status_code": response.status_code}
        try:
            return response.json()
        except ValueError:
            return {"ok": response.is_success, "status_code": response.status_code, "text": response.text[:1000]}


def n8n_headers() -> dict[str, str]:
    return {"X-N8N-API-KEY": required("N8N_API_KEY", N8N_API_KEY)}


def configured_providers() -> list[str]:
    providers = []
    if OPENROUTER_API_KEY and OPENROUTER_MODEL:
        providers.append("openrouter")
    if NVIDIA_API_KEY and NVIDIA_MODEL:
        providers.append("nvidia")
    return providers


async def _call_provider(provider: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    if provider == "openrouter":
        key = required("OPENROUTER_API_KEY", OPENROUTER_API_KEY)
        model = required("OPENROUTER_MODEL", OPENROUTER_MODEL)
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.getenv("ANDARIA_SITE", "https://andaria.com.br"),
            "X-Title": "Andaris MCP-Genio",
        }
    elif provider == "nvidia":
        key = required("NVIDIA_API_KEY", NVIDIA_API_KEY)
        model = required("NVIDIA_MODEL", NVIDIA_MODEL)
        url = f"{NVIDIA_BASE_URL}/chat/completions"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    else:
        raise ValueError("Provedor não suportado")

    async with httpx.AsyncClient(timeout=90, follow_redirects=False) as client:
        response = await client.post(
            url,
            headers=headers,
            json={"model": model, "messages": messages, "max_tokens": 1200},
        )
        response.raise_for_status()
        data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("provider_empty_response")
    message = choices[0].get("message") or {}
    text = message.get("content", "")
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("provider_empty_content")
    return {"text": text.strip(), "provider": provider, "model": data.get("model", model)}


async def chat_with_provider(prompt: str, system_prompt: str | None = None) -> dict[str, Any]:
    """Try the preferred hosted model API, then the other configured provider."""
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("A mensagem está vazia")
    if len(prompt) > 20000:
        raise ValueError("A mensagem excede o limite de 20.000 caracteres")
    providers = configured_providers()
    if not providers:
        raise RuntimeError("Nenhum provedor de IA configurado")
    preferred = [AI_PROVIDER, "nvidia" if AI_PROVIDER == "openrouter" else "openrouter"]
    ordered = [name for name in preferred if name in providers]
    messages = [
        {"role": "system", "content": (system_prompt or "Você é o copiloto operacional do Andaris. Seja claro, conciso e nunca afirme que executou uma ação sem evidência. Para executar automações, oriente o operador a usar os comandos autorizados do cockpit.").strip()[:10000]},
        {"role": "user", "content": prompt},
    ]
    errors = []
    for provider in ordered:
        try:
            return await _call_provider(provider, messages)
        except Exception as exc:
            logger.warning("AI provider %s failed (%s)", provider, type(exc).__name__)
            errors.append(provider)
    raise RuntimeError("Todos os provedores de IA configurados falharam: " + ", ".join(errors))


@mcp.tool()
async def ai_chat(prompt: str) -> dict[str, Any]:
    """Gera uma resposta via OpenRouter/NVIDIA com fallback entre provedores configurados."""
    return await chat_with_provider(prompt)


@mcp.tool()
async def system_status() -> dict[str, Any]:
    """Mostra configuração e acessibilidade dos serviços, sem revelar tokens."""
    result: dict[str, Any] = {
        "service": APP_NAME,
        "ai_providers_configured": configured_providers(),
        "preferred_ai_provider": AI_PROVIDER,
        "telegram_configured": bool(TELEGRAM_TOKEN and TELEGRAM_WEBHOOK_SECRET),
        "telegram_operator_count": len(TELEGRAM_ALLOWED_CHAT_IDS),
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
async def n8n_recent_executions(limit: int = 5) -> dict[str, Any]:
    """Consulta execuções recentes do n8n, filtradas para workflows permitidos."""
    base = required("N8N_URL", N8N_URL)
    _ = required("N8N_API_KEY", N8N_API_KEY)
    limit = max(1, min(int(limit), 20))
    if not N8N_ALLOWED_WORKFLOWS:
        return {"executions": [], "message": "Nenhum workflow autorizado."}
    data = await get_json(f"{base}/api/v1/executions?limit={limit}", headers=n8n_headers())
    rows = data.get("data", []) if isinstance(data, dict) else []
    allowed = [item for item in rows if str(item.get("workflowId", "")) in N8N_ALLOWED_WORKFLOWS]
    return {
        "executions": [
            {key: item.get(key) for key in ("id", "workflowId", "status", "startedAt", "stoppedAt", "mode")}
            for item in allowed[:limit]
        ]
    }


@mcp.tool()
async def n8n_trigger_allowed_workflow(workflow_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Chama webhook n8n por identificador permitido; nunca aceita URL do chamador."""
    if workflow_id not in N8N_ALLOWED_WORKFLOWS:
        raise ValueError("workflow_id não está na allowlist")
    base = required("N8N_WEBHOOK_BASE", N8N_WEBHOOK_BASE)
    if any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-." for c in workflow_id):
        raise ValueError("workflow_id inválido")
    safe_payload = payload or {}
    if len(json.dumps(safe_payload, ensure_ascii=False).encode("utf-8")) > 100_000:
        raise ValueError("payload excede o limite de 100 KB")
    result = await post_json(f"{base}/{workflow_id}", safe_payload, timeout=60)
    return result if isinstance(result, dict) else {"result": result}


async def telegram_send(chat_id: str | int, text: str) -> None:
    if not TELEGRAM_TOKEN:
        logger.error("Telegram token not configured; cannot send message")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        for offset in range(0, len(text) or 1, 3900):
            chunk = text[offset:offset + 3900]
            response = await client.post(url, json={"chat_id": chat_id, "text": chunk})
            response.raise_for_status()


def _cockpit_help() -> str:
    return (
        "🚀 ANDARIS · COCKPIT\n\n"
        "/cockpit ou /status — estado dos serviços\n"
        "/providers — provedores de IA configurados\n"
        "/workflows — workflows autorizados no n8n\n"
        "/runs — execuções recentes do n8n\n"
        "/run ID [JSON] — executar workflow autorizado\n"
        "Qualquer outra mensagem conversa com a IA.\n\n"
        "Só chats explicitamente autorizados podem operar o cockpit."
    )


async def _handle_telegram_message(message: dict[str, Any]) -> None:
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    if not chat_id or chat_id not in TELEGRAM_ALLOWED_CHAT_IDS:
        logger.warning("Ignored Telegram message from non-allowlisted chat")
        return
    text = str(message.get("text") or "").strip()
    if not text:
        return
    command = text.split(maxsplit=1)[0].split("@", 1)[0].lower()

    try:
        if command in {"/start", "/help"}:
            await telegram_send(chat_id, _cockpit_help())
        elif command in {"/cockpit", "/status"}:
            status = await system_status()
            lines = ["🚀 ANDARIS · COCKPIT", ""]
            for key, value in status.items():
                lines.append(f"{key}: {', '.join(value) if isinstance(value, list) else value}")
            await telegram_send(chat_id, "\n".join(lines))
        elif command == "/providers":
            providers = configured_providers()
            await telegram_send(chat_id, f"IA preferencial: {AI_PROVIDER}\nDisponíveis: {', '.join(providers) if providers else 'nenhum configurado'}")
        elif command == "/workflows":
            data = await n8n_list_allowed_workflows()
            workflows = data.get("workflows", [])
            body = "\n".join(f"• {w.get('name') or 'Workflow'} — ID {w.get('id')} — {'ativo' if w.get('active') else 'inativo'}" for w in workflows)
            await telegram_send(chat_id, "Workflows autorizados:\n" + (body or "Nenhum workflow disponível."))
        elif command == "/runs":
            data = await n8n_recent_executions(5)
            executions = data.get("executions", [])
            body = "\n".join(
                f"• #{item.get('id')} · workflow {item.get('workflowId')} · {item.get('status') or 'status desconhecido'}"
                for item in executions
            )
            await telegram_send(chat_id, "Execuções recentes:\n" + (body or "Nenhuma execução recente encontrada."))
        elif command == "/run":
            parts = text.split(maxsplit=2)
            if len(parts) < 2:
                await telegram_send(chat_id, "Uso: /run ID_DO_WORKFLOW [JSON opcional]")
                return
            workflow_id = parts[1].strip()
            payload: dict[str, Any] = {}
            if len(parts) == 3:
                parsed = json.loads(parts[2])
                if not isinstance(parsed, dict):
                    raise ValueError("O payload JSON precisa ser um objeto.")
                payload = parsed
            result = await n8n_trigger_allowed_workflow(workflow_id, payload)
            await telegram_send(chat_id, "✅ Solicitação enviada ao n8n.\n" + json.dumps(result, ensure_ascii=False)[:2500])
        else:
            result = await chat_with_provider(text)
            await telegram_send(chat_id, f"[{result['provider']} · {result['model']}]\n\n{result['text']}")
    except Exception as exc:
        logger.exception("Telegram cockpit operation failed (%s)", type(exc).__name__)
        safe_message = str(exc) if isinstance(exc, (ValueError, json.JSONDecodeError)) else "A operação falhou. Confira a configuração e os logs do serviço."
        await telegram_send(chat_id, f"⚠️ {safe_message[:1000]}")


@mcp.custom_route("/telegram/webhook", methods=["POST"], include_in_schema=False)
async def telegram_webhook(request: Request) -> Response:
    if not TELEGRAM_TOKEN or len(TELEGRAM_WEBHOOK_SECRET) < 32:
        return JSONResponse({"error": "telegram_not_configured"}, status_code=503)
    supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(supplied, TELEGRAM_WEBHOOK_SECRET):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        update = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    if not isinstance(update, dict):
        return JSONResponse({"error": "invalid_update"}, status_code=400)
    message = update.get("message")
    if not isinstance(message, dict):
        return JSONResponse({"ok": True})
    # Acknowledge Telegram immediately; do the potentially slow provider call after the response.
    return JSONResponse({"ok": True}, background=BackgroundTask(_handle_telegram_message, message))


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health" or request.url.path == "/telegram/webhook":
            return await call_next(request)
        if len(API_TOKEN) < 32:
            return JSONResponse({"error": "server_auth_not_configured"}, status_code=503)
        supplied = request.headers.get("authorization", "")
        expected = f"Bearer {API_TOKEN}"
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            return JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
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
