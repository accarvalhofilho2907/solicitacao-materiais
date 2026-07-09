# RESUMO DO PROJETO — Sistema de Solicitação de Materiais (para continuar em outro chat)

> Este documento é um **handoff completo**. Se você subir o projeto zipado em um novo chat, leia este arquivo primeiro: ele explica o que é, como roda, o que já foi feito e o que falta.

---

## 1. O que é
Plataforma web onde **colaboradores (Solicitantes)** pedem materiais e o **Administrador** gerencia, cota com fornecedores e fecha a compra. Fornecedores **não acessam** o sistema — só recebem o contato (e-mail/WhatsApp). Empresa: Serena Energia / Cluster Delta MA (comprador: Antonio Carlos Carvalho).

## 2. Tecnologia
- **Backend:** Python + **Flask** (padrão _app factory_), Flask-SQLAlchemy, Flask-Login, Flask-WTF (CSRF), Flask-Migrate.
- **Banco:** **PostgreSQL** em produção (**Neon**, grátis, persistente); **SQLite** local para dev.
- **Servidor:** **Gunicorn** (`gunicorn wsgi:app`).
- **Front:** Bootstrap 5 + fonte Poppins, tema Coral #FF5246 / Grafite #4B4B4B / Verde #32CAA0 (sem exibir o nome da empresa).
- **E-mail:** SMTP **não configurado** — os envios são "simulados" (log). Método oficial = **mailto/Outlook manual** + **WhatsApp (wa.me)** + **"copiar texto"**.
- **Imagens:** upload **desativado** (item 61) para poupar armazenamento no plano grátis.

## 3. REGRA DE TRABALHO (importante!)
Todo pedido do usuário é **registrado no `Plano-Tecnico.md` (changelog, item numerado ⬜) e NÃO executado na hora**. Só implementar quando o usuário disser **"rodar"**. Após cada novo item, mostrar ao usuário **apenas a lista de PENDENTES**. Está na memória do projeto também.

## 4. Papéis e acesso
- **solicitante:** cria solicitação, vê o painel (todos veem tudo), comenta.
- **almoxarifado:** = solicitante + **confirma chegada** (inclusive parcial).
- **visualizador:** só leitura.
- **admin:** faz **tudo** (inclui aprovar, cotar, definir fornecedor, confirmar chegada, cadastros).
- Sem autocadastro: admin cria os usuários (e-mail + senha). Troca de senha obrigatória no 1º acesso.
- Admin único definido em `definir_admin.py` (antonio.carvalho@srna.co, senha provisória `Trocar@123`).

## 5. Fluxo de status (solicitação)
`AGUARDANDO_APROVACAO` → `AGUARDANDO_ENVIO_COTACAO` → `AGUARDANDO_RECEBIMENTO_COTACAO` → `AGUARDANDO_DEFINICAO_FORNECEDOR` → `AGUARDANDO_CHEGADA` → `CONCLUIDO` (+ `CANCELADA`). Labels/lista em `app/models.py` (STATUS, STATUS_LABEL, STATUS_PADRAO).

## 6. Mapa de arquivos
- `wsgi.py` — entrada do Gunicorn (`app`).
- `config.py` — lê variáveis de ambiente (DATABASE_URL, BASE_URL, SECRET_KEY, ADMIN_EMAIL, MAIL_*, CLOUDINARY_URL).
- `app/__init__.py` — `create_app`, `_light_migrate` (migração automática no boot: cria colunas/tabelas novas, define `ativo=TRUE`, converte cadastros p/ MAIÚSCULAS), `_seed_tipos` (32 tipos padrão), rota pública `/r/<id>` (link curto → redireciona pro link do produto), context_processor (badges/contadores).
- `app/models.py` — modelos: Usuario, Empresa, TipoMaterial, Atividade, Cidade, Transportadora, Fornecedor, **Solicitacao**, Imagem, Comentario, PedidoCompra, Orcamento, Notinha, LogSolicitacao, Sugestao + tabelas N×N (`fornecedor_tipo`, `solicitacao_fornecedor_excluido`).
- `app/auth.py` — login, troca de senha no 1º acesso.
- `app/solicitante.py` — painel (livre p/ todos, filtros avançados), nova solicitação (sem foto), detalhe, exportar PDF.
- `app/admin.py` — **o maior**: painel/filtros, cartões, aprovações (lote + PDF de fichas), cotação (WhatsApp/E-mail/Texto por fornecedor, marcar enviada, reenviar), definir fornecedor + OC + frete, orçamentos (lançar/cancelar), comparativo, remover/devolver fornecedor da cotação, duplicar, pendências, histórico de preços, cadastros (CRUD), cadastro inline (JSON).
- `app/almox.py` — confirmar chegada (parcial e total).
- `app/notinhas.py` — lançamento de notas (data, fornecedor, atividade, valor; competência automática da data; filtros; atividade inline; export PDF).
- `app/geral.py` — FAQ, novidades, sugerir melhoria.
- `app/pdf.py`, `app/pdf_orcamento.py` — geração de PDFs e leitura de orçamento em PDF (texto; **sem OCR**).
- `app/util.py` — telefone BR (E.164) e dias úteis.
- `app/emails.py`, `app/storage.py`, `app/extensions.py`, `app/seed_data.py` — auxiliares.
- `app/templates/` — base.html (menu, tema, JS de filtros/cópia) + telas admin/solicitante/almox/notinhas/geral.
- `Plano-Tecnico.md` — **roadmap/changelog** (fonte da verdade do que foi feito; itens 1–108).
- `referencia_cotacao.md` — modelo do e-mail de cotação + **tabela fixa das 15 SPEs Delta (SPE, Endereço, CNPJ, I.E.)** + assinatura. Os mesmos dados estão em `SPES_COTACAO` no `app/admin.py`.
- `DEPLOY.md`, `iniciar.bat` — guia de deploy e atalho local.

## 7. Modelo do e-mail de cotação (itens 73/75/76/77/91)
- **Assunto:** `SRNA | <Nome Fantasia>: Cotação de material #COT-AAAA-000` (sequencial por ano).
- **Corpo:** saudação + condições (i. Frete CIF; ii. Pagamento 30 DDL; iii. Uso e Consumo) + **tabela de produtos** (`#nº#`, produto, fabricante ou "N/D", qtd, link curto) + prazo 5 dias úteis + assinatura.
- **Tabela de SPEs/CNPJs:** só no **e-mail** (não vai no WhatsApp/Texto pronto).
- Colunas alinhadas em texto puro (mailto/WhatsApp).

## 8. Como rodar LOCAL (Windows)
1. `python -m venv .venv` → `.\.venv\Scripts\Activate.ps1` (se bloquear: `Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process`).
2. `python -m pip install -r requirements.txt`.
3. `python wsgi.py` (ou `iniciar.bat`). Abre em `http://localhost:5000` com SQLite (`app.db`).
   - Local, o link curto sai como `localhost` (normal — só abre no seu PC).

## 9. Deploy (produção) — fluxo GitHub Desktop → Render
1. Editar na pasta do projeto e **copiar `app/` + arquivos alterados** para a pasta do **repositório clonado** (GitHub Desktop).
2. **Commit** + **Push** para `main` → **Render** publica sozinho.
3. **Neon:** banco PostgreSQL (string vai na env `DATABASE_URL`, terminando em `?sslmode=require`).
4. **Render — variáveis de ambiente:** `DATABASE_URL`, `SECRET_KEY`, `BASE_URL=https://<seu-app>.onrender.com`, `ADMIN_EMAIL`. (MAIL_* e CLOUDINARY_URL opcionais.)
5. **Start Command:** `gunicorn wsgi:app`. Python fixado em `3.12.7` (`.python-version`).
6. A **migração roda sozinha no boot** (cria colunas/tabelas novas e maiusculiza cadastros antigos) — **não apaga dados**.
- Observações do plano grátis: o Render **"dorme"** após 15 min ocioso (primeiro acesso demora ~30s); 750h/mês; sem disco persistente (por isso banco no Neon).

## 10. O que já foi entregue (resumo por versão)
- **v1.0–1.3:** MVP, papéis, status, fornecedores (razão social/fantasia/contato/WhatsApp/tipos), frete CIF/FOB, cadastros, brandbook, aprovações, cotação, OC, PDF, FAQ/novidades/sugestões, senha 1º acesso.
- **v1.4–1.5:** painel livre, menu Compras, comparativo (produto/fornecedor), filtros dropdown, notinhas + atividades, leitor de orçamento PDF, admin também solicita, ativar todos tipos.
- **v1.6:** menu clean, badges, botões WhatsApp/E-mail/Texto por fornecedor, link curto `/r/<id>`, editar e-mail do usuário, aprovar em lote + PDF de fichas, editar quantidade + logs/histórico, notinhas melhoradas, fotos desativadas.
- **v1.7:** link curto automático (host), novo modelo de e-mail (SPEs, sequencial, N/D, assinatura), botão "cotação enviada" por fornecedor, chegada parcial, admin com tudo, **cadastros em MAIÚSCULAS** (+ backfill), cadastro inline de tipo (admin) e atividade (notinhas), editar tipo/local/fabricante, competência automática, filtro por valor, prazo hoje, cidade FOB clara, cabeçalho com papel, busca nos dropdowns.
- **v1.8:** cancelar orçamento de fornecedor, WhatsApp/Texto sem CNPJs, filtro preservado ao abrir/voltar, **prazo de cotação vencido** (badge + filtro).
- **v1.9:** **remover fornecedor da cotação** ("não tem o item") + devolver, **duplicar** solicitação, **reenviar cotação** (renova prazo), **último preço** ao lançar orçamento, **histórico de preços** por fornecedor, **cartões** no painel, painel **"O que precisa de mim hoje"**, **chegada atrasada** (badge/filtro), filtro de **atividade múltiplo** nas notinhas, filtros enxutos, home de cadastros repaginada.
- **v1.10 (08/07/2026):** **tema escuro** em todo o sistema + nome trocado para **ALMOXARIFADO**; menu reestruturado em **Início / Operação / Relatórios e Impressões** (com sino de notificações); **Geração de Etiquetas** (Envio de Material com as 15 Deltas + Identificação de Item com moldura/faixa Serena), ambas em PDF A4 com 2/4/6/8 por folha; **Relatório de Recebimento** e **Relatório de Envio** de materiais em PDF (modelo "Relatório de Carga Almoxarifado Delta MA", não salva histórico); **backup .sql** para baixar; removido o botão extra de cancelar orçamento (ficou só "remover fornecedor sem o item").
- **v1.11 (08/07/2026):** leva grande de 21 pedidos — **alternar tema Claro/Escuro por usuário**; telefone do fornecedor visível na cotação; dropdowns pesquisáveis de Tipo de Material e nova **Unidade de Medida** (aparece junto ao produto na cotação); vincular fornecedores a um Tipo pelo próprio cadastro do tipo; **pop-up "Cotação enviada"** (marca todos, pergunta se quer mais algum antes de fechar o processo); **pop-up de escolha de SPE** ao enviar cotação por e-mail; campo antigo "Solicitar cotação" retirado do item (envio agora centralizado em Compras → Enviar cotação); tela de **Enviar cotação reformada** (expandir todos os status, busca por empresa/tipo/produto, excluir empresas da tela); **desativar fornecedores**; nova tela de **Coletas próprias** (por cidade, com "copiar texto" para o motorista); **Geração de Etiquetas**: fonte bem maior, **pré-visualização do grid A4**, opção "Outro" no remetente, PDF para anexar ao e-mail, renomeado para **"Etiqueta de caixas/embalagens"**, campo de Nota Fiscal, selos de Frágil/Explosivo/Empilhável; **Relatório de Recebimento/Envio unificado** numa tela só (Status decide o modo), Responsável vira dropdown de Usuários, fotos dinâmicas (abrem ao preencher NF/CT-e), múltiplas fotos da galeria, marcação "Avariado?" com observação obrigatória e aviso no cabeçalho do PDF; **data de chegada editável**; **Backup restrito a Admin**, movido para o menu do usuário; **Notinhas com pop-up** de "Adicionar nova notinha", separado dos filtros. **Drag-and-drop** no Importar Orçamento (a leitura do PDF em si segue pendente — ver item 114). **Corrigido também um erro crítico de produção** (SSL connection closed, Neon/Render) com `pool_pre_ping`.
- **v1.12 (09/07/2026):** leva 135–149 — **Relatório de Carga redesenhado** com paleta Serena e layout profissional, agora em **7 seções** (Cabeçalho, Remetente, Destinatário, Transportadora, Dados da Carga, Fotos, Observações), com **fotos embutidas de verdade no PDF (uma por página)**; **fluxo de CNPJ**: campo CNPJ primeiro, validação de dígito verificador (pop-up se inválido), autopreenchimento se já cadastrado e **cadastro automático pendente** de Fornecedor/Transportadora se novo, com **tela de aprovação** para o Admin em Cadastros; **nome de arquivo automático** do relatório (Envio/Recebimento + empresa + NF + data); **Status nasce vazio** e Responsável pré-preenchido. **Etiquetas**: fonte adaptativa ao tamanho do nome, dados centralizados, **símbolos nos selos** (frágil/explosivo/empilhar), grids **01/02/04/06/08/10/12/14/16** por folha, **orientação retrato/paisagem**, **contato do remetente editável**, preview do grid corrigido, botão combinado **Gerar PDF e abrir e-mail**. **Menu lateral (sidebar) no celular** com botão hambúrguer (desktop segue horizontal). **Coletas próprias** agrupadas por cidade → fornecedor, com contato do fornecedor. **Checkbox por item** ao enviar cotação. **Cards de Cadastros** sem as bordas amarelas (visual Serena). Reaplicado o **fix do pop-up de e-mail** (abre o mailto do usuário, não o envio SMTP simulado).
- **v1.12.1 (09/07/2026, correções):** 3 bugs corrigidos — (1) pop-up de CNPJ inválido que reabria em loop e não deixava corrigir; (2) **Internal Server Error ao gerar relatório com fotos** (faltava o **Pillow** no requirements — agora incluído — e as fotos passaram a ser normalizadas/rotação EXIF corrigida antes de entrar no PDF, com blindagem contra foto inválida); (3) NF e CT-e voltaram a **pedir a foto** ao ter o número preenchido, e essas fotos entram no PDF com legenda própria.
- **v1.12.3 (09/07/2026):** corrigida a **causa raiz** do erro 500 ao gerar relatório com fotos (achada pelo log do Render): a coluna `email` da tabela de fornecedores era `NOT NULL` no banco de produção, e o cadastro pendente vindo do relatório não tem e-mail. A migração automática agora remove essa trava (`ALTER TABLE ... DROP NOT NULL`). Testado com o caso real que quebrou.
- **v1.12.4 (09/07/2026):** cabeçalho do Relatório de Carga redesenhado (o usuário achou o antigo feio). Escolhida a opção "bloco grafite com status integrado": faixa grafite com barrinhas coral+verde na lateral, marca "S" em quadrado coral (não há logo em arquivo), título, e bloco de status colorido encaixado à direita (verde=recebimento, coral=envio).
- **v1.12.5 (09/07/2026):** refinamento do cabeçalho — a faixa cinza (grafite) passou a ocupar **toda a largura do topo**, com o status virando uma **tag colorida dentro da própria faixa**; **removida a barrinha verde estreita** da esquerda (ficou só a coral fina).

## 11. PENDENTES (não rodados)
- **Item 114 — Importar Orçamento (leitura do PDF):** o drag-and-drop já foi entregue, mas a **extração dos itens do PDF** ainda erra para layouts diferentes do primeiro modelo. Há **4 modelos reais anexados** (FBM, Cofermeta, Ferramentech e Lojão/Tucano) documentados no `Plano-Tecnico.md` — **cada um com layout, ordem de colunas e até separador decimal diferentes**. Estratégia recomendada: detectar o fornecedor pelo CNPJ no topo do PDF e aplicar um padrão de leitura específico para cada um. Falta calibrar o parser para os 4 (e decidir o que fazer com campos extras como NCM/CST/%ICMS). É o único item funcional ainda pendente além do 150. Os PDFs originais ficam com o usuário; ele reenvia quando formos rodar.
- **Item 130 — Layout geral (parcial):** aplicado nas telas tocadas nas últimas levas (Notinhas, Coletas próprias). Se houver telas antigas específicas incomodando, é só apontar quais.
- **Item 150 — Cadastro único de Fornecedores/Empresas + endereço estruturado — EM EXECUÇÃO (09/07/2026):** blocos 1–5 concluídos e testados — unificação aditiva no banco (sem quebrar login), cadastro unificado com papéis (Fornecedor/Empresa interna) + CNPJ obrigatório + endereço estruturado com CEP automático (ViaCEP), busca sem acento no sistema todo, notificação no sininho para cadastros sem CNPJ, e endereço estruturado no Relatório de Carga e nas Etiquetas. Falta só um ajuste fino: a tela de cadastro de Usuário ainda usa a tabela `empresas` antiga (funciona pelo vínculo aditivo). **Mexe no banco — fazer backup no Render antes de subir.**

Detalhe completo de cada item, com todas as regras combinadas, está no `Plano-Tecnico.md`.

## 12. Descartados
Importação de fornecedores por planilha (70), OCR de orçamento por imagem (85), Nº de OC sequencial (102), exportar Excel de solicitações/notinhas (103), relatório de gastos (104), anexar orçamento como comprovante (105).

## 13. Próximo grande passo combinado
O usuário está montando **em HTML** a base de um **módulo de Almoxarifado (estoque)** em outro chat. Quando tiver o HTML, o plano é **encaixar como módulo dentro deste mesmo app** (mesmo login, banco e layout) — recomendado em vez de app separado. Chave comum de ligação: o **Nº da solicitação**.

## 14. Convenções / cuidados
- Cadastros salvos sempre em **MAIÚSCULAS** (exceto e-mail/senha).
- Nunca expor caminhos internos; instrução da organização: **não incluir PII de clientes**. Os CNPJs das SPEs são dados do **próprio comprador** (ok usar na cotação).
- Senha do banco (Neon) é secreta — se vazar, resetar em Neon → Settings.
- Testes rápidos: há scripts `test_v1x.py` de referência (rodados em sandbox com SQLite temporário e e-mails mockados).
