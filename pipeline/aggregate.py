#!/usr/bin/env python3
"""Agrega uma rodada do pipeline (somente biblioteca padrão; matplotlib opcional para gráficos).

Uso: python3 aggregate.py <pasta_da_rodada> [--watts 31] [--tarifa 1.00] [--watts-origem tdp|medido]

Gera na pasta da rodada: resultados.csv, resumo.md e (se houver matplotlib) dois gráficos PNG.
Pode rodar no Mac mini (python3) ou no PC, depois de copiar a pasta.
"""
import argparse
import csv
import glob
import json
import os
import re
import statistics as st
import sys


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_kv(path):
    d = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8", errors="replace"):
            if ":" in line:
                k, v = line.split(":", 1)
                d[k.strip()] = v.strip()
            elif "=" in line:
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    return d


def markers(path):
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


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def col(rows, name):
    return [v for v in (fnum(r.get(name)) for r in rows) if v is not None]


def window(rows, a, b):
    return [r for r in rows if a <= float(r["epoch"]) <= b]


def mean(v):
    return sum(v) / len(v) if v else None


def fmt(x, nd=2):
    return "" if x is None else f"{x:.{nd}f}"


def thermal_stats(rows):
    out = {}
    cores = [c for c in (rows[0].keys() if rows else []) if c.startswith("coretemp:Core")]
    cmax = [max(v) for v in (col(rows, c) for c in cores) if v]
    cmean = [mean(v) for v in (col(rows, c) for c in cores) if v]
    out["core_temp_max_C"] = max(cmax) if cmax else None
    out["core_temp_media_C"] = max(cmean) if cmean else None  # núcleo mais quente, em média
    hs = col(rows, "applesmc:TC0H_C")
    out["tc0h_max_C"] = max(hs) if hs else None
    fan = [v for c in (rows[0].keys() if rows else []) if c.startswith("applesmc:") and c.endswith("_rpm") for v in col(rows, c)]
    out["fan_max_rpm"] = max(fan) if fan else None
    thr = col(rows, "throttle_count")
    out["throttle_delta"] = (thr[-1] - thr[0]) if len(thr) >= 2 else None
    fq = col(rows, "freq_cpu0_kHz")
    out["freq_media_MHz"] = mean(fq) / 1000 if fq else None
    ma = col(rows, "mem_avail_kB")
    out["mem_avail_min_MB"] = min(ma) / 1024 if ma else None
    sw = col(rows, "swap_used_kB")
    out["swap_max_MB"] = max(sw) / 1024 if sw else None
    hwm = col(rows, "proc_hwm_kB")
    out["pico_rss_MB"] = max(hwm) / 1024 if hwm else None
    return out


def parse_ppl(path):
    if not os.path.exists(path):
        return None, None
    txt = open(path, errors="replace").read()
    m = re.findall(r"Final estimate:\s*PPL\s*=\s*([0-9.]+)\s*\+/-\s*([0-9.]+)", txt)
    if m:
        return float(m[-1][0]), float(m[-1][1])
    m = re.findall(r"PPL\s*=\s*([0-9.]+)", txt)
    return (float(m[-1]), None) if m else (None, None)


def collect(run, watts, tarifa):
    rows_out, evals = [], {}
    for mdir in sorted(d for d in glob.glob(os.path.join(run, "*")) if os.path.isdir(d)):
        name = os.path.basename(mdir)
        if not os.path.exists(os.path.join(mdir, "meta.txt")) and not os.path.exists(os.path.join(mdir, "status.txt")):
            continue
        meta = read_kv(os.path.join(mdir, "meta.txt"))
        status = read_kv(os.path.join(mdir, "status.txt")).get("status", "?")
        mk = markers(os.path.join(mdir, "marcadores.csv"))
        log = read_csv(os.path.join(mdir, "log.csv")) if os.path.exists(os.path.join(mdir, "log.csv")) else []
        ev_path = os.path.join(mdir, "eval", "eval_summary.json")
        ev = json.load(open(ev_path, encoding="utf-8")) if os.path.exists(ev_path) else None
        if ev:
            evals[name] = ev
        ppl, ppl_err = parse_ppl(os.path.join(mdir, "ppl.txt"))
        base = {
            "modelo": name, "quant": meta.get("quant", ""), "params_B": meta.get("params_B", ""),
            "status": status, "hash_estavel": meta.get("hash_estavel", ""),
            "hash_confere_manifesto": meta.get("hash_confere_manifesto", "").split(" ")[0],
            "acuracia": ev["acuracia"] if ev else None,
            "acertos": f"{ev['acertos']}/{ev['n_perguntas']}" if ev else "",
            "eval_pred_tps_medio": ev["pred_tps_medio"] if ev else None,
            "ppl": ppl, "ppl_erro": ppl_err,
        }
        benches = sorted(glob.glob(os.path.join(mdir, "bench_t*.csv")))
        if not benches:
            rows_out.append(base)
            continue
        for bpath in benches:
            t = int(re.search(r"bench_t(\d+)\.csv", bpath).group(1))
            try:
                b = read_csv(bpath)
            except Exception:  # noqa: BLE001
                b = []
            pp = next((r for r in b if int(r["n_prompt"]) > 0 and int(r["n_gen"]) == 0), None)
            tg = next((r for r in b if int(r["n_gen"]) > 0 and int(r["n_prompt"]) == 0), None)
            row = dict(base)
            row["threads"] = t
            ref = pp or tg or {}
            row["model_type"] = ref.get("model_type", "")
            row["model_size_MiB"] = fmt(fnum(ref.get("model_size")) / 2**20, 1) if ref.get("model_size") else ""
            row["build_commit"] = ref.get("build_commit", "")
            row["pp_tps"] = fnum(pp["avg_ts"]) if pp else None
            row["pp_desvio"] = fnum(pp["stddev_ts"]) if pp else None
            row["tg_tps"] = fnum(tg["avg_ts"]) if tg else None
            row["tg_desvio"] = fnum(tg["stddev_ts"]) if tg else None
            row["n_prompt"] = pp["n_prompt"] if pp else ""
            row["n_gen"] = tg["n_gen"] if tg else ""
            a, z = mk.get(f"bench_t{t}_inicio"), mk.get(f"bench_t{t}_fim")
            row["gate_ok"] = meta.get(f"bench_t{t}_gate_ok", "")
            row["inicio_gate_C"] = meta.get(f"bench_t{t}_inicio_gate_C", "")
            if a and z and log:
                row.update(thermal_stats(window(log, a, z)))
            if row["tg_tps"]:
                jt = watts / row["tg_tps"]
                row["J_por_token"] = jt
                row["tokens_por_J"] = 1 / jt
                row["R$_por_milhao_tokens"] = jt * 1e6 / 3.6e6 * tarifa
            rows_out.append(row)
    return rows_out, evals


COLS = ["modelo", "quant", "params_B", "threads", "model_type", "model_size_MiB", "status", "hash_estavel",
        "hash_confere_manifesto", "pp_tps", "pp_desvio", "tg_tps", "tg_desvio", "n_prompt", "n_gen",
        "core_temp_media_C", "core_temp_max_C", "tc0h_max_C", "fan_max_rpm", "throttle_delta", "freq_media_MHz",
        "pico_rss_MB", "mem_avail_min_MB", "swap_max_MB", "gate_ok", "inicio_gate_C",
        "acuracia", "acertos", "eval_pred_tps_medio", "ppl", "ppl_erro",
        "J_por_token", "tokens_por_J", "R$_por_milhao_tokens", "build_commit"]


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(COLS)
        for r in rows:
            w.writerow([("" if r.get(c) is None else (f"{r[c]:.4f}" if isinstance(r.get(c), float) else r.get(c, ""))) for c in COLS])


def write_md(path, run, rows, evals, watts, origem, tarifa):
    rm = read_kv(os.path.join(run, "run_meta.txt"))
    L = []
    L.append(f"# Resumo da rodada `{os.path.basename(run.rstrip('/'))}`\n")
    L.append(f"- Data: {rm.get('data', 'n/d')} | CPU: {rm.get('cpu', 'n/d')}")
    L.append(f"- Governor: {rm.get('governor', 'n/d')} | Ambiente: {rm.get('temperatura_ambiente_C', 'n/d')} °C | Etapas: {rm.get('stages', 'n/d')}")
    L.append(f"- Bench: threads {rm.get('threads', 'n/d')}, pp{rm.get('pp', '?')}/tg{rm.get('tg', '?')}, {rm.get('reps', '?')} repetições, linha de base {rm.get('base_s', '?')} s")
    L.append(f"- Térmica: núcleos ≤ {rm.get('target_nucleos_C', 'n/d')} °C e {rm.get('gate_sensor', 'n/d')} ≤ {rm.get('gate_max_C', 'n/d')} °C antes de cada janela; abortar em {rm.get('abort_C', 'n/d')} °C")
    L.append(f"- Energia estimada com **{watts:g} W ({origem})** e tarifa R$ {tarifa:.2f}/kWh. "
             f"{'TDP não é consumo medido.' if origem == 'tdp' else ''}\n")
    L.append("## Desempenho, térmica e memória\n")
    L.append("| Modelo | Quant | Thr | pp t/s | tg t/s | Pico RAM (MB) | Núcleo máx (°C) | TC0H máx (°C) | Ventoinha máx | Throttle Δ | Status |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for r in rows:
        L.append(f"| {r['modelo']} | {r.get('quant', '')} | {r.get('threads', '')} | {fmt(r.get('pp_tps'))} | {fmt(r.get('tg_tps'))} | "
                 f"{fmt(r.get('pico_rss_MB'), 0)} | {fmt(r.get('core_temp_max_C'), 0)} | {fmt(r.get('tc0h_max_C'), 1)} | "
                 f"{fmt(r.get('fan_max_rpm'), 0)} | {fmt(r.get('throttle_delta'), 0)} | {r.get('status', '')} |")
    L.append("\n## Qualidade (conjunto fixo, temperatura 0, seed 42)\n")
    cats = sorted({c for e in evals.values() for c in e["por_categoria"]})
    if evals:
        L.append("| Modelo | Acertos | " + " | ".join(cats) + " |")
        L.append("|---|---:|" + "---:|" * len(cats))
        for name, e in evals.items():
            cells = []
            for c in cats:
                pc = e["por_categoria"].get(c)
                cells.append(f"{pc['acertos']}/{pc['total']}" if pc else "")
            L.append(f"| {name} | {e['acertos']}/{e['n_perguntas']}{'' if e.get('completo') else ' (incompleto)'} | " + " | ".join(cells) + " |")
    else:
        L.append("Nenhuma avaliação de qualidade nesta rodada.")
    ppls = [r for r in rows if r.get("ppl") is not None]
    if ppls:
        L.append("\n## Perplexidade\n")
        L.append("| Modelo | Quant | PPL | ± |")
        L.append("|---|---|---:|---:|")
        seen = set()
        for r in ppls:
            if r["modelo"] in seen:
                continue
            seen.add(r["modelo"])
            L.append(f"| {r['modelo']} | {r.get('quant', '')} | {fmt(r['ppl'], 3)} | {fmt(r.get('ppl_erro'), 3)} |")
    L.append("\n## Energia estimada (geração)\n")
    L.append("| Modelo | Thr | J/token | tokens/J | R$ por 1 milhão de tokens |")
    L.append("|---|---:|---:|---:|---:|")
    for r in rows:
        if r.get("J_por_token") is not None:
            L.append(f"| {r['modelo']} | {r.get('threads', '')} | {fmt(r['J_por_token'], 2)} | {fmt(r['tokens_por_J'], 4)} | {fmt(r['R$_por_milhao_tokens'], 2)} |")
    L.append("\n## Integridade e ressalvas\n")
    for r in rows:
        if r.get("threads") in (None, "") or r is next((x for x in rows if x["modelo"] == r["modelo"]), None):
            L.append(f"- `{r['modelo']}`: hash estável = {r.get('hash_estavel') or 'n/d'}; confere com manifesto = {r.get('hash_confere_manifesto') or 'n/d'}; status = {r.get('status')}")
    L.append("- Valores térmicos são do intervalo do `llama-bench`; o pico de RAM é o `VmHWM` do processo medido.")
    L.append("- Uma rodada por modelo não estima variabilidade entre execuções; repita o pipeline para obter média e desvio.")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def charts(run, rows):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib ausente: gráficos não gerados (rode no PC para obtê-los).")
        return
    data = [r for r in rows if r.get("tg_tps")]
    if not data:
        return
    labels = [f"{r['modelo']}\n{r.get('threads')}T" for r in data]
    fig, ax = plt.subplots(figsize=(max(6, 1.6 * len(data)), 4.5))
    x = range(len(data))
    ax.bar([i - 0.2 for i in x], [r.get("pp_tps") or 0 for r in data], 0.4, label="prompt (pp)")
    ax.bar([i + 0.2 for i in x], [r["tg_tps"] for r in data], 0.4, label="geração (tg)")
    ax.set_xticks(list(x)); ax.set_xticklabels(labels, fontsize=8); ax.set_ylabel("tokens/s"); ax.legend(); ax.grid(axis="y", alpha=.3)
    ax.set_title("Vazão por modelo")
    fig.tight_layout(); fig.savefig(os.path.join(run, "grafico_vazao.png"), dpi=130); plt.close(fig)
    q = [r for r in data if r.get("acuracia") is not None]
    if q:
        fig, ax = plt.subplots(figsize=(6.5, 4.5))
        for r in q:
            ax.scatter(r["tg_tps"], r["acuracia"] * 100)
            ax.annotate(f"{r['modelo']} ({r.get('threads')}T)", (r["tg_tps"], r["acuracia"] * 100), fontsize=8, xytext=(4, 4), textcoords="offset points")
        ax.set_xlabel("geração (tokens/s)"); ax.set_ylabel("acerto no conjunto fixo (%)"); ax.grid(alpha=.3)
        ax.set_title("Qualidade vs velocidade")
        fig.tight_layout(); fig.savefig(os.path.join(run, "grafico_qualidade_vs_vazao.png"), dpi=130); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--watts", type=float, default=31.0)
    ap.add_argument("--tarifa", type=float, default=1.0)
    ap.add_argument("--watts-origem", choices=["tdp", "medido"], default="tdp")
    a = ap.parse_args()
    rows, evals = collect(a.run, a.watts, a.tarifa)
    if not rows:
        print("Nenhum modelo encontrado em", a.run)
        return 1
    write_csv(os.path.join(a.run, "resultados.csv"), rows)
    write_md(os.path.join(a.run, "resumo.md"), a.run, rows, evals, a.watts, a.watts_origem, a.tarifa)
    charts(a.run, rows)
    print("Gerado:", os.path.join(a.run, "resultados.csv"), "e resumo.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
