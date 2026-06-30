# Plano Técnico — Sistema de Solicitação de Materiais

> Plataforma web para terceiros solicitarem materiais e o administrador gerenciar e disparar pedidos de compra aos fornecedores.
> Versão 1.0 — 29/06/2026

---

## 1. Visão geral

Aplicação web responsiva (funciona no celular) com dois papéis: **Solicitante** e **Administrador**. O solicitante abre pedidos de material e acompanha o status; o administrador vê tudo, gerencia status, cadastra fornecedores por tipo de material e dispara o pedido de compra por e-mail (PDF anexo + corpo do e-mail). Fornecedores **não acessam o sistema** — só recebem e-mail.

**Fora de escopo (por ora):** integração com ERP e login para fornecedores.

---

## 2. Stack tecnológica

| Camada | Tecnologia | Observação |
|---|---|---|
| Backend | Python 3.12 + **Flask** (o "motor" do site, que recebe os cliques e devolve as páginas) | Leve, simples de hospedar |
| ORM / migrations (organização e controle de mudanças do banco) | SQLAlchemy (tradutor entre o código e o banco) + Flask-Migrate / Alembic (histórico de mudanças na estrutura do banco, sem perder dados) | Versionamento de schema (da estrutura das tabelas) |
| Banco de dados (a "planilha gigante e organizada" com todos os dados) | **PostgreSQL** | Hospedado no Neon (ver §8) |
| Autenticação (controle de quem entra) | Flask-Login (gerencia o "entrar/sair") + senha com hash (bcrypt/argon2 — embaralhamento irreversível: nunca guardamos a senha real) | Sessão por cookie (lembra quem está logado) |
| Templates / frontend (as telas) | Jinja2 (molde das páginas) + **Bootstrap 5** (kit de visual pronto, funciona no celular) | Sem framework JS pesado no MVP (1ª versão enxuta) |
| "Tempo quase real" | Polling (o site pergunta ao servidor a cada ~15s se algo mudou) | Simples e suficiente; evita WebSocket (conexão sempre aberta, frágil no plano grátis) |
| Geração de PDF | WeasyPrint ou ReportLab (ferramenta que cria o arquivo PDF) | Pedido de compra em PDF |
| Armazenamento de imagens | **Cloudinary** (free) ou Supabase Storage — "cofre" externo só para as fotos | Disco do Render é efêmero (apaga arquivos sozinho) — não guardar imagem nele |
| E-mail | SMTP (serviço que dispara os e-mails) via **Brevo** (300/dia grátis) | Notificações e pedido de compra |
| Servidor WSGI (o "porteiro" que mantém o site no ar) | Gunicorn | Produção |

**Por que polling e não WebSocket:** no tier (plano) gratuito o serviço "dorme". O WebSocket (conexão sempre aberta) é frágil nesse cenário; o polling leve (perguntar de tempos em tempos) atende o "tempo quase real" sem complexidade.

---

## 3. Papéis e permissões

**Solicitante**
- Login por e-mail e senha (criado pelo admin).
- Cria solicitação (material, quantidade, fabricante, link de similar, imagens).
- Vê **apenas** as próprias solicitações e o status de cada uma.
- Recebe e-mail a cada atualização/pergunta na sua solicitação.
- Pode responder perguntas do admin (comentário na solicitação).

**Administrador**
- Vê **todas** as solicitações; edita campos e altera status.
- Faz perguntas / comentários (dispara e-mail ao solicitante).
- Cadastra usuários (e-mail + senha + papel) — **não há autocadastro**.
- Cadastra fornecedores e o mapeamento fornecedor × tipo de material.
- Botão **"Enviar pedido de compra"**: gera PDF e envia e-mail aos fornecedores do tipo de material.
- **Registra os orçamentos** que cada fornecedor responde por e-mail (valor, prazo, condições, anexo) e vê o **comparativo** lado a lado de todos os orçamentos da solicitação.

---

## 4. Modelo de dados

```
usuarios
  id (PK)
  nome
  email (único)
  senha_hash
  papel            -- 'solicitante' | 'admin'
  ativo (bool)
  criado_em

tipos_material
  id (PK)
  nome (único)     -- ex.: "Elétrico", "Hidráulico", "EPI"

fornecedores
  id (PK)
  nome
  email
  telefone (opc.)
  ativo (bool)

fornecedor_tipo            -- N:N fornecedor × tipo de material
  fornecedor_id (FK)
  tipo_material_id (FK)

solicitacoes
  id (PK)
  solicitante_id (FK usuarios)
  tipo_material_id (FK)    -- define quais fornecedores recebem
  material (texto)
  quantidade (int)
  fabricante (texto)
  link_similar (texto/URL)
  status                   -- ver §5
  criado_em
  atualizado_em

imagens
  id (PK)
  solicitacao_id (FK)
  url                      -- URL no Cloudinary/Storage
  criado_em

comentarios               -- perguntas/respostas/observações
  id (PK)
  solicitacao_id (FK)
  autor_id (FK usuarios)
  texto
  criado_em

pedidos_compra
  id (PK)
  solicitacao_id (FK)
  pdf_url
  enviado_em
  enviado_por (FK usuarios)

pedido_destinatarios
  pedido_id (FK)
  fornecedor_id (FK)
  email_destino            -- snapshot do e-mail no envio

orcamentos                 -- resposta de preço de cada fornecedor
  id (PK)
  solicitacao_id (FK)
  fornecedor_id (FK)
  valor_total (decimal)
  moeda                    -- ex.: 'BRL'
  prazo_entrega            -- ex.: "10 dias úteis"
  condicoes_pagamento (texto)
  observacoes (texto)
  anexo_url                -- PDF/imagem do orçamento, opcional
  escolhido (bool)         -- marca o orçamento vencedor
  registrado_por (FK usuarios)   -- admin que lançou
  recebido_em
```

> O fornecedor não digita nada no sistema: ele responde por e-mail e o **admin lança o orçamento** manualmente. Por isso o orçamento guarda quem registrou (`registrado_por`).

---

## 5. Fluxo de status da solicitação

```
ABERTA → EM_ANALISE → PEDIDO_ENVIADO → AGUARDANDO_ORCAMENTOS →
ORCAMENTOS_RECEBIDOS → EM_COMPRA → RECEBIDA → CONCLUIDA
                  ↘ AGUARDANDO_SOLICITANTE (pergunta do admin)
                  ↘ CANCELADA
```

- **ABERTA** — criada pelo solicitante.
- **EM_ANALISE** — admin avaliando.
- **AGUARDANDO_SOLICITANTE** — admin fez uma pergunta; volta a EM_ANALISE quando respondida.
- **PEDIDO_ENVIADO** — botão "Enviar pedido de compra" acionado.
- **AGUARDANDO_ORCAMENTOS** — pedido enviado, esperando os fornecedores responderem preço.
- **ORCAMENTOS_RECEBIDOS** — admin lançou os orçamentos e pode comparar/escolher o vencedor.
- **EM_COMPRA / RECEBIDA / CONCLUIDA / CANCELADA** — acompanhamento.

Toda mudança de status e todo comentário geram registro e disparam e-mail às partes.

---

## 6. Telas

**Comuns**
- Login (e-mail + senha).

**Solicitante**
- Painel "Minhas solicitações" (lista com status, atualiza por polling).
- Nova solicitação (formulário + upload de imagens).
- Detalhe da solicitação (dados, imagens, histórico de comentários, responder pergunta).

**Administrador**
- Painel geral (todas as solicitações, filtros por status/solicitante/tipo).
- Detalhe da solicitação (editar, mudar status, comentar/perguntar, **Enviar pedido de compra**).
- **Lançar orçamento** de um fornecedor (valor, prazo, condições, anexo).
- **Comparativo de orçamentos** — tabela lado a lado de todos os orçamentos da solicitação, com destaque para o menor preço e o menor prazo, e botão para **marcar o vencedor**.
- Cadastro de usuários.
- Cadastro de tipos de material.
- Cadastro de fornecedores + mapeamento por tipo de material.
- Pré-visualização do PDF antes do envio.

---

## 7. Notificações por e-mail

Eventos que disparam e-mail (via SMTP/Brevo):
- Nova solicitação criada → admin.
- Mudança de status → solicitante.
- Comentário/pergunta do admin → solicitante.
- Resposta do solicitante → admin.
- Pedido de compra enviado → fornecedores mapeados (PDF anexo + corpo) e cópia ao admin.
- Orçamento lançado / vencedor escolhido → solicitante (informativo, opcional).

Templates de e-mail em HTML simples, com link direto para a solicitação no sistema.

---

## 8. Hospedagem (estratégia gratuita → paga)

A pesquisa de junho/2026 mostra que **só o Render** oferece tier gratuito real para Flask sem cartão de crédito. Porém o **Postgres grátis do Render expira em 30 dias** (depois 14 dias de carência e é apagado). Para atender "sem perder dados", separamos app e banco:

| Componente | Fase grátis | Limite/risco | Fase paga (~US$5–7/mês) |
|---|---|---|---|
| App Flask | **Render** Free Web Service | Dorme após 15 min parado (cold start: 1º acesso demora 30–60s); 750h/mês | Render Starter **US$7/mês** (sempre ligado) |
| Banco | **Neon** Free Postgres | 0,5 GB; 100 CU-h/mês (horas de uso ativo — ele "dorme" quando ninguém usa); **sem expiração** | Neon Launch (~US$5) se crescer |
| Imagens | **Cloudinary** Free | 25 créditos/mês | Plano pago só se necessário |
| E-mail | **Brevo** Free SMTP | 300 e-mails/dia | Sobe de plano se necessário |

**Por que não o Postgres do Render na fase grátis:** ele é apagado em 30 dias. O **Neon** mantém os dados indefinidamente no free tier — é o que protege contra perda de dados durante o teste.

**Migração para pago é rápida e sem perder dados:** o banco (Neon) já é persistente; ao aprovar, basta mudar o serviço do Render de Free para Starter (US$7) — mesma `DATABASE_URL`, sem migração de dados. Custo-alvo total: ~US$7/mês.

**Atenção ao cold start na demonstração:** na fase grátis, se ninguém usar por 15 min, o primeiro acesso demora ~30–60s. Para o teste com terceiros, vale avisar ou usar um "ping" periódico simples.

---

## 9. Segurança

- Senhas com hash forte (embaralhamento irreversível — argon2/bcrypt); nunca em texto puro.
- HTTPS automático (o cadeado do navegador: conexão criptografada) — incluído no Render.
- Proteção CSRF (impede outro site de enviar formulários no seu nome) em todos os formulários, via Flask-WTF.
- Autorização por papel em cada rota/página (solicitante só vê o que é dele).
- Dados sensíveis (SMTP, banco, Cloudinary) em variáveis de ambiente (guardados fora do código, em local protegido do servidor).
- Validação de upload: tipos de imagem permitidos e tamanho máximo.
- Rate limit no login (limite de tentativas, para barrar ataque de força bruta).

---

## 10. Roadmap por fases

**Fase 1 — Fundação**
Projeto Flask, modelo de dados + migrations, login e papéis, CRUD de usuários (admin).

**Fase 2 — Núcleo do solicitante**
Criar solicitação com upload de imagens, painel "minhas solicitações", detalhe com polling.

**Fase 3 — Núcleo do admin**
Painel geral com filtros, edição e mudança de status, comentários/perguntas, cadastro de tipos e fornecedores (mapeamento por tipo).

**Fase 4 — Pedido de compra + e-mail**
Geração de PDF, botão "Enviar pedido de compra", roteamento por tipo de material, notificações por e-mail em todos os eventos.

**Fase 5 — Orçamentos e comparativo**
Lançamento de orçamentos pelo admin, tela de comparativo lado a lado (destaque de menor preço/prazo) e marcação do vencedor.

**Fase 6 — Deploy e teste**
Deploy no Render + Neon + Cloudinary + Brevo, testes com usuários reais, ajustes.

**Pós-aprovação**
Migrar app para plano pago (Render Starter), avaliar custos, planejar fases futuras (ERP, portal de fornecedores).

---

## 11. Decisões tomadas

1. **Tipos de material** — **cadastráveis pelo admin** (tabela `tipos_material`, CRUD na área administrativa).
2. **PDF do pedido** — **sem dados da empresa por enquanto**. O PDF traz só os dados do material/solicitação; quaisquer dados da empresa vão no **corpo do e-mail**, escrito pelo admin no momento do envio.
3. **E-mails ao fornecedor** — **sem assinatura**. Corpo limpo, editável pelo admin antes de enviar.
4. **Domínio** — usar a **URL gratuita do Render** (sem domínio próprio).
5. **Volume esperado** — **~500 pedidos/mês**. Cabe nos tiers gratuitos (ver §12).

---

## 12. Dimensionamento dos limites grátis (~500 pedidos/mês)

| Recurso | Estimativa de uso | Limite grátis | Folga |
|---|---|---|---|
| E-mails (Brevo) | ~500 pedidos × ~5 e-mails = ~2.500/mês | 300/dia (~9.000/mês) | Confortável |
| Banco (Neon) | só texto (imagens ficam no Cloudinary) | 0,5 GB | Anos de dados |
| Imagens (Cloudinary) | depende do nº de fotos/pedido | 25 créditos/mês | Monitorar; maior risco |
| App (Render Free) | 750 h/mês | 750 h/mês | OK, mas dorme ocioso |

**Pontos de atenção:**
- **Cloudinary** é o limite que pode apertar primeiro se houver muitas fotos por pedido. Mitigar comprimindo imagens no upload (redimensionar para ~1280px, qualidade ~80%).
- **Cold start do Render** (30–60s após 15 min ocioso) tende a aparecer com 500 pedidos/mês distribuídos no dia. Ao migrar para o **Render Starter (US$7/mês)** o serviço fica sempre ligado e o problema some.

---

## 13. Solicitações de mudança (changelog)

Registro de toda alteração pedida após o MVP, com status: ⬜ pendente · 🔧 em desenvolvimento · ✅ concluída.

### 29/06/2026
1. **✅ Editar fornecedores** — tela de edição com alterar dados, **ativar/desativar** e remapear tipos. *(Implementado e testado.)*
2. **✅ Filtros em "Minhas solicitações" (solicitante)** — filtros por status, tipo e busca por material no painel do solicitante (sempre restrito às próprias). *(Implementado e testado.)*
3. **✅ Conjunto completo de filtros (admin)** — status, tipo de material, **solicitante**, **período (de/até)** e busca por texto. *(Implementado e testado.)*
4. **✅ Aprovação + envio em lote** — *(muda o fluxo)*: nova solicitação entra como **"Aguardando aprovação"** e só vira **"Aberta"** após o admin **aprovar** (botão no painel). A página **"Enviar pedidos"** junta todos os itens aprovados e dispara **um e-mail por fornecedor** (PDF consolidado com os itens dos tipos que ele atende); os itens passam a **"Aguardando orçamentos"**. *(Implementado e testado.)*
5. **✅ Remetente e respostas do e-mail** — remetente via `MAIL_FROM` e **Reply-To = e-mail do admin** (respostas dos fornecedores voltam para o admin). *(Implementado e testado. Em produção, verificar remetente/domínio no Brevo.)*
6. **✅ Leitor de PDF de orçamento (de-para + preenchimento automático)** — o admin sobe o **PDF do orçamento** do fornecedor; o sistema **lê e lista item a item** (descrição + valor). O admin faz o **"de-para"**, casando cada item lido com os itens de solicitação que estão com status **Aberto**. O sistema então **puxa os valores automaticamente** para o comparativo, sem digitação manual. *(Implementado e testado em 29/06/2026 — menu "Importar orçamento".)*
   - *Observação técnica:* a extração depende do layout do PDF de cada fornecedor. PDFs com texto (gerados digitalmente) leem bem; PDFs escaneados (imagem) exigem OCR e são menos precisos. Em layouts muito diferentes, o passo de "de-para" garante a conferência manual antes de gravar os valores. Linhas de "total" podem aparecer como item — basta deixá-las em "ignorar".
7. **✅ Admin alterar quantidade com registro (auditoria)** — o admin edita a **quantidade** no detalhe da solicitação; o sistema grava o **valor original**, **quem alterou** e **quando**, e exibe um aviso na tela. *(Implementado e testado em 29/06/2026.)*

8. **⬜ Cadastrar os tipos de material padrão (32 tipos)** — carregar no sistema a lista informada: CONSUMIVEIS EM GERAL, LINHA DE TRANSMISSÃO, TI/INFORMATICA, SOLDA EM GERAL, PINTURA EM GERAL, VIAS DE ACESSO EM GERAL, REFRIGERAÇÃO EM GERAL, FERRAMENTAS EM GERAL, CUPIM - ESP, VEICULO EM GERAL, COPA E COZINHA EM GERAL, BATERIAS/PILHAS EM GERAL, UTENSILIOS EM GERAL, BELZONA - ESP, RESISTENCIAS DE AQUECIMENTO EM GERAL, CONECTORES DE SUBESTAÇÃO EM GERAL, MUFLAS/BOTINHAS/TERMINACOES, EMBALAGENS EM GERAL, SIEMENS - ESP, WEG - ESP, ELOS - ESP, DELTA STAR - ESP, MEGABRAS - ESP, NANOPROTECH - ESP, SALVI BR - ESP, SADEL - ESP, TREETECH - ESP, TILUB - ESP, BOBINAS MADEIRA EM GERAL, ELETRONICA EM GERAL, MERCADO LIVRE - ESP, ROLAMENTOS EM GERAL. *(Já existe o script `seed_tipos.py` com a lista; pendente: fazer os tipos carregarem automaticamente ao iniciar, sem precisar rodar comando.)*
9. **✅ Melhorar o leitor de PDF de orçamento** — trocada a extração para **pdfplumber** e adicionado um reconhecedor do padrão estruturado "código · descrição · unidade · qtde · preço unitário · subtotal" (orçamentos REALSYS/DELTA). Agora extrai descrição limpa e o **preço unitário** correto; layouts desconhecidos caem no método heurístico. A tela de de-para mostra qtde, preço unitário e subtotal. *Calibrado e testado com PDF real DELTA (30 itens; soma dos subtotais bateu com o TOTAL do PDF). Implementado em 29/06/2026.*
   - *Pendências futuras (item 9b):* permitir o admin escolher entre preço unitário e subtotal; **OCR** para PDFs escaneados; calibrar para outros layouts de fornecedor conforme aparecerem.

> **Itens 1–7 e 9 concluídos** (29/06/2026). **Pendente: item 8** (carregar os 32 tipos automaticamente).

### 29/06/2026 — redesenho de fluxo (a implementar)

10. **⬜ Brandbook / identidade visual** — aplicar um guia de marca ao layout (cores, tipografia, logo, espaçamentos). **Não exibir o nome da empresa ainda** — só preparar a estrutura visual.
11. **⬜ Novo fluxo de status (substitui os atuais)** — **remover todos os status atuais** e adotar a sequência:
    1. **Aguardando aprovação** — criada pelo solicitante (automático).
    2. **Aguardando envio p/ cotação** — após o admin aprovar.
    3. **Aguardando recebimento da cotação** — após o admin enviar o pedido aos fornecedores.
    4. **Aguardando definição de fornecedor** — após o admin lançar/importar os valores de todos os fornecedores.
    5. **Aguardando chegada** — após o admin definir o fornecedor e enviar a Ordem de Compra.
    6. **Concluído** — após o almoxarifado confirmar a chegada do material.
    7. **Cancelada** — (manter como opção de saída.)
12. **⬜ Novo papel "Almoxarifado"** — login próprio (criado pelo admin). Visão semelhante à do solicitante; **única diferença: pode marcar a chegada do material**, mudando o status para **Concluído**. **Escopo de visão (definido):** acompanha as solicitações **a partir da aprovação** (todo o ciclo de compra), mas só pode **agir** (marcar chegada) quando o item está em "Aguardando chegada".
13. **⬜ Tela de aprovações/notificações (admin)** — uma tela única que lista tudo que precisa de aprovação; o admin **aprova ou edita** direto dali.
14. **⬜ Campo "prazo de recebimento" (obrigatório)** — ao mudar o status para **"Aguardando chegada"**, é obrigatório informar um prazo de recebimento. Incluir o campo na solicitação.
15. **⬜ Prazo de 5 dias úteis na cotação** — no e-mail de solicitação de cotação ao fornecedor, incluir o **prazo de 5 dias úteis** para retorno.

> **Status:** itens 10–15 **registrados, a implementar em rodada futura** (a pedido). Escopo do Almoxarifado já definido (item 12).

### 29/06/2026 — cadastro de fornecedor, frete e cadastros gerais (a implementar)

16. **⬜ Novos campos do fornecedor** — cadastro passa a ter: **Razão Social**, **Nome Fantasia**, **E-mail**, **Nome do contato**, **Telefone (WhatsApp)** + tipos atendidos. O telefone com **normalização inteligente**: entender DDD e o dígito **9** na frente do celular (padronizar para o formato +55 DD 9XXXX-XXXX). *(Sugestão técnica: biblioteca `phonenumbers`.)*
17. **⬜ Cotação via WhatsApp** — além do e-mail, botão que abre o WhatsApp do contato do fornecedor via **link "clicar para conversar" (wa.me)** com a mensagem **já preenchida**. **Definido:** usar o link click-to-chat (sem custo/API). *Limitação:* o link só leva **texto** — não anexa PDF. Por isso a cotação vai por WhatsApp como **pedido escrito de forma bem legível** (lista de itens, qtd, etc.); o **PDF continua sendo enviado pelo e-mail**. (O admin pode anexar o PDF manualmente na conversa, se quiser.)
18. **⬜ Tipo de frete após definir o fornecedor** — ao definir o fornecedor vencedor, indicar o frete: **CIF** ou **FOB**. Se **FOB**, campo obrigatório: **Transportadora** ou **Colaborador do parque**. Se Transportadora → indicar qual (cadastro de Transportadoras). Se Colaborador do parque → indicar a **cidade** de retirada (cadastro de Cidades). **Definido:** essa informação é **interna**, fica registrada na **Ordem de Compra** do sistema; **não é enviada ao fornecedor**.
19. **⬜ Área única de "Cadastro"** — centralizar num só lugar os cadastros: **Usuários, Tipos de material, Fornecedores, Cidades, Transportadoras** (e o que mais surgir).

**Definições adicionais (29/06/2026):**
- **Remetente do e-mail:** usar o **SMTP do próprio provedor de e-mail do admin** (o remetente é o e-mail dele; sem serviço de terceiros).
- **Texto fixo no WhatsApp:** incluir aviso de que *"esta solicitação também foi enviada por e-mail, porém estamos encaminhando aqui também"* (pode responder por e-mail ou pelo WhatsApp).

> **Status:** itens **8 e 10–19 concluídos** (implementados e testados em 29/06/2026 — testes end-to-end + smoke de todas as telas dos 3 papéis passaram).

### Resumo do novo fluxo implementado (29/06/2026)

- **Status:** Aguardando aprovação → Aguardando envio p/ cotação → Aguardando recebimento da cotação → Aguardando definição de fornecedor → Aguardando chegada → Concluído (+ Cancelada).
- **Papéis:** Solicitante, Administrador, **Almoxarifado** (acompanha a partir da aprovação e confirma a chegada → Concluído).
- **Tela de Aprovações** (notificações) para o admin aprovar/editar.
- **Cotação:** e-mail (PDF) + botão **WhatsApp** (link wa.me com texto pronto e o aviso de "também enviado por e-mail"); prazo de **5 dias úteis** citado no texto/e-mail.
- **Definição de fornecedor:** escolhe o orçamento vencedor + **frete CIF/FOB** (FOB → Transportadora ou Colaborador+Cidade, interno) + **prazo de recebimento obrigatório** → envia Ordem de Compra.
- **Cadastros (área única):** Usuários, Tipos, Fornecedores (Razão Social, Nome Fantasia, E-mail, Contato, WhatsApp com normalização DDD+9), Cidades, Transportadoras.
- **32 tipos** carregados automaticamente no primeiro start.
- **Identidade visual:** paleta Coral/Grafite/Areia/Verde + fonte Poppins (sem nome/logo, conforme pedido).

### 29/06/2026 — ajustes pós-implementação (a implementar)

20. **⬜ Almoxarifado = solicitante + confirma entrega** — o papel passa a ser igual ao solicitante (cria solicitações e vê o painel dele) e, além disso, **confirma a chegada** do material. Em resumo: "um solicitante que confirma entrega".
21. **⬜ Editar/desativar em todos os cadastros** — incluir editar e ativar/desativar em Usuários, Tipos, Cidades, Transportadoras, Empresas (Fornecedores já tem). Adicionar flag "ativo" onde faltar.
22. **⬜ Local / frente de serviço na solicitação** — novo campo informando onde o material será usado / a frente de serviço.
23. **⬜ Fotos e link no envio** — o PDF da cotação deve incluir as **fotos e/ou o link**; no **WhatsApp**, incluir ao menos o **link do produto**.
24. **⬜ Remover "Condições de pagamento"** do lançamento de orçamento.
25. **⬜ Papel "Somente visualização"** — para colaboradores que não podem solicitar material. **Definido:** mesma tela do solicitante, porém **somente leitura** (sem o botão de nova solicitação e sem ações).
26. **⬜ UF no cadastro de Cidades** — adicionar o campo UF.
27. **⬜ Busca nos tipos do fornecedor** — caixa de pesquisa para filtrar os "tipos de material atendidos" no cadastro de fornecedor.
28. **⏳ Definir admin único** — tornar **antonio.carvalho@srna.co** administrador e remover os demais administradores. *(Operação de dados — feita por script, pois roda no banco.)*
29. **⬜ Painel já filtrado** — por padrão, o painel mostra todos os status **exceto Concluído e Cancelado**.
30. **⬜ Filtros multi-seleção** — permitir filtrar por **vários status** e **vários solicitantes** ao mesmo tempo.
31. **⬜ Cadastro de Empresas** — nova entidade Empresa; o cadastro de usuário passa a ter o campo **Empresa**.
32. **⬜ Cadastro rápido inline** — em todos os formulários que usam um cadastro, permitir **cadastrar o item na hora** (sem sair da tela).

33. **⬜ FAQ detalhado** — página de perguntas frequentes, bem explicada, acessível a todos.
34. **⬜ Exportar PDF** — o usuário seleciona as solicitações que quiser e exporta um PDF para guardar.
35. **⬜ Troca de senha no 1º acesso** — Almoxarifado e Solicitante (e Visualização) trocam a senha obrigatoriamente no primeiro login.
36. **⬜ Admin reseta senha** — o admin entra no cadastro do usuário e redefine a senha (forçando nova troca no próximo acesso).
37. **⬜ Campo de atualizações (discreto)** — uma área discreta de "novidades/atualizações" da plataforma.
38. **⬜ Caixa de melhorias** — campo amigável para o colaborador sugerir melhorias na plataforma (admin recebe/vê).

> **Status:** itens **20–38 CONCLUÍDOS** (implementados e testados em 29/06/2026 — testes end-to-end + smoke de 25 telas dos 4 papéis passaram). Versão **v1.3**.

### Resumo do que entrou na v1.3
- **Papéis:** Almoxarifado agora é "um solicitante que confirma entrega" (cria solicitações, vê o painel dele e confirma chegadas); novo papel **Somente visualização** (vê tudo, só leitura).
- **Senhas:** troca obrigatória no 1º acesso; o admin pode **resetar a senha** de qualquer usuário (cadastro do usuário).
- **Cadastros:** editar e ativar/desativar em todos (usuários, tipos, cidades, transportadoras, empresas, fornecedores); **cadastro de Empresas** (campo no usuário); **UF** nas cidades; **busca** nos tipos do fornecedor; **cadastro rápido inline** (botão "+") em selects.
- **Solicitação:** campo **local / frente de serviço**; **fotos e link** embutidos no PDF; **link do produto** no texto do WhatsApp; removido "condições de pagamento".
- **Painel:** filtro padrão oculta Concluído/Cancelada; filtros **multi-seleção** de status e de solicitantes.
- **Extras:** **exportar** solicitações selecionadas em PDF; **FAQ** detalhado; **Novidades** (rodapé discreto); **caixa de sugestões** (admin vê em Cadastros → Sugestões).
- **Admin único:** script `definir_admin.py` define antonio.carvalho@srna.co como admin e rebaixa os demais.

### 29/06/2026 — melhorias de UX (a implementar)

39. **✅ Melhorar os filtros (lista suspensa com seleção por clique)** — filtros de status e solicitante agora são **dropdowns com caixas de seleção** (clica e marca, sem Ctrl). *(Implementado e testado, v1.4.)*
40. **✅ Retirar "Sugestões" da área de Cadastros** — Sugestões saiu de Cadastros e virou um item próprio no menu do admin. *(Implementado, v1.4.)*

41. **✅ Painel de visualização livre para todos** — todos os papéis veem todas as solicitações no painel; ações continuam por papel. (Resolve o painel vazio do almoxarife.) *(Implementado, v1.4.)*

42. **✅ Retirar "Nova" do cabeçalho** *(v1.4)* — remover o link "Nova" do menu superior (informação ambígua). A criação de solicitação continua acessível pelo botão "+ Nova solicitação" dentro do painel.
43. **✅ Admin também pode pedir material** *(v1.4)* — permitir que o administrador abra solicitações pela própria plataforma (hoje só solicitante/almoxarifado criam).

44. **✅ Ativar todos os tipos de material** *(v1.4)* — marcar todos os tipos como ativos (operação de dados; pode ser um botão "ativar todos" no cadastro de Tipos ou um script rápido).

45. **✅ Botão "Quer fazer uma nova solicitação?"** *(v1.4)* — após enviar uma solicitação, exibir um botão/atalho para abrir outra rapidamente (na tela de confirmação/detalhe pós-envio).

46. **✅ Marcar todas as caixas no painel** *(v1.4)* — incluir no cabeçalho da tabela do painel uma caixa "selecionar todas" (marca/desmarca todas de uma vez), usada na exportação em PDF. **Já vir tudo marcado por padrão.**

47. **✅ Menu "Compras"** *(v1.4)* — agrupar num menu único "Compras" as opções: **Enviar Cotação**, **Importar Orçamento** e um **terceiro item (Orçamentos importados / Comparativo)** que lista as solicitações em **"Aguardando definição de fornecedor"** já mostrando o **menor custo de cada fornecedor** para aquelas compras (visão consolidada para decidir o fornecedor).

48. **✅ Notinhas (lançamento de notas)** *(v1.5)* — para **Almoxarifado** e **Admin**, incluir notas com: **Data** (padrão = hoje), **Fornecedor** (do cadastro), **Atividade** (lista de seleção — **novo cadastro "Atividades"**) e **Valor da notinha**. **Resumo no topo do Painel (só admin):** mostrar apenas o **total do mês corrente** + um **filtro de Atividade** (escolher uma atividade ou "todas"). *Prévia visual (v2) enviada ao usuário antes de implementar.*

> **Item 48 APROVADO pelo usuário** (prévia v2). Pronto para implementar quando ele disser "rodar".

49. **❌ Relatório de recebimento com fotos — DESCARTADO** (29/06/2026) — o usuário optou por não fazer, por causa do limite de armazenamento do plano grátis (Cloudinary 25 GB é teto acumulativo). Mantido aqui só como registro.

50. **✅ Filtro por Fornecedor** *(v1.5)* — incluir o filtro por **fornecedor** no painel (mesmo padrão de lista suspensa com seleção dos demais filtros), permitindo ver as solicitações por fornecedor definido/cotado.

51. **✅ Fornecedor atende vários tipos** — já implementado: o cadastro de fornecedor permite marcar **vários tipos de material** (relação N×N, com busca). Nenhuma ação necessária.

52. **✅ Corrigir tipos sem "ativo"** *(v1.5 — migração agora define ativo=True onde estava NULL)* — tipos criados antes do campo `ativo` ficaram com `ativo = NULL` após a migração, então **não aparecem** nas telas de fornecedor (que filtram `ativo=True`) — impede selecionar tipos ao editar. *Correção:* a migração deve definir `ativo=True` para os existentes (e/ou as telas tratarem NULL como ativo). **Workaround atual:** botão "Ativar todos os tipos" em Cadastros → Tipos.

53. **✅ Comparativo por produto OU por fornecedor** *(v1.5)* — no Comparativo, oferecer a escolha do tipo de visão: **por produto** (como está hoje) ou **por fornecedor**, onde agrupa tudo o que um determinado fornecedor cotou mais barato. Na visão **por fornecedor**, incluir um botão **"Aprovar tudo desse fornecedor"** — define esse fornecedor como vencedor, de uma só vez, em todos os itens em que ele é o mais barato.
54. **✅ Nome completo do item do orçamento (obrigatório)** *(v1.5)* — trazer no comparativo o **nome completo do item** como o fornecedor descreveu no orçamento. No painel/detalhe da solicitação, ao lançar orçamento, incluir esse campo (descrição do item do fornecedor) como **obrigatório**.

> **Regra de trabalho (a pedido, 29/06/2026):** todo pedido enviado é **registrado no roadmap e NÃO executado** na hora. Implementação só quando o usuário disser "rodar".
>
> **Nota técnica:** adicionada uma micro-migração automática de schema (roda ao iniciar o app) que cria colunas novas sem apagar dados — assim mudanças no banco não exigem recriar o `app.db`.
