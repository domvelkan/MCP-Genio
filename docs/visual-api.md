# Central Visual API

The central endpoint is served by MCP-Genio and delegates image generation to the authenticated Andaria backend. It prefers Hugging Face when `HF_TOKEN` is configured and `COCKPIT_IMAGE_PROVIDER=auto`; otherwise it uses OpenRouter Images if configured.

## Render environment

**MCP-Genio**
- `VISUAL_API_TOKEN`: independent random secret, at least 32 characters. Share only with clients that need image generation.
- `ANDARIA_VISUAL_RENDER_URL`: defaults to `https://andaria.onrender.com/api/cockpit/visual/render`.
- Existing `COCKPIT_BRIDGE_TOKEN`: must match Andaria's `MCP_GENIO_TOKEN`.

**Andaria**
- `HF_TOKEN`: optional Hugging Face token with inference access.
- `COCKPIT_IMAGE_PROVIDER`: `auto` (default), `huggingface`, or `openrouter`.
- `COCKPIT_HF_IMAGE_MODEL`: defaults to `black-forest-labs/FLUX.1-dev`.
- Existing `OPENROUTER_API_KEY` remains the fallback provider key.
- `COCKPIT_IMAGE_MODEL`: OpenRouter image model, defaults to `bytedance-seed/seedream-4.5`.

Do not commit secrets or put them in prompts, query strings, or logs. Store the visual API token in each client's secret/credential store.

## Request

`POST https://mcp-genio.onrender.com/api/v1/visual/generate`

Headers:
- `Authorization: Bearer <VISUAL_API_TOKEN>`
- `Content-Type: application/json`

Body:
```json
{
  "prompt": "cinematic concept art of a bioluminescent forest, no text",
  "aspect_ratio": "16:9",
  "response_format": "url"
}
```

Supported aspect ratios: `1:1`, `3:2`, `2:3`, `4:3`, `3:4`, `16:9`, `9:16`. Prompts are limited to 1,800 characters.

### URL/data-URI response

With `response_format=url`, the JSON includes `image_url` as a `data:image/...;base64,...` URI. This is a self-contained data URI, **not a public, persistent internet URL**. Use it when a client accepts data URIs or needs to decode the image itself.

### Binary response

With `response_format=binary`, the response body is the raw image bytes with the correct image content type and a filename header. This is generally the best choice for n8n binary workflows, Apps Script Drive uploads, and Colab.

## cURL

Binary image:
```bash
curl -X POST 'https://mcp-genio.onrender.com/api/v1/visual/generate' \
  -H 'Authorization: Bearer YOUR_VISUAL_API_TOKEN' \
  -H 'Content-Type: application/json' \
  --data '{"prompt":"cinematic forest at dawn","aspect_ratio":"16:9","response_format":"binary"}' \
  --output andaris-visual.png
```

JSON/data URI:
```bash
curl -sS -X POST 'https://mcp-genio.onrender.com/api/v1/visual/generate' \
  -H 'Authorization: Bearer YOUR_VISUAL_API_TOKEN' \
  -H 'Content-Type: application/json' \
  --data '{"prompt":"cinematic forest at dawn","response_format":"url"}'
```

## Google Apps Script

Store the secret under **Project Settings → Script Properties** as `VISUAL_API_TOKEN`. Do not hardcode it in a shared script.

```javascript
function generateAndSaveVisual() {
  const token = PropertiesService.getScriptProperties().getProperty('VISUAL_API_TOKEN');
  if (!token) throw new Error('Missing VISUAL_API_TOKEN');

  const response = UrlFetchApp.fetch(
    'https://mcp-genio.onrender.com/api/v1/visual/generate',
    {
      method: 'post',
      contentType: 'application/json',
      headers: { Authorization: 'Bearer ' + token },
      payload: JSON.stringify({
        prompt: 'cinematic forest at dawn',
        aspect_ratio: '16:9',
        response_format: 'binary'
      }),
      muteHttpExceptions: true
    }
  );

  if (response.getResponseCode() < 200 || response.getResponseCode() >= 300) {
    throw new Error('Visual API failed: HTTP ' + response.getResponseCode());
  }
  const blob = response.getBlob().setName('andaris-visual.png');
  return DriveApp.createFile(blob).getUrl();
}
```

## n8n

Use an **HTTP Request** node:
- Method: `POST`
- URL: `https://mcp-genio.onrender.com/api/v1/visual/generate`
- Authentication: Header Auth credential, header `Authorization`, value `Bearer <VISUAL_API_TOKEN>`
- Body Content Type: JSON
- Body: `prompt`, `aspect_ratio`, and `response_format: binary`
- Configure the response to be returned as a file/binary and assign the desired binary property (for example `image`).

Use the node's binary output to upload to Drive, send through Telegram, or pass to another node. Avoid using the data-URI mode for spreadsheet cells or other fields with small size limits.

## Colab / Python

```python
import os
import requests

response = requests.post(
    "https://mcp-genio.onrender.com/api/v1/visual/generate",
    headers={"Authorization": f"Bearer {os.environ['VISUAL_API_TOKEN']}"},
    json={
        "prompt": "cinematic forest at dawn",
        "aspect_ratio": "16:9",
        "response_format": "binary",
    },
    timeout=240,
)
response.raise_for_status()
with open("andaris-visual.png", "wb") as output:
    output.write(response.content)
```

## Current limits

- The data-URI mode is not a shareable public URL. A public URL requires an object-storage destination and expiry/access policy.
- Generation is synchronous. Hugging Face cold starts or model/provider load can take time; clients should use generous timeouts.
- Render's free services can sleep, causing cold starts.
- The ComfyUI workflow API is separate and remains dependent on a reachable `COMFYUI_URL`.
