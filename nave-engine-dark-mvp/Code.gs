/**
 * Nave Engine — Dark MVP
 * Manual-first product discovery and content packaging.
 * No publishing, purchasing, or autonomous affiliate claims.
 */
const NE = {
  SHEETS: { QUEUE: 'Fila_Garimpo', LOGS: 'Logs' },
  HEADERS: ['id','createdAt','query','title','url','source','status','attempts','idempotencyKey','raioX','hook','copy','promptVideo','driveFileId','lastError'],
  STATUS: { PENDING: 'Pendente', PROCESSING: 'Processando', READY: 'Acervo Pronto', REVIEW: 'Revisão Manual', ERROR: 'Erro' },
  MAX_ATTEMPTS: 2,
  QUERIES: [
    'site:amazon.com.br suporte ergonômico para notebook',
    'site:shopee.com.br organizador de mesa produtividade',
    'site:amazon.com.br fone cancelamento de ruído'
  ]
};

function setupNaveEngine() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) throw new Error('Abra este Apps Script a partir de uma planilha Google.');
  ensureSheet_(ss, NE.SHEETS.QUEUE, NE.HEADERS);
  ensureSheet_(ss, NE.SHEETS.LOGS, ['timestamp','level','event','details']);
  const props = PropertiesService.getScriptProperties();
  if (!props.getProperty('NAVE_DRIVE_FOLDER_ID')) {
    const folder = DriveApp.createFolder('Nave Engine — Dark MVP — Acervo');
    props.setProperty('NAVE_DRIVE_FOLDER_ID', folder.getId());
  }
  log_('INFO','SETUP','Abas e pasta do acervo verificadas.');
  return 'Setup concluído. Configure as Script Properties antes de buscar/processar.';
}

function discoverProducts() {
  const props = PropertiesService.getScriptProperties();
  const apiKey = props.getProperty('SEARCH_API_KEY');
  const cx = props.getProperty('SEARCH_ENGINE_ID');
  if (!apiKey || !cx) throw new Error('Configure SEARCH_API_KEY e SEARCH_ENGINE_ID em Script Properties.');
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(NE.SHEETS.QUEUE);
  if (!sheet) throw new Error('Execute setupNaveEngine() primeiro.');
  let added = 0;
  NE.QUERIES.forEach(query => {
    const endpoint = 'https://www.googleapis.com/customsearch/v1?key=' + encodeURIComponent(apiKey) +
      '&cx=' + encodeURIComponent(cx) + '&q=' + encodeURIComponent(query) + '&num=5';
    const response = UrlFetchApp.fetch(endpoint, { muteHttpExceptions: true });
    if (response.getResponseCode() !== 200) {
      log_('ERROR','SEARCH_HTTP_' + response.getResponseCode(),'Consulta falhou: ' + query);
      return;
    }
    const payload = JSON.parse(response.getContentText());
    (payload.items || []).forEach(item => {
      const url = canonicalUrl_(item.link || '');
      if (!url || !isAllowedStore_(url)) return;
      const key = digest_(url.toLowerCase());
      if (findByKey_(sheet, key)) return;
      sheet.appendRow([
        Utilities.getUuid(), new Date(), query, item.title || '', url,
        domain_(url), NE.STATUS.PENDING, 0, key, '', '', '', '', '', ''
      ]);
      added++;
    });
  });
  log_('INFO','DISCOVERY_COMPLETE','Novas oportunidades: ' + added);
  return 'Novas oportunidades registradas: ' + added;
}

function processPendingTasks() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(NE.SHEETS.QUEUE);
  if (!sheet) throw new Error('Execute setupNaveEngine() primeiro.');
  const data = sheet.getDataRange().getValues();
  if (data.length < 2) return 'Fila vazia.';
  const headers = data[0];
  let processed = 0;
  for (let r = 1; r < data.length; r++) {
    const row = data[r];
    const col = key => headers.indexOf(key);
    if (row[col('status')] !== NE.STATUS.PENDING && row[col('status')] !== NE.STATUS.ERROR) continue;
    const attempts = Number(row[col('attempts')] || 0);
    if (attempts >= NE.MAX_ATTEMPTS) {
      sheet.getRange(r+1,col('status')+1).setValue(NE.STATUS.REVIEW);
      continue;
    }
    sheet.getRange(r+1,col('status')+1).setValue(NE.STATUS.PROCESSING);
    sheet.getRange(r+1,col('attempts')+1).setValue(attempts+1);
    SpreadsheetApp.flush();
    try {
      const product = { title: row[col('title')], url: row[col('url')], source: row[col('source')], query: row[col('query')] };
      const content = generateContent_(product);
      validateContent_(content);
      const fileId = savePackage_(product, content, row[col('idempotencyKey')]);
      ['raioX','hook','copy','promptVideo'].forEach(k => sheet.getRange(r+1,col(k)+1).setValue(content[k]));
      sheet.getRange(r+1,col('driveFileId')+1).setValue(fileId);
      sheet.getRange(r+1,col('status')+1).setValue(NE.STATUS.READY);
      sheet.getRange(r+1,col('lastError')+1).clearContent();
      notifyAndaria_(product, content, row[col('idempotencyKey')]);
      log_('INFO','TASK_READY','Linha ' + (r+1) + ' finalizada; chave ' + row[col('idempotencyKey')]);
      processed++;
    } catch (err) {
      const nextStatus = attempts + 1 >= NE.MAX_ATTEMPTS ? NE.STATUS.REVIEW : NE.STATUS.ERROR;
      sheet.getRange(r+1,col('status')+1).setValue(nextStatus);
      sheet.getRange(r+1,col('lastError')+1).setValue(safeError_(err));
      log_('ERROR','TASK_FAILED','Linha ' + (r+1) + ': ' + safeError_(err));
    }
  }
  return 'Tarefas concluídas nesta execução: ' + processed;
}

function generateContent_(product) {
  const props = PropertiesService.getScriptProperties();
  const prompt = 'Responda SOMENTE JSON válido com exatamente estes campos string: raioX, hook, copy, promptVideo. ' +
    'Analise como oportunidade comercial sem inventar preço, especificação ou benefício não confirmado. ' +
    'Indique incertezas em raioX. Produto: ' + JSON.stringify(product);
  const openRouterKey = props.getProperty('OPENROUTER_API_KEY');
  if (openRouterKey) {
    try {
      return parseModelResponse_(callChatApi_('https://openrouter.ai/api/v1/chat/completions', openRouterKey,
        props.getProperty('OPENROUTER_MODEL') || 'openai/gpt-4o-mini', prompt));
    } catch (e) { log_('WARN','OPENROUTER_FALLBACK','Provedor primário falhou; tentando fallback se configurado.'); }
  }
  const nvidiaKey = props.getProperty('NVIDIA_API_KEY');
  const nvidiaBase = props.getProperty('NVIDIA_BASE_URL') || 'https://integrate.api.nvidia.com/v1/chat/completions';
  const nvidiaModel = props.getProperty('NVIDIA_MODEL');
  if (nvidiaKey && nvidiaModel) {
    return parseModelResponse_(callChatApi_(nvidiaBase, nvidiaKey, nvidiaModel, prompt));
  }
  throw new Error('Nenhum provedor de IA disponível/configurado.');
}

function callChatApi_(endpoint, key, model, prompt) {
  const response = UrlFetchApp.fetch(endpoint, {
    method: 'post', contentType: 'application/json', muteHttpExceptions: true,
    headers: { Authorization: 'Bearer ' + key },
    payload: JSON.stringify({ model: model, temperature: 0.3, messages: [
      { role: 'system', content: 'Você é um analista cuidadoso de produtos e copywriter. Nunca invente fatos.' },
      { role: 'user', content: prompt }
    ] })
  });
  if (response.getResponseCode() < 200 || response.getResponseCode() >= 300)
    throw new Error('Provedor IA HTTP ' + response.getResponseCode());
  const body = JSON.parse(response.getContentText());
  const choice = body.choices && body.choices[0] && body.choices[0].message && body.choices[0].message.content;
  if (!choice) throw new Error('Resposta vazia do provedor.');
  return choice;
}

function parseModelResponse_(raw) {
  const cleaned = String(raw).replace(/^\s*```(?:json)?\s*/i,'').replace(/\s*```\s*$/,'').trim();
  return JSON.parse(cleaned);
}
function validateContent_(v) {
  const required = ['raioX','hook','copy','promptVideo'];
  if (!v || required.some(k => typeof v[k] !== 'string' || !v[k].trim()))
    throw new Error('JSON inválido: os quatro campos string são obrigatórios.');
}
function savePackage_(product, content, key) {
  const props = PropertiesService.getScriptProperties();
  const folderId = props.getProperty('NAVE_DRIVE_FOLDER_ID');
  if (!folderId) throw new Error('Execute setupNaveEngine() para criar a pasta do Drive.');
  const folder = DriveApp.getFolderById(folderId);
  const filename = 'nave-' + String(key).slice(0,12) + '.txt';
  const existing = folder.getFilesByName(filename);
  if (existing.hasNext()) return existing.next().getId();
  const body = [
    'NAVE ENGINE — DARK MVP','Título: ' + product.title,'URL: ' + product.url,'Fonte: ' + product.source,
    '', 'RAIO-X', content.raioX, '', 'HOOK', content.hook, '', 'COPY', content.copy, '', 'PROMPT DE VÍDEO', content.promptVideo,
    '', 'Status: revisão humana obrigatória antes de publicação.'
  ].join('\n');
  return folder.createFile(filename, body, MimeType.PLAIN_TEXT).getId();
}
function notifyAndaria_(product, content, key) {
  const props = PropertiesService.getScriptProperties();
  const endpoint = props.getProperty('ANDARIA_AGENT_TASK_URL');
  const token = props.getProperty('COCKPIT_BRIDGE_TOKEN');
  if (!endpoint || !token) return;
  const response = UrlFetchApp.fetch(endpoint, {
    method:'post', contentType:'application/json', muteHttpExceptions:true,
    headers:{'X-Cockpit-Bridge-Token':token},
    payload:JSON.stringify({source:'nave-engine-dark-mvp', idempotencyKey:key, objective:'Pacote comercial para revisão humana', product:product, output:content})
  });
  if (response.getResponseCode() < 200 || response.getResponseCode() >= 300)
    log_('WARN','ANDARIA_BRIDGE_FAILED','Ponte Andaria HTTP ' + response.getResponseCode());
}
function ensureSheet_(ss, name, headers) {
  let sheet = ss.getSheetByName(name);
  if (!sheet) sheet = ss.insertSheet(name);
  if (sheet.getLastRow() === 0) sheet.appendRow(headers);
  sheet.setFrozenRows(1);
}
function findByKey_(sheet, key) {
  if (sheet.getLastRow() < 2) return false;
  const keys = sheet.getRange(2,9,sheet.getLastRow()-1,1).getValues();
  return keys.some(r => String(r[0]) === key);
}
function canonicalUrl_(url) {
  return String(url).split('#')[0].replace(/\?.*$/,'').replace(/\/$/,'');
}
function isAllowedStore_(url) {
  return /(^|\.)((amazon\.com\.br)|(shopee\.com\.br)|(aliexpress\.com))$/i.test(domain_(url));
}
function domain_(url) {
  const m = String(url).match(/^https?:\/\/([^/:]+)/i);
  return m ? m[1].toLowerCase().replace(/^www\./,'') : '';
}
function digest_(value) {
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, value, Utilities.Charset.UTF_8)
    .map(b => ('0' + ((b + 256) % 256).toString(16)).slice(-2)).join('');
}
function log_(level,event,details) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss && ss.getSheetByName(NE.SHEETS.LOGS);
  if (sheet) sheet.appendRow([new Date(),level,event,String(details || '').slice(0,500)]);
}
function safeError_(err) { return String(err && err.message ? err.message : 'Falha desconhecida').slice(0,300); }
