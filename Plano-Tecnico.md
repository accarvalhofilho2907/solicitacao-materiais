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

102. **❌ Nº de Ordem de Compra sequencial — DESCARTADO** (30/06/2026).
103. **❌ Exportar Excel de solicitações/notinhas — DESCARTADO** (30/06/2026).
104. **❌ Relatório de gastos por período/fornecedor/atividade — DESCARTADO** (30/06/2026).
105. **❌ Anexar orçamento do fornecedor como comprovante — DESCARTADO** (30/06/2026).

> **Regra de trabalho (a pedido, 29/06/2026):** todo pedido enviado é **registrado no roadmap e NÃO executado** na hora. Implementação só quando o usuário disser "rodar". **Após cada novo item, informar ao usuário apenas a lista de PENDENTES (não os concluídos).**
>
> **Nota técnica:** adicionada uma micro-migração automática de schema (roda ao iniciar o app) que cria colunas novas sem apagar dados — assim mudanças no banco não exigem recriar o `app.db`.
