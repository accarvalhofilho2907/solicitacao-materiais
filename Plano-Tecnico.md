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

55. **✅ Botão "Abrir no e-mail" (mailto) por fornecedor + corpo em tabela** — no **Enviar cotação (lote)** e na tela da solicitação, **um botão de e-mail ao lado de cada fornecedor** que abre o Outlook já com destinatário, assunto e corpo preenchidos, para o admin só clicar Enviar (envia da conta real, sem SMTP/TI). Resultado: cada fornecedor terá **3 botões lado a lado — WhatsApp, E-mail e Texto pronto** (ver item 63). O **corpo em formato de tabela/estruturado** (Nº, material, quantidade, fabricante, link). *Limitações do mailto:* texto puro (tabela em colunas alinhadas, não HTML) e **não anexa PDF** automaticamente. **Método oficial de e-mail: mailto/Outlook manual.**

56. **✅ Marcar se o fornecedor usa e-mail** — incluir uma caixa de seleção ao lado do e-mail no cadastro do fornecedor ("usa e-mail"/"contatar por e-mail"), pois há fornecedores com quem o contato não é por e-mail. Quando desmarcado, o fornecedor não entra no envio de cotação por e-mail (fica só WhatsApp / outro meio) e o e-mail deixa de ser obrigatório.

57. **✅ Filtro/busca no cadastro de Fornecedores** — incluir um campo de busca na lista de fornecedores (por nome fantasia, razão social, contato, tipo) para localizar rápido quando houver muitos cadastrados.

58. **✅ Editar e-mail do usuário** — permitir alterar o e-mail no editar do usuário (hoje a edição muda nome, papel, empresa, ativo e senha, mas não o e-mail).

59. **✅ Filtros completos no painel dos demais papéis** — no painel do **Somente visualização** (e também do **Solicitante** e do **Almoxarifado**), usar os mesmos filtros avançados do admin: listas suspensas com seleção (status, solicitante, fornecedor), tipo, busca por material e período (de/até). Hoje esses papéis têm só filtros simples (status, tipo, busca).

60. **✅ Balõezinhos (badges) de pendência no menu** — mostrar contadores no cabeçalho: (a) ao lado de **Aprovações**, a quantidade de solicitações aguardando aprovação; (b) sobre **Compras**, a quantidade aguardando envio de cotação, e ao abrir o menu Compras, o mesmo número sobre **Enviar cotação**. Os balõezinhos somem quando não há nada pendente.

61. **✅ Desativar o anexo de fotos** — ocultar/desativar o campo de upload de imagens na nova solicitação (e demais lugares de upload), por enquanto, para não consumir armazenamento no plano grátis. Manter de forma que dê para reativar depois facilmente.

62. **✅ Editar/excluir notinha** — permitir editar (data, fornecedor, atividade, valor) e excluir uma notinha lançada, para corrigir erros. Os totais por mês/fornecedor recalculam automaticamente.

63. **✅ Botão "Ver/copiar texto" no envio em lote** — ao lado de "Abrir WhatsApp", um botão que abre um **pop-up (modal) com o texto pronto** da cotação e um botão **"Copiar"**, para o admin colar onde quiser, sem abrir uma aba nova do WhatsApp a cada vez.
64. **✅ Encurtar o link do produto** — gerar um **link curto** para os links gigantes de produto. Recomendado: **redirect interno** (ex.: `…/r/<id>` que redireciona para a URL longa) — grátis, sem depender de terceiros; alternativa é um encurtador externo (TinyURL/is.gd). Usar o link curto nos textos de WhatsApp/e-mail/cotação.

65. **✅ Exportar ficha(s) da solicitação em PDF na tela de Aprovações** — incluir caixa de seleção por item na tela de **Aprovações** e um botão para **exportar em PDF os marcados**. O PDF deve ser a **ficha completa de cada solicitação** (material, quantidade, fabricante, tipo, local/frente, link, solicitante, status, datas — e imagens se houver), **não apenas a tabela resumida**.

66. **✅ Aprovações: editar quantidade + aprovar marcados em lote** — na tela de Aprovações, permitir **editar a quantidade** de cada item (ex.: pedido 100 → ajustar para 50), registrando a alteração no histórico da solicitação. E incluir um botão para **aprovar em lote todos os itens marcados** (usando as caixas de seleção do item 65).
67. **✅ Histórico/linha do tempo da solicitação (logs)** — guardar todo o histórico de cada solicitação como um conjunto de logs com data/hora: criada, foi para aprovação, aprovada, enviada para cotação, aguardando orçamento, definição de fornecedor, ordem de compra, aguardando chegada, concluída — além de alterações de quantidade, comentários, etc. Exibir como linha do tempo no detalhe.

68. **✅ Menu superior mais clean** — reduzir a poluição do cabeçalho: deixar no topo só os itens principais (Painel, Aprovações, Compras, Notinhas) e agrupar os secundários (Cadastros, Sugestões, FAQ, Sugerir, Novidades, Sair) dentro de um **menu do usuário** (nome/avatar à direita, com dropdown). *Prévia visual APROVADA pelo usuário.*

69. **✅ Melhorias nas Notinhas** —
    - **Valor:** aceitar só **números e vírgula** (bloquear o ponto ".").
    - **Obrigatórios:** Data, Fornecedor, Atividade e Valor (hoje Atividade é opcional).
    - **Competência:** incluir um campo de competência (mês/ano) que o admin possa escolher/editar, podendo ajustar ali os valores do mês corrente.
    - **Exportar em PDF** as notinhas.
    - **Filtros** por data, fornecedor e atividade na tela de notinhas.

### 30/06/2026 — link, controle de envio e modelo de e-mail (a implementar)

70. **❌ Importação de fornecedores em lote via planilha — DESCARTADO** (usuário vai cadastrando aos poucos).

71. **✅ Link curto detectar o endereço automaticamente** *(v1.7)* — em vez de depender da variável `BASE_URL`, o link curto (`/r/<id>`) deve usar o endereço de onde o sistema está sendo acessado (`request.url_root`). Assim, no Render sai o endereço do Render e local sai o local, sem precisar configurar nada. *(Corrige o link saindo como `localhost:5000` em produção.)*

72. **✅ Botão "Cotação enviada" por fornecedor (Enviar Cotação)** *(v1.7)* — na tela de Enviar Cotação, incluir **um botão para cada fornecedor** que marca a cotação daquele fornecedor como **enviada** e **já altera o status** das solicitações correspondentes (de "Aguardando envio de cotação" → "Aguardando recebimento de cotação"). Registrar no histórico/log qual fornecedor e quando.

73. **✅ Novo modelo do e-mail de cotação** *(v1.7)* — padronizar assunto, corpo e assinatura (detalhes completos salvos em `referencia_cotacao.md`):
    - **Assunto:** `SRNA | <Nome Fantasia do fornecedor>: Cotação de material #<sequencial>` — criar um **número sequencial de cotação** gerado pelo sistema.
    - **Corpo:** saudação ("Olá, *<contato>*, tudo bem?"), pedido considerando **i. Frete CIF; ii. Pagamento 30 DDL; iii. Material de Uso e Consumo**.
    - **"Dados para Cotação"** em tabela: bloco fixo com as **SPEs do comprador** (SPE, Endereço, CNPJ, I.E. — 15 SPEs Delta, ver `referencia_cotacao.md`).
    - **"Produtos"** em tabela: Nº da solicitação (com `#` antes e depois, ex.: `#1#`), Produto, Fabricante/Marca, Quantidade, Link do produto (link curto).
    - **Prazo para retorno:** 5 dias úteis (com a data-limite calculada, "Até DD/MM/AAAA").
    - **Assinatura fixa:** Antonio Carlos Carvalho / Analista Administrativo Jr de O&M – Cluster Delta MA / +55 (86) 99939-9872 / srna.co.
    - *Obs.: no mailto (texto puro) a "tabela" sai em colunas alinhadas por texto; tabela HTML de verdade só com envio por SMTP.*

### 30/06/2026 — cadastro inline de tipo, fabricante N/D e ajustes do e-mail (a implementar)

74. **✅ Cadastrar tipo de material na hora (só ADMIN)** *(v1.7)* — na **Nova solicitação**, no campo **Tipo de Material**, se o tipo necessário não existir, permitir **cadastrá-lo ali mesmo** (sem sair da tela). Essa opção fica **disponível somente para o ADMIN** — solicitante/almoxarifado/visualização não veem.

75. **✅ Fabricante em branco → "N/D"** *(v1.7)* — quando o campo **Fabricante** da solicitação estiver vazio, exibir **"N/D"** no e-mail, no WhatsApp e no texto pronto da cotação (em vez de deixar a coluna em branco).

76. **✅ Formato do sequencial de cotação = `COT-AAAA-000`** *(v1.7)* — definir o sequencial do item 73 no formato **`COT-2026-001`** (prefixo `COT`, ano, número com 3 dígitos, reiniciando a cada ano). Atualiza o item 73.

77. **✅ Melhorar o alinhamento das tabelas no texto** *(v1.7)* — alinhar melhor as colunas das tabelas ("Dados para Cotação" e "Produtos") no texto puro (mailto/WhatsApp/texto pronto), usando largura fixa de colunas / espaçamento monoespaçado para as colunas ficarem retas. Atualiza o item 73.

78. **✅ Cadastrar Atividade na hora nas Notinhas** *(v1.7)* — na tela de **Notinhas**, no campo **Atividade**, se a atividade desejada não existir, permitir **cadastrá-la ali mesmo** (sem sair da tela). Disponível para **Almoxarifado e Admin** (ambos lançam notinhas).

79. **✅ Competência automática nas Notinhas** *(v1.7)* — **travar/remover** o campo de digitação da competência; ela passa a ser **preenchida automaticamente** a partir do **mês/ano da data da notinha** (ex.: data 15/03/2026 → competência 2026-03). Atualiza o item 69 (que permitia editar a competência). Vale para criar e editar.

80. **✅ Admin tem TODAS as opções de todos os papéis** *(v1.7)* — o administrador passa a acumular **todas as ações** de qualquer usuário. Em especial, **marcar o recebimento/chegada do material** (hoje exclusivo do Almoxarifado) também fica disponível para o Admin. Regra geral: tudo que Solicitante, Almoxarifado e Visualização podem fazer, o Admin também pode.

81. **✅ Confirmar chegada PARCIAL dos itens** *(v1.7)* — no campo de **confirmar chegada**, o Almoxarifado (e o Admin, item 80) informa **quantas unidades chegaram**. Comportamento: se a quantidade recebida for **menor que a pedida**, registra a chegada parcial e mantém o item **"Aguardando chegada"** (mostrando recebido X de Y); quando o total recebido **atinge a quantidade**, o item vai para **Concluído**. Cada recebimento (parcial ou total) entra no **histórico/log** com data, quantidade e quem confirmou. *(Sugestão técnica: campo `quantidade_recebida` acumulada na solicitação.)*

82. **✅ Mostrar o tipo de usuário no cabeçalho** *(v1.7)* — hoje o cabeçalho exibe "Solicitação de materiais" para todos. Passar a exibir o **papel do usuário logado** (ex.: "Almoxarifado", "Solicitante", "Administrador", "Visualização"). Pedido feito para o Almoxarifado; aplicar a mesma lógica para todos os papéis.

83. **✅ Busca dentro das listas suspensas dos filtros** *(v1.7)* — nos filtros de **Status, Solicitante e Fornecedor** (listas suspensas com caixas de seleção), incluir um **campo de busca no topo do dropdown** que filtra as opções conforme o texto digitado, com correspondência **parcial e sem diferenciar maiúsculas/acentos** (ex.: digitar "lumi" mostra "Iluminar"). Aplicar em todos os painéis (admin, solicitante, almoxarifado, visualização).

84. **✅ Editar Tipo, Local/Frente e Fabricante da solicitação** *(v1.7)* — além da quantidade (item 66), permitir **editar** na solicitação os campos **Tipo de material**, **Local/Frente de serviço** e **Fabricante**. Mesmo padrão da edição de quantidade (pelo Admin, registrando a alteração no histórico/log).

85. **❌ Leitor de orçamento por imagem (OCR) — DESCARTADO** (30/06/2026) — usuário optou por **não seguir com OCR**. O importador continua só com PDF de texto; orçamento em imagem é digitado na mão.

86. **✅ Deixar clara a cidade escolhida (frete FOB / Colaborador do parque)** *(v1.7)* — na tela **Definir fornecedor + Ordem de Compra**, quando o frete é **FOB → Colaborador do parque**, o campo de **cidade** de retirada está confuso (dropdown pequeno e sem rótulo; não mostra claramente a cidade selecionada mesmo após escolher). Melhorar: **rótulo "Cidade de retirada"**, campo mais largo e exibir de forma clara a cidade selecionada (e o botão "+" de cadastro inline ao lado, identificado).

87. **✅ Prazo de recebimento com data de hoje por padrão** *(v1.7)* — no campo **Prazo de recebimento** (tela Definir fornecedor + Ordem de Compra), já vir **preenchido com a data de hoje** por padrão, mas **editável** (mesmo padrão da data nas Notinhas).

88. **✅ Todos os cadastros em MAIÚSCULAS** *(v1.7)* — em **todos os cadastros, sem exceção** (Tipos de material, Fornecedores — razão social, nome fantasia, contato —, Cidades, Transportadoras, Atividades, Empresas, Usuários — nome —, etc.), **converter o texto para MAIÚSCULAS automaticamente ao salvar**, mesmo que a pessoa digite em minúsculas. Aplicar tanto no cadastro novo quanto na edição. **Backfill automático:** incluir no `_light_migrate` (roda sozinho no deploy) uma rotina **única** que converte para maiúsculas **todos os cadastros já existentes** — sem o usuário precisar rodar SQL no Neon. *(E-mail e senha ficam de fora; e-mail permanece em minúsculas.)*

89. **✅ Filtro por valor nas Notinhas** *(v1.7)* — incluir, junto aos filtros das Notinhas (data, fornecedor, atividade), um filtro por **valor** — faixa **mínimo/máximo** (R$ de / até). Recalcula os totais conforme o filtro.

90. **✅ Remover um fornecedor da cotação de uma solicitação (fornecedor não tem o item)** *(v1.9)* — *(CORRIGIDO 30/06/2026 — interpretação anterior estava errada)* Na tela da solicitação, poder **marcar que um fornecedor específico não tem o item / recusou** aquela solicitação e **removê-lo da lista de fornecedores** daquela solicitação (some dos botões WhatsApp/E-mail/Texto e do agrupamento de envio em lote). É por **solicitação** (não desativa o fornecedor no cadastro). Registrar no histórico/log ("Fornecedor X removido — sem o item"). Poder também **reverter** (voltar o fornecedor à lista). *(Sugestão técnica: tabela de exclusão solicitação×fornecedor.)* **✅ Item 90-extra RESOLVIDO (08/07/2026, rodado):** botão extra de cancelar/excluir orçamento já lançado foi **removido** (rota `excluir_orcamento` e coluna do botão na tela); ficou só "Não tem" (remover fornecedor da cotação).

91. **✅ WhatsApp/Texto pronto sem o quadro de CNPJs** *(v1.8)* — no **WhatsApp** e no **Texto pronto** (copiar), **não incluir** o quadro "Dados para Cotação" (tabela de SPEs/CNPJs). Esse bloco fica **somente no e-mail**. O WhatsApp/Texto mantém saudação, condições, tabela de produtos, prazo e assinatura. Atualiza os itens 73/77.

92. **✅ Manter o filtro ao abrir um item e voltar** *(v1.8)* — hoje, ao aplicar um filtro no painel, abrir uma solicitação e voltar, o filtro é **perdido**. Passar a **preservar o filtro** ao entrar no item e retornar (o botão "Abrir"/"Voltar ao painel" carrega os mesmos filtros). Só **voltar ao padrão** quando o usuário **muda de aba/seção** (clica em outro item do menu). Aplicar no painel do admin e nos demais papéis.

93. **✅ Alerta de prazo de cotação vencido** *(v1.8)* — registrar a **data-limite de retorno da cotação** (5 dias úteis) no momento do envio/marcação e exibir um **local/indicador** das solicitações cujo **prazo já venceu** (status "Aguardando recebimento da cotação" com data-limite < hoje). Objetivo: o admin consegue **fechar o processo** e seguir para a definição de fornecedor/compra mesmo sem todas as cotações. *(Ex.: badge "prazo vencido" + filtro/lista dedicada; sugestão técnica: campo `prazo_cotacao` na solicitação.)*

94. **✅ Filtro de Atividade nas Notinhas com múltipla seleção** *(v1.9)* — no filtro de **Atividade** das Notinhas, permitir **escolher mais de uma atividade** ao mesmo tempo (multi-seleção, no padrão de lista suspensa com caixas de seleção dos outros filtros). Os totais (do filtro e por fornecedor) **somam** todas as atividades selecionadas. Aplicar também no resumo de atividade do painel do admin, se fizer sentido.

95. **✅ Enxugar os filtros (Solicitações e Notinhas)** *(v1.9)* — reduzir a **largura dos campos De/Até** (estão largos demais) e **remover o texto** "Por padrão mostra tudo menos Concluído e Cancelada" no painel de Solicitações. Aplicar o mesmo enxugamento no filtro das Notinhas.

96. **✅ Deixar as telas de cadastro mais organizadas/bonitas** *(v1.9 — polida a home de Cadastros; telas já em cards)* — padronizar visualmente **todas as telas de Cadastro** (Tipos, Fornecedores, Cidades, Transportadoras, Atividades, Empresas, Usuários): alinhamento dos formulários, espaçamentos, largura de campos, tabelas mais limpas e consistência entre elas.

97. **✅ Dashboard com cartões no topo** *(v1.9)* — cartões clicáveis com os contadores: aguardando aprovação, aguardando envio de cotação, cotação vencida, aguardando chegada. Cada cartão leva ao painel já filtrado.

98. **✅ Painel "O que precisa de mim hoje"** *(v1.9)* — uma tela consolidada juntando: aprovações pendentes + cotações com prazo vencido + chegadas atrasadas.

99. **✅ Reenviar cotação com 1 clique** *(v1.9)* — para solicitações aguardando recebimento da cotação, botão para **reenviar** a um fornecedor (regera WhatsApp/E-mail/Texto), registra o reenvio no histórico e renova o prazo (5 dias úteis).

100. **✅ Último preço ao lançar orçamento** *(v1.9)* — ao lançar orçamento na solicitação, mostrar o **histórico de preços** recentes daquele material (fornecedor, valor, data) como referência.

101. **✅ Badge de chegada atrasada** *(v1.9)* — quando o `prazo_recebimento` já passou e o item ainda está "Aguardando chegada", mostrar um indicador "chegada atrasada" (painel e tela de chegadas), com contador.

106. **✅ Duplicar solicitação** *(v1.9)* — botão para criar uma nova solicitação copiando material, tipo, fabricante, quantidade, link e local (para compras recorrentes). Nasce em "Aguardando aprovação".

107. **✅ Histórico de preços por fornecedor** *(v1.9)* — página que lista, por fornecedor, os orçamentos já lançados (item, valor, data, solicitação), como apoio à negociação.

108. **✅ Backup para baixar** *(v1.10, rodado 08/07/2026)* — botão "Baixar backup (.sql)" no menu Relatórios e Impressões (`admin.backup`), gera **dump lógico `.sql`** (INSERT statements de todas as tabelas) direto pela aplicação — funciona tanto no SQLite local quanto no Postgres/Neon em produção, sem depender de `pg_dump` externo.

### 08/07/2026 — Geração de Etiquetas (Almoxarifado) (a implementar)

109. **✅ Campo "Geração de Etiquetas"** *(v1.10, rodado 08/07/2026)* — dentro do menu "Relatórios e Impressões". Visível para **Almoxarifado e Admin**. Permite gerar etiquetas de diversos tipos e tamanhos preenchendo dados em tela, sempre pensando no **layout impresso em folha A4**.
    - **Tipos de etiqueta:** **"Envio de Material"** (detalhado abaixo, 1ª fase) e **"Identificação de Item"** (liberado junto, a especificar — etiqueta simples para prateleira/caixa do estoque interno; layout e campos a definir antes de rodar). *(O tipo "Devolução", cogitado antes, foi **retirado** do escopo — 08/07/2026.)*
    - **Fluxo da etiqueta "Envio de Material":**
      1. **Remetente** — dropdown com as **Deltas da Serena Energia** (lista fixa, análoga às SPEs do `referencia_cotacao.md`/`SPES_COTACAO`). Ao escolher, preenche automaticamente: nome da Delta, endereço completo e CNPJ. Contato do remetente é sempre fixo: **Antonio Carlos Carvalho / (86) 99939-9872 / antonio.carvalho@srna.co**.
         - **Lista de Deltas (Remetente) fornecida pelo usuário — usar como fonte fixa, mesmo padrão do bloco de SPEs:**
           | Delta | Endereço | CNPJ | I.E. |
           |---|---|---|---|
           | Delta 3 I Energia S.A. | Rua Rio Novo, 47 - Centro - Paulino Neves/MA - 65585-000 | 23.598.517/0002-00 | 124895123 |
           | Delta 3 II Energia S.A. | Rua Rio Novo, 47 - Centro - Paulino Neves/MA - 65585-000 | 23.598.858/0002-86 | 124897193 |
           | Delta 3 III Energia S.A. | Rua Rio Novo, 47 - Centro - Paulino Neves/MA - 65585-000 | 23.598.847/0002-04 | 124897070 |
           | Delta 3 IV Energia S.A. | Rua Rio Novo, 47 - Centro - Paulino Neves/MA - 65585-000 | 23.598.842/0002-73 | 124897029 |
           | Delta 3 V Energia S.A. | Rua Rio Novo, 47 - Centro - Paulino Neves/MA - 65585-000 | 23.598.829/0002-14 | 124897134 |
           | Delta 3 VI Energia S.A. | Rua Rio Novo, 47 - Centro - Paulino Neves/MA - 65585-000 | 23.598.831/0002-93 | 124896995 |
           | Delta 3 VII Energia S.A. | Rua Rio Novo, 47 - Centro - Paulino Neves/MA - 65585-000 | 23.598.844/0002-62 | 124897100 |
           | Delta 3 VIII Energia S.A. | Rua Rio Novo, 47 - Centro - Paulino Neves/MA - 65585-000 | 15.190.472/0002-02 | 12.512653-0 |
           | Delta 5 I Energia S.A. | Rodovia MA-315, s/n, Vias Internas do Complexo Eólico Delta 5, Zona Rural - Paulino Neves/MA - 65585-000 | 29.296.171/0002-72 | 12.556889-4 |
           | Delta 5 II Energia S.A. | Rodovia MA-315, s/n, Vias Internas do Complexo Eólico Delta 5, Zona Rural - Paulino Neves/MA - 65585-000 | 29.303.897/0002-95 | 12.556898-3 |
           | Delta 6 I Energia S.A. | Rodovia MA-315, s/n, Vias Internas do Complexo Eólico Delta 6, Zona Rural - Paulino Neves/MA - 65585-000 | 29.296.141/0002-66 | 12.556908-4 |
           | Delta 6 II Energia S.A. | Rodovia MA-315, s/n, Vias Internas do Complexo Eólico Delta 6, Zona Rural - Paulino Neves/MA - 65585-000 | 29.296.975/0002-71 | 12.556887-8 |
           | Delta 7 I Energia S.A | Rodovia MA-315, s/n, Vias Internas do Complexo Eólico Delta 7, Zona Rural - Paulino Neves/MA - 65585-000 | 30.866.542/0002-93 | 12.583428-4 |
           | Delta 7 II Energia S.A | Rodovia MA-315, s/n, Vias Internas do Complexo Eólico Delta 7, Zona Rural - Paulino Neves/MA - 65585-000 | 30.905.225/0002-39 | 12.583447-0 |
           | Delta 8 I Energia S.A. | Rodovia MA-315, s/n, Vias Internas do Complexo Eólico Delta 8, Zona Rural - Paulino Neves/MA - 65585-000 | 30.866.547/0002-16 | 12.583436-5 |
      2. **Destinatário** — dropdown com os **Fornecedores já cadastrados** no sistema (mesma base de cadastro usada na cotação). Ao escolher, preenche automaticamente endereço completo, CNPJ, contato, telefone e e-mail do fornecedor — mas **todos esses campos ficam editáveis na hora** (contato pode ser trocado; telefone e e-mail podem ser incluídos/alterados na tela, sem precisar editar o cadastro do fornecedor).
      3. **Quantidade de volumes** — o sistema pergunta quantos volumes serão enviados, para saber **quantas etiquetas gerar** (1 etiqueta por volume, numeradas ex. "Volume 1/3", "Volume 2/3"...).
      4. **Layout/tamanho da etiqueta** — antes de gerar, oferecer opção de **quantas etiquetas por folha A4**: **02, 04, 06 ou 08** etiquetas iguais por folha (grid de tamanhos proporcionais à folha A4, maior quando menos etiquetas por folha).
      5. Gerar o **PDF pronto para impressão** em A4, com o grid escolhido, repetindo o layout de etiqueta (remetente, destinatário, volume X/Y) conforme a quantidade de volumes/etiquetas.
    - **Pendências técnicas a decidir antes de rodar:** desenho exato do layout de cada etiqueta (quais campos aparecem e em que posição/tamanho de fonte); se haverá algum código/QR vinculando ao Nº da solicitação (ver item 13 do resumo — chave comum com o futuro módulo de Almoxarifado/estoque); layout e campos da etiqueta "Identificação de Item".

### 08/07/2026 — Reestruturação do menu + Relatório de carga (RODADO)

110. **✅ Reestruturar o menu principal** *(v1.10, rodado 08/07/2026)* — novo agrupamento, substituindo o menu antigo:
    - **i. "Início"** (era "Painel") — ícone de casa 🏠.
    - **ii. "Operação"** — agrupa: Aprovações, Chegadas, Compras (enviar cotação/importar orçamento/comparativo/histórico de preços) e **Notinhas** (agora dentro do grupo Compras). **Sino de notificações** 🔔 no topo mostrando pendências do usuário logado (aprovações + cotações a enviar, reaproveitando os contadores já existentes).
    - **iii. "Relatórios e Impressões"** — visível **somente para Almoxarifado e Admin**. Agrupa: **Geração de Etiquetas** (item 109) e o **Relatório de Recebimento / Relatório de Envio** (item 111), além do link de Backup (.sql, item 108).
    - FAQ, Sugestões, Novidades e Cadastros continuam no menu do usuário (avatar), como já era.

111. **✅ Relatório de Recebimento e Envio de Materiais** *(v1.10, rodado 08/07/2026)* — dentro de "Relatórios e Impressões". **São duas telas/rotas distintas** (`/relatorios/carga/recebimento` e `/relatorios/carga/envio`), acessíveis só por **Almoxarifado e Admin**. Cada um só gera o PDF na hora para imprimir — **não fica salvo nem gera histórico no sistema** (decisão do usuário, 08/07/2026).
    - **Cabeçalho do PDF fiel ao modelo em foto** ("Relatório de Carga Almoxarifado Delta MA"): faixa colorida com título + selo de status ("Recebido"/"Enviado"), Data, Responsável, Razão Social, CNPJ, Inscrição Estadual, Endereço, bloco "Dados da Carga" (Nota Fiscal, Série, OC, Valor da NF, Natureza da operação, CT-e, Valor do CT-e) e Observações.
    - Data vem pré-preenchida com hoje e Responsável com o nome do usuário logado (editáveis).
    - **Não** foi implementado (fica para depois, se o usuário quiser): puxar Razão Social/CNPJ/IE/Endereço automaticamente de um cadastro de fornecedor — hoje é preenchido à mão, pois o cadastro de Fornecedor não tem esses campos ainda.

112. **✅ Tema escuro (dark mode) em todo o sistema + renomear para "ALMOXARIFADO"** *(v1.10, rodado 08/07/2026)* — fundo escuro (#1B1B1B / cards #232323) em todas as telas, mantendo Coral (#FF5246) como cor de destaque e Verde (#32CAA0) como cor de sucesso. O nome exibido no topo (e no título das páginas) mudou de "Solicitação de Materiais" para **"ALMOXARIFADO"** em todo o app.

### 08/07/2026 — Lista grande de melhorias (a implementar)

113. **✅ Alternar tema Claro/Escuro por usuário** — botão/switch no menu (ao lado do sino ou no menu do usuário). Preferência **gravada por usuário** no banco (novo campo em `Usuario`, ex. `tema_preferido`), persistindo entre sessões/dispositivos.

114. **🟡 PARCIAL — Corrigir leitura do Importar Orçamento (PDF) + permitir arrastar o arquivo** *(rodado 08/07/2026, exemplos anexados 08/07/2026)*:
    - **✅ Drag-and-drop** implementado na tela de importar orçamento (arraste o PDF na área pontilhada, ou clique para escolher o arquivo como antes).
    - **⬜ Extração de texto ainda não corrigida.** Usuário anexou 2 modelos reais de orçamento que hoje erram — guardados aqui para quando for implementar:
      - **Modelo "FBM" (Mancais e Acessórios, orçamento nº 404893):** linha em texto corrido com espaçamento simples (não é tabela real do PDF): `Item Qtde Código Peça/Descrição Marca Prazo Preço Unit. Preço Total` — ex.: `1 100 6203 ZZ - ROL. RIGIDO DE ESFERAS SKF 1 A 2 DIAS 16,00 1.600,00`. O código vem **antes** da descrição (5 dígitos, não 6+ como o padrão atual espera), e a marca/prazo ficam em colunas de texto livre entre a descrição e os valores.
      - **Modelo "Cofermeta" (orçamento nº 11246140 / pedido 185187):** tabela mais densa, com colunas extras que o padrão atual não tem: `N° Código UN Descrição Marca Qtde NCM CST %ICMS Vr.Unit Vr.Total Prazo ICMS ST` — ex.: `1 52852 PC ROL RIGIDO ESFERA 6203-2Z SKF 100,00 84821010 200 4,00 14,98 1.498,00 IMEDIATO 0,00`. Tem NCM e CST no meio da linha (que não existem no padrão atual) e os valores já vêm com ICMS incluso.
      - Nenhum dos dois bate com o único padrão hoje reconhecido (`ITEM_RE` em `app/pdf_orcamento.py`, calibrado para código de 6+ dígitos seguido de unidade/qtd/preço/subtotal simples) — confirma que cada fornecedor precisa do seu próprio padrão de reconhecimento (`_PADROES`, já preparado para receber mais de um).
      - **Modelo "Ferramentech" (Ferramentas e Equipamentos, cotação/coleta de preço nº 044235):** cabeçalho "Cotação" + "REF: COLETA DE PREÇO Nº". Destinatário na linha "À DELTA 3 VIII ENERGIA S.A.". Tabela com colunas `Item | Código | Descrição do Produto | NCM | C.A | Qtd | P.Unitário | Valor | Prazo Entrega` — ex.: `1 014313 JOGO CHAVE COMB.06-32MM REF.1B26M GEDORE GEDORE 1B-26M 82041100 1 1,063.47 1,063.47 1 - Imediato`. Repare que **usa ponto como separador decimal** (`1,063.47` = mil e sessenta e três reais e quarenta e sete centavos, padrão americano) — diferente dos outros que usam vírgula. Fecha com "TOTAL BRUTO". Fornecedor tem CNPJ/IE no topo.
      - **Modelo "Lojão das Ferramentas / Tucano" (ERP SysPro, orçamento nº 1967):** cabeçalho "ORÇAMENTO" + Número/Emissão/Validade/Vendedor. Dados do cliente em bloco (Nome, Endereço, Cidade, Bairro, CPF/CNPJ, Telefone). Tabela com colunas `QTDE | UNID | CÓDIGO | REFERENCIA | DESCRIÇÃO | PREÇO | TOLST` (ordem diferente: **quantidade vem primeiro**, e há uma coluna REFERENCIA muitas vezes vazia) — ex.: `1,00 UNID 1000 TORNO MECÂNICO ... MR-334 29.037,08 29.037,07`. Algumas descrições **quebram em duas linhas** (a descrição continua na linha seguinte antes dos valores) — isso vai exigir cuidado no parser. Rodapé com SUBTOTAL/DESCONTO/FRETE/TOTAL.
      - **Resumo dos 4 modelos (anexados 08–09/07/2026):** FBM, Cofermeta, Ferramentech e Lojão/Tucano — **cada um com layout, ordem de colunas e até separador decimal diferentes**. Isso confirma que o leitor precisa de um padrão por fornecedor (identificado pelo CNPJ ou por marcadores no topo do PDF), não um padrão único. Os 4 PDFs originais estão com o usuário; ele reenvia quando formos rodar o item.
      - **Ainda faltam antes de rodar:** decidir a estratégia (detectar o fornecedor pelo CNPJ no topo e aplicar o padrão específico de cada um é o caminho mais robusto); decidir o que fazer com campos extras (NCM, CST, %ICMS do Cofermeta; C.A do Ferramentech) — provavelmente ignorar na extração, já que o que importa é código/descrição/qtd/preço; tratar o separador decimal americano do Ferramentech; e tratar descrições que quebram em 2 linhas (Lojão).

    - **✅ EXECUTADO (09/07/2026):** `pdf_orcamento.py` reescrito com **um parser por fornecedor, detectado pelo CNPJ no topo do PDF** (Cofermeta, FBM, Ferramentech, Lojão/Tucano), mais um parser genérico de fallback para PDFs desconhecidos. Cada parser trata as particularidades: descrição na linha acima do código (Cofermeta), marca/prazo em texto (FBM), **separador decimal americano** `1,063.47` (Ferramentech), e **descrições que quebram em 2 linhas** (Lojão). Testado com os 4 PDFs reais: Cofermeta 2 itens, FBM 2, Ferramentech 38, Lojão 33 — todos com descrição/qtd/preço unitário/subtotal corretos. **Bug reportado corrigido:** a Cofermeta antes lia lixo do cabeçalho (CEP, CNPJ, endereço) porque caía no fallback frágil; agora lê os rolamentos certos. Campos extras (NCM/CST/ICMS/C.A) são ignorados. O preço continua editável no de-para (`_parse_valor` aceita BR e US).
    - **⬜ +2 modelos novos a calibrar (anexados 10/07/2026) — ainda NÃO implementados (aguardando "rodar"):**
      - **Iluminar (Comercio e Serviços, orçamento nº 000.160.718):** CNPJ do fornecedor `03.534.081/0001-06`. Cabeçalho "Orçamento". Bloco de dados do cliente (NOME/RAZÃO SOCIAL, Nome Fantasia, CNPJ, ENDEREÇO, RCA/vendedor). Tabela `CÓDIGO | DESCRIÇÃO DO PRODUTO | QUANT | EMBALAGEM | VL TAB | VL DESC | VL UNIT | VL TOTAL` — ex.: `240286 TERM OLHAL COMPRESSAO 95MM-12MM 1F 2C / MARCA: INTELLI ; NCM: 85359090 | 100,0000 | UN | 10,35 | 0,00 | 10,35 | 1.035,00`. Formato BR. A descrição tem uma 2ª linha ("MARCA: ... NCM: ...") que provavelmente deve ser ignorada ou anexada. Totais: Valor Total Tabela / Descontos / Total Itens / Frete / Valor Total Líquido.
      - **Dimensional Brasil (A Sonepar Company, orçamento nº 5242148):** CNPJ do fornecedor `06.913.480/0015-63`. Cabeçalho com dados do cliente (Empresa, CNPJ, Contato, Endereço, Cidade/UF). Tabela `ITEM | CÓDIGO | DESCRIÇÃO | C.FISCAL | ICMS | QTDE | UNID | PREÇO UNITÁRIO | PREÇO TOTAL | ICMS ST | FATURAMENTO EM` — ex.: `1 727677 TERMINAL COMPR TUB CT 95MM2... INTELLI [+ várias linhas de "DESCRIÇÃO TÉCNICA:"] 85359090 7,00 100 PC 7,93 793,00 0,00 até 1 dia`. Formato BR. **Desafio:** a descrição é enorme e quebra em **muitas linhas** (bloco "DESCRIÇÃO TÉCNICA: ... | ... | ...") antes de chegar aos valores — o parser vai precisar juntar/ignorar essas linhas e achar a linha que tem os valores (qtd/preço). Totais: TOTAL SEM ICMS ST / TOTAL ICMS ST / TOTAL COM ICMS ST.
      - Com isso, são **6 modelos reais** conhecidos (FBM, Cofermeta, Ferramentech, Lojão, Iluminar, Dimensional). Quando rodar, adicionar os parsers de Iluminar e Dimensional ao `_FORNECEDORES` (detecção por CNPJ) e testar os 6. Os PDFs ficam com o usuário; ele reenvia ao rodar.

    - **✅ EXECUTADO (10/07/2026) — parsers Dimensional, Mundial Tintas e Iluminar adicionados:** `_parse_dimensional` (layout embaralhado — casa a linha de valores e a descrição do produto separando das linhas "DESCRIÇÃO TÉCNICA"), `_parse_mundial` (preço unitário com 3 casas decimais), `_parse_iluminar` (escrito pela estrutura conhecida). Detecção por CNPJ ampliada para as 10 primeiras linhas. **Testado com os PDFs reais:** Cofermeta 2, FBM 2, Ferramentech 38, Lojão 33, Mundial Tintas 8, Dimensional 1 — todos corretos. **Iluminar:** parser escrito mas **ainda não testado com arquivo real** (o PDF veio só como anexo no chat, não como arquivo) — validar quando o usuário reenviar o PDF. São **7 modelos** cobertos agora.

115. **✅ Mostrar telefone junto ao e-mail do fornecedor no envio de cotação** — na tela de solicitação/cotação, ao lado do nome/e-mail de cada fornecedor, exibir também o **telefone** cadastrado.

116. **✅ Lista suspensa pesquisável para Tipo de Material na Nova Solicitação** — trocar o campo atual por um dropdown com busca (mesmo padrão já usado nos filtros — item 83).

117. **✅ Unidade de Medida do material** — novo campo na solicitação, com **lista fixa pré-definida no sistema** (kg, L, un, m, m², m³, cx, par, rolo, etc. — lista exata a fechar antes de rodar). Também em **dropdown pesquisável**. A unidade escolhida deve aparecer **junto ao nome do produto no envio da cotação** (e-mail/WhatsApp/texto).

118. **✅ Vincular fornecedores a um Tipo de Material no próprio cadastro do tipo** — ao criar/editar um Tipo de Material, poder **entrar nele e marcar quais fornecedores** atendem esse tipo (hoje o vínculo só é feito pelo cadastro do Fornecedor). As duas telas devem ficar sincronizadas (é a mesma tabela `fornecedor_tipo`).

119. **✅ Botão "Cotação enviada" com pop-up de confirmação** — ao clicar em um fornecedor, o sistema **marca todos os fornecedores da lista como enviados de uma vez** e abre um **pop-up perguntando**: "Enviar para mais algum fornecedor?" ou "Isso é tudo?". Se marcar que quer mandar para mais algum: grava o evento no **histórico da solicitação** e **mantém a mesma tela aberta** (sem mudar status). Se marcar que é tudo: aí sim muda o **status** da solicitação para "Aguardando recebimento da cotação".

120. **✅ Pop-up de SPE ao clicar em "Enviar cotação por e-mail"** — ao clicar para enviar por e-mail, abrir um **pop-up perguntando qual SPE** (das 15 Deltas) está solicitando aquela cotação, e enviar o e-mail **já filtrado/preenchido** com os dados dessa SPE (reaproveita a lista de `SPES_COTACAO`). *(Confirmado 08/07/2026: pode ser o mesmo pop-up do item 122, combinando escolha de itens + SPE numa única tela.)*

121. **✅ Retirar o campo "Solicitar cotação" de dentro do item (tela da solicitação)** — remover esse bloco da tela de detalhe da solicitação individual, já que o envio passa a ser centralizado na tela de "Enviar cotação" (itens 119/120/122).

122. **✅ Expandir "Enviar cotação" para qualquer status + busca** — hoje a tela `admin.enviar_lote` só mostra os itens com status "Aguardando envio p/ cotação". Adicionar:
    - Um **botão "Expandir todos os itens"** para incluir solicitações de **outros status** também.
    - **Busca/filtro** por empresa (fornecedor), tipo de material ou nome do produto, para achar rapidamente o item e mandar cotação mesmo fora do fluxo padrão.
    - *(Combina com o item 120: o mesmo pop-up de envio por e-mail pode perguntar a SPE.)*

123. **✅ Excluir empresas do processo de cotação (por item ou na tela de enviar cotação)** — além do "remover fornecedor da solicitação" (item 90, que já existe por solicitação), permitir excluir/pular fornecedores específicos **também na tela de Enviar Cotação em lote**, para casos em que já se sabe que aquele fornecedor não tem o produto, sem precisar abrir cada item.

124. **✅ Desativar fornecedores** — no cadastro de Fornecedores, adicionar a opção de marcar como **inativo** (campo `ativo` já existe no modelo `Fornecedor` — falta expor o toggle na tela de cadastro, igual aos outros cadastros). Fornecedor inativo não aparece mais nas listas de cotação.

125. **✅ Tela de "Coletas próprias" (retirada em São Luís, Parnaíba etc.)** — nova tela que lista as solicitações com **frete FOB / retirada por colaborador**, agrupadas por **cidade de retirada**, com um botão **"Copiar texto"** que monta uma mensagem pronta (itens + fornecedor + endereço de retirada) para colar num grupo do motorista.

126. **✅ Geração de Etiquetas — aumentar o tamanho da fonte** — hoje as etiquetas (Envio de Material e Identificação de Item) estão com letras pequenas para colar numa caixa física; aumentar a fonte em ambos os tipos, respeitando os grids de 2/4/6/8 por folha.

127. **✅ Pré-visualização ao lado das opções "Etiquetas por folha A4"** — ao clicar em 02/04/06/08, mostrar uma **prévia visual** (miniatura) de como fica a divisão da folha, antes de gerar o PDF.

128. **✅ Relatório de Recebimento/Envio — unificar em um único campo/tela + melhorias de fluxo** *(rodado 08/07/2026)*:
    - **✅ Unificado** — uma só tela/rota (`/relatorios/carga`); o campo **Status** decide se é "Recebimento" ou "Envio" e isso reflete no cabeçalho do PDF (selo verde/coral).
    - **✅ Responsável** é lista suspensa puxando os usuários cadastrados (login do sistema), pré-selecionado com quem está logado.
    - **✅ Campo de foto abre dinamicamente** ao digitar Nota Fiscal ou CT-e.
    - **✅ Fotos múltiplas** — um único seletor de arquivo com `multiple`, aceita selecionar várias da galeria de uma vez, com preview.
    - **✅ Marcação "Avariado?"** por foto — não aparece na imagem, mas exige observação obrigatória daquela foto e gera um aviso vermelho no cabeçalho do PDF quando qualquer foto está marcada.
    - **✅ Fotos são temporárias** — ficam só no navegador (preview local), nunca são enviadas para o servidor nem ficam salvas; usadas apenas para o colaborador se organizar visualmente antes de gerar o PDF (o PDF em si não inclui as imagens, só o aviso textual de avaria — anexar fotos dentro do PDF pode ser um próximo passo, se for necessário).

129. **✅ Campo em "Chegada" para alterar a data de confirmação** — na tela de confirmar chegada (Almoxarifado), permitir **editar a data da chegada** para uma data diferente da de hoje (ex.: registro feito com atraso).

130. **🟡 PARCIAL — Reorganizar opções da tela para o canto superior direito** *(rodado 08/07/2026 onde já ficou claro)* — aplicado nas telas novas/alteradas nesta leva: **Notinhas** ("+ Adicionar nova notinha" no topo direito), **Coletas próprias** ("Copiar texto" no topo direito de cada card). O pedido original era genérico ("a mapear quais exatamente"); não mexi em telas antigas que não foram tocadas nesta leva para não arriscar quebrar layouts que já funcionavam. Se houver telas específicas que ainda incomodam, é só apontar quais e viram itens novos e objetivos.

131. **✅ Restringir Backup ao Admin + mover para o menu do usuário** — o link de Backup (.sql, item 108) deve ficar **liberado só para o papel Admin** (hoje também aparece pra Almoxarifado dentro de Relatórios e Impressões) e mudar de local: passa a ficar no **menu do nome do usuário** (avatar, canto superior direito), igual ao item "Cadastros", em vez de dentro de "Relatórios e Impressões".

132. **✅ Reorganizar tela de Notinhas — separar "Adicionar" de "Filtrar"** — hoje os dois blocos (adicionar nova notinha e filtrar a lista) ficam confusos na mesma tela. Trocar por um **botão "Adicionar nova notinha"** que abre um **pop-up/modal** dedicado só para o lançamento; a tela principal fica só com os filtros e a listagem.

133. **✅ Ajustes finos na Geração de Etiquetas** *(rodado 08/07/2026)*:
    - **✅** Opção **"Outro"** na lista suspensa de Remetente — abre campos de texto livre para nome, endereço e CNPJ.
    - **✅** Botão extra **"Gerar PDF para anexar ao e-mail"** — gera o mesmo PDF com nome de arquivo pensado para anexar manualmente (confirmado: não é tecnicamente possível anexar automaticamente via link `mailto:`, então a solução é baixar + anexar à mão).
    - **✅** Tipo renomeado de "Envio de Material" para **"Etiqueta de caixas/embalagens"** em toda a interface.
    - **✅** Campo opcional de **Nota Fiscal** na etiqueta.
    - **✅** Selos de natureza da carga: **Frágil, Explosivo, Pode empilhar, Não empilhar** — aparecem destacados na etiqueta.

102. **❌ Nº de Ordem de Compra sequencial — DESCARTADO** (30/06/2026).
103. **❌ Exportar Excel de solicitações/notinhas — DESCARTADO** (30/06/2026).
104. **❌ Relatório de gastos por período/fornecedor/atividade — DESCARTADO** (30/06/2026).
105. **❌ Anexar orçamento do fornecedor como comprovante — DESCARTADO** (30/06/2026).

### 08/07/2026 — Correção crítica de produção (fora do roadmap, aplicada direto)

134. **✅ Corrigido erro "SSL connection has been closed unexpectedly" em produção** — o usuário reportou Internal Server Error no site publicado (Render + Neon). Causa: o Neon (plano grátis) derruba conexões ociosas, e o SQLAlchemy tentava reusar uma conexão morta do pool de conexões. Corrigido em `config.py` com `SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}`, que testa a conexão antes de cada uso e descarta conexões antigas preventivamente. Não requer nenhuma ação além do próximo deploy.

> **Fechamento da leva v1.11 (08/07/2026):** dos 21 itens pedidos nesta leva grande (113 a 133), **19 foram concluídos**, **1 ficou parcial por decisão explícita do usuário** (item 130, escopo genérico demais para fechar sozinho) e **1 ficou parcial por depender de material externo** (item 114 — extração de PDF de orçamento precisa de exemplos reais dos PDFs que erram para ser calibrada; o drag-and-drop dessa mesma tela já foi entregue). Todo o restante foi testado (rotas, fluxos de POST, geração de PDF, renderização visual em dois temas) antes da entrega.

### 08/07/2026 — Redesign do Relatório de Carga (a implementar)

135. **✅ Redesenhar o PDF do Relatório de Recebimento/Envio + embutir as fotos de verdade** — feedback do usuário: o PDF atual "está muito feio" e **nenhuma foto anexada na tela aparece no PDF gerado** (hoje as fotos servem só de preview visual na tela, confirmando avaria, mas não vão para o documento). Ações confirmadas:
    - **Redesenho completo do layout** (não só trocar cor) — tipografia, espaçamento e organização das seções revistos do zero, buscando visual mais profissional/moderno, mantendo as informações que já existem (cabeçalho, dados do fornecedor, dados da carga, observações).
    - **Paleta oficial Serena** no lugar do azul/roxo atual: Coral **#FF5246** (faixas/destaques principais), Grafite **#4B4B4B** (textos), Verde **#32CAA0** (detalhes/status), Areia **#EDE9E5** (fundos claros/seções) — mesma paleta já usada no resto do sistema e nas etiquetas.
    - **Fotos embutidas de verdade no PDF final** — a foto da Nota Fiscal, a foto do CT-e, e as fotos gerais da carga (com a respectiva marcação/observação de avaria, se houver) passam a aparecer como imagens dentro do próprio PDF gerado, não só como preview na tela.
    - **Pendência técnica a resolver ao implementar:** hoje as fotos são tratadas como **temporárias** (só no navegador, nunca enviadas ao servidor — decisão tomada em 08/07/2026 no item 128). Para embutir no PDF, as fotos precisam ser enviadas junto com o formulário no momento de gerar o documento (o PDF é montado no servidor). Isso não significa que elas passam a ficar *salvas/arquivadas* no sistema depois — continuam sendo usadas só para montar aquele PDF específico e podem ser descartadas em seguida; só muda que agora **precisam trafegar até o servidor** no momento de gerar o relatório (antes não precisavam, pois só apareciam na tela).

### 08/07/2026 — Ajustes de Etiquetas + menu mobile (a implementar)

136. **✅ Corrigir bug visual: pré-visualização do grid não bate com a impressão real** — a etiqueta em si **imprime corretamente** (confirmado pelo usuário: 2 por folha = uma em cima e uma embaixo; 4 por folha = duas em cima e duas embaixo, e assim por diante). O bug é só na **miniatura de pré-visualização** (item 127) na tela: ela está renderizando errado (mostrando os blocos empilhados numa coluna estreita em vez do grid 2x2/2x3/2x4 correto), por causa do jeito como o flexbox foi montado em `app/templates/relatorios/etiquetas.html`. Corrigir a miniatura para refletir fielmente o grid real usado no PDF (`_GRID` em `app/pdf_etiquetas.py`).

137. **✅ Ícone/símbolo visual para cada selo de natureza da carga** — hoje os selos (Frágil, Explosivo, Pode empilhar, Não empilhar) aparecem só como texto colorido na etiqueta. Adicionar um **símbolo visual reconhecível** ao lado de cada um (ex.: taça quebrada para Frágil, chama/explosão para Explosivo, setas para cima para Pode empilhar, "X" para Não empilhar) — desenhados diretamente no PDF (ReportLab), já que não há biblioteca de ícones prontos no ambiente.

138. **✅ Centralizar os dados na etiqueta "Etiqueta de caixas/embalagens"** — hoje o conteúdo (Remetente/Destinatário) fica alinhado à esquerda dentro do slot; centralizar horizontalmente.

139. **✅ Fonte adaptativa por tamanho do nome (etiquetas)** — hoje a fonte é fixa por layout (2/4/6/8 por folha — item 126). Mudar para: a fonte usa o **maior tamanho possível que ainda couber** no espaço da etiqueta; à medida que o nome (remetente/destinatário) for maior, a fonte diminui automaticamente para caber. Quebra de linha (texto em várias linhas) continua permitida — o ajuste de tamanho é um complemento à quebra, não uma substituição.

140. **✅ Menu lateral recolhível no celular** — hoje no mobile o menu superior (Início / Operação / Relatórios e Impressões / sino / avatar) fica espremido e desorganizado. Trocar por um **menu lateral (sidebar) que expande e recolhe** — abre com um botão "hambúrguer" no topo, desliza da esquerda, com os mesmos itens/grupos do menu atual (Início, Operação, Relatórios e Impressões, notificações, usuário). No desktop o menu horizontal atual continua como está; a mudança é só para telas pequenas (mobile).

### 08/07/2026 — Bugfix urgente + novos pedidos (Coletas próprias, Enviar cotação, Etiquetas, Relatório de carga)

141. **✅ CORRIGIDO (rodado direto, fora do fluxo normal de espera) — Pop-up de e-mail (item 120) não abria o e-mail do usuário** — bug real encontrado: o pop-up de escolha de SPE estava chamando a função de **envio via SMTP do servidor** (`enviar_email`, que só funciona se `MAIL_HOST` estiver configurado — não está em produção, então virava só log/nada visível), em vez de abrir o **e-mail do próprio usuário** via `mailto:` (que é como todo o resto do sistema já funciona — WhatsApp/E-mail/Texto pronto, desde a v1.6). Corrigido: a rota `admin.enviar_lote_email` agora devolve o link `mailto:` já pronto (com a SPE escolhida, produtos e assinatura) e o navegador abre automaticamente o cliente de e-mail padrão do usuário, exatamente como o botão de e-mail que já existia antes do item 120. Esse fix foi feito imediatamente por ser um bug bloqueando uma função recém-entregue, e não uma melhoria nova — segue a regra de honestidade sobre bugs vs. pedidos.
    - **Resposta à pergunta "não é possível já anexar o arquivo com nome específico?":** não é possível técnica alguma — é uma limitação do protocolo `mailto:` em si (nenhum navegador permite que um link anexe arquivos automaticamente ao e-mail, por segurança, já que isso abriria brecha para sites anexarem arquivos maliciosos sem o usuário perceber). O caminho que já existe e continua sendo o único possível: baixar o PDF (com nome de arquivo organizado) e arrastar manualmente para dentro do e-mail já aberto.

142. **✅ Coletas Próprias — mostrar contato do fornecedor + agrupar por empresa** — na tela de Coletas Próprias (item 125): ao lado do nome da empresa/fornecedor, mostrar também **nome do contato, e-mail e telefone** (puxados do cadastro do Fornecedor — confirmado 08/07/2026, mesmo contato usado na cotação). Além disso, a lista de itens já é agrupada por cidade (item 125); agora also **agrupar/ordenar por fornecedor** dentro de cada cidade, para o colaborador ver de uma vez só tudo que tem para coletar numa mesma empresa.

143. **✅ Checkbox de seleção de itens em "Enviar cotação" (após expandir/filtrar)** — hoje a tela agrupa e envia por fornecedor (todos os itens daquele fornecedor de uma vez). Adicionar **checkbox por item** (solicitação) dentro de cada grupo de fornecedor, para o usuário escolher manualmente **quais itens específicos** vão entrar naquele envio de cotação — útil depois de usar "Expandir todos os status" ou a busca (item 122), quando nem todo item retornado deve necessarimente ir junto.

144. **✅ Geração de Etiquetas — ajustes no Remetente e mais opções de layout:**
    - **Nome do contato do remetente deixa de ser fixo** ("Antonio Carlos Carvalho") — passa a vir **pré-preenchido como padrão**, mas em um **campo editável**, permitindo trocar por outra pessoa quando necessário.
    - **Mais opções de "etiquetas por folha A4":** além de 02/04/06/08, incluir **01 (uma etiqueta ocupando a folha toda)**, **10, 12, 14 e 16** por folha.
    - **Orientação da folha:** opção de **Retrato (vertical)** ou **Paisagem (horizontal)**, além da quantidade por folha.

145. **✅ Relatório de Recebimento/Envio — reestruturação completa do formulário** *(detalhado 08/07/2026, substitui a versão anterior deste item)*. Nova organização em seções:

    **1. Cabeçalho** (já coberto no registro anterior deste item): Data, Responsável (pré-preenchido com o usuário logado), Status (nasce **desmarcado/vazio** — obriga escolha ativa entre Recebimento/Envio). Todos os campos do cabeçalho obrigatórios.

    **2. Remetente:** Razão Social ou Nome (**obrigatório** — único campo obrigatório da seção), CNPJ (aceita **somente números** digitados, sistema formata automaticamente no padrão `00.000.000/0000-00`), Inscrição Estadual (aceita **somente números**, sistema formata com um hífen antes do último dígito, ex.: `123456789-0`), Endereço.

    **3. Destinatário:** mesmos campos e mesmas regras do Remetente.

    **4. Transportadora:** Razão Social ou Nome (**obrigatório**), CNPJ, Endereço — **sem campo de Inscrição Estadual** (confirmado 08/07/2026, diferente de Remetente/Destinatário). Indicar no campo/dica que essas informações costumam vir no próprio CT-e.

    **5. Dados da Carga:**
    - Nº Nota Fiscal, Série, OC (se informado).
    - Quantidade de volumes (numérico).
    - Tipo de volume — **lista suspensa** (Pallets, Caixas de madeira, Caixas de papelão, Tambores, Sacos, etc. — lista exata a fechar antes de rodar) **+ opção "Outro" com campo de texto livre**.
    - Valor da Nota Fiscal.
    - Natureza da Operação — **lista suspensa fixa** com opções comuns (Venda de Mercadoria, Remessa para Conserto, Devolução, Transferência, Uso e Consumo, etc. — lista exata a fechar antes de rodar) **+ opção "Outro"**.
    - Nº CT-e, Valor do CT-e.
    - **Tomador do CT-e** — lista suspensa com **Razão Social + CNPJ do Remetente** ou **do Destinatário** (usa os dados já preenchidos nas seções 2 e 3 acima, sem digitar de novo).
    - Breve descrição do tipo da carga da nota (campo de texto livre).

    **6. Fotos da carga** — mantém o fluxo já existente (fotos dinâmicas ao preencher NF/CT-e + múltiplas da galeria + marcação "Avariado?" com observação obrigatória — itens 128/135).

    **7. Observações Gerais** — campo de texto livre. **No PDF final, as observações de avaria marcadas nas fotos (item 128/135) aparecem junto com as Observações Gerais**, não em seção separada (ajuste em relação ao que foi implementado antes, que colocava "Observações de Avaria" numa seção própria).

    **Regras de qualidade das fotos no PDF (reforça o item 135):** cada foto embutida no PDF deve ter **boa qualidade/resolução**, e **uma foto por página** (não miniaturas lado a lado) — para dar espaço a cada imagem ser vista com clareza.

    **Novo fluxo de cadastro automático de fornecedor/transportadora** *(detalhado 08/07/2026)*:
    - Em Remetente, Destinatário e Transportadora, o **campo CNPJ vem primeiro** na ordem de preenchimento (antes de Razão Social/Nome e Endereço).
    - Ao sair do campo CNPJ, o sistema **valida se o número é um CNPJ verdadeiramente válido** (dígito verificador, não só a máscara de formatação). Se for **inválido**, abre um **pop-up avisando o usuário e pedindo para corrigir** antes de deixar prosseguir no formulário.
    - Se o CNPJ for válido, o sistema **busca esse CNPJ no cadastro** (Fornecedores, para Remetente/Destinatário; Transportadoras, para Transportadora):
      - **Se encontrar** → **autopreenche** Razão Social/Nome e Endereço com os dados já cadastrados (o usuário não digita de novo).
      - **Se não encontrar** (CNPJ novo) → abre os campos do formulário de cadastro (Razão Social, Nome Fantasia, Endereço, contato, etc. — os mesmos campos do cadastro de Fornecedor/Transportadora hoje) para o usuário preencher ali mesmo, **exceto o campo de Tipo de Material/atividade** (esse não é preenchido nesse fluxo — fica em branco para o Admin completar depois, se for o caso).
      - Esse novo cadastro é salvo como **pendente de aprovação**: Remetente/Destinatário novo → **Fornecedor pendente**; Transportadora nova → **Transportadora pendente** (ver regras de pendência abaixo).
    - Sempre que um **CNPJ novo** for digitado em Remetente, Destinatário ou Transportadora (isto é, um CNPJ que ainda não existe no cadastro), o sistema deve **criar automaticamente um registro pendente**:
      - Remetente/Destinatário com CNPJ novo → cria um **Fornecedor pendente de aprovação** (novo campo de status/aprovação a criar no modelo `Fornecedor`, já que hoje só existe `ativo` True/False — um fornecedor "pendente" não deve aparecer nas listas normais de cotação até ser aprovado pelo Admin).
      - Transportadora com CNPJ novo → cria um registro **pendente** na tabela `Transportadora` já existente (mesma lógica de aprovação, adaptada a essa tabela).
    - O Admin precisa de uma **tela/lista de pendências de cadastro** (fornecedores e transportadoras aguardando aprovação) para revisar e aprovar/rejeitar antes que entrem definitivamente nas listas usadas pelo resto do sistema (cotação, frete FOB, etc.).
    - **Pendências técnicas a fechar antes de rodar:** lista exata de opções para "Tipo de volume" e "Natureza da Operação"; desenho da tela de aprovação de cadastros pendentes (pode entrar dentro de Cadastros, como uma aba/seção nova); definir biblioteca/algoritmo de validação de dígito verificador de CNPJ (cálculo padrão da Receita Federal, sem necessidade de serviço externo).

147. **✅ Nome automático do arquivo/registro do Relatório de Carga** *(confirmado 08/07/2026)* — o nome do relatório (usado como nome do arquivo PDF baixado, e também como referência caso volte a virar um registro no sistema no futuro) segue o padrão:
    - **Envio:** `Envio <Destinatário (Nome Fantasia)> <Nº NF, se houver> <Data>`
    - **Recebimento:** `Recebimento <Remetente (Nome Fantasia)> <Nº NF, se houver> <Data>`
    - Regras: se não houver Nº da NF, esse trecho simplesmente não entra no nome (sem espaço duplo ou traço vazio no lugar). Sem caracteres especiais no nome — só espaços separando as partes (nada de `/`, `-`, `_`, `:` etc., já que isso quebraria nome de arquivo em alguns sistemas operacionais). Data no formato `DD MM AAAA` (com espaços, não barras).
    - Exemplo: `Envio Fornecedor Teste 1234 08 07 2026` (Destinatário "Fornecedor Teste", NF 1234, data 08/07/2026) ou `Recebimento Fornecedor Teste 08 07 2026` (sem NF informada).

148. **✅ Botão combinado "Gerar PDF e abrir e-mail" (cotação e/ou etiquetas)** — confirmado 08/07/2026: como não é tecnicamente possível anexar o PDF automaticamente ao e-mail (limitação do navegador, não do sistema — ver item 141), criar um botão único que faz as duas ações em sequência num só clique: **(1)** baixa o PDF (nome de arquivo já organizado) **e (2)** abre o e-mail do usuário já preenchido (destinatário, assunto, corpo) logo em seguida — poupando o usuário de clicar em dois botões separados. O usuário só precisa arrastar o arquivo que acabou de cair na pasta Downloads para dentro do e-mail já aberto. Aplicar nas telas que já têm os dois botões separados hoje (Geração de Etiquetas — item 133 — e, quando fizer sentido, no fluxo de Enviar Cotação).

149. **✅ Corrigir bordas amarelas feias nos cards de "Cadastros" no tema escuro** *(print anexado 08/07/2026)* — a tela `Cadastros` (Usuários, Empresas, Tipos de material, Fornecedores, Cidades, Transportadoras, Atividades) usa as classes Bootstrap `border-start border-4 border-warning` em cada card, pensadas como uma discreta barrinha lateral no tema claro original — no tema escuro (item 113) ficaram destacando como um contorno amarelo grosso em volta de cada quadrado, visualmente pesado e fora da paleta do sistema. Também há um resíduo do tema antigo (`style="color:var(--grafite)"` fixo no título de cada card) que deveria usar a variável de texto correta em vez de uma cor fixa. Trocar por um visual mais discreto e alinhado com o resto do sistema, usando as cores da paleta Serena (ex.: hover com Coral, sem a barra amarela grossa) — mesmo tratamento visual dado às outras telas já revisadas nesta leva (`app/templates/admin/cadastros.html`).

> **Fechamento da leva v1.12 (09/07/2026):** rodados os itens **135 a 149**. Todos implementados e testados (rotas, geração de PDF, upload de fotos, fluxo de CNPJ com cadastro pendente, validação visual em desktop e mobile). Destaques: redesenho completo do Relatório de Carga com paleta Serena e fotos embutidas (135); reestruturação do formulário em 7 seções com CNPJ-first, validação de dígito verificador, autopreenchimento e cadastro pendente de fornecedor/transportadora + tela de aprovação (145); nome de arquivo automático (147); etiquetas com fonte adaptativa, símbolos nos selos, grids 01–16 e orientação retrato/paisagem, remetente editável (136–139, 144); menu lateral no mobile (140); coletas próprias agrupadas por fornecedor com contato (142); checkbox por item na cotação (143); bordas dos cards de Cadastros corrigidas (149). Também foi **reaplicado o fix do item 141** (pop-up de e-mail abrindo o mailto do usuário em vez do envio SMTP simulado) — o zip recebido tinha a versão antiga dessa função. **Pendentes de verdade:** item 114 (leitura de PDF de orçamento — parser ainda precisa ser calibrado para os 2 modelos anexados) e item 130 (parcial, por escopo genérico).

> **Correções v1.12.1 (09/07/2026)** — três bugs reportados após a v1.12, todos corrigidos:
> 1. **Pop-up de CNPJ inválido reabria em loop** (não deixava corrigir): era o clássico `alert()` + `focus()` dentro do evento `onblur`, que reabria o alerta a cada tentativa. Removido o `focus()` forçado, adicionada trava anti-reentrada e o campo agora fica só com borda vermelha (`is-invalid`) — o usuário corrige normalmente.
> 2. **Internal Server Error ao gerar relatório com fotos:** causa raiz era o **Pillow ausente do `requirements.txt`** — o ReportLab precisa dele para processar JPEG, então funcionava local mas quebrava no Render. Adicionado `Pillow==10.4.0`. Além disso, toda foto agora é **normalizada** (converte para RGB, corrige rotação EXIF de celular, reduz tamanho) antes de entrar no PDF, e a geração inteira ficou dentro de try/except (se uma foto for inválida, ela é pulada com aviso em vez de derrubar o relatório).
> 3. **NF/CT-e não pediam foto:** no redesenho da v1.12 esse comportamento tinha sido substituído por um campo único de fotos. Reposto: ao digitar o Nº da Nota Fiscal aparece o campo "📷 Foto da Nota Fiscal"; ao digitar o Nº do CT-e aparece "📷 Foto do CT-e". Essas fotos entram no PDF como primeiras páginas, com legenda própria.

> **Correções v1.12.2 (09/07/2026)** — o erro 500 ao gerar relatório com fotos **persistiu mesmo após o deploy com o Pillow**, então o código foi blindado em todos os pontos que poderiam derrubar a requisição (a causa exata depende do log do Render, ainda não obtido; estas mudanças garantem que, seja qual for, não vire mais "Internal Server Error" cru):
> - **Criação de cadastro pendente (CNPJ novo)** agora está dentro de try/except com rollback: se o `commit` falhar no PostgreSQL, faz rollback e segue gerando o PDF (o relatório é prioridade; o cadastro pendente é um bônus e não pode derrubar o documento).
> - **Download trocado de `send_file(BytesIO)` para `Response` direta** com o PDF em bytes — mais previsível sob Gunicorn — e o `Content-Disposition` é montado de forma segura (nome com acento tratado via Werkzeug, com fallback ASCII).
> - **Geração do PDF** continua dentro de try/except com `logger.exception` (o traceback real aparece no log do Render) e, em caso de falha, o usuário recebe uma mensagem amigável em vez do erro cru.
> - **Se o erro voltar a acontecer**, o log do Render passará a mostrar a linha exata (procurar por "Falha ao gerar PDF do relatório de carga" ou "Falha ao criar cadastro pendente"). Próximo passo, se persistir, é tratar fotos **HEIC** (formato do iPhone) — que exige a lib `pillow-heif`, ainda não incluída.

> **Correção v1.12.3 (09/07/2026) — causa raiz do erro 500 encontrada pelo log:** `NotNullViolation` na coluna `email` da tabela `fornecedores`. O e-mail passou a ser opcional no modelo (item 145 — cadastro pendente vindo do relatório não tem e-mail), mas a **tabela em produção (Postgres/Neon) foi criada com `email NOT NULL`**, e mudar o modelo não remove a restrição já existente no banco. Ao criar o fornecedor pendente (ex.: JOTUN BRASIL) com `email=None`, o Postgres recusava o INSERT e derrubava a requisição. **Correção:** a migração automática de boot agora executa `ALTER TABLE fornecedores ALTER COLUMN email DROP NOT NULL` no Postgres, removendo a trava. Testado com o cenário exato do log (JOTUN BRASIL, CNPJ válido, sem e-mail, com foto) — agora gera o PDF normalmente e cria o cadastro pendente. As blindagens da v1.12.2 seguem no lugar como rede de segurança.

> **Melhoria v1.12.4 (09/07/2026) — cabeçalho do Relatório de Carga redesenhado:** o usuário achou o topo da 1ª página feio. Foram geradas 3 opções (faixa coral cheia / minimalista / bloco grafite com status integrado) e o usuário escolheu a **opção 3**. Aplicada em `pdf_carga.py`: bloco grafite com barrinhas coral+verde na lateral esquerda, marca "S" em quadrado coral (não há logo em arquivo), título "RELATÓRIO DE CARGA" + subtítulo, e um bloco de status colorido encaixado à direita ocupando toda a altura do cabeçalho (verde em Recebimento, coral em Envio). Sem logo em imagem — usa "S" estilizado em texto.

> **Ajuste v1.12.5 (09/07/2026) — refinar o cabeçalho:** o usuário ainda achou feio. Dois ajustes aplicados: (1) a **faixa grafite agora ocupa toda a largura do topo** (o status deixou de ser um bloco separado à direita e virou uma **tag/pílula colorida dentro da própria faixa grafite**); (2) **removida a barrinha verde estreita** vertical da esquerda — ficou só a barrinha coral fina. Resultado mais limpo. Verde/coral da tag de status seguem indicando Recebimento/Envio.

> **Correção v1.13.1 (09/07/2026) — "Request Entity Too Large" no Relatório de Carga:** um colaborador tentou anexar fotos pelo celular e o servidor recusou com a tela crua "Request Entity Too Large" (erro 413). Causa: o limite era `MAX_CONTENT_LENGTH = 16 MB` por requisição, e fotos de celular (3-5 MB cada) estouram isso com poucas fotos. **Correção:** limite aumentado para **100 MB** por requisição, configurável no Render pela variável de ambiente `MAX_UPLOAD_MB` (sem mexer no código). Além disso, adicionado um **handler amigável para o erro 413**: em vez da tela crua, o usuário vê o aviso "Os arquivos enviados passaram do limite de X MB por envio. Envie menos fotos de uma vez (ou fotos menores) e tente novamente." e volta para a tela anterior. **Pendência registrada (não feita ainda, a pedido):** encolher as fotos automaticamente no navegador antes do upload (redimensionar/comprimir via JS) — resolveria na raiz e deixaria tudo mais rápido; o usuário preferiu, por ora, só aumentar o limite do servidor.

> **Correção v1.13.2 (09/07/2026) — "exceeded its memory limit" no Render (relatório com muitas fotos):** depois de aumentar o limite de upload, um membro da equipe gerou um relatório com mais fotos e o Render reiniciou por estourar a **memória** (e-mail "Web Service solicitacao-materiais exceeded its memory limit"). Causa: montar um PDF com várias fotos de celular (3-5 MB, às vezes 11 MB cada) carrega tudo na RAM de uma vez, e o plano do Render tem pouca memória. **Correção em duas frentes (a solução de raiz que estava no roadmap):** (1) **Compressão no navegador antes do upload** — ao gerar o PDF, as fotos (NF, CT-e e as múltiplas) são redimensionadas e recomprimidas via canvas, então sobem já menores (o servidor nunca segura o arquivo original pesado). Se a compressão falhar, envia como está (não trava o usuário). (2) **Backend mais econômico** — `_normalizar_imagem` com `optimize=True`, fecha o bitmap PIL no `finally`, e a foto original é liberada da memória (`foto["bytes"]=None`) assim que normalizada. Testado com 15-25 fotos.

> **Ajuste v1.13.3 (09/07/2026) — manter a qualidade das fotos (a pedido):** o usuário precisa **dar zoom nas fotos e ler detalhes finos** (nº de série, etiquetas), então pediu para manter a qualidade alta (aceitando reduzir só um pouco para não travar). Os parâmetros de compressão foram elevados de 1600px/q80 para **2400px / qualidade 90** — tanto na compressão do navegador quanto na normalização do backend. Isso preserva a nitidez para zoom, ainda reduzindo a foto original do celular (4000px+). Como fotos em alta resolução pesam mais, foi adicionado um **aviso na tela** quando o usuário seleciona mais de 20 fotos, sugerindo dividir em mais de um relatório para não sobrecarregar a memória. **Se ainda estourar com muitas fotos de alta qualidade:** o próximo passo seria subir o plano do Render (mais RAM) — registrado como possível ação futura.

> **Regra de trabalho (a pedido, 29/06/2026):** todo pedido enviado é **registrado no roadmap e NÃO executado** na hora. Implementação só quando o usuário disser "rodar". **Após cada novo item, informar ao usuário apenas a lista de PENDENTES (não os concluídos).**

### 09/07/2026 — Unificar cadastro de Fornecedores e Empresas + endereço estruturado (a implementar)

150. **⬜ Cadastro único de Fornecedores/Empresas com CNPJ, IE e endereço estruturado (+ CEP automático)** — pedido do usuário (áudio, 09/07/2026). Objetivo: ter **um só lugar** com todos os dados das empresas/fornecedores, para poder puxar automaticamente no Relatório de Carga e nas Etiquetas. Decisões confirmadas:

    **(a) Unificar "Fornecedores" e "Empresas" numa lista única** *(confirmado: viram UM cadastro só)*. Hoje são duas tabelas distintas: `empresas` (só `nome`; usada para vincular o usuário à sua empresa, via `Usuario.empresa_id`) e `fornecedores` (razão social, contato, WhatsApp, tipos, e agora CNPJ/IE/endereço/aprovação). A unificação vira uma tabela só de "Empresas/Fornecedores".
    - **⚠ Implicação técnica a resolver antes de rodar (importante):** `Usuario.empresa_id` aponta para `empresas`. Ao unificar, é preciso decidir como migrar esse vínculo (cada usuário passa a apontar para um registro da tabela unificada). Isso mexe em: cadastro/edição de usuário, seed inicial, e a exibição "empresa do usuário". Migração precisa preservar os vínculos existentes (não pode deslogar/quebrar usuários). **Plano seguro:** manter a tabela `fornecedores` como base da unificação (já tem mais campos), migrar os registros de `empresas` para dentro dela marcando um tipo/flag, e reapontar `Usuario.empresa_id` para os novos IDs — tudo via migração automática idempotente, sem apagar dados.
    - **Possível campo "tipo de papel"** no cadastro unificado (ex.: marcar se aquela empresa é fornecedora, se é uma empresa interna/SPE, ou ambos), para as listas certas aparecerem em cada tela (cotação x vínculo de usuário). A definir no detalhamento.

    **(b) Campos novos no cadastro unificado** (além dos que já existem): CNPJ (com máscara e validação de dígito verificador, como no relatório), Inscrição Estadual (máscara), e **endereço estruturado**.

    **(c) Endereço dividido em campos separados** *(confirmado: em TODOS os lugares)* — `CEP`, `logradouro`, `número`, `bairro`, `complemento`, `cidade`, `estado`. Aplicar no **cadastro unificado**, no **Relatório de Carga** (Remetente/Destinatário/Transportadora) e na **Geração de Etiquetas** (remetente/destinatário).
    - Hoje o endereço é um campo único de texto (`endereco`). Vira 7 campos. A migração mantém o texto antigo (joga no `logradouro` ou num campo de observação) para não perder o que já existe.

    **(d) CEP com autopreenchimento** *(confirmado: sim, via ViaCEP)* — ao digitar o CEP, consultar a API pública gratuita **ViaCEP** (`https://viacep.com.br/ws/<cep>/json/`) e preencher logradouro, bairro, cidade e estado automaticamente; o usuário completa número e complemento. Funciona quando o computador tem internet (a chamada é feita pelo navegador do usuário via JS). Se o CEP não for encontrado ou estiver offline, os campos ficam editáveis manualmente (fallback).

    **(e) Cadastros antigos ficam sem os dados novos** *(confirmado)* — os muitos fornecedores já cadastrados não têm CNPJ, telefone nem endereço. Tudo bem: os campos novos entram **vazios/opcionais**, sem quebrar nada e sem obrigar preenchimento retroativo. Ficam disponíveis para preencher quando o usuário quiser/precisar.

    **Pendências a fechar antes de rodar:** (1) confirmar o "tipo de papel" do cadastro unificado (fornecedor / empresa interna / ambos) e como cada tela filtra; (2) confirmar se o CNPJ passa a ser obrigatório no cadastro novo ou continua opcional (por causa dos antigos sem CNPJ); (3) validar o plano de migração de `Usuario.empresa_id` para não quebrar logins. **É uma mudança estrutural grande — recomendo rodar isoladamente, sem misturar com outros itens na mesma leva, para testar bem a migração.**

    **Decisões confirmadas em 09/07/2026 (fecham as pendências acima):**
    - **(1) Papel:** cada cadastro pode ser marcado como **Fornecedor** e/ou **Empresa interna** (dois checkboxes independentes — pode ser um, o outro, ou os dois). A cotação lista só os marcados como Fornecedor; o vínculo de usuário usa os marcados como Empresa interna.
    - **(2) CNPJ obrigatório** nos cadastros — **inclusive para os antigos**. Como os antigos não têm CNPJ, eles **não são bloqueados retroativamente**, mas o sistema gera uma **notificação no sininho** pedindo para completar/atualizar os cadastros antigos (um aviso por cadastro incompleto, ou um aviso agregado — a definir no detalhamento). Novos cadastros exigem CNPJ válido na hora de salvar.
    - **(3) Migração aditiva (sem risco de quebrar login):** em vez de apagar a tabela `empresas` e renumerar (o que quebraria `Usuario.empresa_id`), a unificação será **aditiva** — preserva os IDs existentes e os vínculos atuais intactos; a migração roda no boot e, em caso de qualquer falha, faz rollback sem aplicar nada (deixa como estava). O resultado visível é uma lista única de Fornecedores/Empresas, mas por baixo nenhum vínculo existente é renumerado.
    - **(4) Busca sem sinais gráficos (acentos) — vale para TODO o sistema:** todas as buscas/pesquisas passam a **ignorar acentuação e sinais gráficos** — ex.: digitar "veiculos" encontra "Veículos", "acucar" encontra "Açúcar". Aplicar em todos os campos de busca (fornecedores, tipos, solicitações, notinhas, etc.), normalizando tanto o termo digitado quanto o conteúdo comparado (remoção de diacríticos + case-insensitive). *Isto é um requisito transversal, não só do cadastro unificado.*

    **PROGRESSO DA EXECUÇÃO (09/07/2026) — item 150 em andamento, rodando em blocos:**
    - ✅ **Bloco 1 — Fundação (feito e testado):** `Fornecedor` ganhou flags `is_fornecedor`/`is_empresa_interna`, endereço estruturado (cep, logradouro, numero, bairro, complemento, cidade, estado) + helpers `endereco_completo`, `cadastro_incompleto`. `Usuario` ganhou `empresa_fornecedor_id` (novo vínculo) mantendo `empresa_id` antigo. Migração aditiva no boot (`_unificar_empresas_fornecedores`): fornecedores viram is_fornecedor=True; cada Empresa vira um Fornecedor com is_empresa_interna=True; Usuario.empresa_fornecedor_id populado pelo mapa. Testado: empresas intactas, vínculos remapeados, login preservado, idempotente (não duplica).
    - ✅ **Bloco 2 — Cadastro unificado (feito e testado):** tela `admin/fornecedores.html` reescrita como "Fornecedores / Empresas": checkboxes de papel, CNPJ (obrigatório e validado nos novos; recusa salvar sem CNPJ válido), IE, endereço estruturado com **CEP autopreenchendo via ViaCEP** (JS no navegador). Edição idem. Lista mostra papel (badges), CNPJ (ou "sem CNPJ") e cidade; filtro "Sem CNPJ" e busca.
    - ✅ **Bloco 4 — Busca sem acento (feito e testado):** `util.sem_acentos()` e `util.contem_busca()`; aplicado nas buscas de material (admin e solicitante), no Enviar Cotação, e na busca do cadastro unificado. Testado com Veículos/Açúcar/Subestação/São Luís.
    - ✅ **Bloco 5 — Notificação no sininho (feito e testado):** context_processor conta cadastros ativos sem CNPJ (`n_cadastros_incompletos`); o sino soma essa contagem e mostra o item "X cadastro(s) sem CNPJ — completar" apontando para `/admin/fornecedores?incompletos=1`.
    - ✅ **Bloco 3 — Endereço estruturado no Relatório de Carga e nas Etiquetas (feito e testado 09/07/2026):** o formulário do Relatório de Carga (Remetente/Destinatário/Transportadora) agora tem os 7 campos de endereço separados (CEP, logradouro, número, bairro, complemento, cidade, UF) via macro `campos_endereco`, com **CEP autopreenchendo via ViaCEP** (`buscaCepCarga`). O autopreenchimento por CNPJ (quando o cadastro já existe) preenche os campos estruturados. No backend, `carga_gerar` monta o endereço a partir dos campos separados (`_endereco_estruturado`), e o cadastro pendente criado a partir do relatório salva os campos estruturados. Nas Etiquetas: o dropdown de fornecedor puxa o `endereco_completo` do cadastro, e foi adicionado um **CEP com autopreenchimento** que monta o endereço no campo da etiqueta (mantido como campo único porque a etiqueta é pequena — mas alimentado pelo endereço estruturado). Testado: relatório gera com endereço montado, cadastro pendente salva campos estruturados, etiqueta gera OK.
    - ⬜ **Ajustes finos pendentes:** fazer o cadastro/edição de Usuário usar a lista de "empresas internas" da tabela unificada (hoje ainda usa a tabela `empresas` antiga — funciona por causa do vínculo aditivo, mas o ideal é migrar a tela também); avaliar esconder a tela antiga de "Empresas" do menu Cadastros (ou transformá-la em atalho para a lista unificada filtrada por empresa interna).

    - ✅ **Busca por papel no mesmo campo (09/07/2026):** a pedido do usuário, o campo de busca de Fornecedores/Empresas agora reconhece **palavras-chave de papel**: digitar "empresa" (ou "interna") filtra os marcados como Empresa interna; "fornecedor" filtra os marcados como Fornecedor; "sem cnpj"/"incompleto" filtra os cadastros incompletos. Continua buscando por nome, CNPJ e cidade normalmente, sempre ignorando acentos. Tudo num campo só (sem botões extras).
>
> **Nota técnica:** adicionada uma micro-migração automática de schema (roda ao iniciar o app) que cria colunas novas sem apagar dados — assim mudanças no banco não exigem recriar o `app.db`.

### 09/07/2026 — Padronizar cadastro de Transportadoras (a implementar)

151. **⬜ Cadastro de Transportadoras pedir as mesmas informações que Fornecedores/Empresas** — pedido do usuário (09/07/2026). Hoje a tabela `transportadoras` tem só: `nome`, `cnpj`, `endereco` (texto único), `aprovacao`, `ativo`. O objetivo é deixar o cadastro de Transportadora **com os mesmos campos** do cadastro unificado de Fornecedores/Empresas (item 150): razão social / nome fantasia, **CNPJ** (obrigatório e validado nos novos, com máscara), **Inscrição Estadual**, **contato / telefone / e-mail**, e **endereço estruturado** (CEP, logradouro, número, bairro, complemento, cidade, estado) com **CEP autopreenchendo via ViaCEP**. Também herdar os comportamentos: **busca sem acento**, e **notificação no sininho** para transportadoras antigas sem CNPJ.
    - **Decisão a confirmar antes de rodar:** a Transportadora deve virar **também um registro no cadastro unificado** (uma terceira flag, tipo `is_transportadora`, na mesma tabela `fornecedores`), ou continuar numa **tabela separada** (`transportadoras`) só que com os mesmos campos? A primeira opção (unificar de vez) é mais limpa e coerente com o item 150 — um cadastro só para tudo (fornecedor / empresa interna / transportadora), e o Relatório de Carga puxaria os três do mesmo lugar. A segunda é menos mexida, mas mantém a duplicação. **Recomendação:** unificar (adicionar `is_transportadora` ao cadastro único), de forma aditiva como no item 150, sem quebrar os vínculos/relatórios existentes.
    - Migração aditiva: as transportadoras já cadastradas entram no cadastro unificado (ou ganham os campos novos vazios), sem obrigar preenchimento retroativo — igual à regra do item 150 para os antigos.

152. **⬜ Importar Orçamento aceitar foto arrastada direto do WhatsApp** — pedido do usuário (10/07/2026). Na tela "Importar Orçamento", além do PDF, permitir **arrastar uma foto/print do orçamento direto do WhatsApp** (ou de qualquer lugar) e o sistema ler os itens dessa imagem. Hoje a importação lê só PDF (via `pdf_orcamento.py`). 
    - **Implicação técnica a avaliar antes de rodar:** ler itens de uma **foto** (não de um PDF com texto) exige **OCR** (reconhecimento de texto em imagem) — o texto não está "selecionável" como num PDF, é pixel. Isso é bem mais complexo e menos preciso que o parser atual de PDF: fotos de WhatsApp costumam vir tortas, com sombra, baixa resolução, e o OCR erra mais. Opções: (a) usar uma lib de OCR (ex.: Tesseract) no servidor — mas o Render tem pouca memória/CPU e OCR é pesado; (b) usar um serviço externo de OCR/visão (tem custo e depende de internet); (c) aceitar a imagem, rodar OCR e cair no **de-para editável** (o usuário corrige o que o OCR errar antes de importar) — mais realista. **A decidir com o usuário:** qual abordagem, e se o volume/qualidade das fotos justifica o esforço, ou se o caminho é orientar a mandar o PDF quando possível (a maioria dos fornecedores manda PDF). Registrar como item que precisa dessa conversa antes de rodar.
    - Enquanto isso, o **drag-and-drop de PDF** já funciona; este item estende para imagens.

### 10/07/2026 — Nova leva de pedidos (a implementar; registrados, aguardando "rodar")

153. **⬜ ADMIN poder editar TODOS os campos na edição da solicitação (inclusive o nome/material)** — hoje a edição da solicitação restringe alguns campos. O pedido: **somente o ADMIN** consegue editar o **nome do material e todos os demais campos** informados na solicitação (liberação total de edição para admin). Usuários comuns seguem com a edição limitada de hoje. A implementar: na tela de edição da solicitação, se `current_user.is_admin`, destravar todos os campos (material, tipo, unidade, quantidade, etc.).

154. **⬜ Duplicar solicitação já abrir com os campos editáveis (para o solicitante ajustar)** — hoje ao duplicar, a nova solicitação abre "travada"/pronta. O pedido: ao duplicar, abrir a nova solicitação **em modo de edição**, com os campos abertos, para o colaborador (usuário que faz solicitação) ajustar antes de salvar. Vale para os usuários que podem criar solicitação.

155. **⬜ Campo UNIDADE obrigatório e restrito às unidades cadastradas (idem Tipo de Material)** — o campo **Unidade** (de medida/quantidade) deve ser **obrigatório** e só aceitar valores da **lista cadastrada** (dropdown fechado, sem texto livre). O mesmo para o **Tipo de Material**: obrigatório e restrito ao cadastro. Objetivo: padronizar e evitar digitação livre/errada. *(Hoje as unidades vêm de `UNIDADES_MEDIDA` — confirmar se é isso que deve virar a lista fechada, ou se haverá um cadastro editável de unidades.)*

156. **⬜ COLETAS AVULSAS em Operação, puxando para Coletas Próprias, com status** — criar em **Operação** um campo/tela só para **Coletas Avulsas**, onde se informa **o que coletar** e a **cidade**; esses itens aparecem/são puxados no campo de **Coletas Próprias**. Precisa de **status**: **Em preparação**, **A coletar**, **Concluído**. A definir no detalhamento: se "Coleta Avulsa" é uma nova entidade/tabela própria (com descrição, cidade, status, datas) e como exatamente ela se integra à tela de Coletas Próprias que já existe.
    - **DEFINIÇÕES (10/07/2026):** a Coleta Avulsa **não tem orçamento nem compra** — é só uma coleta a fazer, aproveitando uma viagem já programada. Ex.: "pegar 2 rádios em São Luís" enquanto o motorista já vai buscar outra compra lá.
    - **É uma entidade NOVA** (tabela própria `coleta_avulsa`), separada das solicitações. Campos: **Descrição** (o que coletar), **Quantidade**, **Fornecedor OU Endereço** (escolher um dos dois — se informar o fornecedor/cadastro, os dados de contato vêm dele; se não, informa endereço/contato manual), **Frente de Serviço**, **Contato** (só se não informar o fornecedor, pois o cadastro já traz o contato), e **Status** (Em preparação / A coletar / Concluído).
    - **Integração:** as coletas avulsas com status "A coletar" (e talvez "Em preparação") aparecem na tela de **Coletas Próprias**, agrupadas por cidade junto com as coletas que já vêm das solicitações FOB, e entram no texto pronto para o motorista. Ao concluir, saem da lista ativa.
    - **A confirmar antes de rodar:** (1) "Frente de Serviço" é um campo de texto livre ou uma lista cadastrada? (2) A cidade da coleta avulsa usa o mesmo cadastro de cidades das solicitações (`cidade_retirada`)?
    - **DEFINIÇÕES FINAIS (10/07/2026):** "Frente de Serviço" = **texto livre**. Cidade = usar o mesmo cadastro de cidades das solicitações (dropdown de cidades já existente), para agrupar junto na tela de Coletas Próprias.

157. **⬜ +1 modelo de orçamento: Mundial Tintas** — incluir o orçamento da **Mundial Tintas Ltda** (CNPJ `13.421.123/0001-48`, orçamento nº 30852) como base para a importação (item 114). Layout: cabeçalho do fornecedor + bloco do cliente; tabela `N. | Codigo | Descrição | NCM | UN | Quantidade | Pr Venda | Valor Total | Prazo | %ICM | %RED | %IPI`. Formato BR (vírgula decimal). Ex.: `1 320890 INTERSEAL 670HS ALUMINIO 3208.90.10 GL 10,000 366,190 3.661,90 0,00 ...`. Detalhe: a coluna de preço unitário ("Pr Venda") tem **3 casas decimais** (`366,190`). Totais: Total Produtos / Total Orçamento. Agora são **7 modelos** conhecidos (FBM, Cofermeta, Ferramentech, Lojão, Iluminar, Dimensional, Mundial Tintas). PDF fica com o usuário; reenviar ao rodar.

158. **⬜ Cadastro rápido "on the fly" de FORNECEDOR/FABRICANTE e TIPO DE ATIVIDADE (com aprovação)** — em **todos os lugares onde se informa o fornecedor/fabricante**, se ele não estiver cadastrado, permitir **abrir os campos e cadastrar na hora** (todos os campos do cadastro), e esse novo cadastro **sobe para aprovação** (fica pendente até um admin aprovar). O **mesmo comportamento para TIPOS de ATIVIDADE**.
    - **ESCLARECIMENTO (10/07/2026):** o usuário achou que "FABRICANTE" podia ter sido confusão com **Fornecedor** — provavelmente é o mesmo conceito (o cadastro unificado de Fornecedores/Empresas do item 150). Então o núcleo do pedido é: **poder cadastrar um fornecedor novo na hora**, direto de qualquer tela que peça fornecedor (ex.: nova solicitação, relatório de carga, coleta avulsa), sem sair da tela, e esse cadastro entra como **pendente de aprovação** (já existe o fluxo de cadastro pendente no item 145/150 — reaproveitar).
    - **AINDA A CONFIRMAR antes de rodar:** o que é **"Tipo de Atividade"**? Não existe esse conceito no sistema hoje (há "Tipo de Material"). Pode ser: (a) o mesmo que Tipo de Material (outra confusão de termo), (b) um cadastro novo (ex.: categorias de serviço/atividade), ou (c) outra coisa. Precisa o usuário esclarecer o que é e onde apareceria. **Enquanto não esclarecer, este item fica parcialmente bloqueado** — a parte de "cadastrar fornecedor na hora com aprovação" está clara e pode rodar; a de "Tipo de Atividade" aguarda definição.
    - **DEFINIÇÃO FINAL (10/07/2026):** "Tipo de Atividade" foi **confusão com Tipo de Material** — não é um cadastro novo. Portanto o item 158 fica reduzido a: **cadastrar Fornecedor na hora (on the fly) com aprovação**, a partir das telas que pedem fornecedor. Nada a fazer sobre "Tipo de Atividade".
