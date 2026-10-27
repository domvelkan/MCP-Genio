# Nave Engine — Dark MVP

Módulo isolado em `nave-engine-dark-mvp/` dentro do MCP-Genio. Não altera `andaris-mcp-gateway`, não publica conteúdo e não compra produtos.

## Escopo do primeiro piloto
- Nicho: acessórios e hardware para estudo/produtividade.
- Descoberta via Google Programmable Search / Custom Search JSON API.
- Lista de fontes permitidas no MVP: Amazon Brasil, Shopee Brasil, AliExpress.
- Deduplicação por URL normalizada + SHA-256.
- Processamento limitado a duas tentativas; depois vai para `Revisão Manual`.
- Geração de quatro campos: `raioX`, `hook`, `copy`, `promptVideo`.
- Arquivo TXT no Google Drive e log na aba `Logs`.
- OpenRouter primário e NVIDIA NIM opcional como fallback.
- Ponte opcional para Andaria via `ANDARIA_AGENT_TASK_URL` e `COCKPIT_BRIDGE_TOKEN`.
- Revisão humana antes de publicação.

## Instalação
1. Crie uma planilha nova e abra **Extensões → Apps Script**.
2. Cole `Code.gs`; em Project Settings ative a exibição do manifesto e substitua o conteúdo de `appsscript.json`.
3. Execute `setupNaveEngine()` e conceda as permissões.
4. Em Script Properties configure:
   - Obrigatórias para pesquisa: `SEARCH_API_KEY`, `SEARCH_ENGINE_ID`.
   - Pelo menos um provedor: `OPENROUTER_API_KEY` e opcionalmente `OPENROUTER_MODEL`; ou `NVIDIA_API_KEY`, `NVIDIA_MODEL`, opcional `NVIDIA_BASE_URL`.
   - Opcionais: `ANDARIA_AGENT_TASK_URL`, `COCKPIT_BRIDGE_TOKEN`.
5. Execute `discoverProducts()`, inspecione a aba `Fila_Garimpo`, depois execute `processPendingTasks()`.

## Limites / cuidados
- O Custom Search não garante que resultados sejam listagens compráveis nem que tenham afiliação. Validar link, disponibilidade, preço e condições de afiliado manualmente.
- Não colocar chaves no código ou na planilha. Usar Script Properties.
- O envio para Andaria é opcional e depende do contrato de payload do endpoint instalado; testar separadamente antes de considerar a ponte validada.
- Gatilhos automáticos não são criados pelo setup. Só criar após testes manuais e revisão dos logs.
- Este primeiro incremento ainda não foi executado numa conta Google real; autorização, quotas e integrações externas precisam de validação operacional.
