# Sistema de Solicitação de Materiais

App em Flask + PostgreSQL para terceiros solicitarem materiais e o administrador
gerenciar, disparar pedidos de compra por e-mail e comparar orçamentos.

Já está **testado e funcionando** (login, solicitações, status, pedido de compra em
PDF, orçamentos e comparativo). Siga os passos abaixo.

---

## A) Rodar no seu computador (teste rápido)

Pré-requisito: ter o **Python 3.11+** instalado.

1. Abra o terminal nesta pasta.
2. Crie o ambiente e instale as dependências:
   ```
   python -m venv .venv
   .venv\Scripts\activate          (Windows)   |   source .venv/bin/activate  (Mac/Linux)
   pip install -r requirements.txt
   ```
3. Crie o administrador inicial (e dados de exemplo):
   ```
   set SEED_DEMO=1                    (Windows)   |   export SEED_DEMO=1   (Mac/Linux)
   python seed.py
   ```
   Isso cria o login admin `admin@example.com` / senha `admin123`
   (troque definindo `SEED_ADMIN_EMAIL` e `SEED_ADMIN_SENHA` antes de rodar).
4. Suba o app:
   ```
   python wsgi.py
   ```
5. Abra o navegador em **http://localhost:5000** e faça login.

> Sem configurar e-mail, o sistema funciona normalmente e apenas **registra os e-mails no terminal**
> (em vez de enviar). É ótimo para testar antes de plugar o SMTP.

---

## B) Colocar no ar de graça (Render + Neon)

A estratégia: **app no Render** (grátis) + **banco no Neon** (grátis e que não expira).
Custo na fase de teste: **R$ 0**.

### 1. Banco de dados — Neon
1. Crie conta em https://neon.tech (grátis, sem cartão).
2. Crie um projeto Postgres.
3. Copie a **connection string** (algo como `postgresql://usuario:senha@host/db?sslmode=require`).
   Guarde — será o `DATABASE_URL`.

### 2. E-mail — Brevo (opcional, mas necessário para enviar de verdade)
1. Crie conta em https://www.brevo.com (300 e-mails/dia grátis).
2. Em **SMTP & API**, pegue: host (`smtp-relay.brevo.com`), porta `587`, login e senha SMTP.
   Esses viram `MAIL_HOST`, `MAIL_PORT`, `MAIL_USER`, `MAIL_PASS`.

### 3. Imagens — Cloudinary (opcional)
1. Crie conta em https://cloudinary.com (grátis).
2. Copie a variável **CLOUDINARY_URL** do painel.
   Sem isso, as imagens são salvas no servidor (no Render grátis elas se perdem ao reiniciar —
   por isso o Cloudinary é recomendado assim que possível).

### 4. Subir o código — Render
1. Suba esta pasta para um repositório no **GitHub** (privado serve).
2. Em https://render.com crie **New > Web Service** apontando para o repositório.
3. O Render lê o arquivo `render.yaml`. Em **Environment**, preencha as variáveis:
   - `DATABASE_URL` = string do Neon
   - `BASE_URL` = a URL que o Render der ao app (ex.: `https://seu-app.onrender.com`)
   - `MAIL_HOST`, `MAIL_PORT`, `MAIL_USER`, `MAIL_PASS`, `MAIL_FROM`, `ADMIN_EMAIL`
   - `CLOUDINARY_URL` (se usar)
   - `SECRET_KEY` é gerada automaticamente.
4. Faça o deploy. Quando terminar, crie o admin uma única vez no **Shell** do Render:
   ```
   SEED_ADMIN_EMAIL=voce@empresa.com SEED_ADMIN_SENHA=suaSenha python seed.py
   ```
5. Acesse a URL do Render e faça login como admin.

> **Atenção (plano grátis):** o app "dorme" após 15 min sem uso; o primeiro acesso depois disso
> demora ~30–60s. Some quando migrar para o **Render Starter (US$7/mês)**, sem trocar nada do banco.

---

## C) Primeiros passos dentro do sistema (como admin)

1. **Tipos** → cadastre os tipos de material (ex.: Elétrico, Hidráulico).
2. **Fornecedores** → cadastre cada fornecedor e marque os tipos que ele atende.
3. **Usuários** → crie os solicitantes (e outros admins, se quiser).
4. Pronto: os solicitantes já podem abrir pedidos; você acompanha no **Painel**.

---

## D) Como funciona o dia a dia (fluxo completo)

**Papéis:** Solicitante, Administrador (compras) e **Almoxarifado**. O administrador cria todos os usuários em **Cadastros → Usuários**.

**1. Solicitante abre o pedido** ("Nova solicitação": material, quantidade, fabricante, link similar, imagens). Nasce em **"Aguardando aprovação"**.

**2. Admin aprova** na tela **Aprovações** (aprovar ou abrir para editar). Vai para **"Aguardando envio p/ cotação"**.

**3. Admin envia a cotação** em **"Enviar cotação"**: agrupa por fornecedor e envia **um e-mail por fornecedor** (PDF). Há também botão **WhatsApp** por fornecedor (abre a conversa com o texto pronto; o texto avisa que também foi por e-mail). O prazo de **5 dias úteis** é citado automaticamente. Vai para **"Aguardando recebimento da cotação"**.

**4. Fornecedor responde** (e-mail volta para você pelo Reply-To, ou responde no WhatsApp).

**5. Admin lança os orçamentos** — manual ("Lançar orçamento") ou **Importar PDF** (de-para). Vai para **"Aguardando definição de fornecedor"**.

**6. Admin define o fornecedor + frete + Ordem de Compra** na tela da solicitação: escolhe o orçamento vencedor, o **frete (CIF/FOB)** — se FOB, Transportadora ou Colaborador do parque (cidade) — e o **prazo de recebimento (obrigatório)**. O sistema envia a OC ao fornecedor (o frete é interno, não vai no e-mail). Vai para **"Aguardando chegada"**.

**7. Almoxarifado confirma a chegada** na tela **Acompanhamento**. Vai para **"Concluído"**.

**Cadastros (menu único):** Usuários, Tipos de material, Fornecedores (Razão Social, Nome Fantasia, E-mail, Contato, WhatsApp), Cidades e Transportadoras. Os **32 tipos** padrão já entram sozinhos no primeiro start. O telefone do fornecedor é normalizado automaticamente para WhatsApp (entende DDD e o dígito 9).

**Outros recursos:** filtros no painel (admin e solicitante), alterar quantidade com auditoria, editar/desativar fornecedor.

> **Importante:** ao atualizar a aplicação, rode `python -m pip install -r requirements.txt` de novo —
> entrou a biblioteca **pdfplumber** (leitura dos PDFs de orçamento). O banco se atualiza sozinho ao
> iniciar (micro-migração adiciona colunas novas sem apagar dados).

---

## E) Novidades da v1.3 (papéis, senhas, cadastros, extras)

**Papéis:** Solicitante, **Almoxarifado** (solicita como o solicitante e confirma a chegada de material em "Confirmar chegadas"), **Somente visualização** (vê tudo, sem criar/editar) e Administrador.

**Senhas:** todo usuário troca a senha no 1º acesso. O admin pode **resetar a senha** de um usuário em Cadastros → Usuários → Editar (campo "Resetar senha").

**Definir você como admin único:** rode uma vez `python definir_admin.py`. Ele torna **antonio.carvalho@srna.co** o único administrador (senha provisória `Trocar@123`, trocada no 1º acesso) e rebaixa os demais admins para solicitante.

**Cadastros (menu único):** Usuários, **Empresas** (vinculadas ao usuário), Tipos, Fornecedores, Cidades (com **UF**), Transportadoras e **Sugestões**. Todos com editar/ativar-desativar e **cadastro rápido "+"** direto nos formulários. Na lista de tipos do fornecedor há **busca**.

**Solicitação:** novo campo **local / frente de serviço**; o PDF de cotação leva **fotos e link**; no WhatsApp vai o **link do produto**.

**Painel:** abre filtrado (tudo menos Concluído/Cancelada) e permite filtrar **vários status** e **vários solicitantes**. Dá para **exportar em PDF** as solicitações selecionadas (marque as caixas e clique em "Exportar").

**Ajuda:** menu **FAQ**, link discreto **Novidades & atualizações** no rodapé, e **Sugerir** (caixa de melhorias que chega ao admin).

---

## Estrutura do projeto

```
config.py            Configurações (lê variáveis de ambiente)
wsgi.py              Ponto de entrada (Render usa: gunicorn wsgi:app)
seed.py              Cria o admin inicial e dados de exemplo
requirements.txt     Dependências
render.yaml          Configuração de deploy no Render
app/
  __init__.py        Monta o app
  models.py          Tabelas (usuários, solicitações, fornecedores, orçamentos...)
  auth.py            Login/logout
  solicitante.py     Telas do solicitante (com filtros)
  admin.py           Telas do administrador (filtros, aprovação, envio em lote, edição de fornecedor)
  emails.py          Envio de e-mail (SMTP) com Reply-To para o admin
  pdf.py             Geração do PDF do pedido (individual e em lote)
  pdf_orcamento.py   Leitor de PDF de orçamento do fornecedor (de-para)
  storage.py         Upload de imagens (local ou Cloudinary)
  templates/         Páginas HTML
```
