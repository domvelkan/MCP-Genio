# MCP-Genio

Servidor MCP independente para integração controlada entre clientes MCP, ComfyUI, n8n e verificação opcional de saúde do Hermes.

## Recursos
- MCP Streamable HTTP em `/mcp`.
- Token Bearer obrigatório para todas as rotas exceto `/health`.
- ComfyUI: estado da fila, histórico por prompt ID e envio de workflow JSON.
- n8n: listagem filtrada por allowlist e disparo de webhooks autorizados.
- Docker, Render Blueprint e CI no GitHub Actions.

## Configuração
Configure as variáveis de ambiente documentadas em `.env.example`. Gere o token com:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Instale e execute:

```bash
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 10000
```

Endpoints: `/health` e MCP em `/mcp`.

## Segurança
- Não comite segredos ou arquivos `.env`.
- Mantenha ComfyUI e n8n privados quando possível.
- Preencha `N8N_ALLOWED_WORKFLOWS` somente com identificadores autorizados.
- `N8N_WEBHOOK_BASE` deve apontar para a instância confiável de n8n; proteja webhooks também no próprio n8n.
- O envio de workflows ao ComfyUI executa o conteúdo enviado; use workflows revisados e restrinja o acesso ao MCP.
- `HERMES_HEALTH_URL` é somente uma verificação GET; este projeto não executa comandos arbitrários no Debian.

## Deploy
Use `render.yaml` como ponto de partida. Configure segredos no painel do Render antes de disponibilizar o serviço. O Blueprint usa plano Starter como base de serviço persistente; confirme custo e região antes do deploy.

Este projeto precisa ser validado contra suas instâncias reais antes de ser considerado pronto para produção.