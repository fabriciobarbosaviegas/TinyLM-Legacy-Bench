#!/usr/bin/env python3
"""Gera um gráfico térmico (PNG) a partir de log.csv + marcadores.csv de uma execução.

Uso: python3 tools/plot_thermal.py <pasta_da_execucao> [-o saida.png] [--titulo "texto"]

Requer matplotlib. Funciona com os formatos termico-v1, termico-v3 e com a pasta de um modelo do pipeline.
Painéis: núcleos (coretemp), demais sensores (applesmc), ventoinha (se existir).
Fundo: cinza = linha de base, azul = carga (bench), verde = resfriamento.
"""
import argparse
import csv
import os
import sys


def read_markers(path):
    m = {}
    if os.path.exists(path):
        for line in open(path):
            if "," in line:
                k, v = line.strip().split(",", 1)
                try:
                    m[k] = float(v)
                except ValueError:
                    pass
    return m


def first_marker(mk, *names):
    for n in names:
        if n in mk:
            return mk[n]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta")
    ap.add_argument("-o", "--saida", default=None)
    ap.add_argument("--titulo", default=None)
    a = ap.parse_args()
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib não instalado (pip install matplotlib).")
        return 2
    rows = list(csv.DictReader(open(os.path.join(a.pasta, "log.csv"), encoding="utf-8")))
    mk = read_markers(os.path.join(a.pasta, "marcadores.csv"))
    t_bench = first_marker(mk, "bench_inicio", "bench_t2_inicio") or float(rows[0]["epoch"])
    t_end = first_marker(mk, "bench_fim", "bench_t2_fim")
    t_fim = first_marker(mk, "fim")
    T = [float(r["epoch"]) - t_bench for r in rows]

    def series(col):
        return [float(r[col]) if r.get(col, "") != "" else float("nan") for r in rows]

    cols = list(rows[0].keys())
    cores = [c for c in cols if c.startswith("coretemp:Core")]
    board = [c for c in cols if c.startswith("applesmc:") and c.endswith("_C")]
    fans = [c for c in cols if c.endswith("_rpm")]
    panels = 1 + (1 if board else 0) + (1 if fans else 0)
    fig, ax = plt.subplots(panels, 1, figsize=(10, 3.3 * panels), sharex=True, squeeze=False)
    ax = ax[:, 0]
    for a_ in ax:
        a_.grid(alpha=.3)
        a_.axvspan(T[0], 0, color="#dddddd", alpha=.45, lw=0)
        if t_end:
            a_.axvspan(0, t_end - t_bench, color="#cfe3ff", alpha=.45, lw=0)
            a_.axvspan(t_end - t_bench, (t_fim or t_end) - t_bench, color="#d9f2d9", alpha=.5, lw=0)
    i = 0
    for c in cores:
        ax[i].plot(T, series(c), lw=1.3, label=c.replace("coretemp:", "").replace("_C", ""))
    tj = [c for c in board if c.endswith("TC0D_C")]
    for c in tj:
        ax[i].plot(T, series(c), lw=1, ls="--", color="gray", label="TC0D")
    ax[i].axhline(100, color="k", ls=":", lw=.8)
    ax[i].set_ylabel("Temperatura (°C)")
    ax[i].legend(loc="center right", fontsize=8)
    ax[i].set_title(a.titulo or os.path.basename(os.path.normpath(a.pasta)))
    i += 1
    if board:
        for c in board:
            if c in tj:
                continue
            ax[i].plot(T, series(c), lw=1.2, label=c.replace("applesmc:", "").replace("_C", ""))
        ax[i].set_ylabel("Temperatura (°C)")
        ax[i].legend(loc="upper right", fontsize=7, ncol=2)
        i += 1
    if fans:
        for c in fans:
            ax[i].plot(T, series(c), color="k", lw=1.2)
        ax[i].set_ylabel("Ventoinha (rpm)")
    ax[-1].set_xlabel("Segundos desde o início do llama-bench")
    fig.tight_layout()
    out = a.saida or os.path.join(a.pasta, "curva_termica.png")
    fig.savefig(out, dpi=130)
    print("Gerado:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
