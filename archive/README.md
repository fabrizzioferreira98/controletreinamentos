# Archive

## Papel

Esta area guarda artefatos historicos fora da operacao viva do produto.

## Regra

- Nada aqui deve ser importado, executado, buildado, testado ou usado em release.
- Snapshots e backups so entram aqui quando houver valor de auditoria ou comparacao.
- Evidencias sensiveis de producao nao devem ser arquivadas no repo.
- Todo item arquivado deve ter nome com contexto e data, origem, motivo e status registrados em `MANIFEST.md`.

## Subareas

- `repo-snapshots/` para snapshots classificados de saida de build ou arvore do repo. Nao e backup arbitrario.
- `temp-backups/` para backups temporarios de arvore ou estrutura. Conteudo interno misto so e aceitavel quando fizer parte de um backup encapsulado.
- `old-wrappers/` para wrappers antigos fora da trilha viva. Compat vivo nao entra aqui.
- `local-artifacts/` para artefatos locais sem papel arquitetural, mantidos apenas se houver valor de auditoria.

## Regra de entrada

Todo item em `archive/` precisa ter classificacao previa. Nao use esta area como lixeira generica.

Backups, snapshots, dumps, copias aninhadas e residuos arquivaveis nao devem nascer na raiz nem na arvore viva por conveniencia. Se precisarem ficar no repo, entram diretamente na subarea correta e no `MANIFEST.md`; se forem operacionais, sensiveis ou sem valor historico, ficam fora do repo ou sao removidos.

Se um item voltar a ter consumidor operacional, ele deve ser reclassificado fora de `archive/` antes de qualquer uso.

Para decidir se um item pertence a compat, legacy, archive ou remocao, use `docs/governance/legacy-policy.md`.

## Padrao minimo

- Nome: contexto legivel mais data de captura ou arquivamento (`YYYYMMDD` ou `YYYYMMDD-HHMMSS`).
- Origem: caminho ou area de onde o item veio.
- Motivo: por que foi preservado em vez de removido.
- Status: `snapshot`, `backup`, `wrapper antigo`, `copia aninhada` ou `doc historica`.

## Permanencia minima

- `snapshot`: fica apenas enquanto tiver valor de comparacao, auditoria ou explicacao de transicao. Pode sair quando a fonte canonica atual bastar e nao houver auditoria pendente.
- `backup`: fica temporariamente para comparacao ou rollback historico. Pode sair quando nao houver consumidor, referencia viva ou necessidade de auditoria.
- `wrapper antigo`: fica somente como referencia de migracao. Pode sair quando a trilha canonica e os wrappers vivos documentados cobrirem os consumidores.
- `copia aninhada`: fica como excecao temporaria auditavel. Pode sair quando nao houver automacao externa, referencia viva ou necessidade de comparacao.
- `doc historica`: fica em `docs/archive/` ou `docs/migration/retired-platforms/` enquanto explicar decisao, migracao ou contexto encerrado.
- Artefato local, cache, build gerado, runtime mutavel ou evidencia sensivel nao tem permanencia padrao no repo.

## Nunca voltar para a arvore viva

Snapshots, backups, wrappers antigos, copias aninhadas e docs historicas nao devem ser restaurados como fonte viva. Se algum conteudo arquivado voltar a ser necessario, ele deve ser reimplementado ou reconsolidado na trilha canonica apropriada, com nova classificacao fora de `archive/`.
