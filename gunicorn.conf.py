# [R40] Configuração do Gunicorn carregada automaticamente (mesmo comando "gunicorn wsgi:app").
# O timeout padrão do Gunicorn é 30s — processar um relatório de carga com ~20 fotos grandes
# (mesmo já otimizado com draft()/compressão) pode passar disso, matando o worker no meio e
# quebrando o link/download para o usuário (WORKER TIMEOUT, já visto antes no item 100/104).
timeout = 120  # segundos; dá folga real para relatórios com bastante foto, sem exagerar
