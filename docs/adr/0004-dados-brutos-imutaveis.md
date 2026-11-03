# ADR 0004: dados brutos imutáveis; derivados reproduzíveis

- **Data:** 2026-10-06
- **Status:** aceita

## Contexto

A pesquisa precisa ser auditável: números dos relatórios têm de poder ser refeitos a partir dos arquivos originais.

## Decisão

- `data/raw/` guarda as execuções exatamente como saíram do script e **nunca é editado** depois do commit (correções vão em `experiments/<EXP>/README.md`, seção "Desvios").
- Tudo que é derivado (`resultados.csv`, figuras, resumos) é gerado por scripts versionados e vive em `data/processed/` ou `reports/`.
- Toda execução é validada por `tools/validate_run.py` antes do commit; a CI revalida `data/raw/`.
- Modelos (`.gguf`) e arquivos de logits (`.kld`) **não** entram no Git.

## Consequências

Histórico claro; repositório leve. Rodadas sem arquivamento (como a v2 do bench térmico) perdem valor como dado primário.

## Alternativas consideradas

Versionar tudo com Git LFS (custo e complexidade desnecessários para arquivos pequenos); guardar só relatórios (não auditável).
