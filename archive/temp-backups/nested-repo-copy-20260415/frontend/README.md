# Frontend App

Frontend separado do produto autenticado.

## Build

```powershell
& "..\\.venv\\Scripts\\python.exe" ".\\scripts\\build_frontend.py"
```

Opcionalmente informe um arquivo `.env`:

```powershell
& "..\\.venv\\Scripts\\python.exe" ".\\scripts\\build_frontend.py" --env-file ".env.example"
```

O build gera arquivos estaticos em `dist/`.

## Estrategia

- app estatico independente
- roteamento por hash
- autenticacao via cookie de sessao + CSRF
- consumo de `/api/v1/...`
- deploy separado do backend
