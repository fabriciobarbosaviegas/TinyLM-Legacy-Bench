# Experimentos

Cada experimento tem uma pasta `EXP-AAAA-NNN-<slug>/` criada por `tools/new_experiment.sh` a partir de `_template/`.

```bash
tools/new_experiment.sh hardware-vs-qualidade "Efeito do hardware na qualidade das respostas"
```

## Regras

1. **Pré-registre antes de coletar** (`PREREGISTRO.md`) e commite. Mudanças depois disso vão em "Adendos" ou em "Desvios", com data e motivo.
2. **Um experimento = uma pergunta.** Coletas exploratórias entram como experimento com status `exploratório` e sem pré-registro (como o EXP-2026-001).
3. Dados brutos ficam em `data/raw/` (imutáveis); o experimento só aponta para eles. Resultados derivados vão para `data/processed/` e `reports/`.
4. Todo relatório cita o commit do repositório e o commit do llama.cpp usados.

## Registro

| ID | Título | Status | Pré-registro |
|---|---|---|---|
| [EXP-2026-001](EXP-2026-001-termico-macmini-qwen0.5b/) | Linha de base térmica do Mac mini 1,1 (Qwen2.5 0.5B Q5_K_M) | em análise | não (exploratório) |
