# Relatórios

Relatórios são **derivados**: citam o commit do repositório e o commit do llama.cpp, apontam para os dados em `data/raw/` e para o experimento em `experiments/`.

| Relatório | Assunto |
|---|---|
| [2026-10-03_relatorio-build-e-bench-macmini.md](2026-10-03_relatorio-build-e-bench-macmini.md) | Como o llama.cpp foi colocado para funcionar no Mac mini: o que deu certo, o que deu errado e os primeiros resultados |
| [2026-10-04_relatorio-termico-v3-macmini.md](2026-10-04_relatorio-termico-v3-macmini.md) | Relatório térmico da rodada v3 (metodologia e resultados) |
| [2026-10-05_relatorio-i5-1035g1.md](2026-10-05_relatorio-i5-1035g1.md) | Linha de base do notebook i5-1035G1 |
| [2026-10-05_comparativo-macmini-vs-i5.md](2026-10-05_comparativo-macmini-vs-i5.md) | Comparativo de vazão, térmica e energia estimada por TDP |

Figuras em `figures/`. Para uma nova rodada: `python3 tools/plot_thermal.py <pasta_da_execucao> -o reports/figures/<nome>.png`.

## Padrão para novos relatórios

Nome `AAAA-MM-DD_<assunto>.md`. Seções mínimas: resumo; plataforma; metodologia; resultados; limitações; reprodução (comandos, commit, dados). Valores estimados devem ser rotulados como estimativa; hipóteses, como hipótese.

Nota: os relatórios de 2026-10-03 a 2026-10-05 foram escritos antes da estrutura deste repositório e podem citar nomes de arquivo de saída que mudaram de lugar (por exemplo `bench_termico_v3.sh`, agora em `tools/legacy/`).
