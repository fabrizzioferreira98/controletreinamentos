# Manual Unificado Tecnico e Operacional

Este arquivo foi normalizado para o modelo servidor local / self-hosted Windows e passa a funcionar como indice mestre de documentacao.

## Fontes atuais de verdade

- arquitetura atual: [C:\apps\controle-treinamentos\ARCHITECTURE.md](C:\apps\controle-treinamentos\ARCHITECTURE.md)
- operacao do servidor Windows: [C:\apps\controle-treinamentos\docs\operations\WINDOWS_SELF_HOSTED_SERVER.md](C:\apps\controle-treinamentos\docs\operations\WINDOWS_SELF_HOSTED_SERVER.md)
- gates e release: [C:\apps\controle-treinamentos\docs\operations\RELEASE_GATES.md](C:\apps\controle-treinamentos\docs\operations\RELEASE_GATES.md)
- manual consolidado resumido: [C:\apps\controle-treinamentos\docs\MANUAL_UNIFICADO.md](C:\apps\controle-treinamentos\docs\MANUAL_UNIFICADO.md)
- exemplos de ambiente:
  - [C:\apps\controle-treinamentos\service\windows\env\prod.env.example](C:\apps\controle-treinamentos\service\windows\env\prod.env.example)
  - [C:\apps\controle-treinamentos\service\windows\env\hml.env.example](C:\apps\controle-treinamentos\service\windows\env\hml.env.example)

## Escopo vigente

O sistema deve ser entendido e operado hoje com estas premissas:

- backend Flask executando via Waitress
- frontend oficial servido pelo Caddy
- PostgreSQL local como banco operacional
- storage local para fotos, PDFs e anexos
- jobs, backup, restore e monitoramento executados no host local
- ambientes `prod` e `hml` separados no mesmo servidor ou em servidores locais equivalentes

## Politica de documentacao

Qualquer instrucao antiga que pressuponha plataforma cloud, runtime serverless, banco externo gerenciado ou deploy PaaS deve ser tratada como conteudo legado desativado. A operacao oficial do projeto e local e self-hosted.
