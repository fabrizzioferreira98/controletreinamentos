# Manual Unificado do Sistema

Este documento foi consolidado para refletir o estado self-hosted / servidor local do sistema.

## Referencias oficiais atuais

- operacao do servidor Windows: [C:\apps\controle-treinamentos\docs\operations\WINDOWS_SELF_HOSTED_SERVER.md](C:\apps\controle-treinamentos\docs\operations\WINDOWS_SELF_HOSTED_SERVER.md)
- arquitetura vigente: [C:\apps\controle-treinamentos\docs\architecture\ARCHITECTURE.md](C:\apps\controle-treinamentos\docs\architecture\ARCHITECTURE.md)
- configuracao de producao: [C:\apps\controle-treinamentos\ops\windows\env\prod.env.example](C:\apps\controle-treinamentos\ops\windows\env\prod.env.example)
- configuracao de homologacao: [C:\apps\controle-treinamentos\ops\windows\env\hml.env.example](C:\apps\controle-treinamentos\ops\windows\env\hml.env.example)
- release e regressao: [C:\apps\controle-treinamentos\docs\operations\RELEASE_GATES.md](C:\apps\controle-treinamentos\docs\operations\RELEASE_GATES.md)

## Estado arquitetural oficial

- hospedagem oficial: servidor local Windows
- proxy reverso: Caddy
- app server: Waitress
- banco oficial: PostgreSQL local
- storage oficial: filesystem local
- frontend oficial: app estatica servida pelo Caddy
- jobs e backups: rotinas locais no host

## Escopo

Os antigos materiais de cloud/serverless foram aposentados. Este manual agora deve ser lido em conjunto com os documentos operacionais acima, que representam a fonte atual de verdade para instalacao, operacao, backup, restore, release e validacao dos ambientes `prod` e `hml`.
