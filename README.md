# MCP-Genio

Camada de coordenação em nuvem do ecossistema Andaris: MCP, cockpit operacional, provedores de IA e execução controlada de workflows. O bot Telegram existente continua recebendo updates pelo serviço Andaria; o Genio **não registra um segundo webhook para o mesmo bot**.

## Papel de cada componente

- **Andaria**: mantém a integração existente com Telegram e encaminha apenas comandos explícitos `/cockpit ...` do chat administrativo.
- **MCP-Genio**: serviço de nuvem para ferramentas MCP, cockpit, roteamento OpenRouter/NVIDIA, consulta ao n8n e integração opcional com ComfyUI.
- **Andaris Kernel**: autoridade para contexto, proveniência e autorização. O endpoint autenticado `/v1/gate/action` avalia as políticas server-side; o Genio exige `GO` antes de enviar ações ao n8n ou executar workflows no ComfyUI.
- **andaris-mcp-gateway**: ponte OAuth/MCP existente para recursos no Debian. É opcional e pode ficar indisponível quando o Debian estiver desligado; o cockpit e chamadas de IA hospedadas não dependem dele.

## Ferramentas MCP

- `ai_chat(prompt)`: OpenRouter com fallback para NVIDIA, ou a ordem configurada em `AI_PROVIDER`.
- `system_status()`: estado/configuração dos provedores, ComfyUI, n8n e endpoint opcional do Hermes.
- `comfyui_queue_status()`, `comfyui_history(prompt_id)`, `comfyui_submit_workflow(workflow, client_id?)`.
- `n8n_list_allowed_workflows()`, `n8n_recent_executions(limit)`, `n8n_trigger_allowed_workflow(workflow_id, payload?)`.

## Comandos do Telegram

No bot Andaris já existente:

- `/cockpit` ou `/cockpit status` — estado operacional.
- `/cockpit providers` — provedores de IA configurados.
- `/cockpit workflows` — workflows autorizados.
- `/cockpit runs` — execuções recentes.
- `/cockpit run ID_DO_WORKFLOW {"chave":"valor"}` — chama o webhook associado ao ID permitido.
- `/cockpit ask sua pergunta` — conversa usando o provedor de IA hospedado.

O Genio não aceita comandos arbitrários do Debian. O comando `/cockpit run` só aceita IDs incluídos em `N8N_ALLOWED_WORKFLOWS`; use essa allowlist apenas para workflows revisados. A chamada pode produzir efeitos externos conforme a lógica do workflow.

## Configuração

Gere um token aleatório com:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Configure no serviço **MCP-Genio** no Render:

- `GENIO_MCP_TOKEN`: token de pelo menos 32 caracteres.
- `COCKPIT_BRIDGE_TOKEN`: token aleatório de pelo menos 32 caracteres, compartilhado somente com o serviço Andaria.
- `OPENROUTER_API_KEY` + `OPENROUTER_MODEL`; opcionalmente `NVIDIA_API_KEY` + `NVIDIA_MODEL` para fallback.
- `N8N_URL`, `N8N_API_KEY`, `N8N_ALLOWED_WORKFLOWS`, `N8N_WEBHOOK_BASE`.
- `COMFYUI_URL` apenas se a instância for alcançável a partir da nuvem.
- `HERMES_HEALTH_URL` é somente uma verificação GET; não executa comandos no Hermes.\n- `KERNEL_GATEWAY_URL` e `KERNEL_GATEWAY_TOKEN` são obrigatórios para operações com efeitos colaterais; sem eles, a execução falha fechada.\n- O Kernel precisa ter `KERNEL_ACTION_POLICIES` configurado para cada ação permitida, por exemplo `n8n.workflow:ID_DO_WORKFLOW` e `comfyui.submit`.

No serviço **Andaria** (arquivo `andaris/render.yaml`), configure:

- `MCP_GENIO_URL`: URL pública do serviço MCP-Genio, sem barra final.
- `MCP_GENIO_TOKEN`: o mesmo valor configurado como `COCKPIT_BRIDGE_TOKEN` no Genio (não reutilize o token geral do MCP).

O comando do Telegram é encaminhado pelo webhook que já existe no Andaria. **Não aponte o webhook do mesmo bot para o Genio**, pois isso interromperia o webhook atual.

## Execução local

```bash
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 10000
```

Endpoints: `/health`, API interna autenticada `/api/cockpit/command` e MCP Streamable HTTP em `/mcp`.

## Segurança e limites atuais

- Não comite segredos nem arquivos `.env`.
- O acesso MCP exige Bearer token. A API interna de cockpit exige um token de ponte separado; a validação do chat administrativo é feita pelo webhook existente do Andaria antes do encaminhamento.
- Mantenha ComfyUI e n8n privados sempre que possível.
- Submeter workflow JSON ao ComfyUI pode executar operações arbitrárias; use somente workflows revisados e clientes confiáveis.
- O endpoint do Hermes é apenas monitoramento. A ponte de comandos específicos do Hermes continua opcional e depende do Debian/túnel. A integração de execução com o Kernel está implementada no código, mas ainda precisa de deploy, políticas e testes reais.
- URLs locais como `127.0.0.1` ou `localhost` não são acessíveis pelo Render.
- Os testes e o deploy devem ser confirmados antes de considerar a solução pronta para produção.

## Deploy

Use `render.yaml` como ponto de partida. Configure os segredos manualmente no Render; nenhum token real é armazenado no repositório. O Blueprint usa plano Starter, cujo custo e região devem ser confirmados antes da implantação.
