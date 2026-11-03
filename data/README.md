# Dados

```
data/
├── raw/            # execuções originais, IMUTÁVEIS depois do commit
│   ├── macmini-1-1/
│   │   ├── termico/    # rodadas do bench térmico legado (v1/v3)
│   │   └── pipeline/   # rodadas do pipeline (criar ao arquivar a primeira)
│   └── notebook-i5/    # só o relatório por ora (sem dados brutos)
└── processed/      # derivados reproduzíveis (CSV agregados, figuras)
```

## Regras

1. **Brutos não se editam.** Se houver erro, registre em `experiments/<EXP>/README.md` (seção "Desvios"); não altere o arquivo.
2. **Todo dado bruto é validado** antes do commit: `python3 tools/validate_run.py <pasta>` (a CI roda `--all data/raw`).
3. **Nomes:** `raw/<maquina>/<tipo>/<AAAAMMDD_HHMMSS>_<script>_<modelo>/`. `<maquina>` = id de `hardware/`.
4. **Tamanho:** execuções pequenas (< ~1 MB; o bench térmico tem ~50 KB) vão direto no Git. Arquivos grandes (> ~10 MB) usam Git LFS ou armazenamento externo (por exemplo Zenodo), com o link e o sha256 no README do experimento. **Nunca** versione `.gguf` nem arquivos de logits `.kld` (podem ter GiB).
5. **Derivados** (`processed/`) devem poder ser regenerados por script versionado; cite o script e o commit no cabeçalho do arquivo ou no README do experimento.
6. Dados de qualidade (acertos, perplexidade) devem indicar o sha256 do `.gguf` usado e se ele foi verificado contra o publicado.

## Conteúdo atual

| Pasta | Origem | Observação |
|---|---|---|
| `raw/macmini-1-1/termico/20261003_145137_v1_*` | bench térmico v1 | legado; logger mais pesado |
| `raw/macmini-1-1/termico/20261003_191125_v1_*` | bench térmico v1 | legado |
| `raw/macmini-1-1/termico/20261003_200114_v3_*` | bench térmico v3 | rodada mais completa; sensores applesmc |

A rodada v2 do bench térmico não foi arquivada.

Formato dos arquivos: [`docs/06-dicionario-de-dados.md`](../docs/06-dicionario-de-dados.md).
