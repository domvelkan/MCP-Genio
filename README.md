# MCP-Genio

Camada de coordenação em nuvem do ecossistema Andaris: MCP, cockpit operacional, provedores de IA e execução controlada de workflows. O bot Telegram existente continua recebendo updates pelo serviço Andaria; o Genio **não registra um segundo webhook para o mesmo bot**.

## Papel de cada componente

- **Andaria**: mantém a integração existente com Telegram e encaminha apenas comandos explícitos `/cockpit ...` do chat administrativo.
- **MCP-Genio**: serviço de nuvem para ferramentas MCP, cockpit, roteamento de IA, consulta ao n8n e integração opcional com ComfyUI.
- **Andaria AI/Visual**: reutiliza a chave OpenRouter e o token Hugging Face já mantidos pelo serviço Andaria; a geração visual pode enviar o resultado diretamente ao Telegram sem hospedar ComfyUI.
- **Andaris Kernel**: autoridade para contexto, proveniência e autorização. O endpoint autenticado `/v1/gate/action` avalia as políticas server-side; o Genio exige `GO` antes de enviar ações ao n8n ou executar workflows no ComfyUI.
- **andaris-mcp-gateway**: ponte OAuth/MCP existente para recursos no Debian. É opcional e pode ficar indisponível quando o Debian estiver desligado; o cockpit e chamadas de IA hospedadas não dependem dele.

## Ferramentas MCP

- `ai_chat(prompt)`: OpenRouter direto quando configurado; senão, proxy autenticado para a chave OpenRouter já mantida pelo Andaria. NVIDIA é fallback opcional quando a chave própria estiver configurada.
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
- `/cockpit visual descrição da imagem` — usa a API de imagem hospedada pelo Andaria e envia a imagem ao mesmo chat do Telegram.

O Genio não aceita comandos arbitrários do Debian. O comando `/cockpit run` só aceita IDs incluídos em `N8N_ALLOWED_WORKFLOWS`; use essa allowlist apenas para workflows revisados. A chamada pode produzir efeitos externos conforme a lógica do workflow.

## Configuração

Gere um token aleatório com:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Configure no serviço **MCP-Genio** no Render:

- `GENIO_MCP_TOKEN`: token de pelo menos 32 caracteres.
- `COCKPIT_BRIDGE_TOKEN`: token aleatório de pelo menos 32 caracteres, compartilhado somente com o serviço Andaria.
- A chave `OPENROUTER_API_KEY` já existente no serviço Andaria é reutilizada pelo proxy privado; não é necessário copiar seu valor para o Genio. Para fallback NVIDIA, configure `NVIDIA_API_KEY` e `NVIDIA_MODEL` diretamente no Render, sem enviar o segredo pelo chat.
- `N8N_URL`, `N8N_API_KEY`, `N8N_ALLOWED_WORKFLOWS`, `N8N_WEBHOOK_BASE`.
- `COMFYUI_URL` apenas se a instância for alcançável a partir da nuvem. Para geração visual simples, prefira `/cockpit visual` com Hugging Face já integrado ao Andaria.
- `HERMES_HEALTH_URL` é somente uma verificação GET; não executa comandos no Hermes.
- `KERNEL_GATEWAY_URL` e `KERNEL_GATEWAY_TOKEN` são obrigatórios para operações com efeitos colaterais; sem eles, a execução falha fechada.
- O Kernel precisa ter `KERNEL_ACTION_POLICIES` configurado para cada ação permitida, por exemplo `n8n.workflow:ID_DO_WORKFLOW` e `comfyui.submit`.

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
- O endpoint do Hermes é apenas monitoramento. A ponte de comandos específicos do Hermes continua opcional e depende do Debian/túnel.
- O serviço Genio e o gate do Kernel estão implantados; o token do Kernel está configurado, mas a lista `KERNEL_ACTION_POLICIES` está vazia. Portanto, **todas as execuções com efeitos colaterais permanecem bloqueadas** até o n8n estar corrigido, os IDs reais serem revisados e as políticas serem cadastradas.
- O serviço `meu-n8n-gemeo` no Render está configurado como Rust com `cargo build --release` e falha porque o repositório não tem `Cargo.toml`; ele não deve ser usado como n8n ativo.
- A rota de IA hospedada está configurada e o health check confirmou que a chave OpenRouter existe no Andaria. A rota visual foi adicionada, mas depende de confirmar o deploy e a disponibilidade do token Hugging Face.
- A validação ponta a ponta no Telegram ainda exige enviar os comandos de teste ao bot; não foi afirmado sucesso de execução sem evidência.
- URLs locais como `127.0.0.1` ou `localhost` não são acessíveis pelo Render.
- Os testes e o deploy devem ser confirmados antes de considerar a solução pronta para produção.

## Deploy

Use `render.yaml` como ponto de partida. Configure os segredos manualmente no Render; nenhum token real é armazenado no repositório. O Blueprint está no plano Free para validar o fluxo sem criar cobrança. Esse plano pode suspender o serviço após inatividade; para um cockpit realmente sempre disponível, será necessário aprovar a mudança para Starter no Render.
