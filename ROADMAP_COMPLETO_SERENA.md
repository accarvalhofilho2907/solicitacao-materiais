# ROADMAP COMPLETO — MÓDULO ALMOXARIFADO / SISTEMA "SOLICITACAO ALMOX" (Serena)

> Documento de retomada. Guarda TODO o histórico e as decisões do projeto.
> **Regra de ouro:** todo pedido vai primeiro para este roadmap; só é implementado
> no código após ordem explícita do Antonio ("pode rodar" / "manda bala").

---

## 0. COMO RETOMAR A CONVERSA
1. Abra uma conversa nova com o Claude.
2. Anexe **este arquivo** (`ROADMAP_COMPLETO_SERENA.md`) e os arquivos que quiser mexer.
3. Diga: "vamos continuar o projeto Almoxarifado a partir do roadmap".

### Arquivos do projeto (para reanexar quando for continuar)
- `solicitacao-materiais.zip` — sistema Flask, já com o módulo Almoxarifado integrado.
- `iniciar.bat` — inicializador Windows com **Python 3.12** (`py -3.12`).
- `corrigir_fornecedores.py` — elimina o traceback do "item 150".
- `Prototipo_Extintores.html` — protótipo v2 de Extintores (aprovado).
- `Prototipo_Coletor.html` — protótipo v2 do Coletor (nova ordem de telas, aprovado).
- `CONTROLE_DE_EXTINTORES_DMA.xlsm` — planilha-fonte dos 246 extintores.

---

## 1. CONTEXTO
Sistema Flask **SOLICITACAO ALMOX** (pasta `solicitacao-materiais`). Decisão: incorporar o
módulo Almoxarifado dentro dele. Roda local via `iniciar.bat` (Python 3.12; SQLite `app.db` no
protótipo). Login admin: **antonio.carvalho@srna.co**; `definir_admin.py` reseta senha p/ `Trocar@123`.

Ambiente: só o comando `py` funciona (não `python`); usar **Python 3.12** (3.14 não compila
Pillow/psycopg2). Traceback do "item 150" (Empresas/Fornecedores) é inofensivo;
`corrigir_fornecedores.py` resolve.

---

## 2. JÁ IMPLEMENTADO NO FLASK (no zip)
Menu 📦 Almoxarifado (ADMIN/ALMOXARIFADO). Hub com tópicos; liberados: Chaves, Extintores,
Colaboradores. Demais "Em construção". Extintores com 246 registros reais. Models `almox_chaves`,
`almox_extintores`, `almox_colaboradores`, `almox_log`.
**Obs:** essa versão ainda tem o papel RONDA (removido depois) e as telas são a versão simples
inicial — os refinamentos abaixo ainda não foram implementados (aguardam "pode rodar").

---

## 3. PAPÉIS DE ACESSO (login)
ADMIN, ALMOXARIFADO, SOLICITANTE, VISUALIZADOR. **RONDA: removido** (redundante com "Colaborador
diverso"). Acesso ao módulo: ADMIN e ALMOXARIFADO. Dois conceitos de papel: acesso ao sistema
(loga) × colaborador de campo (não loga, identificado por QR).

---

## 4. CHAVES
- Remover coluna **Código**. Descrição vem do nome no cadastro. Status mantém.
- **Com quem** = lista suspensa vinda de Colaboradores.
- Renomear **Local → "Quadro de Chaves"**.
- Cadastro por **botão** (Descrição + Quadro de Chaves pesquisável).
- Novo cadastro **"Quadro de Chaves"** (lista própria) dentro do Almoxarifado.
- **Cada chave tem QR individual; o "Quadro de Chaves" é o localizador dela.**

---

## 5. EXTINTORES (protótipo v2 aprovado)
- **Situação = Status operacional**, ciclo:
  `No Prazo → Próx. Vencimento → Irregular/Vencido → Em Recarga → Pronto p/ Reposição → No Prazo`.
- **Próx. Vencimento** na competência anterior ao vencimento (vence jan/2027 → dez/2026 já mostra).
- Validade da carga **ou** Teste Hidrostático vencidos → Irregular/Vencido + notifica ADMIN.
- Filtros: Prédio, Local, Tipo/Carga, Situação. QR abre ficha/checklist (registra nome + hora).
- **Checklist (10 itens):** 1) Acesso e sinalização desobstruídos; 2) Lacre e pino intactos;
  3) Manômetro na faixa verde; 4) Mangueira/difusor/gatilho sem danos; 5) Cilindro sem corrosão/
  amassados/vazamentos; 6) Rótulo legível; 7) Suporte/fixação ok; 8) Peso/carga adequados;
  9) Validade da carga vigente; 10) Teste hidrostático no prazo.
- Não conforme → Irregular + notifica ADMIN.
- Botão **Regularizar**: "Levado ao Almox D6" (recarga) ou "Reposto no local" (checklist; se OK
  volta No Prazo).
- Checklist do **Almoxarifado** (conferência e reposto-no-local) tem item extra
  **"Colada a etiqueta QR Code?"** → se Não, abre **Pendência de Regularização** (aba separada,
  visível a ADMIN e ALMOXARIFADO, fica até dar baixa).
- Novo vencimento da recarga e do TH: **campos de rolagem MMM + AAAA**.
- Botão **Exportar PDF** da lista filtrada.
- Impressão de QR (seção Impressões): **Folha A4** (recortar e colar com fita, sem PC no local)
  e **Etiqueta térmica** (Elgin L42 Pro, poliéster/vinil); filtra → seleciona → imprime todos.
- **Elgin L42 Pro:** só USB/Ethernet/Serial, **sem Bluetooth/Wi-Fi** → imprime no PC; celular só **lê** o QR.
- Dados reais: 246 extintores — SEPN(8), DELTA3(29), DELTA6(23), MIR(5), UNIT(181);
  tipos PQS 04/06/20/50KG e CO²06KG; classes ABC/BC.

### 5.1 Trâmite do extintor no CAMPO (DECISÃO)
- Diferente de chaves/material (que vão ao balcão): a inspeção/retirada do extintor acontece **onde
  ele está** (galpão/pátio), com o **próprio celular do colaborador**.
- O colaborador lê o **QR do extintor**; ao abrir a ficha, o sistema **pede login**:
  **Login = CPF** e **Senha = a mesma senha usada no coletor para retirar material** (credencial única).
- Após logar, acessa **apenas** a ficha/checklist/retirada daquele extintor (acesso mínimo, escopo
  de extintor — não navega no resto do sistema). Tudo registrado no nome dele (data/hora).
- **Primeiro acesso:** se o colaborador ainda não tem senha (nunca passou pelo coletor), define a
  senha ali no login do extintor; a mesma senha passa a valer no coletor.
- **Reset de senha** do colaborador disponível para ADMIN e ALMOXARIFADO (caso esqueça).
- Consequência: a senha do colaborador é uma **credencial única**, válida no coletor (assinatura/
  confirmação) e no login do extintor no campo.

---

## 6. COLABORADORES
- Cadastro: **NOME COMPLETO, CPF, CARGO, EMPRESA, PAPEL**.
- Cadastro feito pelo Almoxarifado = sempre **"Colaborador diverso"** (inspeciona extintor,
  retira/repõe extintor, pede/devolve chave, pega/devolve material).
- **PAPEL vira cadastro próprio** (lista de papéis, cada um com suas tarefas — a "caixinha" volta,
  só no cadastro de Papel, não em cada usuário).
- Após cadastrar: imprimir **QR** (térmica e foto).

---

## 7. COLETOR (uso do Almoxarifado; protótipo v2 aprovado)

### 7.0 Desktop × Coletor (DECISÃO)
- A **interface do coletor** (menu RETIRAR/DEVOLVER, leitura de QR, cesta, senha) é **exclusiva do
  modo coletor/smartphone** — é operação de campo, de mão, com leitura de QR pela câmera.
- No **desktop (computador)**, o sistema abre as **telas de gestão já validadas** (módulo
  Almoxarifado: Chaves, Extintores, Colaboradores, Impressões, Relatórios) — consulta, cadastro,
  impressão. **Não** mostra a tela de retirar/devolver.
- O roteamento para o modo coletor = **papel ALMOXARIFADO/ADMIN + aparelho de mão**.
  SOLICITANTE/VISUALIZADOR **nunca** acessam o coletor, em aparelho nenhum.

### 7.0.1 Coletor = aparelho dedicado (DECISÃO)
- O coletor é um **aparelho dedicado do almoxarifado**, que fica **sempre logado como ALMOXARIFADO**
  (sessão persistente, não expira toda hora — o aparelho não sai do balcão).
- O **colaborador de campo NUNCA loga** para chaves/material: é identificado por **QR** e confirma
  com **senha**. Ele não navega nem escolhe nada no coletor — quem opera é o almoxarife.
- Após cada operação (retirar/devolver), o coletor **volta sozinho à tela inicial**, pronto para o
  próximo colaborador (nunca fica "no meio" da operação de outra pessoa).
- **Botão protegido de "trocar operador / sair"** disponível para troca de turno; no dia a dia
  ninguém mexe.

### 7.1 Tela inicial do coletor (botões)
`RETIRAR/DEVOLVER · ENTRADA · MOVIMENTAÇÃO · INVENTÁRIO · CADASTRO · AJUSTES EM GERAL · SISTEMA`
- **Liberados:** RETIRAR/DEVOLVER, MOVIMENTAÇÃO, SISTEMA.
- **Bloqueados (em construção):** ENTRADA, INVENTÁRIO, CADASTRO, AJUSTES.
- Campo de **busca ÚNICO** (nome/CPF/empresa/cargo juntos). Ao abrir RETIRAR, o coletor já lê o QR sozinho.

### 7.2 RETIRAR
QR do colaborador (ou busca) → embaixo mostra **o que ele já está com** (retiradas anteriores em
aberto) + a **CESTA** nova (seleção material × chave, lista pesquisável) → lê o **localizador** →
lista itens do localizador → lê QR de cada item → cesta → **FINALIZAR** → conferência →
colaborador confere/OK → **senha** (1ª vez: define senha + repete + confirma CPF; depois só senha).

### 7.3 DEVOLVER
QR do colaborador → mostra o que está com ele → marca o que devolver (se +1 unidade, pergunta
quantas) → lê QR do **localizador de destino** → aprova → conferência → OK → senha (o Almoxarifado
pode usar a **própria senha**, pois outra pessoa pode vir devolver).

### 7.4 MOVIMENTAÇÃO (fim do dia) — já funciona para CHAVES
Lê QR da **Estocagem Temporária** (localizador especial onde cai o devolvido do dia) → lista itens
→ cesta (um a um ou todos) → aprova → na prateleira seleciona itens, OK, lê QR do **localizador** →
transferido. Botão **"transferir todos"** → aviso grande de confirmação → lê QR do localizador.
**Local = Localizador.** Material entra depois (junto do módulo de estoque).

### 7.5 Senha do colaborador
É **assinatura/confirmação no coletor** e **também** a credencial de login do extintor no campo
(Login = CPF; Senha = esta). **Não** é acesso ao sistema de gestão. Identificação no coletor
continua por QR; a senha só valida a operação e o acesso à ficha do extintor. Definida na 1ª vez
(no coletor com CPF, ou no 1º acesso ao extintor). Reset por ADMIN/ALMOXARIFADO.

---

## 8. ARQUITETURA / OFFLINE / SINCRONIZAÇÃO (DECISÃO FINAL)

### 8.1 Hospedagem
- **Somente NUVEM.** Sem servidor local (a Serena não tem, e não compensa manter máquina no site).

### 8.2 Modo de operação do coletor
- **DECISÃO (fase 1): Coletor ONLINE primeiro.** Interface otimizada p/ celular, leitura de QR
  pela câmera, exige internet no momento da operação (há sinal/Wi-Fi no almox). Coloca em uso
  rápido. O **offline-first** (IndexedDB + fila + sync) fica para a fase 2, evoluindo em cima disto.
- Coletor roda **offline-first**: funciona sem conexão e **sincroniza em segundo plano** de tempos
  em tempos, sem travar a operação. Cobre tanto queda de internet (link externo) quanto perda de
  Wi-Fi no galpão.
- **Consequência assumida:** com offline-first + nuvem, dois coletores podem retirar o mesmo item
  antes de sincronizar → pode gerar **estoque negativo**. Não é defeito; é o trade-off do modelo.
  Resolvido na tela de Estoque Negativo (seção 9).

### 8.3 IndexedDB no coletor (PWA) — regras para não estourar/perder dados
- IndexedDB é generoso (fatia do disco livre; muito além do localStorage), mas seguem regras:
- Coletor usa IndexedDB **apenas como CACHE + FILA de sincronização**, **não** como banco definitivo.
  Guarda o necessário para operar (catálogo de itens, colaboradores, saldos) + fila de ações
  pendentes. O **histórico completo mora na nuvem**.
- **Ação confirmada na nuvem sai da fila local** → a fila nunca vira depósito permanente; tamanho
  local fica pequeno e estável.
- Solicitar **armazenamento persistente** ao navegador (reduz risco de limpeza automática).
- **Sincronizar com frequência** (a fila offline é para minutos/horas, não dias). Quanto mais rápido
  sincroniza, menor o volume local e menor a chance de estoque negativo.
- **Atenção iOS/Safari:** pode limpar o IndexedDB de PWAs após ~7 dias sem uso. **Preferir Android**
  nos coletores (política de retenção mais estável) e não deixar fila pendente por dias.

### 8.4 Backup
- **Backup automático** do banco na nuvem (rotina periódica).

### 8.5 Banco de dados
- Nuvem em **PostgreSQL** (melhor para acesso simultâneo que SQLite; já usado no Render).

---

## 9. ESTOQUE NEGATIVO (na seção de OPERAÇÃO)
- Novo item **"Estoque Negativo"** dentro de Operação. Visível e resolvível por **ADMIN e ALMOXARIFADO**.
- **Prevenção:** na retirada, checa saldo antes de confirmar e bloqueia com aviso se insuficiente.
  Para chave (peça única): se já está "em uso", não deixa retirar de novo.
- **Detecção:** se o saldo ficar negativo (retiradas concorrentes / fila offline chegando atrasada),
  o item é marcado com alerta "Estoque negativo" e sobe notificação a ADMIN e ALMOXARIFADO.
- **Tela de resolução:** mostra **as duas (ou mais) ações conflitantes** que causaram o furo
  (quem, quando, qual coletor, o que cada uma diz) e **pede para escolher qual é a correta**.
  Ao escolher, o sistema **mantém a certa e estorna a(s) outra(s)**, acertando o saldo.
- Motivo/observação **obrigatório**; tudo gravado no **log** (quem resolveu, quando, qual ação
  prevaleceu). Para chave: a escolha define com quem a chave realmente está.
- **PENDENTE decidir:** ao estornar uma ação, **avisar o colaborador afetado** ou só registrar no log?

---

## 10. TÓPICOS "EM CONSTRUÇÃO"
Painel, Entrada de material, Devolução forçada, Inventário, Ajuste de item, Produto,
Unidades/validade/calibração, Kit, Consulta de estoque, Movimentações (estoque), Etiquetas,
QR em massa, Log de ações, Relatórios, Coletor (demais funções).
Controle de **material** completo vem depois; a MOVIMENTAÇÃO já roda para **chaves** agora.

---

## 11. STATUS / PRÓXIMO PASSO
- Nada das seções 3–9 foi implementado no Flask ainda — tudo aguarda o "pode rodar".
- Protótipos aprovados: Extintores (v2) e Coletor (v2).
- Ordem sugerida de implementação quando autorizar:
  1. Remover RONDA. 2. Chaves (Quadro de Chaves + QR individual). 3. Colaboradores (cadastro +
  Papéis + QR). 4. Coletor (RETIRAR/DEVOLVER/MOVIMENTAÇÃO para chaves). 5. Extintores (ciclo
  completo + checklist + pendências + PDF + impressão A4/térmica).
- Arquitetura (nuvem, offline-first, PWA/IndexedDB, estoque negativo) entra junto quando a operação
  do coletor for para produção.

---

*Fim do roadmap. Este arquivo + os arquivos da seção 0 preservam todo o histórico.*

---

## 12. REFORMA DO FLUXO DE EXTINTORES (IMPLEMENTADO ✓)

### 12.1 Abertura da ficha
- Ao abrir a ficha, **perguntar primeiro**: **Inspeção** ou **Reposição (troca programada)**.
- Só depois de escolher, mostra o passo a passo correspondente.

### 12.2 Checklist
- Vem **DESMARCADO** (hoje vinha tudo OK) — a pessoa marca cada item.
- Item da etiqueta vale **para TODOS os usuários** (não só almox), texto novo:
  **"Etiqueta grudada e em bom estado?"**.
- Regra de status pela inspeção:
  - Qualquer um dos 9 itens (fora etiqueta) em desacordo → **Irregular/Vencido**.
  - **Só** a etiqueta ruim → status **Atenção** (segue em uso no local) + sobe p/ pendências.
  - Etiqueta + outro item ruins → **Irregular/Vencido** (o mais grave manda).
- Datas vencidas (carga ou TH) → **Irregular/Vencido**.

### 12.3 Status possíveis
No prazo · Próximo do vencimento · **Irregular/Vencido** · **Atenção** (só etiqueta) ·
Em recarga · Pronto p/ reposição.

### 12.4 Fluxo Irregular → recarga
- Irregular → **abre pendência de regularização** automaticamente; só sai da pendência quando
  **retornar ao local**.
- Na ficha Irregular, mostrar **só** o botão **"Levado ao Almox D6 p/ Recarga"** —
  **sem pedir nome** (pega do usuário logado).
- Só **depois** de clicar (status = **Em recarga**) é que aparece o **checklist do almoxarifado**
  (conferência no retorno).
- Inspeção de retorno: **não** pede nome (pega do usuário) e **remove** o item
  "Acesso e sinalização desobstruídos" (está no almox).

### 12.5 Reposição programada (troca)
- Escolhida na abertura da ficha (extintor perto de vencer).
- Fluxo: **troca o extintor** e faz o **checklist do NOVO**, lançando **nova validade da carga**
  e **novo teste hidrostático** (MMM/AAAA). **Não** passa pelo D6.
- Ao confirmar, **não** escreve nome (pega do usuário).

### 12.6 Atenção (etiqueta)
- Extintor **continua em uso** no local, só sinalizado; sobe p/ pendências (tipo etiqueta).
- Sai da Atenção/pendência quando a etiqueta for reposta.

### 12.7 Cadastro de novo extintor
- Botão de **novo extintor** na lista + botão de **desativar** dentro da ficha.
- **Código automático** (sequencial do sistema).
- Prédio, local, tipo/carga, classe = **campo livre com sugestões** dos valores já existentes
  (datalist: escolhe existente ou digita novo).
- Validade e TH em MMM/AAAA. Nasce com QR e faz **checklist inicial** de conferência.
- Cadastro **só para ADMIN e ALMOXARIFADO**.

### 12.8 Histórico
- No histórico da ficha, **clicar num registro abre o detalhe** (checklist item a item, quem, quando).

### 12.9 Pendências
- Tudo (regularização + etiqueta) aparece no **sininho 🔔 já existente** na barra do topo,
  para ADMIN e ALMOXARIFADO.

---

## 13. LOGIN UNIFICADO POR CPF/E-MAIL + CADASTRO PELA TELA COLABORADORES

**Decisão do Antonio:** NÃO mover tabelas (evita orfanizar histórico: solicitações,
movimentações, logs apontam p/ usuarios.id). Em vez disso: cadastra as pessoas pela tela
**Colaboradores** e desativa manualmente os antigos em **Usuários** (são poucos).

Para isso funcionar:
- **Login aceita Colaborador** também: por **CPF (só números) OU e-mail** + senha.
  Login de Usuário por e-mail continua igual (ninguém perde acesso).
- Colaborador pode **entrar no sistema (computador)** conforme o papel, além do coletor/campo.
- **Senha definida no 1º login por CPF** (mesmo mecanismo do extintor).
- Tela Colaboradores: nome, **e-mail (opcional)**, **CPF (obrigatório, só números, único)**,
  cargo, empresa (**lista suspensa de Empresas**, mesma dos usuários), papel
  (lista existente; almox cadastra como "COLABORADOR DIVERSO").
- Duas tabelas continuam existindo; transição feita à mão pelo Antonio.

---

## 14. TROCA DE PAPEL / EDIÇÃO DO COLABORADOR (com histórico)

**Cadastro do colaborador (tela Colaboradores):**
- Se quem cadastra é **ALMOXARIFADO** → campo de papel NÃO aparece; sai "COLABORADOR DIVERSO".
- Se quem cadastra é **ADMIN / MASTER** → mostra seletor de **papel**
  (Colaborador diverso, Almoxarifado, Admin). **Admin só o MASTER concede.**

**Editar colaborador (perfil):**
- **Admin/Master:** altera papel, empresa e cargo.
- **Almoxarifado:** edita só cargo e empresa (NÃO mexe em papel).
- Empresa por lista suspensa (Empresas); papel pela lista de papéis.

**Histórico:** registrar TODA alteração de **papel, empresa e cargo**
(de → para, quem alterou, quando). Visível no perfil do colaborador.

**Proteções:** admin só concedido pelo Master; Almoxarifado nunca altera papel.

---

## 15. MELHORIAS EM CHAVES + ESTRUTURAÇÃO (a implementar)

1. **Busca de quem retirou/devolveu** (chaves): pesquisar por **nome, CPF ou bipando o QR**.
2. **Retirar chave pede a senha do colaborador** (como já é no coletor).
3. **Log geral de movimentações** do sistema (histórico de tudo), com tela para consultar.
4. **Estruturação:**
   - Colaboradores passa a viver no menu **Cadastro**.
   - Tela **Usuários** renomeada para **"Usuários - Antigo"**, movida para baixo, em desuso,
     **acesso só do Master**.
5. **Papéis do colaborador** devem incluir os papéis já existentes do sistema
   (solicitante, almoxarifado, visualizador, admin) + colaborador diverso.

---

## 16. AJUSTES EM CHAVES (a implementar — aguardando "pode rodar")

**Decisão: chaves só no DESKTOP.** Remover retirar/devolver chave do COLETOR
(coletor mantém material: retirar, movimentar, inventário). Um caminho só = mais simples.

1. **Refazer a retirada/devolução no desktop** num modal limpo (o formato atual na linha
   da tabela ficou ruim): busca de colaborador por **nome/CPF/QR** + **senha** na retirada.
2. **BUG:** Quadro de Chaves cadastrado **não aparece na lista** ao cadastrar/editar a chave. Investigar/corrigir.
3. **Editar dados da chave** (descrição, quadro, etc.) guardando **histórico do que mudou**.
4. **Histórico da chave**: ver com quem esteve ao longo do tempo (todas as movimentações daquela chave).
5. Históricos/relatórios de chave vivem em **Relatórios e Impressões**, com **atalho dentro de Chaves**
   para pesquisar rápido. (Ir construindo esse módulo de Relatórios e Impressões aos poucos.)

### 16.1 Detalhe do BUG do Quadro (diagnóstico do Antonio)
- Sintoma: ao **cadastrar a chave nova**, escolheu o quadro; após finalizar, a chave aparece
  na lista **sem o quadro** (coluna Quadro de Chaves vazia). O quadro EXISTE — falhou o VÍNCULO.
- Causa provável: no form de nova chave o quadro é um input "buscar" (datalist) que só preenche
  o campo escondido `quadro_chave_id` quando o texto casa exatamente com uma opção. Se o id não
  foi preenchido, a chave salva sem quadro.
- Correção pretendida: usar um `<select>` real do quadro OU resolver o quadro pelo NOME no servidor
  (fallback) quando o id não vier. Conferir também `chave_nova()` e a property `quadro_nome`.

---

## 17. LEITURA: LEITOR FÍSICO + CÂMERA SOB DEMANDA (a implementar — aguardando "pode rodar")

**Contexto:** os aparelhos variam por pessoa — uns têm **coletor com leitor físico** (scanner
dedicado, "digita" o código e manda Enter), outros usam **celular/tablet comum** (câmera).

**Desenho único para todo campo de leitura (coletor e telas do desktop com bip):**
- Campo de **texto normal** com foco pronto:
  - **Leitor físico** → bipa direto, câmera FECHADA; ao receber o **Enter** do leitor, o sistema
    resolve/confirma automaticamente (colaborador/chave/material).
  - **Celular comum** → botãozinho **📷** ao lado abre a câmera só naquele momento; lê e fecha sozinha.
  - **Digitação manual** (nome/CPF) continua valendo.
- Ninguém fica preso com a câmera aberta o tempo todo (hoje o fluxo abre a câmera automaticamente).
**Aplica-se a:** coletor (material) e, quando as chaves virarem "só desktop" (seção 16), aos campos
de leitura do desktop também.

### 16.2 Fluxo de chaves por QR (desktop) + QR do Quadro
- **Quadro de Chaves ganha QR próprio** (qr_uid) + impressão A4/térmica (igual chaves/extintores).
- Fluxo de retirada/devolução no desktop:
  1. (Atalho) bipar **QR do quadro** → mostra/filtra as chaves daquele quadro.
     **Não é obrigatório** — dá para ir direto na chave (QR dela ou busca por nome).
  2. Bipar **QR da chave** → seleciona a chave.
  3. Bipar **crachá do colaborador** (ou digitar nome/CPF) + **senha** → confirma.
- Toda leitura segue a seção 17 (leitor físico com câmera fechada OU botão 📷 no celular).
- Backfill: gerar qr_uid para os quadros já cadastrados.

---

## 18. UNIFICAÇÃO DO SISTEMA + MENU LATERAL (a implementar — aguardando "pode rodar")

**Visão:** juntar "Solicitação Almox" e "Almoxarifado" num sistema só, com **menu lateral
dividido por seções** (como era antes — NÃO os ícones/cards de hoje).

1. **Menu lateral por seções** (Claude propõe agrupamento; Antonio ajusta). Incorporar dentro do
   menu único: **Operação**, **Relatórios e Impressões** e o que hoje está no **menu do nome**
   (Cadastros, Log do sistema, etc.). "Sair" e "trocar senha" continuam no cantinho do perfil.
2. **Chaves nos DOIS, mas o BIPE só no coletor:**
   - Desktop de Chaves = gestão/consulta (cadastrar, editar, histórico, QR). **Remover o
     retirar/devolver bipando do desktop.**
   - Coletor = retirar/devolver chave (tudo bipado lá). (Corrige a decisão anterior da seção 16.)
3. **Papéis — TODAS as tarefas possíveis:** no cadastro de novo papel, o checkbox lista **todas**
   as tarefas do sistema inteiro, **inclusive as que ainda serão feitas** (deixar pronto).
4. **Tema:** remover claro/escuro; manter **só o tema escuro**.
5. **Entregável agora:** HTML de **maquete visual** do menu lateral unificado (sem implementar).

### 18.1 Coletor no sistema unificado (DECISÃO)
- O **item "Coletor" SAI do menu lateral do desktop** (não serve no computador).
- O **coletor continua como está hoje** (tela de campo, botões grandes, QR) — passa a ser
  o **"modo campo"** do sistema único (mesmo login/banco), acessado direto no aparelho de mão.
- Duas caras do mesmo sistema: **menu lateral = gestão (desktop)** × **coletor = campo (aparelho de mão)**.
  Coletor não ganha menu lateral; desktop não ganha atalho de coletor.

---

## 19. HIERARQUIA FÍSICA (Planta → Armazém → Localizador) + SEÇÕES DO MENU (a implementar — aguardando "pode rodar")

### 19.1 Empresas + Fornecedores
- **Unificar** Empresas e Fornecedores num cadastro só (já decidido antes).

### 19.2 Hierarquia física nova (3 níveis)
- **Planta** = o site (ex.: Delta Maranhão).
- **Armazém** = galpão dentro da planta (ex.: Galpão D6).
- **Localizador** = estante/prateleira no formato **A*1*3** (asterisco):
  **A** = fileira de estantes (1 LETRA, A–Z), **1** = estante (número), **3** = nível da prateleira (número).
- Localizador pertence a um Armazém, que pertence a uma Planta.
- **Substitui o "Local" plano de hoje (LocalAlmox) SÓ para MATERIAL e CHAVES.**
  **Extintores NÃO usam** este localizador (mantêm Prédio/Local próprio — ficam na parede, não em prateleira).
- Migração sem perder dados: manter locais antigos durante a transição; "Estocagem Temporária"
  continua existindo (armazém/localizador especial p/ devolução do dia).

### 19.3 Gerador em massa de localizadores (fica na seção MOVIMENTO)
- Informar intervalo: fileira inicial→final (letras), estante inicial→final (números),
  nível inicial→final (números). Gera TODAS as combinações de uma vez.
- Ex.: A–J × 1–5 × 1–7 = 350 localizadores. Validação: fileira = 1 letra; estante/nível = números.

### 19.4 Reorganização do menu lateral em 4 seções
- **Cadastro** (onde se cadastra), **Movimento** (onde se executa), **Relatório**, **Ajuda**
  (Log do sistema, FAQ, sugestão de melhoria, etc.).
- Claude propõe o encaixe das telas nas 4 seções; Antonio ajusta.
- **Caixa de busca no topo da barra lateral** para achar rápido o item de menu.

### 19.5 Renomear "Papéis" → "Perfis de acesso"
- O cadastro antes chamado "Papéis" passa a se chamar **"Perfis de acesso"** (menu e telas).
- Motivo: mais claro que é sobre permissão/o que a pessoa pode acessar; não confunde com o
  "cargo/função" do colaborador (que é outro campo).
- Obs. de implementação: é troca de RÓTULO na interface. Internamente o conceito segue o mesmo
  (grupo de tarefas/permissões); avaliar se vale renomear termos internos ou só os textos visíveis.

### 19.6 Padrão único de tela de cadastro (todos os cadastros)
- Ao abrir qualquer cadastro: **lista** do que já está cadastrado + **botão "Novo"** no topo.
- Clicar em "Novo" abre o formulário de criação.
- **Editar = clicar no item da lista** e alterar ali (marcar/desmarcar tarefas nos Perfis de acesso;
  editar campos nos demais). Vale para: Perfis de acesso, Colaboradores, Empresas+Fornecedores,
  Planta, Armazém, Localizador, Quadros de chave, Material, Extintor, Tipos/Cidades/Transportadoras/Atividades.

### 19.7 AUTORIZAÇÃO DE IMPLEMENTAÇÃO (Antonio: "manda bala")
- Antonio autorizou implementar a reforma **no sistema real**, em **BLOCOS TESTADOS** (não tudo de uma vez).
- Ordem de blocos proposta pelo Claude (ver STATUS abaixo).

### 19.8 STATUS — Bloco 1 (Fundação visual) IMPLEMENTADO ✓
- base.html reescrito: **menu lateral** com 4 seções (Cadastro/Movimento/Relatório/Ajuda),
  **busca no topo**, **seções recolhíveis**, **casinha** ao lado do logo, **ícones de linha**
  (sprite SVG), **tema só escuro** (toggle claro/escuro removido).
- Todos os links existentes preservados e reorganizados nas seções. Testado: telas renderizam 200
  (admin e almoxarifado). Backup do layout antigo NÃO vai no zip.
- OBS pré-existente (não é do bloco): `_unificar_empresas_fornecedores` no __init__.py lança
  IntegrityError (fornecedores.nome NOT NULL) em alguns bancos, mas está em try/except e o app segue.
  Tratar no bloco de Empresas+Fornecedores.
- PRÓXIMOS: Bloco 2 (padrão lista+Novo+editar / renomear Perfis / unificar Empresas+Fornecedores),
  Bloco 3 (Planta→Armazém→Localizador + gerador), Bloco 4 (chaves), Bloco 5 (relatórios).

### 19.9 STATUS — Bloco 2 (parte 1/3): renomear Papéis → Perfis de acesso ✓
- Renomeado o RÓTULO visível em: tela almox/papeis.html (título/textos/botões), botão e cabeçalho
  em colaboradores.html, e colaborador_perfil.html. Campos internos (name="papel") mantidos.
- "Perfis de acesso" agora é ITEM PRÓPRIO no menu lateral (seção Cadastro, admin) — não fica mais
  escondido dentro de Colaboradores. Ícone shield. Testado (renderiza 200).
- FALTA no Bloco 2:
  - (2/3) Unificar Empresas + Fornecedores DE VERDADE. Diagnóstico: migração `_unificar...`
    já existe mas FALHA porque a tabela física `fornecedores` tem coluna legada `nome` NOT NULL
    que o insert não preenche (no model, `nome` é @property). Conserto envolve mexer nessa coluna
    no Postgres de PRODUÇÃO (Neon) — fazer com cuidado, passo próprio, com backup.
  - (3/3) Padrão "lista + botão Novo + editar clicando" em todos os cadastros (rollout tela a tela).

### 19.10 STATUS — Bloco 2 (parte 2/3): unificação Empresas+Fornecedores — CONSERTADA ✓
- CAUSA do erro achada: tabela física `fornecedores` tinha colunas legadas NOT NULL (`nome` e `email`)
  que os inserts não preenchiam (no model `nome` era @property; email opcional).
- CONSERTO (cross-DB, sem ALTER arriscado em produção): `nome` virou coluna real + evento
  SQLAlchemy `before_insert/before_update` (em models.py) que SEMPRE preenche `nome`
  (a partir de nome_fantasia/razao_social) e coage `email` None→"" . Cobre todos os pontos que
  criam Fornecedor (unificação, admin.fornecedores, relatorios). Funciona em SQLite e Postgres.
- Testado em cópia do banco real: unificação COMPLETA (3 empresas viram fornecedores
  is_empresa_interna), 0 fornecedores sem nome, telas 200.
- Menu: item "Fornecedores" renomeado para **"Empresas e Fornecedores"** (a tela admin.fornecedores
  já é lista unificada). Item "Empresas" mantido (ainda alimenta o dropdown de empresa em Colaboradores).
- FALTA (fecho da unificação, próximo passo com cuidado): apontar o dropdown de empresa
  (Colaboradores) para a fonte única (Fornecedor is_empresa_interna) e aposentar a tabela/ tela
  Empresa antiga — toca em dependências, fazer testado.
- FALTA ainda no Bloco 2: parte (3/3) padrão "lista + Novo + editar clicando" nos cadastros.

### 19.11 Perfis de acesso — lista COMPLETA de tarefas (todas as possíveis)
- Expandir TAREFAS_COLABORADOR (hoje só 4) para TODAS as tarefas do sistema, agrupadas por área,
  como na maquete. Incluir as FUTURAS marcadas "em breve" e DESABILITADAS (não selecionáveis)
  até a funcionalidade existir — para não haver caixinha que "não faz nada".
- Grupos: Operação/Solicitações, Chaves, Extintores, Material, Locais físicos, Coletor,
  Pessoas/Colaboradores, Cadastros, Relatório, Ajuda/Administração.
- A tela de Perfis passa a renderizar por grupo (com subtítulos), não uma lista corrida.

### 19.11-STATUS Perfis de acesso — lista completa IMPLEMENTADA ✓
- TAREFAS_PERFIL: 68 tarefas em 10 grupos (11 marcadas "em breve"/desabilitadas). Model + almox.py + papeis.html.
- Tela renderiza por grupos; futuras desabilitadas; validação ignora futuras ao salvar. Perfis antigos (4 tarefas) seguem válidos. Testado.

### 19.12 Fecho da unificação Empresas+Fornecedores ✓
- Campo "Empresa" do colaborador (tela Colaboradores e Perfil) agora lê de **Fornecedor** (fonte única),
  listando empresas E fornecedores. Antes lia da tabela Empresa antiga.
- Item "Empresas" isolado REMOVIDO do menu — ficou só **"Empresas e Fornecedores"** (admin.fornecedores).
- Rota admin.empresas e tabela Empresa continuam existindo por baixo (não removidas), mas sem link no menu.
- Testado: dropdown populado por Fornecedor, telas 200, menu sem "Empresas" isolado.

### 19.13 STATUS — Bloco 2 (parte 3/3): padrão lista + Novo + editar ✓ (BLOCO 2 COMPLETO)
- Cadastros simples (Tipos, Cidades, Transportadoras, Atividades) reescritos no padrão:
  lista protagonista + botão "＋ Novo" (modal) + editar clicando (colapso inline). Back-link antigo removido.
- Colaboradores e Perfis de acesso já tinham telas próprias adequadas (Colaboradores usa modal Novo;
  Perfis usa card + lista — modal com 68 checkboxes seria ruim, mantido card por decisão de UX).
- Empresas e Fornecedores (admin.fornecedores): mantida como está (form próprio) — polir depois se quiser.
- Testado: 4 cadastros renderizam, criam pelo modal e editam.
- **BLOCO 2 COMPLETO** (renomear Perfis ✓, unificação Empresas+Fornecedores ✓, fecho empresa ✓,
  lista completa de tarefas ✓, padrão de cadastro ✓).

### PRÓXIMOS BLOCOS (grandes, seguirão um a um, testados):
- Bloco 3: Planta→Armazém→Localizador (A*1*3) + gerador em massa + migrar "Local" antigo (mexe em dados).
- Bloco 4: Chaves (bipe só no coletor, desktop gestão, QR do quadro, editar+histórico, fluxo bipar quadro→chave).
- Bloco 5: Central de relatórios (vários relatórios) + seção 17 (leitor físico + câmera).

### 19.14 STATUS — Bloco 3 (núcleo): Planta / Armazém / Localizador + gerador ✓
- Models novos: Planta, Armazem (planta_id), Localizador (armazem_id, fila/estante/nivel, qr_uid,
  código "F*E*N", caminho planta/armazém/código, unique por armazém+fila+estante+nível).
- ProdutoAlmox ganhou `localizador_id` (aditivo; _light_migrate adiciona a coluna). `local_nome`
  prefere o localizador, senão o Local antigo. NADA destrutivo — Local antigo e Estocagem Temp. seguem.
- Rotas + telas (padrão lista+Novo+editar): Plantas, Armazéns, Localizadores. Gerador em massa
  (intervalos fila/estante/nível; pula duplicados). Itens no menu: Cadastro (Planta/Armazém/Localizador)
  e Movimento (Gerar localizadores). Ícone de Planta = aerogerador.
- Testado em cópia do banco real: tabelas criadas, coluna adicionada, telas 200, gerou 12 e regerar pulou.
- FALTA do Bloco 3 (próximo sub-passo, toca telas de material/coletor): usar o localizador nas
  operações de material (entrada/saída/mover) no lugar do "Local" antigo — coexistindo até migrar tudo.
- AINDA: Bloco 4 (chaves) e Bloco 5 (relatórios + leitor físico/câmera).

### 19.15 STATUS — Bloco 4 (parte 1): chaves = gestão no desktop, bipe só no coletor ✓
- Desktop de Chaves reescrito como GESTÃO (sem retirar/devolver): lista + Nova chave (modal, select
  de quadro) + Editar (inline, com log de mudanças) + Histórico da chave + Quadros + Imprimir QR + busca.
- BUG do quadro CORRIGIDO: chave_nova agora resolve o quadro por id (select) ou nome (_resolver_quadro);
  chave criada já vincula o quadro. Antes o datalist não preenchia o id e a chave ficava sem quadro.
- Novas rotas: chave_editar (edita descrição+quadro, loga de→para) e chave_historico (movimentações da chave).
- Coletor NÃO afetado (usa coletor_api_confirmar, não chave_toggle). chave_toggle mantida mas não usada no desktop.
- Testado: gestão 200, criação com quadro OK, edição OK, histórico 200.
- FALTA Bloco 4 (parte 2): QR próprio do QUADRO (qr_uid + impressão A4/térmica) e fluxo no COLETOR
  de bipar quadro → escolher chave → crachá + senha. Depois: Bloco 5 (relatórios) + leitor físico/câmera.

### 19.16 CORREÇÕES pós-deploy (erros 500 em produção) ✓
Diagnóstico pelos logs do Render (Postgres):
1) papeis/novo — DataError varchar(400): a lista completa de tarefas passa de 400 chars.
   FIX: coluna PapelColaborador.tarefas -> db.Text; _light_migrate amplia varchar->TEXT no Postgres (idempotente).
2) coletas-proprias e precos — sort por fornecedor.nome com nome None (fornecedores antigos sem nome).
   FIX: lambdas toleram None ((nome or "")); e _light_migrate faz BACKFILL de fornecedores.nome
   (COALESCE fantasia/razão/email/'SEM NOME') para linhas antigas.
Testado local (SQLite): perfil grande salva (762 chars), coletas/precos/notinhas 200, 0 forn sem nome.
OBS: o ALTER TYPE TEXT é Postgres-only (não testável no SQLite local), roda no boot do deploy, em try/except.
AÇÃO DO ANTONIO: subir este zip e fazer novo deploy (a migração roda no boot e conserta a coluna + nomes).

### 19.17 Perfis: "marcar todos" por grupo + Bloco 4 parte 2 (QR do quadro) ✓
- Perfis de acesso: cada título de grupo (OPERAÇÃO, CHAVES, etc.) ganhou checkbox "marcar todos"
  que marca/desmarca as tarefas do grupo (pula as "em breve"); estado inicial sincronizado. Testado.
- QuadroChave ganhou qr_uid (QUAD-...). quadro_novo gera; backfill lazy preenche os existentes ao abrir
  a tela de quadros. Rota quadros_qr (impressão A4/térmica). Tela de quadros com botão "Imprimir QR"
  (todos) e link "QR" por linha. Testado: coluna criada, quadros com QR, telas 200.
- Bloco 4 parte 1 (gestão desktop, bug quadro, editar, histórico) + parte 2 (QR do quadro) FEITOS.
- FALTA do Bloco 4 (opcional, não obrigatório): atalho no COLETOR de bipar o QR do quadro para listar
  as chaves dele (o coletor já bipa chave por chave hoje; isso é conveniência). Fazer com cuidado depois.

### 19.18 STATUS — Bloco 5: Central de relatórios ✓
- Nova tela almox.relatorios_central: reúne num lugar só TODOS os relatórios/exportações que já existem,
  agrupados: Chaves (situação, CSV, PDF, QR chaves, QR quadros), Material/Estoque (saldo CSV, mov CSV/PDF),
  Extintores (ver, PDF), Solicitações/Compras (preços, carga, etiquetas — admin), Pessoas (colaboradores,
  perfis), Sistema/Gestão (log, backup — admin). Links de admin só aparecem para admin.
- Item "Central de relatórios" no menu (seção Relatório). Testado: 200, grupos presentes, links válidos.
- OBS: a central REÚNE os relatórios existentes (não cria relatórios novos). Se faltar algum relatório
  específico que ainda não existe, é item novo a levantar com o Antonio.
- FALTA (opcional): atalho coletor bipar quadro→chave; e o fecho do Bloco 3 (material usar localizador);
  coletor offline (fase 2) e itens menores.

### 19.19 Perfis: lista minimizada + expandir ao clicar + botão Novo ✓
- Tela de Perfis reorganizada: topo com botão "＋ Novo perfil" (área de criação recolhível);
  perfis cadastrados agora em lista FECHADA (list-group), cada um mostra nome + contagem de tarefas
  e EXPANDE ao clicar no cabeçalho (chevron gira). Editar tarefas / desativar dentro do expandido.
  Mantido "marcar todos" por grupo. Testado (200, lista, criação recolhida, expansão).

### 20. REGRA REFORÇADA PELO ANTONIO
- SEMPRE registrar no roadmap primeiro e SÓ executar quando o Antonio mandar. (Regra de ouro.)

### 20.1 PENDENTE (aguardando "pode executar") — Campo Perfil do colaborador = Perfis cadastrados
PROBLEMA: no cadastro/edição do colaborador, o campo "Perfil de acesso" mostra uma lista FIXA no código
(PAPEIS_COLAB em almox.py: Colaborador diverso, Solicitante, Almoxarifado, Visualizador, Admin).
Não são os Perfis de acesso que o Antonio cadastra (tela de Perfis). Por isso "aparecem perfis não cadastrados".

DECISÃO DO ANTONIO: o campo deve listar os PERFIS QUE ELE CADASTRA (PapelColaborador).

ALERTA/CUIDADO (área sensível = permissão):
- Hoje PAPEIS_COLAB alimenta o nível de acesso (is_admin, is_almox, pode_solicitar, pode_almox_modulo...).
  Trocar o campo direto para os Perfis cadastráveis (que são CONJUNTOS DE TAREFAS) pode fazer o sistema
  perder a noção de quem é admin/almoxarife → risco de travar ou liberar acesso indevido.
PLANO quando autorizar (fazer testado + migração):
- Definir como cada Perfil cadastrável concede poderes (derivar is_admin/is_almox/pode_* das TAREFAS do perfil,
  ex.: solicitar_aprovar, mat_*, etc.), OU adicionar no PapelColaborador flags de nível de acesso.
- Mapear os valores antigos (Admin/Almoxarifado/Solicitante/Visualizador/Colaborador diverso) para Perfis
  equivalentes e migrar os colaboradores atuais sem perder acesso.
- Atualizar colaboradores.html/colaborador_perfil.html para listar PapelColaborador no lugar de PAPEIS_COLAB.
- Testar: login, menu, permissões por papel, e cada colaborador existente mantendo o acesso.

### 20.2 PENDENTE (aguardando "pode executar") — Revisar LIBERAÇÕES do Perfil de acesso
Para o Perfil de acesso virar a FONTE ÚNICA de permissão (decisão do Antonio no 20.1), faltam no
cadastro do Perfil as "liberações de nível" que hoje vêm da lista fixa (PAPEIS_COLAB). Mapeado do código:
o papel controla: is_admin, is_almox, is_viewer, pode_solicitar, pode_almox_modulo, pode_chaves,
pode_extintores, pode_colaboradores, pode_gerir.

ADICIONAR um grupo novo de tarefas no Perfil, ex.: "ACESSO E ADMINISTRAÇÃO":
- acesso_admin        -> concede is_admin (poder total)
- acesso_almoxarife   -> concede is_almox
- acesso_modulo_almox -> pode_almox_modulo (entra no módulo almox)
- acesso_chaves       -> pode_chaves
- acesso_extintores   -> pode_extintores
- acesso_colaboradores-> pode_colaboradores / pode_gerir
- acesso_solicitar    -> pode_solicitar
- acesso_visualizador -> só leitura (is_viewer)

E FAZER (quando autorizar): as propriedades de permissão (is_admin, pode_*) passarem a derivar das
TAREFAS do Perfil do colaborador (não mais do campo papel fixo). Migrar os colaboradores atuais:
Admin->perfil com acesso_admin; Almoxarifado->acesso_almoxarife (+módulos); Solicitante->acesso_solicitar;
Visualizador->acesso_visualizador; Colaborador diverso->sem acessos administrativos.
CUIDADO: mexe em login/permissão — testar cada papel e cada colaborador existente mantendo acesso.
Nota: manter compatibilidade — se um colaborador ainda não tem Perfil novo, cair no comportamento antigo
até a migração rodar, para ninguém ficar sem acesso no deploy.

### 20.3 CORREÇÃO DE ENTENDIMENTO (substitui 20.1 e 20.2) — Perfil 100% por permissões granulares
O Antonio NÃO quer "papéis" como Almoxarifado/Admin (nem como rótulo, nem como checkbox que já traz poderes).
MODELO FINAL desejado:
- Um único conceito: PERFIL DE ACESSO (cadastrável). O colaborador tem um Perfil.
- O que o Perfil pode = SOMENTE a soma das PERMISSÕES GRANULARES que o Antonio marca ao criar/editar o perfil.
- Não existe mais "nível de acesso"/PAPEIS_COLAB. Nada de poderes embutidos por nome. Ex.: se ele cria um
  perfil "Almoxarifado", é ELE quem marca os checkboxes que definem o que esse perfil pode.

PERMISSÕES GRANULARES (checkboxes) — derivadas do que o sistema controla hoje (is_admin, is_almox, pode_*):
Grupo "ACESSO E PERMISSÕES":
- perm_modulo_almox     -> entrar no módulo de almoxarifado (pode_almox_modulo)
- perm_chaves           -> acessar/gerenciar chaves (pode_chaves)
- perm_extintores       -> acessar/gerenciar extintores (pode_extintores)
- perm_colaboradores    -> ver/cadastrar/editar colaboradores (pode_colaboradores + pode_gerir)
- perm_perfis           -> gerenciar Perfis de acesso
- perm_aprovar          -> aprovar/reprovar solicitações
- perm_cotacao          -> enviar cotações
- perm_solicitar        -> criar solicitações (pode_solicitar)
- perm_cadastros        -> acessar cadastros (empresas/tipos/cidades/etc.)
- perm_relatorios       -> ver relatórios / central
- perm_log              -> ver log do sistema
- perm_backup           -> baixar backup
- perm_total            -> PODER TOTAL (equivale ao admin de hoje) — só um checkbox, sem rótulo especial

IMPLEMENTAÇÃO (quando o Antonio autorizar; NÃO EXECUTAR AINDA):
1) Adicionar as permissões acima em TAREFAS_PERFIL (grupo ACESSO E PERMISSÕES), não-futuras.
2) Reescrever as propriedades de permissão do Colaborador para DERIVAR das tarefas do seu Perfil:
   is_admin = perm_total; pode_almox_modulo = perm_total or perm_modulo_almox; pode_chaves = ...; etc.
3) Colaborador passa a ter Perfil (PapelColaborador) no lugar do campo papel fixo. Remover PAPEIS_COLAB da UI.
4) MIGRাção dos colaboradores atuais (mapear papel antigo -> perfil equivalente com as permissões certas):
   admin->perm_total; almoxarifado->perm_modulo_almox+chaves+extintores+colaboradores+solicitar(+cadastros/relatorios);
   solicitante->perm_solicitar; visualizador->(nenhuma de escrita); colaborador diverso->nenhuma administrativa.
5) SEGURANÇA anti-lockout: enquanto um colaborador não tiver Perfil novo, cair no comportamento antigo;
   garantir que o próprio Antonio (admin master) NUNCA perca acesso (fallback do e-mail dele para perm_total).
6) Testar login + cada permissão + cada colaborador existente mantendo acesso. Backup do Neon antes.

### 20.3 STATUS — Perfil por permissões granulares IMPLEMENTADO ✓
- TAREFAS_PERFIL ganhou grupo "Acesso e permissões" (perm_total, perm_modulo_almox, perm_chaves,
  perm_extintores, perm_colaboradores, perm_perfis, perm_aprovar, perm_cotacao, perm_solicitar,
  perm_cadastros, perm_relatorios, perm_log, perm_backup) — todas selecionáveis.
- Colaborador: permissões (is_admin, is_almox, pode_*) agora DERIVAM das tarefas do Perfil (self.papel
  guarda o NOME do perfil). Fallback anti-lockout: sem perfil correspondente, mantém acesso antigo.
- Dropdown do colaborador (novo/editar) lista os Perfis cadastrados (PapelColaborador), não mais PAPEIS_COLAB.
- _seed_perfis_padrao no boot: cria/preenche ADMIN(perm_total), ALMOXARIFADO(módulo+chaves+ext+colab+...),
  SOLICITANTE(solicitar), VISUALIZADOR(vazio), COLABORADOR DIVERSO(solicitar). Se já existir e estiver VAZIO,
  preenche; se já configurado, NÃO toca. Assim colaboradores com papel antigo não perdem acesso.
- Usuario (login staff, ex.: Antonio admin) NÃO afetado — segue pelo papel próprio. Sem risco de lockout do admin.
- Testado: perfis-padrão ok, almox/admin/solicitante derivam certo, perfil custom concede só o marcado,
  admin intacto, telas 200, grupo de permissões aparece.
- OBS: PAPEIS_COLAB ainda existe no código (não usado na UI). Limpeza opcional depois.

### 20.4 Perfis de acesso: filtro por nome + mostrar só ativos por padrão
- Campo de busca no topo da lista (filtra por nome, sem acento/maiúsculas).
- Ao abrir, exibir só perfis ATIVOS; opção (checkbox/toggle) para "mostrar inativos".

### 20.5 Importação em lote (CSV) — Colaboradores e Empresas/Fornecedores
- Formato CSV (UTF-8; abre/salva no Excel; sem dependência extra no Render).
- Botão "Importar CSV" nas telas de Colaboradores e de Empresas e Fornecedores + link p/ baixar MODELO.
- Regras iguais ao manual: nome/campos em MAIÚSCULA (upper), acento preservado como hoje,
  CPF/CNPJ só números e únicos. Perfil do colaborador opcional (nome de um Perfil existente).
- Comportamento: PULAR linhas duplicadas/erradas e mostrar RESUMO (quantas criadas, quantas puladas e por quê).
- Colaboradores CSV: nome;cpf;email;empresa;cargo;perfil
- Empresas/Fornecedores CSV: razao_social;nome_fantasia;cnpj;email;telefone;cidade;estado;tipo(empresa|fornecedor)

### 20.5 STATUS — Importação em lote (CSV) IMPLEMENTADA ✓
- Colaboradores: rotas colaboradores_modelo_csv + colaboradores_importar; botão "Importar CSV" + modal
  com link do modelo. Colunas nome;cpf;email;empresa;cargo;perfil. Nome/empresa/cargo -> UPPER; CPF só
  números e único; perfil opcional (nome de Perfil existente, senão COLABORADOR DIVERSO). Pula duplicado/sem
  nome-cpf e mostra resumo.
- Empresas/Fornecedores: rotas fornecedores_modelo_csv + fornecedores_importar; botão + modal + modelo.
  Colunas razao_social;nome_fantasia;cnpj;email;telefone;cidade;estado;tipo(empresa|fornecedor). UPPER nos
  nomes; CNPJ só números e único (pula duplicado). tipo define is_empresa_interna/is_fornecedor.
- CSV UTF-8 com BOM (Excel abre com acento certo); detecta separador ; ou ,; aceita latin-1 no fallback.
- Testado: modelos 200, criação em MAIÚSCULA, perfil aplicado, duplicados/erros pulados (colab e forn).

### 20.6 Modelo de importação em .xlsx (Excel de verdade)
- Trocar modelo baixável de CSV para .xlsx (abre em colunas, mais fácil de preencher). Header em negrito.
- Importação aceita .xlsx E .csv (detecta pela extensão). Regras iguais (UPPER, CPF/CNPJ únicos, pular+resumo).
- Adiciona openpyxl ao requirements (usado para gerar/ler xlsx).

### 20.6 STATUS — Modelo em .xlsx ✓
- openpyxl adicionado ao requirements. Helpers _gerar_xlsx e _ler_planilha (xlsx/csv) no almox.py.
- Modelos agora baixam em .xlsx (cabeçalho negrito, colunas largas). Importação aceita .xlsx E .csv.
- admin reusa os helpers via import lazy (sem import circular). Testado: modelos xlsx 200, import xlsx
  cria em MAIÚSCULA, perfil aplicado, empresa/fornecedor ok.

### 21. REGRA FIRME (reforçada) — SEMPRE parar e esperar OK do Antonio
A partir daqui: registrar no roadmap e PARAR. Só executar item quando o Antonio disser "pode executar".
Nunca emendar execução sem autorização explícita, mesmo dentro de uma mesma conversa.

### 21.1 PENDENTE (aguardando OK) — Filtros DENTRO de cada relatório da central
Hoje só o de extintores tem filtro (por prédio). Plano de filtros por relatório:
- CHAVES (relatorio_chaves + csv + pdf): filtro por STATUS (disponível/em uso), QUADRO, e busca por descrição.
  Aplicar os mesmos filtros na exportação CSV/PDF (via query string).
- MATERIAL — SALDO (materiais_saldo_csv + tela de saldo se houver): filtro por TIPO de material,
  LOCALIZADOR/armazém, e "abaixo do mínimo".
- MATERIAL — MOVIMENTAÇÕES (materiais_mov_csv/pdf): filtro por PERÍODO (data inicial/final),
  TIPO de movimento (entrada/saída/ajuste/mover), e produto.
- EXTINTORES (extintores_pdf + tela): manter prédio e ADICIONAR status (ok/atenção/vencido) e local.
- SOLICITAÇÕES/COMPRAS (histórico de preços, carga): filtro por PERÍODO e fornecedor (verificar o que já existe).
- Padrão de UI: uma barra de filtros no topo de cada relatório (datas, selects, busca) que reenvia via GET;
  os botões de exportar CSV/PDF herdam os mesmos filtros aplicados.
IMPLEMENTAÇÃO: fazer 1 relatório por vez, testado, e empacotar — começando pelo que o Antonio priorizar.

### 21.2 PENDENTE (aguardando OK) — Remover importação em lote de Empresas/Fornecedores
Decisão do Antonio: manter importação via Excel SOMENTE para Colaboradores.
Remover de Empresas/Fornecedores:
- admin.py: rotas fornecedores_modelo_csv e fornecedores_importar (e a const FORN_CSV_COLS, se sem uso).
- fornecedores.html: botão "Importar CSV" + modal #modalImportForn + link do modelo.
Manter intactos: importação de Colaboradores (rotas, modelo, botão/modal) e os helpers _gerar_xlsx/_ler_planilha
(continuam usados pelos colaboradores).
Testar: fornecedores.html abre 200 sem o botão/modal; colaboradores segue importando normal.

### 21.3 PENDENTE (aguardando OK) — "Ver como perfil" (impersonar temporário) para o admin master
IDEIA: no menu do nome (canto sup. direito), o admin master escolhe um PERFIL cadastrado e passa a ver o
sistema COMO aquele perfil (permissões/menus daquele perfil), para validar o que cada perfil enxerga.

COMPORTAMENTO (seguro, sem lockout):
- É um "ver como" TEMPORÁRIO: por baixo continua sendo o admin master real. Não altera o usuário no banco.
- Guardar em sessão algo tipo session["ver_como_perfil"] = <nome do perfil>. Só o admin master pode ativar.
- Enquanto ativo: as permissões efetivas (is_admin, pode_*) passam a refletir as TAREFAS daquele perfil,
  MAS a capacidade de VOLTAR fica sempre garantida (o "voltar" não depende de permissão do perfil simulado).
- Banner fixo no topo: "Você está vendo como PERFIL X — Voltar ao meu acesso" (botão sempre visível).
- Escolha SOMENTE entre PapelColaborador cadastrados (ativos).

IMPLEMENTAÇÃO (quando autorizar):
- Rota admin: ativar_ver_como (POST, valida master + perfil existe) e sair_ver_como (POST, limpa sessão).
- Camada de permissão: um helper que, se session["ver_como_perfil"] setado E usuário é master, calcula
  is_admin/pode_* a partir das tarefas do perfil simulado; senão, comportamento normal.
  ATENÇÃO: a rota sair_ver_como e o banner NÃO podem depender das permissões simuladas (anti-lockout).
- base.html: dropdown do nome com submenu "Ver como perfil" (lista perfis) + banner quando ativo.
- Só master: guardar/checar current_user real (não o simulado) para permitir sair a qualquer momento.
- Testar: master ativa ver-como ALMOXARIFADO -> vê menu/permite só do perfil; consegue VOLTAR sempre;
  usuário não-master não acessa; nada é alterado no banco.

### 22. COLETOR — Reforma (MAQUETE entregue; implementação aguardando OK)
Pedidos do Antonio para o coletor:
1) Tema escuro igual ao sistema, com brandbook Serena (coral #FF5246, grafite, verde #32CAA0, Poppins).
2) Ao abrir p/ retirar material ou chave: NÃO abrir câmera. Ficar pronto p/ LER DIRETO (leitor físico) —
   aviso central "Leia o crachá". Botão p/ abrir câmera se o colaborador quiser.
3) Busca por nome = lista suspensa PESQUISÁVEL na parte de baixo (achar em qualquer parte do nome).
4) TODAS as listas suspensas do coletor pesquisáveis, casando em qualquer parte do nome.
5) BUG: ao fechar e reabrir, ficou salvo o último CPF — LIMPAR (não persistir CPF entre sessões).
6) A leitura "scanner-first + botão câmera" do colaborador também p/ MATERIAL e CHAVE (mesmo padrão).
7) Botão p/ quem acessa por notebook/desktop ver em moldura de celular/tablet (só desktop; esconder no mobile).
- AGORA: só maquete HTML (maquete_coletor.html) para o Antonio validar visual/fluxo. Implementar só após OK.

### 22.1 COLETOR — Unificar chave e material num fluxo só (maquete atualizada)
- Home do coletor: em vez de "Retirar chave/Retirar material" separados, ter "RETIRAR" e "DEVOLVER"
  (chave é tratada como um item). Manter Inventário e Mover material à parte.
- Fluxo: bipar crachá -> bipar item (chave OU material, mesmo campo) -> confirmar. Sistema reconhece pelo
  prefixo do QR (CH-/QUAD- = chave; demais = material) o que foi lido e trata conforme.
- Maquete atualizada p/ mostrar isso. Implementação no coletor real só após OK.

### 22.2 COLETOR — Localizador na retirada + fluxo em cesta (maquete)
- RETIRADA: crachá -> bipar LOCALIZADOR -> bipar ITEM -> item vai para a CESTA -> volta AUTOMÁTICO
  para o campo de bipar LOCALIZADOR (não para o item). Motivo: mesmo item em prateleiras diferentes;
  amarrar cada saída ao localizador certo evita erro de saldo entre localizadores.
- (Decisão do Antonio: localizador só na RETIRADA por enquanto.)
- PONTO A RESOLVER DEPOIS (registrado, não decidido): na DEVOLUÇÃO e na ENTRADA o item também vai a um
  localizador; definir se bipa localizador nesses casos ou o sistema decide o destino do saldo.

### 22.3 COLETOR — ENTRADA de itens comprados (maquete)
Nova opção "ENTRADA" no coletor (dar entrada do que foi comprado):
- Ler CÓDIGO DE BARRAS do item. Se o código já estiver amarrado a um item comprado antes,
  PUXA as informações automaticamente; o almoxarife só finaliza.
- Campos da entrada:
  - Código do item OU nome (também via leitura de código de barras)
  - Quantidade
  - Valor unitário
  - Fornecedor: com opção "N/D" (não informar). Se veio do código de barras, puxa o fornecedor do
    último cadastro daquele código.
  - Opcionais (aparecem conforme marcado no CADASTRO-RAIZ do item):
    TAG (se em branco, sistema gera automático), CA, Validade, Validade de calibração, Lote.
- CADASTRO x ENTRADA (conceitos):
  - CADASTRO = criar o item na lista de itens disponíveis (cadastro-raiz; define quais opcionais existem).
  - ENTRADA = escolher um item já existente na lista e dar entrada (qtd/valor/nota).
- Se tentar dar ENTRADA em item NÃO cadastrado: abrir a tela de CADASTRO na hora e cadastrar,
  MAS o item novo fica PENDENTE e só fica disponível após APROVAÇÃO de admin/admin master.
- (Tela de cadastro-raiz do item: detalhar em item próprio — Antonio vai falar dela.)
- Maquete: adicionar botão ENTRADA na home + tela de entrada com código de barras, campos e opcionais.

### 22.4 COLETOR — Ajustes (maquete refeita)
ENTRADA: o campo não é "Fornecedor" e sim FABRICANTE, vindo de uma LISTA DE FABRICANTES (novo cadastro
na seção Cadastro). Manter opção N/D; se veio do código de barras, puxa o fabricante do último cadastro.
-> Incluir "Fabricantes" como cadastro (item a criar na seção Cadastro).

INVENTÁRIO: NÃO lê colaborador. Fluxo: bipa LOCALIZADOR -> abre a lista de itens daquele localizador ->
almoxarife ajusta a quantidade de cada item; OU bipa o QR de um item específico e a lista filtra só ele.
- Se o inventário DIMINUIR itens (baixa), precisa de APROVAÇÃO do ADMIN.
- GUARDAR histórico dos inventários (ajustes, principalmente as baixas) para consultar PERDAS por período.
  Criar uma tela/relatório de inventários/perdas acessível (Antonio quer acessar por ela).

MOVER MATERIAL: NÃO lê colaborador. Duas fases:
- Fase 1 (coletar): bipa LOCALIZADOR ORIGEM -> bipa ITEM (se houver 2+ no local, informar a QUANTIDADE a
  retirar) -> repete origem/item -> botão Finalizar -> vai para a CESTA.
- Fase 2 (destinar): tela mostra a cesta; almoxarife confere e APROVA. Em frente a cada localizador destino:
  marca (clica) os itens que quer mover -> bipa LOCALIZADOR DESTINO -> digita SENHA (a cada destino finalizado).
  Ao bipar destino: se o item já existe em OUTRO localizador, AVISO que BLOQUEIA até o almoxarife confirmar
  ciência; senão, aviso de "movidos com sucesso". Pode repetir em outros localizadores com o restante.

### 22.5 COLETOR — Entrada com Nota Fiscal (maquete coletor) + Administrativo/NF (desktop, roadmap)
COLETOR (maquete agora):
- ENTRADA ganha opcional "Há nota fiscal?".
  - SIM: puxa as NOTAS FISCAIS PRÉ-INFORMADAS para LINKAR ao item (busca por nº/fornecedor).
  - Se NÃO localizar a nota informada: informar MANUALMENTE Fornecedor (Vendedor) + Nº da Nota Fiscal.
  - Objetivo: rastreabilidade do item -> nota -> fornecedor.
  - Ao vincular/informar NF, SOBE NOTIFICAÇÃO no sininho para o admin classificar OPEX ou CAPEX.
  - Se foi informado MANUALMENTE (NF sem cadastro prévio): sobe notificação avisando "NF recebida sem
    cadastro prévio".

DESKTOP — nova seção "ADMINISTRATIVO" (maquete depois; implementação após OK):
- Tela de NOTA FISCAL: jogar o PDF ou XML da nota; o sistema LÊ e extrai: Fornecedor, número da nota,
  item(ns), valor, data de emissão.
- Após ler, o usuário FINALIZA o cadastro da nota informando OPEX ou CAPEX e, opcional, ORDEM DE COMPRA.
- Notificações (sininho do topo):
  - "Classificar OPEX/CAPEX" quando uma NF/entrada com nota é registrada.
  - "NF recebida sem cadastro prévio" quando fornecedor+NF foram informados manualmente na entrada.
- (Menu: criar seção Administrativo no menu lateral. Cadastro novo relacionado: Fabricantes — ver 22.4.)
PENDENTE: maquete do desktop (Administrativo/NF) — Antonio vai ver depois.

### 22.6 EXECUÇÃO DO COLETOR — BLOCO 1 (cadastros-base) IMPLEMENTADO ✓
- Model Fabricante (almox_fabricantes) + seed inicial (3M, CISER, SIEMENS, WEG, PADO, TRAMONTINA).
- ProdutoAlmox ganhou: codigo_barras, fabricante_id, pendente_aprovacao, e os flags do cadastro-raiz
  (opc_tag, opc_ca, opc_validade, opc_validade_calib, opc_lote) + propriedade opcionais_ativos.
- _light_migrate cria a coluna nova automaticamente; db.create_all cria a tabela de fabricantes.
- Cadastro de Fabricantes: lista + novo + editar + ativar/desativar + busca + mostrar inativos (rotas em almox.py,
  template fabricantes.html, item no menu base.html após Localizadores).
- Cadastro de item (materiais.html + material_novo): novos campos código de barras, fabricante e os
  checkboxes de opcionais. Rota salva tudo; tela materiais recebe fabricantes.
- Testado em cópia do banco real: tabela/colunas ok, telas 200, fabricante MAIÚSCULO sem duplicar,
  item salvando cod. barras/fabricante/opcionais certos.
PRÓXIMOS BLOCOS (a implementar, mesma leva): Retirar/Devolver (localizador+cesta) | Entrada (fabricante+NF) |
Inventário (câmera+senha+histórico de perdas) | Mover material (2 fases) | Ajuste de instâncias.
Depois: desktop Administrativo/NF + notificações.

### 22.7 EXECUÇÃO DO COLETOR — BLOCOS 2 e 3 IMPLEMENTADOS ✓
Models novos: NotaFiscalAlmox (numero, fornecedor, valor, data, ordem_compra, classificacao OPEX/CAPEX,
origem pre|manual|entrada) e NotificacaoAlmox (tipo, titulo, texto, ref_id, lida) para o sininho.
APIs novas do coletor:
- /coletor/api/localizador/<qr> (aceita qr_uid OU código A*1*3)
- /coletor/api/item/<qr> (unificado: reconhece CHAVE por CH-/QUAD-, senão MATERIAL)
- /coletor/api/buscar?tipo=colab|loc|item|fabricante|nf&q= (busca em qualquer parte do nome, sem acento)
- /coletor/api/retirar (cesta; material baixa saldo amarrado ao LOCALIZADOR; chave vira Em uso; valida saldo)
- /coletor/api/devolver (sem localizador; material soma saldo; chave volta a Disponível)
- /coletor/api/entrada (soma saldo; grava fabricante; NF vincular/manual/sem; gera notificações
  classificar_nf e nf_sem_cadastro; bloqueia entrada em item pendente)
- /coletor/api/item-pendente (cadastro rápido na entrada -> PENDENTE + notificação; indisponível até aprovar)
- /coletor/api/item-opcionais/<id> (opcionais do cadastro-raiz + fabricante do item)
UI: coletor.html reescrito no tema escuro Serena (Poppins/coral/verde), scanner-first (input que captura o
leitor + Enter) com botão de câmera opcional (html5-qrcode), listas pesquisáveis, RETIRAR (crachá->localizador->
item->cesta, pergunta quantidade se material) e DEVOLVER (crachá->item->cesta) + ENTRADA em 3 seções
(item/cód. barras, nota fiscal com seletor, opcionais do cadastro-raiz). Inventário/Mover/Ajuste = "em breve".
Testado: saldo baixa/soma certo, saldo insuficiente barrado, mov com localizador, chave em uso/devolvida,
entrada soma + fabricante, notificações NF, item pendente barra entrada; coletor 200; opcionais corretos.
FALTAM (mesma leva): Bloco 4 Inventário (câmera+senha+histórico de perdas) | Bloco 5 Mover (2 fases) |
Bloco 6 Ajuste de instâncias. Depois: desktop Administrativo/NF + sininho de notificações.

### 22.8 EXECUÇÃO DO COLETOR — BLOCO 4 (Inventário) IMPLEMENTADO ✓
- Model AjusteInventario (produto, localizador, saldo_antes/novo, diferenca, tipo baixa|acrescimo,
  status aplicado|pendente|reprovado, operador, decidido_por/em). Histórico p/ perdas.
- Coletor Inventário (SEM colaborador): bipa localizador -> lista os itens do localizador (via localizador_id)
  -> ajusta quantidade (−/+ ou digita) ou filtra um item por busca/bipe -> Salvar pede SENHA do almoxarife
  (current_user.check_senha) -> volta a ler novo localizador. Botão de câmera incluído.
- REGRA: acréscimo aplica na hora (mov inventario). BAIXA (redução) NÃO altera saldo; cria AjusteInventario
  status pendente + notificação; admin aprova em /inventario/pendentes (aplica saldo + mov) ou reprova.
- Relatório de PERDAS /relatorios/perdas: baixas aplicadas por período (de/até) + total. Menu: "Perdas de
  estoque" (Relatório) e "Baixas de inventário" (Movimento).
- Guards: aprovação = is_admin; perdas = pode_almox_modulo.
- Testado: itens do loc, senha errada barra, acréscimo aplica, baixa pendente, aprovação aplica, perdas lista.

### 22.9 BLOCOS 5 e 6 — dependem de FUNDAÇÃO de dados (a fazer com cuidado, próxima leva)
Descoberta ao implementar: ProdutoAlmox tem UM saldo e UM localizador. Para fazer 5 e 6 CORRETO falta:
- Bloco 5 (Mover) com aviso "item também existe no localizador ABC": exige SALDO POR LOCALIZADOR
  (mesmo item em várias prateleiras com quantidades separadas) -> novo model EstoqueLocalizador
  (produto_id, localizador_id, quantidade). Migração de dados do saldo/localizador atual.
- Bloco 6 (Ajuste de instâncias por TAG): exige INSTÂNCIAS por unidade -> novo model InstanciaItem
  (produto_id, localizador_id, tag, ca, validade, validade_calib, lote, quantidade).
Antonio avisado: é a maior mudança de dados da reforma; será feita testada e com backup, depois do bloco 4.

### 22.10 FUNDAÇÃO (autorizada) — saldo por localizador + instâncias por unidade
Antonio autorizou. Fazer em passos testados, aditivo/reversível (campos antigos viram espelho):
- Model EstoqueLocalizador (produto_id, localizador_id, quantidade). Saldo total do item = SOMA.
  UniqueConstraint (produto_id, localizador_id). Passa a ser a fonte da verdade do estoque.
- Model InstanciaItem (produto_id, localizador_id, tag, ca, validade, validade_calib, lote, quantidade).
- MIGRAÇÃO (uma vez, no boot): para cada ProdutoAlmox com saldo e localizador_id, cria EstoqueLocalizador
  correspondente se ainda não existir. Itens com saldo mas SEM localizador -> localizador "não atribuído"
  (ou mantém em local_id). NÃO apagar saldo/localizador_id antigos (espelho de segurança).
- Recalcular saldo do produto como soma dos EstoqueLocalizador (propriedade/força), mantendo compatibilidade
  com telas que leem produto.saldo.
- Depois: adaptar retirar/entrada/inventário para mexer no EstoqueLocalizador do localizador certo.
- Só então: BLOCO 5 (Mover entre localizadores, aviso "existe em ABC") e BLOCO 6 (Ajuste por instância/TAG).
- Backup do Neon antes do deploy que roda a migração.

### 22.11 FUNDAÇÃO — PASSO 1 (models + migração) IMPLEMENTADO E TESTADO ✓
- Models EstoqueLocalizador (produto+localizador->quantidade, unique) e InstanciaItem (tag/ca/validade/
  validade_calib/lote/quantidade) criados.
- ProdutoAlmox ganhou métodos: linhas_estoque(), recalcular_saldo(), estoque_em(loc), ajustar_estoque(loc,delta)
  (não deixa negativo; atualiza saldo total). saldo do produto continua existindo como TOTAL/espelho.
- _migrar_estoque_localizador() no boot: cria 1 linha de EstoqueLocalizador por produto legado (saldo+localizador),
  sem localizador -> "não atribuído". Idempotente. NÃO apaga saldo/localizador_id antigos.
- Testado: migração preserva saldo (com e sem localizador), idempotente, saldo antigo intacto; métodos
  ajustar/recalcular/multi-localizador corretos.
PRÓXIMO PASSO (fundação parte 2): adaptar retirar/entrada/inventário para mexer no EstoqueLocalizador do
localizador certo; depois BLOCO 5 (Mover entre localizadores + aviso "existe em ABC") e BLOCO 6 (Ajuste por
instância/TAG usando InstanciaItem).

### 22.12 FUNDAÇÃO — PASSO 2 (operações por localizador) IMPLEMENTADO ✓
- RETIRAR: baixa no EstoqueLocalizador do localizador bipado; valida saldo DAQUELA prateleira (não do total);
  front-end envia localizador_id na cesta.
- DEVOLVER e ENTRADA: somam em "não atribuído" (localizador None) até serem movidos a uma prateleira (Bloco 5).
- INVENTÁRIO: lista saldo POR localizador (EstoqueLocalizador); ajuste/baixa referem-se àquela prateleira;
  AjusteInventario ganhou localizador_id; baixa aprovada aplica no localizador certo.
- Testado: retira baixa só a prateleira certa, outra intacta, total recalcula, barra por prateleira,
  devolve p/ não atribuído, inventário por prateleira, baixa pendente aplica no localizador ao aprovar.
PRÓXIMO: BLOCO 5 (Mover entre localizadores, 2 fases, quantidade, senha por destino, aviso "existe em ABC")
e BLOCO 6 (Ajuste de instâncias por TAG via InstanciaItem).

### 22.13 BLOCOS 5 e 6 IMPLEMENTADOS ✓ — REFORMA DO COLETOR COMPLETA
BLOCO 5 — Mover material (2 fases):
- API /coletor/api/estoque/<produto>/<loc> (qtd na prateleira) e /coletor/api/mover (nova; a antiga virou
  /coletor/api/mover-legado). Fase 1: bipa origem -> bipa item (pergunta qtd se 2+) -> cesta. Fase 2: marca
  itens, bipa destino, SENHA do almoxarife por destino. Se o item já existe em OUTRO localizador -> aviso
  BLOQUEIA (needs_confirm) até "ciente". Aplica ajustar_estoque(origem,-q)+(destino,+q); mov movimentacao.
- Testado: avisa conflito (lista prateleira), aplica com ciente, origem baixa/destino sobe/outra intacta,
  sem conflito aplica direto, senha barra.
BLOCO 6 — Ajuste de instâncias (InstanciaItem):
- API /coletor/api/instancias/<produto>/<loc> (instâncias + opcionais do cadastro-raiz + saldo no loc) e
  /coletor/api/instancia-salvar. Lê localizador -> item -> escolhe unidade (ou cria do estoque) ->
  "quantas unidades receberão o ajuste?" -> edita só os campos habilitados no cadastro-raiz -> SENHA.
  SPLIT: ajustar N<Q separa N numa nova instância. NÃO mexe na quantidade de estoque.
- Testado: cria instância, split (1 de 3 -> 2+1 com TAG nova), não mexe no estoque, senha barra.
UI: coletor.html com Mover e Ajuste ligados (fim dos "em breve"). Todas as funções conferidas, coletor 200.
=> COLETOR REFORMADO 100% no backend+UI. Falta (fora do coletor): desktop Administrativo/NF + sininho de
notificações (22.5) — quando o Antonio quiser.

### 22.14 DESKTOP ADMINISTRATIVO + SININHO IMPLEMENTADO ✓
- NotaFiscalAlmox ganhou itens_json; origem agora inclui "importada".
- Sininho (base.html): context processor inject_status calcula n_notif_almox (NotificacaoAlmox não lidas);
  incluído no total do sininho do topo e como item "🔔 N notificação(ões) do almoxarifado".
- Seção "Administrativo" no menu (admin): "Notas fiscais (OPEX/CAPEX)" e "Notificações" (com contador).
- Rotas (almox.py, @is_admin): /notificacoes (+ /<id>/lida), /administrativo (dashboard),
  /administrativo/notas (lista a classificar + classificadas), /administrativo/notas/importar
  (XML NF-e -> _parse_nfe_xml auto-preenche numero/fornecedor/valor/data/itens; PDF -> cria p/ preencher,
  best-effort honesto), /administrativo/notas/<id> (ver), /administrativo/notas/<id>/classificar
  (OPEX/CAPEX + ordem de compra; marca notificações classificar_nf da nota como lidas).
- _parse_nfe_xml: remove namespace SEFAZ; lê ide/nNF, dhEmi, emit/xNome, total/ICMSTot/vNF, det/prod.
- Testado: XML lê tudo, gera notificação, classificar salva+marca lida, PDF cria p/ preencher, telas 200,
  todas as páginas-chave do sistema sobem 200, menu com Administrativo.
LIMITAÇÃO HONESTA: leitura de PDF (DANFE) é best-effort (cria a nota p/ preenchimento manual). XML é completo.
=> Reforma do coletor (6 blocos + fundação) + Administrativo/NF + sininho: TUDO ENTREGUE.

### 22.15 COLETOR — ÍCONES MINIMALISTAS (refeito) ✓
- Substituídos TODOS os emojis do coletor por ícones SVG de traço minimalistas (sprite <symbol> no topo):
  retirar, devolver, entrada, inventario, mover, ajuste, badge(crachá), pin(localizador), scan(item/QR),
  barcode, camera, search. stroke=currentColor (herdam coral/verde do tema).
- HTML: cards da home, pulsos estáticos, botões de câmera, placeholder de busca.
- JS: helper icoSvg(n)/pinIco(); pulsos dinâmicos (fIc/mvIc/ajIc) e badges de localizador passam a usar
  innerHTML com <svg><use>. Zero emojis restantes; coletor 200; 6 cards com .aic.
NOTA (regra de senha do colaborador): CONFIRMADA valendo — 1º uso em Retirar/Devolver define a senha
(mín. 4 dígitos) via _valida_senha_colab; depois valida sempre. (Aviso de "primeiro uso" só aparece hoje
ao errar; oferecido deixar explícito na 1ª tela se o Antonio quiser.)

### 22.16 HOME DO ALMOXARIFADO — tela antiga removida ✓
- home.html reescrita: removida a grade antiga de "tópicos" e TODOS os itens "Em construção"
  (Painel, Entrada, Devolução forçada, Inventário antigo, Ajuste, Produto, Unidades, Kit, Consulta,
  Movimentações, Etiquetas, QR, Log). Endpoint almox.home mantido (é landing pós-login e alvo dos
  botões "← Almoxarifado").
- Nova home = resumo do dia a dia (chaves em uso, extintores, material abaixo do mínimo, pendências) +
  seção "Atalhos" só com telas atuais (Coletor, Material, Movimentações, Fabricantes, Chaves, Extintores,
  Colaboradores, Central de relatórios, Administrativo), cada uma respeitando a permissão do usuário.
- Sair do coletor cai nessa home limpa. TOPICOS/em_construcao viraram código morto (não linkado).
- NOTA: o que o Antonio viu "antigo" no site é a versão em produção (pré-reforma); some após o deploy.

### 21.3 "VER COMO PERFIL" IMPLEMENTADO ✓ (autorizado)
- Só o admin MASTER ativa (botão "👁️ Ver o sistema como este perfil" em cada perfil ativo na tela de Perfis).
- session["ver_como_perfil"] guarda o NOME do perfil; nada é gravado no banco.
- Permissões efetivas: helper _efetivo(prop) usa as tarefas do perfil simulado (mapa is_admin=perm_total,
  pode_almox_modulo/is_almox=perm_modulo_almox, pode_chaves, pode_extintores, pode_colaboradores,
  pode_solicitar; perm_total cobre tudo). is_master NUNCA é simulado (garante a saída).
- Guards (_guard/modulo_required) passam a usar _efetivo; se o perfil simulado não puder abrir a tela,
  em vez de 403 seco mostra tela amigável "não faz parte do perfil" (ver_como_bloqueado.html) com "Voltar".
- Banner fixo no topo do conteúdo enquanto simula: "Você está vendo como PERFIL X — Voltar"
  (link para /ver-como/sair, que é login_required apenas => ANTI-TRAVAMENTO, não depende do perfil simulado).
- Menu lateral (base.html) passa a usar 'perm.*' (permissões efetivas) via app_context_processor -> o preview
  reflete o que o perfil enxerga; sininho do topo também.
- Testado: ativa, banner, menu reflete, tela admin bloqueada amigável, tela permitida abre, sair volta ao normal,
  e simular perfil SEM módulo ainda permite sair (anti-travamento).

### 21.1 FILTROS NOS RELATÓRIOS DA CENTRAL — CONCLUÍDO ✓
- Chaves: já tinha filtros (período/chave/colaborador/quadro/ação) + CSV/PDF herdando via **ctx. (ok)
- Movimentações de material: já tinha (produto/tipo/período) + CSV/PDF herdando. (ok)
- Saldo de material: NOVOS filtros de servidor (categoria, localizador, abaixo do mínimo) via helper
  _filtra_saldo() compartilhado; tela de materiais ganhou formulário; botão "Saldo (CSV)" herda com **ctx.
- Extintores: PDF passou a herdar TODOS os filtros da tela (prédio/local/tipo/situação); botão do PDF
  carrega os 4 parâmetros.
- Observação: "Solicitações/Compras" (admin.precos etc.) fica no módulo admin, fora do escopo do almox.

### 21.2 REMOVER IMPORTAÇÃO DE EMPRESAS/FORNECEDORES — CONCLUÍDO ✓
- Removidas rotas admin.fornecedores_modelo_csv e admin.fornecedores_importar + const FORN_CSV_COLS
  (e imports órfãos). Botão "Importar CSV" e modal #modalImportForn retirados de admin/fornecedores.html.
- Importação em lote agora só para Colaboradores. Testado: rotas 404, tela sem botão, sem referências órfãs.

=> ITEM A (construção) concluído: 21.1, 21.2 e 21.3 (Ver como perfil) entregues.
PENDÊNCIA DE DECISÃO (não é bug): entrada/devolução hoje somam em "não atribuído"; Antonio decide se a
ENTRADA deve perguntar o localizador. Aguardando.

### 22.17 CORREÇÃO — permissões granulares não refletiam no menu/acesso ✓
Sintoma (Antonio): colaborador com perfil COLABORADOR DIVERSO marcado com chaves/extintores granulares
via só "Minhas solicitações" no menu.
Causa: propriedades pode_chaves/pode_extintores/pode_almox_modulo derivavam só das chaves GROSSAS
(perm_chaves/perm_extintores/perm_modulo_almox), mas os perfis usam tarefas GRANULARES (chave_ver,
chave_retirar_devolver, ext_ver, ...). Mismatch => tudo False.
Correção:
- models.py: fonte ÚNICA perm_from_tasks(perms, prop) + grupos _GRUPO_CHAVES/_EXT/_MAT/_LOC. Honra grossas
  E granulares. Novas regras: pode_chaves=qualquer chave_*/perm_chaves; pode_extintores=qualquer ext_*;
  pode_material=qualquer mat_*; pode_almox_modulo=qualquer tarefa do módulo; is_almox=material/recebimento
  (mat_* ou perm_modulo_almox) — separado de pode_almox_modulo.
- Colaborador usa perm_from_tasks; +propriedade pode_material. Usuario (staff) ganhou pode_material.
- "Ver como" (_efetivo) usa a MESMA perm_from_tasks; +pode_material no objeto perm.
- base.html menu não-admin: Chaves gateada por pode_chaves, Extintores por pode_extintores, +Coletor
  (pode_almox_modulo), Material/Chegadas/Notinhas por pode_material, Relatório por pode_almox_modulo.
- Testado: colaborador chaves/ext vê Chaves+Extintores+Coletor (não Material/Chegadas); perfil material vê material.
NOTA/limite: quem tem qualquer permissão do módulo consegue ENTRAR no módulo (necessário p/ Coletor);
telas de material no desktop ainda são gateadas por pode_almox_modulo (alcançáveis por URL). Se o Antonio
quiser murar 100% (perfil de chaves não acessar material nem por URL), gatear rotas de material por
pode_material numa próxima leva.

### 22.18 CORREÇÃO — "Ver como" travado + vazamento de material/relatórios ✓
Problema A: botão "Ver como perfil" nunca aparecia porque definir_admin.py definia papel=admin
mas NUNCA marcava is_master=True. Corrigido: definir_admin.py agora seta eu.is_master=True (e remove
is_master de qualquer outro usuário -> master único). Roda no boot, então basta o próximo deploy.
Problema B (efeito colateral do 22.17): como pode_almox_modulo virou "qualquer tarefa do módulo",
as telas de material, locais físicos e a Central de relatórios (todas guardadas por pode_almox_modulo)
passaram a ser alcançáveis por perfil só de chaves/extintores.
Correção: novas permissões derivadas pode_locais (loc_*/perm_cadastros) e pode_relatorios
(perm_relatorios/carga_*). Guardas trocados (31 rotas): material/fabricantes/locais-de-material/
inventário/perdas -> pode_material; plantas/armazéns/localizadores/gerar -> pode_locais;
Central de relatórios -> pode_relatorios. Menu não-admin: seção Relatório só com pode_relatorios
(Central) e is_almox (etiquetas/carga). Colaborador e Usuario ganharam pode_locais/pode_relatorios;
objeto perm do "Ver como" também.
Testado: colaborador chaves/ext recebe 403 em material/saldo-csv/central/perdas/localizadores (menu e URL),
mantém Chaves/Extintores/Coletor; master vê o botão Ver como, banner ativa, central bloqueada amigável
ao simular chaves-only, e "Voltar" funciona.
ALERTA DEPLOY: este deploy roda definir_admin.py no boot (marca is_master). Fazer backup do Neon antes.

===================================================================
## 23. AUDITORIA DE PERMISSÕES POR PERFIL + AJUSTES (aguardando "pode executar")
Antonio está auditando perfil a perfil e enviará PDFs mostrando o que está marcado/desmarcado
em cada um. Perfis cadastrados hoje: Auxiliar de Almoxarifado, Colaborador Diverso, Solicitante,
Ronda/Porteiro. NADA executado ainda — registrar e esperar autorização. Os PDFs vão refinar
exatamente quais TAREFAS cada perfil tem, para casar com a checagem granular.

### 23.1 MECANISMOS DE PERMISSÃO A AJUSTAR (valem para todos os perfis)
Estes são problemas de CÓDIGO (menu/rotas), não só de marcar/desmarcar no perfil:

(a) "Minhas solicitações" hoje aparece SEMPRE no menu não-admin (fixo). Deve passar a depender de
    permissão de solicitação (ex.: solicitar_ver_minhas / pode_solicitar). Sintoma: RONDA/PORTEIRO
    está vendo "Minhas solicitações" e conseguindo criar solicitação de material sem poder.
    -> Gatear "Minhas solicitações" (menu + rota solicitante.index) por permissão de solicitação.
    -> Gatear criação de solicitação (solicitante.nova / POST) por pode_solicitar, e conferir que
       Ronda/Porteiro sem solicitar_* realmente recebe 403.

(b) COLETOR hoje é liberado por pode_almox_modulo (= QUALQUER tarefa do módulo). Isso faz um perfil
    só de extintores enxergar/abrir o coletor, o que não deve. Criar permissão específica
    pode_coletor = perm_total OU tarefas que o coletor executa (chave_retirar_devolver,
    mat_entrada, mat_saida, mat_mover, mat_ajuste, mat_inventario). Gatear a rota /coletor e o item
    de menu "Coletor" por pode_coletor. (Extintores NÃO usa coletor -> perfil só de extintores não vê.)

(c) EXTINTORES com botões finos: hoje as ações caem no guarda amplo pode_extintores. Precisa
    enforcement granular por tarefa: "Cadastrar extintor" (ext_cadastrar) e "Desativar extintor"
    (ext_desativar) devem ser exigidas nas rotas correspondentes E os botões escondidos na tela de
    extintores quando o perfil não tiver a tarefa. (Ver / inspecionar / repor / conferir /
    baixar pendência seguem suas próprias tarefas.)

### 23.2 REGRAS POR PERFIL (confirmar com os PDFs que o Antonio vai enviar)
- RONDA/PORTEIRO: NÃO pode ver "Minhas solicitações" nem criar solicitação de material.
  (depende de 23.1(a) + o perfil não ter solicitar_*.)
- COLABORADOR DIVERSO: NÃO pode "Minhas solicitações", NÃO pode Chaves, NÃO pode Coletor.
  Em Extintores: NÃO pode "Cadastrar extintor" nem "Desativar extintor" (só as ações que tiver).
  (depende de 23.1(a),(b),(c) + retirar chave_* do perfil.)
- SOLICITANTE: retirar "Cadastrar extintor" e "Desativar extintor"; retirar acesso ao Coletor.
  (depende de 23.1(b),(c).)
- AUXILIAR DE ALMOXARIFADO: manter como está por enquanto.

### 23.3 AJUSTES GERAIS DE UI / FEATURES (junto da auditoria)
(1) Remover o item "Nova solicitação" do grupo Movimento no menu. Criação de solicitação fica só
    dentro de "Minhas solicitações" (como já existe hoje ali). [menu]
(2) FAQ: melhorar o conteúdo e aplicar o TEMA ESCURO (hoje deve estar fora do tema). [template FAQ]
(3) Remover o item "Novidades" do menu. [menu]
(4) CHAVES: incluir a opção de DESATIVAR uma chave (rota + botão + provável tarefa chave_desativar
    no perfil; hoje não existe "desativar chave"). [feature]
(5) QUADRO DE CHAVES = LOCALIZADOR: o quadro de chaves precisa ser tratado como um localizador para
    o colaborador conseguir ler o QR dele no coletor. Estrutural: vincular Quadro a um Localizador
    (ou emitir QR do quadro que o endpoint /coletor/api/localizador reconheça) para que bipar o QR do
    quadro no coletor abra as chaves daquele quadro. [estrutural — detalhar antes de executar]

NOTA: itens 23.1 e 23.2 devem ser validados com o "Ver como perfil" após implementados.

===================================================================
## 24. HOME POR PERFIL + DASHBOARD DE OVERVIEW (aguardando "pode executar")
Registrado a pedido do Antonio. NADA executado. Cada perfil acessa áreas diferentes, então a HOME e
o dashboard devem ser SENSÍVEIS À PERMISSÃO: nunca mostrar estoque/solicitações/números de área que o
perfil não pode ver (usar as permissões efetivas: perm.pode_* / is_admin, mesma base do "Ver como").

### 24.1 HOME repaginada (por permissão)
Trocar a home atual (lista de atalhos) por uma tela "o que fazer agora", em 3 camadas, cada bloco
condicionado à permissão:
(a) Saudação + AÇÕES RÁPIDAS contextuais: "Abrir coletor" (pode_coletor/pode_almox_modulo),
    "Minhas solicitações" (pode_solicitar), "Confirmar chegadas" (is_almox), "Nova solicitação"
    só se mantido (ver 23.3.1). Só aparecem os botões que a pessoa pode usar.
(b) PENDÊNCIAS da pessoa (cada uma atrás da sua permissão):
    - Baixas de inventário aguardando aprovação + NFs a classificar (pode_material / is_admin)
    - Extintores vencendo/vencidos (pode_extintores)
    - Chaves em uso / atrasadas (pode_chaves)
    - Solicitações a aprovar (perm_aprovar)
(c) MINI-INDICADORES (tiles) resumindo só o que a pessoa pode ver: itens abaixo do mínimo,
    chaves disponíveis, extintores no prazo, etc. Solicitante puro vê basicamente saudação + Minhas
    solicitações.
Observação: manter endpoint almox.home (é landing pós-login e destino do "Sair" do coletor).

### 24.2 DASHBOARD de overview (dentro de Relatório)
Nova tela (ex.: almox.dashboard) ligada na Central de relatórios e no menu Relatório, protegida por
pode_relatorios (admin vê tudo). Overview do sistema com cartões + gráficos simples, usando dados que
já existem:
    - Solicitações por status (abertas / aprovadas / negadas / atendidas)
    - Chaves: total, em uso, disponíveis, atrasadas
    - Extintores por situação (no prazo / próximo do vencimento / vencido) via _situacao_extintor
    - Material: itens cadastrados, abaixo do mínimo, baixas de inventário pendentes, valor de estoque
    - NFs a classificar (OPEX/CAPEX)
Opcional: blocos do dashboard também respeitarem permissão (perfil de relatório restrito vê só parte).
Definir antes de executar: gráficos inline (SVG/Chart.js) ou só cartões numéricos na 1ª versão.

### 24.1-ALT HOME "quiosque por perfil" (alternativa à 24.1)
Alternativa registrada a pedido do Antonio (decidir qual seguir na hora de executar).
Conceito: a home COLAPSA na ação principal do perfil, em vez de ser um painel:
- Perfil restrito de campo (Ronda, Colaborador Diverso): tela enxuta, botão GIGANTE central
  "Abrir Coletor" (tocável de primeira, sem rolar), nada de estoque/relatório.
- Solicitante puro: cai direto em "Minhas solicitações" com "+ Nova" em destaque.
- Almoxarife/admin (perfil amplo): hub com 3-4 cartões grandes só das áreas que pode.
Regra: quanto mais restrito o perfil, mais a home vira "ação única"; quanto mais amplo, mais vira hub.
Prós: rápido, mobile-first, zero fricção no campo, não monta blocos fora da alçada.
Contras: mostra menos "visão geral" (compensado pelo dashboard 24.2).
HÍBRIDO possível: quiosque para perfis de 1 ação + painel de pendências (24.1) para perfis amplos;
a home escolhe o formato pela permissão efetiva.
=> DECISÃO PENDENTE: seguir 24.1 (painel de pendências), 24.1-ALT (quiosque) ou o híbrido.

### 23.1(d) COLETOR COM ESCOPO POR PERMISSÃO (refina 23.1(b))
Não basta liberar/bloquear o coletor inteiro — ele precisa respeitar as tarefas do perfil POR DENTRO:
- PORTEIRO/RONDA: coletor deve mostrar SOMENTE "Retirar" e "Devolver" chave (as demais abas —
  Entrada, Mover, Inventário, Ajuste, e retirar/entrada de MATERIAL — escondidas/bloqueadas).
- Se o perfil só tem chave_retirar_devolver, bipar um QR que NÃO seja quadro/chave (ex.: MAT-*,
  localizador de material, LOC-*) deve ser RECUSADO com mensagem clara ("Seu perfil só pode
  retirar/devolver chaves"). Ou seja, as APIs do coletor (/coletor/api/item, /localizador, /retirar,
  /devolver, /entrada, /mover, /instancia-salvar, /inventario...) devem checar a tarefa correspondente
  e negar QR/ação fora do escopo, não só esconder o botão.
Implica: mapear cada aba/rota-API do coletor a uma tarefa (retirar/devolver chave -> chave_retirar_devolver;
material -> mat_*; inventário -> mat_inventario; mover -> mat_mover; etc.) e filtrar as abas visíveis
no coletor.html conforme as permissões efetivas. Validar com "Ver como perfil".

### 23.4 RECONCILIAÇÃO COM OS PDFs (16/07) — marcado x desejado
Chaves de tarefa confirmadas: grupo COLETOR = col_chaves / col_material / col_movimentacao /
col_inventario (col_offline e col_ajustes = em breve). Extintores: ext_cadastrar / ext_desativar.
Solicitação: perm_solicitar (Acesso) + solicitar_criar / solicitar_ver_minhas / solicitar_ver_todas.

DEFINIÇÃO DE COLETOR (revisada, usar as tarefas dedicadas):
- pode_coletor = perm_total OU qualquer col_*  -> controla ver/abrir o coletor e o item de menu.
- Aba "Chaves" (retirar/devolver) = col_chaves ; Aba "Material" = col_material ;
  Aba "Mover" = col_movimentacao ; Aba "Inventário" = col_inventario.
- Incluir col_* em _GRUPO_ALMOX (para pode_almox_modulo, senão perfil só-coletor não entra na home).
- Rota /coletor passa a exigir pode_coletor (não mais pode_almox_modulo). APIs do coletor checam a
  tarefa da aba correspondente (23.1(d)).

AUXILIAR DE ALMOXARIFADO (51) — MANTER (Antonio confirmou). Tem tudo: chaves, extintores (incl.
cadastrar/desativar), material completo, coletor completo (col_chaves/material/movimentacao/inventario),
colaboradores, relatórios, solicitações (criar/ver/ver todas + carga). Nada a mudar.

RONDA/PORTEIRO (16) — marcado: perm_chaves, chave_ver, chave_historico, chave_qr,
chave_retirar_devolver, ext_ver/inspecionar/repor/conferir/desativar/pendencia/qr, col_chaves,
relatorio de chaves, log, FAQ. SEM tarefas de solicitação e SEM col_material.
  Regra desejada: coletor só chaves (OK: só col_chaves) + NÃO ver Minhas solicitações / NÃO solicitar.
  -> Depende do fix de CÓDIGO 23.1(a): hoje "Minhas solicitações" aparece fixo e a criação não está
     gateada, por isso Ronda cria solicitação sem ter solicitar_*. Após 23.1(a)+23.1(b)+23.1(d):
     Ronda fica certo SEM mudar marcação. (Extintores dele inclui desativar — decisão do Antonio,
     mantida.)

COLABORADOR DIVERSO (8) — marcado: chave_ver, chave_retirar_devolver, ext_ver/inspecionar/repor/
pendencia, FAQ, sugestão. SEM col_* (nenhum), SEM solicitar, SEM ext_cadastrar/ext_desativar.
  Regra desejada: NÃO Minhas solicitações (OK, sem solicitar -> resolvido por 23.1(a));
  NÃO coletor (OK: sem col_* -> resolvido por pode_coletor); em extintores NÃO criar/desativar
  (OK: ext_cadastrar/ext_desativar desmarcados -> resolvido por 23.1(c)).
  >>> CONTRADIÇÃO A RESOLVER NA UI: o Antonio disse "Colaborador Diverso NÃO pode chaves", mas o perfil
      está com "Ver chaves" e "Retirar/devolver chave (coletor)" MARCADOS. Para não ter chaves, o Antonio
      precisa DESMARCAR chave_ver e chave_retirar_devolver nesse perfil (ou confirmar se mudou de ideia).
      (Código não decide isso; é marcação.)

SOLICITANTE (10) — marcado: perm_solicitar, solicitar_criar, solicitar_ver_minhas,
solicitar_ver_todas, ext_ver/inspecionar/repor/pendencia/qr, FAQ. SEM col_*, SEM ext_cadastrar/desativar.
  Regra desejada: retirar criar/desativar extintor (OK: já desmarcados -> resolvido por 23.1(c),
  hoje os botões aparecem para qualquer pode_extintores = BUG a corrigir); retirar coletor
  (OK: sem col_* -> resolvido por pode_coletor). Nada a desmarcar; é fix de código.

RESUMO — o que é CÓDIGO (eu faço quando autorizar) x MARCAÇÃO (Antonio ajusta na UI):
  CÓDIGO: 23.1(a) gate de Minhas solicitações + criação por solicitar_*; 23.1(b) pode_coletor por
    col_*; 23.1(c) botões/rotas de ext_cadastrar/ext_desativar por tarefa; 23.1(d) escopo do coletor
    por aba/col_*; + incluir col_* em _GRUPO_ALMOX.
  MARCAÇÃO (Antonio): desmarcar "Ver chaves" e "Retirar/devolver chave" no COLABORADOR DIVERSO
    (se realmente não pode chaves).

### 23 — EXECUTADO (16/07) ✓
Auditoria com os PDFs mostrou que 23.1(a) solicitações, 23.1(b) pode_coletor por col_*, 23.1(d)
escopo do coletor por aba, 23.3.1 (remover Nova solicitação do menu) e 23.3.3 (remover Novidades)
JÁ estavam no código (sessão anterior do coletor). Nesta leva executei o que faltava:
- 23.1(c) EXTINTORES granular: extintor_novo e extintor_cadastro -> ext_cadastrar; extintor_desativar
  -> ext_desativar. Botões "Novo extintor" (lista) e "Desativar" (ficha) escondidos sem a tarefa.
  perm ganhou ext_cadastrar/ext_desativar/chave_desativar.
- 23.3.4 DESATIVAR CHAVE: nova tarefa chave_desativar (grupo Chaves, entra em _GRUPO_CHAVES). Rotas
  /chaves/<id>/desativar e /reativar (guard chave_desativar; chave "Em uso" não desativa). Lista de
  chaves ganhou filtro inativos=1, link "Ver desativadas (N)" e botões Desativar/Reativar por linha.
- 23.3.2 FAQ: reescrito no TEMA ESCURO Serena (acordeão grafite/coral/verde), conteúdo ampliado e
  agrupado (Solicitações, Coletor e QR, Chaves, Extintores, Material, Conta e acesso) + busca client-side.
Testado com os 4 perfis reais (Ronda, Colaborador Diverso, Solicitante, Auxiliar): coletor só nas abas
permitidas (API recusa QR fora do escopo), Minhas solicitações e criação gateadas, criar/desativar
extintor só com a tarefa, desativar/reativar chave, FAQ escuro, e smoke test das telas admin (todas 200).

### PENDENTE (não executado nesta leva — precisa de decisão sua)
- 23.3.5 Quadro de chaves = localizador (estrutural; preciso de definição de como o QR do quadro
  deve se comportar no coletor).
- 24.1 vs 24.1-ALT vs híbrido (formato da HOME) + 24.2 dashboard (cartões x gráficos; blocos por
  permissão?). Aguardando sua escolha para construir.
MARCAÇÃO pendente do Antonio na UI: desmarcar "Ver chaves" e "Retirar/devolver chave" no COLABORADOR
DIVERSO (se ele realmente não pode chaves).

### 24.1 HOME HÍBRIDA — IMPLANTADA ✓ (Antonio escolheu o híbrido)
- Rota almox.home reescrita: decide MODO por permissão efetiva.
  * "quiosque" (perfil de 1 ação): botão grande p/ a ação principal (ordem coletor>solic>chaves>
    extintores>material) + atalhos menores para as outras.
  * "painel" (amplo = admin OU pode_material OU pode_colaboradores OU >=2 áreas): saudação + ações
    rápidas + PENDÊNCIAS clicáveis + tiles clicáveis.
- Ações/pendências/tiles todos gated por permissão e com link de atalho:
  baixas de inventário a aprovar (admin -> inventario_pendentes), NFs a classificar (admin ->
  administrativo), extintores vencidos/vencendo (extintores?situacao=), abaixo do mínimo
  (materiais?baixo=1), chaves em uso (chaves).
- home.html reescrita (quiosque + painel) no tema escuro. Testado: só-coletor e só-extintores caem
  no quiosque; solicitante/ronda/admin no painel; atalhos com href corretos.

### 24.2 DASHBOARD — mockup v2 (com ATALHOS) para aprovação
Refeito conforme pedido do Antonio: TUDO é atalho (clicar em "Aguardando aprovação", numa fatia do
donut de extintores, num tile, etc. abre a lista já filtrada). Arquivo dashboard_mockup_v2.html.
DECISÃO PENDENTE p/ implementar de verdade: manter os gráficos (barras de status + donut de extintores
+ linha de entradas/saídas) ou começar só com cartões numéricos; e se os blocos respeitam permissão.
Mapa de destinos (quando implementar): status de solicitação -> solicitante.index?status=; extintores
por situação -> extintores?situacao=; tiles de material -> materiais (?baixo=1) / inventario_pendentes /
administrativo; chaves -> chaves(?status).

### 25. IDEIA "MEUS ITENS" (material/chave que está comigo) — REGISTRADA (aguarda decisão)
Ideia do Antonio: qualquer pessoa poder ver "o que está comigo" — material retirado por mim e chaves
em meu nome — independente de ter acesso amplo ao módulo. Parecer do Claude: FAZ MUITO SENTIDO e é de
baixo risco (é leitura só dos próprios registros, não expõe estoque/relatórios de terceiros). Proposta:
- Tela "Comigo" (ou bloco na home) por pessoa: lista chaves com status "Em uso" em nome dela + itens de
  material que ela retirou e ainda não devolveu (a partir das movimentações/retiradas do coletor).
- Visível a todos que usam o coletor (não precisa de pode_material/pode_chaves), pois mostra só o que é
  da própria pessoa. Ação rápida "Devolver" a partir dessa lista (respeitando as regras do coletor).
- Requer: garantir que retiradas de material registrem o responsável (colaborador) para poder filtrar
  "comigo"; hoje chaves têm com_quem; material precisa amarrar o responsável na retirada.
DECISÃO PENDENTE: confirmar o escopo (só chaves? chaves+material?) e se vira aba própria ou bloco na home.

### 24.2 DASHBOARD — IMPLANTADO ✓ (com gráficos e atalhos)
Rota almox.dashboard (_guard pode_relatorios). Dados REAIS: tiles (itens em estoque, abaixo do mínimo,
baixas pendentes [admin], unidades em estoque, NFs a classificar [admin]); solicitações por status
(barras, contagem dinâmica por status); extintores por situação (DONUT calculado no servidor:
NO_PRAZO/PROX_VENC/VENCIDO+IRREGULAR+EM_RECARGA); chaves (total/em uso); material entradas x saídas (7d).
TUDO clicável -> abre a tela filtrada: status -> solicitante.index?status=; extintores -> extintores?
situacao=; abaixo do mínimo -> materiais?baixo=1; baixas -> inventario_pendentes; NFs -> administrativo.
Sem campo de custo no material -> "Valor de estoque" virou "Unidades em estoque" (não inventa valor).
Ligado no menu Relatório (admin e não-admin, gated pode_relatorios) e botão no topo da Central.
Testado: 200 com dados, donut/barras/atalhos, e 403 para perfil sem relatórios.

### 26. BUG CORRIGIDO — solicitante errado (colaborador caía em usuário desativado) ✓
Sintoma (Antonio, prints): colaborador AMADEU criava solicitações (#44-47), mas a lista mostrava
"MAILTON MENESES" (usuário desativado) como solicitante.
Causa: Solicitacao.solicitante_id é FK p/ usuarios, mas nova() gravava solicitante_id=current_user.id.
Colaborador e Usuario têm ids independentes -> o id do colaborador (tabela almox_colaboradores)
colidia com o id de um usuário qualquer (Mailton). O log de sistema aparecia certo porque guarda
autor_nome (snapshot).
Correção:
- Solicitacao: solicitante_id agora NULLABLE; +solicitante_colab_id (FK almox_colaboradores) e
  +solicitante_nome (snapshot). Propriedade solicitante_display (nome snapshot -> colaborador -> usuário).
- nova(): detecta colaborador (via __tablename__), grava solicitante_colab_id + solicitante_nome e
  deixa solicitante_id nulo; usuário grava solicitante_id normalmente. LogSolicitacao ganhou autor_nome
  (autor_id nulo p/ colaborador) e autor_display.
- Templates (aprovacoes, dashboard admin, solicitacao, pendencias, index, detalhe) usam solicitante_display;
  histórico da solicitação usa autor_display.
- Migração no boot: DROP NOT NULL em solicitacoes.solicitante_id; ADD COLUMN automático; backfill
  _migrar_solicitante_nome() preenche solicitante_nome das antigas a partir do log de criação
  (AlmoxLog "#<id>: criada" -> autor_nome), caindo no usuário vinculado quando não há log. Idempotente.
- Filtro de solicitante na lista passou a listar só usuários ATIVOS (Mailton desativado some do filtro).
Testado (base nova): colaborador cria e aparece com o nome certo (não o usuário desativado); usuário
cria normal; backfill preenche as antigas pelo log; páginas admin/solicitante 200.
ALERTA DEPLOY: roda migração no boot (DROP NOT NULL + backfill). Backup do Neon antes.

### 27. FIX — "Solicitações" não aparecia para o ADMIN ✓
O item de solicitações só existia no ramo não-admin do menu (Minhas solicitações, por
pode_ver_solicitacoes). O admin (is_admin) via só "Aprovações", não a lista/painel de solicitações.
Correção: adicionado {{ item('solicitante.index','Solicitações') }} no topo do grupo Movimento do menu
admin. Auxiliar e Solicitante já viam "Minhas solicitações" (têm solicitar_ver_* -> pode_ver_solicitacoes).
Testado: admin vê "Solicitações" e abre; solicitante vê "Minhas solicitações"; ambos 200.

### 28. FIX — landing ia para /admin/ antigo, não para a home nova ✓
Login e botão "Início" mandavam o admin para admin.dashboard (painel antigo). A home híbrida
(almox.home) só era vista ao sair do coletor. Correção: _home_para() e o botão sb-home passam a mandar
todo mundo com acesso ao módulo (is_admin ou pode_almox_modulo) para almox.home; sem módulo -> solicitante.index.
admin.dashboard segue acessível por URL (não removido). Testado: admin cai na home híbrida; solicitante no painel.

### 29. FIX — situação duplicada de extintor + pendências unificadas na home ✓
(1) Filtro de extintores mostrava DUAS opções "Irregular / Vencido" (chaves VENCIDO e IRREGULAR têm o
    mesmo rótulo em SITUACAO_LABEL, e o dropdown iterava o dicionário). Agora há SITUACAO_OPCOES (lista
    sem duplicar) e helper _match_situacao: a opção "Irregular / Vencido" (valor VENCIDO) cobre tanto o
    vencido por data quanto o irregular operacional. Aplicado no filtro da tela e no PDF; o badge de cada
    linha continua mostrando o rótulo. Dashboard já linkava ?situacao=VENCIDO -> agora pega os dois.
(2) Home (painel): pendências agora unem extintores irregulares/vencidos E pendências de etiqueta
    (PendenciaEtiqueta abertas -> link almox.pendencias_etiqueta). Contagem de irregular/vencido alinhada
    ao filtro (VENCIDO+IRREGULAR).
Testado: filtro pega irregular e vencido, dropdown com opção única, home lista as duas pendências.

### 30. Extintor: item de conferência de datas + TH anual ✓
(1) Novo item na inspeção: "Data de recarga e teste hidrostático conferem com as datas do app?" (Sim/Não).
    Se "Não", abre campos para informar as datas corretas lidas no extintor (validade mes/ano + TH ano) e
    atualiza e.validade / e.teste_hidrostatico na hora, com log. Não marca irregular (é correção de dado).
    Registrado no itens_json da inspeção. Campos: item_datas, corr_mes_validade, corr_ano_validade, corr_ano_th.
    Prefill com as datas atuais do app. Helpers _parse_mmaaaa_campos / _parse_ano_campo.
(2) Teste hidrostático virou ANUAL (só ano). Guardado como 31/12 do ano (vale o ano todo). _parse_ano("th")
    em cadastro/reposição/troca; _th_label (só ano) em logs/obs/PDF; ficha, lista e cadastro mostram/pedem
    só o ano. Validade da carga (recarga) segue mensal (mês/ano).
Testado: TH anual em cadastro/reposição/ficha/lista; inspeção "Não" corrige validade e TH; "Sim" não altera.

### 31. Extintor irregular/vencido: reposição disponível + botão "Feito a reposição" ✓
- No estado IRREGULAR/VENCIDO, além de "Levado ao Almox D6 p/ Recarga", agora tem "Fazer reposição
  (troca programada)" (form formRepoIrr, checklist prefixo repoirr, mesma rota extintor_reposicao).
- Botão que efetiva a troca renomeado de "Confirmar reposição" para "Feito a reposição" (nos dois
  estados: normal e irregular), pois representa a acao ja realizada.
Testado: ficha irregular mostra as duas opcoes e o botao; reposicao a partir do irregular atualiza
validade/TH e volta para No prazo.

### 32. IDEIA (Antonio) — confirmar chegada no D6 + etiqueta "PARA RECARGA" — REGISTRADA (mockup feito)
Passo novo no ciclo do extintor: apos "Levado ao Almox D6" (Em recarga), o ALMOXARIFADO bipa o QR para
CONFIRMAR que o extintor chegou no D6; com isso, imprime uma ETIQUETA com o LOCALIZADOR do extintor +
"PARA RECARGA", que acompanha o extintor ate a empresa de recarga (rastreabilidade + retorno ao local certo).
Parecer do Claude: bom checkpoint, encaixa como sub-estado do EM_RECARGA (ex.: "CHEGOU_D6"/aguardando
recarga) antes da conferencia de retorno. Mockup visual entregue: etiqueta_recarga_mockup.html (duas
opcoes de tamanho A/B + diagrama do fluxo + botao imprimir).
DECISAO PENDENTE p/ implementar: (a) tamanho da etiqueta (A termica ~62x40mm ou B A6); (b) campos extras
(classe de fogo, n serie, responsavel?); (c) confirmar o sub-estado e a rota de bipar/confirmar no coletor
e a rota de impressao da etiqueta. Localizador vem do cadastro do extintor (predio+local).

### 33. QR do extintor: novo visual + formato Bobina 45x20mm; etiqueta PARA RECARGA sem QR ✓
- Etiqueta "PARA RECARGA" (mockup): removido o QR (o extintor ja tem o proprio). Textos ajustados.
- extintores_qr.html reescrito: novo formato "Bobina 45x20mm (matricial)" alem de A4 e Termica.
  Cada etiqueta 45mm x 20mm, duas por linha (bobina ~ @page 96mm x 22mm, margin 1mm). Layout limpo:
  faixa preta lateral + QR 16mm + tag "EXTINTOR" + codigo (bold) + localizador (predio/local) +
  rodape "SERENA · CLUSTER DELTA". Monocromatico (imprime bem em termica/matricial).
Testado: os tres formatos renderizam com QR (200); bobina traz 45mm e @page 96mm 22mm.
PENDENTE (secao 32): implementar de fato o passo "confirma chegada no D6 + imprime PARA RECARGA"
(sub-estado do EM_RECARGA) apos Antonio escolher tamanho A/B e campos.

### 33.1 QR do extintor: Térmica = 45x20mm (padrão) + A4 grid ✓
Consolidado: a opcao "Etiqueta térmica 45×20mm" virou o formato padrao (2 etiquetas por linha, cada
45x20mm, @page 96x22mm) — tamanho padrao das etiquetas da Serena. Removida a antiga termica 3-col e o
nome "bobina"; agora sao só dois formatos: Térmica (padrao) e Folha A4 (grid). Rota extintores_qr default
mudou para "termica". Etiqueta PARA RECARGA (mockup) tambem no mesmo 45x20mm, 2 por linha, sem QR.

### 33.2 Etiqueta térmica do extintor: sem cabeçalho e local sem cortar ✓
- @page margin 0 (era 1mm) na termica -> o Chrome deixa de imprimir o cabecalho/rodape (data, titulo,
  URL, 1/126). Complemento: usuario deve desmarcar "Cabecalhos e rodapes" em Mais definicoes.
- Nome do local (loc) deixou de cortar: agora quebra em ate 2 linhas (line-clamp 2, sem nowrap/ellipsis).
  QR reduzido 16->15mm e ajuste de fontes/padding para caber o local completo em 45x20mm.

### 33.3 FIX CRÍTICO — QR do extintor quebrava após login (500) ✓
Sintoma (Antonio): ao ler o QR e logar, "quebrava o link". Causa: efeito colateral da secao 23.1(c) —
na ficha, o botao de desativar usava {% if perm.ext_desativar and not campo %}; no fluxo de CAMPO
(colaborador via QR) o objeto 'perm' nao e injetado (usuario nao autenticado via flask-login), e o Jinja
levantava UndefinedError ('perm' is undefined) -> 500 apos o login. Correcao: inverter para
{% if not campo and perm.ext_desativar %} (curto-circuito: em campo nao avalia perm). Testado com CSRF
ligado: colaborador loga pelo QR e ve a ficha (200); admin tambem; campo nao mostra botao desativar.
Obs.: o cabecalho/rodape da impressao (data/URL/1-126) e do navegador — desmarcar "Cabecalhos e rodapes"
em Mais definicoes; @page margin 0 ja aplicado.

### 33.4 QR do extintor: geração no navegador (performance) ✓
Antonio: tela de QR demorava a carregar. Causa real: o servidor gerava TODOS os QR (SVG via lib Python
qrcode) a cada abertura — com ~246 extintores ficava lento. (O formato nao era o problema: a pagina ja
renderiza só um formato por vez.) Correcao: QR passa a ser gerado no NAVEGADOR (lib qrcode-generator via
cdnjs), o servidor manda só os dados (data-url por etiqueta). Geracao em lotes de 40 p/ nao travar a UI;
aviso "Gerando QR codes...". Resposta do servidor caiu para ~0,03s (era proporcional ao nº de extintores).
QR renderizado como <img> com image-rendering:pixelated (nitido para leitura/impressao). Vale p/ termica e A4.

### 33.5 Etiquetas do extintor via PDF EXATO (resolve alinhamento na Elgin) ✓
Impressao pelo navegador em etiqueta recortada 2-up nao alinhava (Chrome nao respeita vaos; Elgin soltava
auto-teste). Solucao: rota /almoxarifado/extintores/etiquetas.pdf gera PDF no tamanho EXATO do rolo.
Medidas reais (Antonio): 2 colunas de 45x20mm, margem esq 2 / meio 2 / dir 1, vao entre linhas 3, liner 95mm.
Cada pagina PDF = uma linha (2 etiquetas). Padrao modo "gap" (pagina 95x20, sensor cuida do vao); modo
"continuo" (95x23, inclui o vao). QR gerado com reportlab (vetorial). Ajuste fino por querystring:
lw,lh,ml,gap,mr,rowgap,qr,dx,dy,modo. Botao "PDF exato (45x20, 2 colunas)" na tela de QR.
Testado: PDF valido, paginas 95x20 (gap) e 95x23 (continuo).
Instrucao de impressao: abrir o PDF, imprimir na Elgin a 100% (sem "ajustar a pagina"), margens 0.

### 33.6 FIX botão "Fazer reposição" (irregular) + PDF em nova aba ✓
- Bug: no estado Irregular/Vencido o botao "Fazer reposicao" nao abria o form. Causa: mostra(id) acessava
  sempre document.getElementById('formInsp'/'formRepo'), que nao existem nesse estado -> erro null.style.
  Corrigido: mostra() itera ['formInsp','formRepo','formRepoIrr'] com null-check (so mexe no que existe).
- PDF de etiquetas ja abre em NOVA ABA (link target=_blank + Content-Disposition inline) — nao baixa.

### 33.7 FIX — QR/PDF ignoravam o filtro + PDF estourava memoria (OOM) ✓
REGRA REAFIRMADA: registrar SEMPRE no roadmap primeiro; executar so quando autorizado; a regra volta
apos cada execucao.
(1) Botao "QR" e o PDF nao passavam o filtro (predio/local/tipo/situacao) -> abriam TODOS os extintores.
    Corrigido: helper _extintores_filtrados() (mesma logica da tela) usado pela tela de QR e pelo PDF;
    botao QR e links (formatos/PDF) repassam o filtro. _filtro_atual() monta os params.
(2) PDF dava 500 (WORKER TIMEOUT / SIGKILL out-of-memory) ao gerar ~246 QR com reportlab QrCodeWidget.
    Trocado por desenho leve: matriz do QR (lib qrcode) desenhada como retangulos com run-length no canvas
    (sem widget grafica). Cache por URL. Filtrado gera em ~0,3s; todos os 246 em ~2,3s sem estourar.
    Testado: filtro respeitado (DELTA6=23 na tela e no PDF=12 paginas); PDF de todos gera OK.
Obs.: durante a correcao houve um deslize (decoradores de rota caíram sobre um helper -> a rota devolvia
lista -> "Extintor is not JSON serializable"); corrigido, rota /extintores/qr unica e helper sem decorador.

### 33.8 Ajuste — "SERENA · CLUSTER DELTA" cortado na etiqueta PDF ✓
A linha de rodape estava a 1,4mm da borda inferior e a impressora cortava. Subida para 3,0mm do fundo
(base + 3.0mm). Continua ajustavel por dy na querystring se precisar.

### 34-37 — RECONSTRUIDOS apos reversao da pasta (20/07) ✓
A pasta de trabalho havia revertido para estado pre-34-37 (o zip 33.8 saiu incompleto). Reaplicados TODOS:
34 (contem_busca em chaves/extintores/movimentacoes/material/log), 35a (Local lista suspensa dependente),
35b (Pendencias em LISTAS itemizadas: irregulares/vencidos + proximos do vencimento, com link p/ ficha),
36 (carga: fotos em arquivo temp no disco por streaming + limpeza), 37 (classe ABC/BC na inspecao).
Testado tudo de novo: home mostra IR-1/PV-1 nas listas; busca sem acento (veiculo/area/eletrica); local
select; classe ABC->BC; carga com 12 fotos gera PDF e limpa temporarios. ALERTA: o zip 33.8 estava
incompleto — usar este.

### 33.9 FIX — QR do extintor quebrava (500) ao montar o historico no fluxo de campo ✓
Log: UndefinedError 'InspecaoExtintor object has no attribute h' em extintor_ficha.html:201 (reg.h.id).
Causa: _ficha_campo passava hist como objetos crus (InspecaoExtintor), mas o template espera lista de
{"h":<registro>, "itens":<dict>} como a ficha do admin monta. Corrigido: _ficha_campo agora monta o hist
embrulhado (parseia itens_json) e passa tambem check_retorno (usado no estado Em recarga). Testado com CSRF:
colaborador loga pelo QR e ve a ficha com historico (200, sem 500).
