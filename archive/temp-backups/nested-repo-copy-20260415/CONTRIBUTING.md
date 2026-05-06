# Guia de Contribuição

Bem-vindo ao repositório do Controle de Treinamentos! Este guia consolida as convenções arquiteturais essenciais aprovadas para o crescimento saudável do sistema.

## 1. Arquitetura em Camadas

Seguimos uma separação clara de responsabilidades:
- **`blueprints/`**: Camada web. Apenas aqui consumimos código do Flask (`request`, `abort`, `jsonify`, `render_template`).
- **`core/`**: Funcionalidades transversais (logging, rate limiter, cache, feature flags).
- **`db/`**: Conexão com o banco, migrations manuais.
- **`infra/`**: Fila de jobs assíncronos (`jobs.py`), disparo de emails (`mailer.py`), rotinas de backup (`backup.py`).
- **`monitoring/`**: Agregação de métricas, formatadores de snapshot.
- **`reports/`**: Geração de PDFs e processamento intensivo de strings/bytes.
- **`repositories/`**: Isolamento de queries SQL brutas usando a classe Pyscopg Cursor. Nada de SQL espalhado.
- **`service_layers/`**: Regras de negócio puras (`produtividade.py`, validações de domínio). Não pode importar Flask.

## 2. Fronteira de Validação Requerida

### NUNCA VALIDE FORMATO NA REGRA DE NEGÓCIO
O payload recebido por uma rota DEVE ser validado estruturalmente na camada HTTP antes de cruzar a fronteira da aplicação. Use validações em `domain_validation.py` apenas para regras ligadas ao negócio (ex: "um piloto Inativo não pode realizar treinamentos").

**Como fazer:**
1. Converta queries e forms usando parsing do Flask.
2. Formate e escape valores logo na rota ou repasse a `http_utils.py` se houver helper.
3. Se o payload falhar na validação tipada, responda `HTTP 400 Bad Request` na mesma hora.

## 3. Tooling Obrigatório (.venv)

O projeto usa:
- **pytest**: Testes obrigatórios. Cobertura atual requerida >40%, meta 65%+. Execute `make cov`.
- **ruff**: Linter ultra-rápido. Execute `make lint`. As falhas bloqueiam o CI.

## 4. Testes e Dependências

Separação estrita:
- `requirements.txt`: Apenas bibliotecas essenciais para a produção (Flask, psycopg2, gunicorn, etc.).
- `requirements-dev.txt`: Ferramentas para CI e DEV (pytest, ruff, black).

## 5. Lidando com Legado

- **God Modules**: Diversos arquivos imensos (como `routes.py`, `monitoring.py`, e módulos na raiz) foram e/ou estão sendo extraídos em pacotes menores (`monitoring/`, `reports/`, `infra/`).
- **Ao contribuir**: Verifique se o código que você está adicionando pertence a algum pacote dedicado novo antes de embuti-lo em `services.py` ou `utils.py`.
