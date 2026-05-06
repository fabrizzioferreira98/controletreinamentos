# Midia e Status de Tripulante

## Papel

Registra compatibilidade com dados antigos de tripulante que ainda precisam permanecer legiveis.

## Local atual

- `backend/src/controle_treinamentos/application/tripulante_media.py`
- `backend/src/controle_treinamentos/infra/media_storage.py`
- `backend/src/controle_treinamentos/service_layers/pure_validation.py`

## Consumidor ou fluxo real

- Fotos antigas em `foto_base64`.
- Storage refs antigos em diretorios legados.
- Status historico `Ferias` normalizado para `Ferias` acentuado no modelo atual.

## Motivo de permanencia

Dados antigos ainda podem existir em banco ou filesystem. O codigo vivo precisa le-los ate haver migracao comprovada.

## Pre-condicao de saida

- Migracao de dados remove dependencias de `foto_base64` e storage refs antigos.
- Suite valida apenas storage refs e status canonicos.
- Plano de rollback definido para dados legados ainda encontrados.
