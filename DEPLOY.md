# Como colocar o sistema online (passo a passo)

Objetivo: publicar o sistema 100% grátis para teste, com link acessível de qualquer
computador ou celular. Arquitetura: **app no Render** + **banco no Neon** + **imagens no
Cloudinary** + **e-mail pelo seu provedor (SMTP)**.

Tempo estimado: ~40 minutos na primeira vez. Você não precisa saber programar — é tudo por telas.

---

## Resumo do que vamos usar (tudo grátis para começar)

| Serviço | Para quê | Plano grátis |
|---|---|---|
| **GitHub** | Guardar o código (o Render lê de lá) | Grátis |
| **Neon** | Banco de dados (PostgreSQL) | Grátis, não expira |
| **Render** | Rodar o site | Grátis (dorme após 15 min ociosa) |
| **Cloudinary** | Guardar as imagens | Grátis (25 GB) |
| **Seu e-mail (SMTP)** | Enviar cotações/avisos | Conforme seu provedor |

---

## Passo 1 — Subir o código para o GitHub

1. Crie uma conta em https://github.com (se não tiver).
2. Crie um repositório novo (pode ser **privado**), ex.: `solicitacao-materiais`.
3. Envie os arquivos desta pasta para o repositório. Duas formas:
   - **Fácil (sem terminal):** instale o **GitHub Desktop** (https://desktop.github.com), faça login,
     "Add local repository" apontando para esta pasta, e clique em **Publish**.
   - **Pelo Git:** dentro da pasta, rode `git init`, `git add .`, `git commit -m "primeira versão"`,
     e siga as instruções do GitHub para `git remote add origin ...` e `git push`.

> O arquivo `.gitignore` já evita subir coisas locais (banco de teste, .venv, uploads).

---

## Passo 2 — Criar o banco de dados (Neon)

1. Acesse https://neon.tech e crie conta (grátis, sem cartão).
2. Crie um **projeto** PostgreSQL (região mais próxima, ex.: South America).
3. Copie a **connection string** (algo como
   `postgresql://usuario:senha@ep-xxxx.neon.tech/neondb?sslmode=require`).
   Guarde — será o `DATABASE_URL`.

---

## Passo 3 — Imagens (Cloudinary) — opcional, mas recomendado

1. Crie conta em https://cloudinary.com (grátis).
2. No painel, copie a variável **CLOUDINARY_URL** (formato `cloudinary://chave:segredo@nome`).
   Guarde — será o `CLOUDINARY_URL`.

> Sem isso o sistema funciona, mas as imagens se perdem quando o Render reinicia. Com o Cloudinary, ficam salvas.

---

## Passo 4 — E-mail (seu provedor SMTP)

Use o SMTP do seu e-mail para que o remetente seja você. Você vai precisar de 4 dados:
host, porta, usuário e senha.

- **Gmail / Google Workspace:** host `smtp.gmail.com`, porta `587`. A senha precisa ser uma
  **"senha de app"** (gerada em Conta Google → Segurança → Senhas de app; exige verificação em 2 etapas).
- **Outlook/Office 365:** host `smtp.office365.com`, porta `587`, seu e-mail e senha.
- **E-mail corporativo:** peça ao TI o servidor SMTP, porta e credenciais.

Guarde: `MAIL_HOST`, `MAIL_PORT`, `MAIL_USER`, `MAIL_PASS`, `MAIL_FROM` (seu e-mail) e `ADMIN_EMAIL` (seu e-mail).

---

## Passo 5 — Publicar no Render

1. Acesse https://render.com e crie conta (pode entrar com o GitHub).
2. **New → Web Service** e selecione o repositório que você subiu no Passo 1.
3. O Render detecta o arquivo `render.yaml`. Confirme:
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn wsgi:app`
   - Plano: **Free**
4. Em **Environment** (variáveis), preencha:

   | Variável | Valor |
   |---|---|
   | `DATABASE_URL` | a string do Neon (Passo 2) |
   | `BASE_URL` | a URL que o Render der ao app (ex.: `https://solicitacao-materiais.onrender.com`) |
   | `MAIL_HOST` / `MAIL_PORT` / `MAIL_USER` / `MAIL_PASS` | dados do seu SMTP (Passo 4) |
   | `MAIL_FROM` / `ADMIN_EMAIL` | seu e-mail |
   | `CLOUDINARY_URL` | do Cloudinary (Passo 3), se usar |
   | `SECRET_KEY` | o Render gera sozinho |

5. Clique em **Create Web Service** e aguarde o deploy terminar (alguns minutos).

---

## Passo 6 — Criar o administrador (uma vez)

No Render, abra o **Shell** do serviço (aba "Shell") e rode:

```
python definir_admin.py
```

Isso cria/define **antonio.carvalho@srna.co** como administrador único, com senha provisória
`Trocar@123` (você troca no primeiro acesso). Os 32 tipos de material já entram sozinhos.

---

## Passo 7 — Acessar e usar

Abra a URL do Render (ex.: `https://solicitacao-materiais.onrender.com`) em qualquer
navegador ou celular. Faça login como admin, e em **Cadastros** crie os usuários
(solicitantes, almoxarifado), fornecedores, tipos, cidades, transportadoras e atividades.

---

## Observações importantes

- **"Dormindo":** no plano grátis, se ninguém usar por 15 minutos, o primeiro acesso seguinte
  demora ~30–60 segundos para "acordar". É normal. Quando quiser que fique sempre rápido,
  troque o serviço do Render para o plano **Starter (~US$7/mês)** — sem trocar o banco, sem perder dados.
- **Dados seguros:** o banco fica no Neon (não é apagado). Trocar o app de grátis para pago não perde nada.
- **Imagens:** o Cloudinary grátis dá 25 GB; comprimir as fotos no upload faz render bastante.
- **Atualizações futuras:** quando mexermos no código, basta enviar para o GitHub que o Render
  publica sozinho; o banco se ajusta automaticamente (micro-migração).
