#!/usr/bin/env python3
"""
Compara tokens/s e temperaturas de vários modelos do llama-bench (bench_termico_v3.sh).

Cada pasta de rodada (termico_AAAAMMDD_HHMMSS_<modelo>/) pode ter:
    log.csv          sensores, 1 linha por segundo (coluna epoch)       [obrigatório]
    bench.csv        saída do llama-bench -o csv (t/s, test_time, quantização)
    marcadores.csv   baseline_inicio, bench_inicio, bench_fim (epoch)
    meta.txt         caminho do modelo, threads, data
Com marcadores.csv + test_time do bench.csv as fases são exatas:
    repouso      baseline_inicio -> bench_inicio
    carregamento bench_inicio    -> início do teste de prompt
    prompt (pp)  início do pp    -> início do teste de geração
    geração (tg) início do tg    -> bench_fim
Sem esses arquivos (rodadas antigas), o início/fim vêm da frequência das CPUs e a
divisão prompt/geração é estimada pelos t/s.

Uso:
    python comparar_modelos.py                 (procura a partir da pasta do script)
    python comparar_modelos.py C:\\...\\gaia\\bin

As rodadas são agrupadas pelo arquivo .gguf (então a mesma pasta pode ter vários
modelos e o mesmo modelo pode estar em várias pastas). Saída em
graficos_comparativos/ (ou -o PASTA):
    comparativo_modelos.png   barras: t/s de prompt e geração + temperaturas por fase, todos os modelos
    curvas_aquecimento.png    curvas de temperatura de todos os modelos sobrepostas
    <modelo>.png              um por modelo: barras por rodada + curvas de cada rodada
    resumo_modelos.csv        médias por modelo   (";" e vírgula decimal, abre no Excel)
    rodadas.csv               números de cada rodada

Requisitos: pandas, matplotlib, numpy.
"""

import argparse
import hashlib
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

MAQUINA = "Mac mini 1,1 (Core Duo T2300)"
PASTA_SAIDA = "graficos_comparativos"
COLS_BENCH = {"n_prompt", "n_gen", "avg_ts"}
COR = {
    "pp": "#2f6fb5", "tg": "#e07b22",
    "repouso": "#a9b1ba", "prompt": "#7fb0e6", "geracao": "#f2b27a", "pico": "#b8322f",
    "carregamento": "#eeeeee",
}
FUNDO = {"carregamento": "#f2f2f2", "prompt": "#e8f1fc", "geracao": "#fdebd9"}


# ------------------------------------------------------------------ utilidades

def br(v, casas=1):
    if v is None or not np.isfinite(v):
        return "–"
    s = f"{v:,.{casas}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def num(x, padrao=np.nan):
    try:
        x = float(x)
        return x if np.isfinite(x) else padrao
    except (TypeError, ValueError):
        return padrao


def colunas(f):
    try:
        return set(pd.read_csv(f, nrows=0).columns)
    except Exception:
        return set()


def salvar(fig, saida, dpi):
    try:
        fig.savefig(saida, dpi=dpi)
    except OSError as e:
        alt = saida.with_name(f"{saida.stem}_{time.strftime('%H%M%S')}{saida.suffix}")
        print(f"  AVISO: não consegui gravar {saida.name} ({e.strerror}); está aberto em "
              f"outro programa? Salvando como {alt.name}.")
        fig.savefig(alt, dpi=dpi)
        saida = alt
    plt.close(fig)
    print(f"  -> {saida}")


def salvar_csv(df, saida):
    try:
        df.to_csv(saida, sep=";", decimal=",", index=False, encoding="utf-8-sig")
        print(f"  -> {saida}")
    except OSError:
        print(f"  AVISO: não consegui gravar {saida.name}; está aberto no Excel?")


# ------------------------------------------------------------------ leitura de uma rodada

def ler_marcadores(pasta):
    f = pasta / "marcadores.csv"
    if not f.is_file():
        return {}
    out = {}
    for linha in f.read_text(errors="replace").splitlines():
        partes = linha.strip().split(",")
        if len(partes) == 2 and np.isfinite(num(partes[1])):
            out[partes[0].strip()] = num(partes[1])
    return out


def ler_meta(pasta):
    f = pasta / "meta.txt"
    out = {}
    if f.is_file():
        for linha in f.read_text(errors="replace").splitlines():
            if ":" in linha:
                k, v = linha.split(":", 1)
                out[k.strip()] = v.strip()
    return out


def ler_bench(f):
    """Testes pp/tg puros do CSV do llama-bench, com o horário de início (epoch UTC)."""
    out = []
    try:
        df = pd.read_csv(f)
    except Exception:
        return out
    for r in df.to_dict("records"):
        npp, ntg = int(num(r.get("n_prompt"), 0)), int(num(r.get("n_gen"), 0))
        tps = num(r.get("avg_ts"))
        if (npp > 0) == (ntg > 0) or not np.isfinite(tps):
            continue
        inicio = np.nan
        try:
            inicio = datetime.strptime(str(r.get("test_time")), "%Y-%m-%dT%H:%M:%SZ") \
                .replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            pass
        out.append({
            "tipo": "pp" if npp else "tg", "n": npp or ntg, "tps": tps,
            "dp": num(r.get("stddev_ts"), 0.0), "inicio": inicio,
            "arquivo_modelo": str(r.get("model_filename") or ""),
            "tipo_modelo": str(r.get("model_type") or ""),
            "tamanho": num(r.get("model_size")), "params": num(r.get("model_n_params")),
            "threads": num(r.get("n_threads")),
        })
    return out


def detectar_carga(df, min_seg=10):
    """(início, fim) em epoch do trecho com as CPUs na frequência máxima."""
    fcols = [c for c in df.columns if c.startswith("freq_cpu")]
    if not fcols:
        raise ValueError("sem colunas freq_cpu* e sem marcadores.csv")
    fmax = df[fcols].max().min()
    cheio = (df[fcols] >= 0.97 * fmax).all(axis=1)
    sust = cheio.astype(float).rolling(min_seg, center=True, min_periods=1).median() >= 0.5
    if not sust.any():
        raise ValueError("não encontrei trecho de carga")
    idx = np.flatnonzero(sust.to_numpy())
    return float(df["epoch"].iloc[idx[0]]), float(df["epoch"].iloc[idx[-1]])


def ler_rodada(log, bench, marc, args):
    df = pd.read_csv(log).sort_values("epoch").reset_index(drop=True)
    cores = [c for c in df.columns if c.endswith(("Core_0_C", "Core_1_C"))] or \
            [c for c in df.columns if c.startswith("coretemp")]
    if not cores:
        raise ValueError("sem colunas de temperatura dos núcleos")
    df["core"] = df[cores].mean(axis=1)
    df["core_max"] = df[cores].max(axis=1)
    rpm = next((c for c in df.columns if c.endswith("rpm")), None)
    dis = next((c for c in df.columns if c.endswith("TC0H_C")), None)

    if "bench_inicio" in marc and "bench_fim" in marc:
        b0, b1, origem = marc["bench_inicio"], marc["bench_fim"], "marcadores"
    else:
        b0, b1 = detectar_carga(df)
        origem = "frequência"
    base0 = marc.get("baseline_inicio", b0 - 60)

    pp = next((b for b in bench if b["tipo"] == "pp"), None)
    tg = next((b for b in bench if b["tipo"] == "tg"), None)
    dentro = lambda x: np.isfinite(x) and b0 - 30 <= x <= b1
    if pp and tg and dentro(pp["inicio"]) and dentro(tg["inicio"]) and pp["inicio"] < tg["inicio"]:
        pp0, tg0, fases = max(pp["inicio"], b0), tg["inicio"], "test_time"
    elif pp and tg:  # estimativa pelos t/s
        t_pp = (args.reps + 1) * pp["n"] / pp["tps"]
        t_tg = args.reps * tg["n"] / tg["tps"]
        pp0, tg0, fases = b0, b0 + (b1 - b0) * t_pp / (t_pp + t_tg), "estimada"
    else:
        pp0, tg0, fases = b0, np.nan, "sem bench"

    df["t"] = df["epoch"] - b0
    sel = lambda a, b: df[(df.epoch >= a) & (df.epoch < b)]
    base = sel(base0, b0 - 2)
    if len(base) < 5:
        base = df[df.epoch < b0]
    carga = sel(b0, b1 + 1)
    p_fase = sel(pp0, tg0) if np.isfinite(tg0) else sel(pp0, b1 + 1)
    g_fase = sel(tg0, b1 + 1) if np.isfinite(tg0) else df.iloc[0:0]

    m = {
        "inicio": b0, "carga_s": b1 - b0, "pp_ini_s": pp0 - b0,
        "tg_ini_s": tg0 - b0 if np.isfinite(tg0) else np.nan,
        "origem_carga": origem, "origem_fases": fases,
        "repouso_C": base.core.median() if len(base) else np.nan,
        "prompt_media_C": p_fase.core.mean() if len(p_fase) else np.nan,
        "geracao_media_C": g_fase.core.mean() if len(g_fase) else np.nan,
        "carga_media_C": carga.core.mean(),
        "pico_C": carga.core_max.max(),
        "dissipador_pico_C": carga[dis].max() if dis else np.nan,
        "ventoinha_media_rpm": carga[rpm].mean() if rpm else np.nan,
        "ventoinha_max_rpm": carga[rpm].max() if rpm else np.nan,
        "throttle": int(df["throttle_count"].max()) if "throttle_count" in df else 0,
        "pp_tps": pp["tps"] if pp else np.nan, "tg_tps": tg["tps"] if tg else np.nan,
        "pp_n": pp["n"] if pp else np.nan, "tg_n": tg["n"] if tg else np.nan,
    }
    m["aquecimento_C"] = m["carga_media_C"] - m["repouso_C"]
    return df[["t", "core"]].copy(), m


# ------------------------------------------------------------------ descoberta

def nome_modelo(arquivo_modelo, meta_modelo):
    caminho = arquivo_modelo or meta_modelo
    if not caminho:
        return None
    return re.split(r"[\\/]", caminho)[-1].removesuffix(".gguf")


def quantizacao(tipo_modelo, nome):
    m = re.search(r"(IQ\d\w*|Q\d\w*|F16|BF16|F32)\s*$", tipo_modelo or "", re.I)
    if m:
        return m.group(1).upper()
    m = re.search(r"(IQ\d[\w]*|Q\d[\w]*|F16|BF16)$", nome or "", re.I)
    return m.group(1).upper() if m else "?"


def encontrar_rodadas(raizes, args):
    logs = []
    for raiz in raizes:
        logs += [f for f in raiz.rglob("*.csv")
                 if PASTA_SAIDA not in f.parts and "epoch" in colunas(f)]
    # rodadas completas (com bench/marcadores ao lado) primeiro, cópias soltas depois
    completo = lambda f: (f.parent / "bench.csv").is_file() or (f.parent / "marcadores.csv").is_file()
    logs.sort(key=lambda f: (not completo(f), str(f)))

    vistos, rodadas, chave_pasta = set(), [], {}
    for f in logs:
        try:
            h = hashlib.md5(f.read_bytes()).hexdigest()
        except OSError:
            continue
        if h in vistos:
            continue
        vistos.add(h)
        pasta = f.parent
        irmaos = [g for g in pasta.glob("*.csv") if "epoch" in colunas(g)]
        sozinho = len(irmaos) == 1
        bench = ler_bench(pasta / "bench.csv") if sozinho and (pasta / "bench.csv").is_file() else []
        marc = ler_marcadores(pasta) if sozinho else {}
        meta = ler_meta(pasta) if sozinho else {}
        b = bench[0] if bench else {}
        nome = nome_modelo(b.get("arquivo_modelo"), meta.get("modelo"))
        pasta_modelo = pasta.parent if pasta.name.startswith("termico_") else pasta
        if nome:
            chave_pasta.setdefault(pasta_modelo, nome)
        try:
            curva, m = ler_rodada(f, bench, marc, args)
        except (ValueError, KeyError) as e:
            print(f"  AVISO: ignorando {f} ({e})")
            continue
        rodadas.append({
            "arquivo": f, "pasta_modelo": pasta_modelo, "nome": nome, "curva": curva, "m": m,
            "quant": quantizacao(b.get("tipo_modelo"), nome),
            "params": b.get("params", np.nan), "tamanho": b.get("tamanho", np.nan),
            "threads": b.get("threads", num(meta.get("threads"))),
        })
    for r in rodadas:  # logs soltos herdam o modelo da pasta
        if not r["nome"]:
            r["nome"] = chave_pasta.get(r["pasta_modelo"], r["pasta_modelo"].name)
            if r["quant"] == "?":
                r["quant"] = quantizacao("", r["nome"])
    return rodadas


def agrupar(rodadas):
    mods = {}
    for r in rodadas:
        mods.setdefault(r["nome"], []).append(r)
    saida = []
    for nome, R in mods.items():
        R.sort(key=lambda r: r["m"]["inicio"])
        res = {"modelo": nome, "quantizacao": next((r["quant"] for r in R if r["quant"] != "?"), "?"),
               "params_B": num(next((r["params"] for r in R if np.isfinite(num(r["params"]))), np.nan)) / 1e9,
               "tamanho_MiB": num(next((r["tamanho"] for r in R if np.isfinite(num(r["tamanho"]))), np.nan)) / 2**20,
               "rodadas": len(R)}
        for k in ("pp_tps", "tg_tps", "carga_s", "repouso_C", "prompt_media_C", "geracao_media_C",
                  "carga_media_C", "aquecimento_C", "ventoinha_media_rpm"):
            v = [r["m"][k] for r in R if np.isfinite(num(r["m"][k]))]
            res[k] = float(np.mean(v)) if v else np.nan
            if k in ("pp_tps", "tg_tps"):
                res[k.replace("tps", "dp")] = float(np.std(v)) if len(v) > 1 else 0.0
        for k in ("pico_C", "dissipador_pico_C", "ventoinha_max_rpm"):
            v = [r["m"][k] for r in R if np.isfinite(num(r["m"][k]))]
            res[k] = float(max(v)) if v else np.nan
        res["throttle"] = max(r["m"]["throttle"] for r in R)
        for k in ("pp_n", "tg_n"):
            v = [r["m"][k] for r in R if np.isfinite(num(r["m"][k]))]
            res[k] = int(v[0]) if v else np.nan
        for k in ("pp_ini_s", "tg_ini_s"):
            v = [r["m"][k] for r in R if np.isfinite(num(r["m"][k]))]
            res[k] = float(np.mean(v)) if v else np.nan
        res["fases"] = ", ".join(sorted({r["m"]["origem_fases"] for r in R}))
        saida.append({"nome": nome, "rodadas": R, "res": res})
    saida.sort(key=lambda m: (-num(m["res"]["tg_tps"], -1), -num(m["res"]["pp_tps"], -1), m["nome"]))
    return saida


def rotulo(m, quebra=True):
    r = m["res"]
    base = m["nome"]
    q = r["quantizacao"]
    if q != "?" and base.lower().endswith(q.lower()):
        base = base[: -len(q)].rstrip("-_.")
    extras = [q]
    if np.isfinite(r["params_B"]):
        extras.append(f"{br(r['params_B'], 2)} B params")
    if np.isfinite(r["tamanho_MiB"]):
        extras.append(f"{br(r['tamanho_MiB'], 0)} MiB")
    return base + ("\n" if quebra else " · ") + " · ".join(extras)


# ------------------------------------------------------------------ gráficos

def estilo(ax, eixo="y"):
    ax.grid(True, axis=eixo, color="#888888", alpha=0.25, lw=0.8)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)


def barras_agrupadas(ax, grupos, series, base=0.0, casas=1, unidade="", largura=0.8, fonte=8.5):
    """series: [(rotulo, cor, valores, erros|None)], um valor por grupo. Desenha blocos com o valor em cima."""
    n, k = len(grupos), len(series)
    w = largura / k
    x = np.arange(n)
    topo = base
    for i, (rot, cor, vals, errs) in enumerate(series):
        vals = np.asarray(vals, float)
        pos = x - largura / 2 + w * (i + 0.5)
        ok = np.isfinite(vals)
        e = None if errs is None else np.asarray(errs, float)[ok]
        ax.bar(pos[ok], vals[ok] - base, bottom=base, width=w * 0.9, color=cor, label=rot,
               yerr=e, error_kw={"ecolor": "#333333", "capsize": 2.5, "lw": 0.9})
        for p, v, ee in zip(pos[ok], vals[ok], (e if e is not None else np.zeros(ok.sum()))):
            ax.text(p, v + num(ee, 0), f"{br(v, casas)}{unidade}", ha="center", va="bottom",
                    fontsize=fonte, rotation=90 if k >= 4 and n > 3 else 0)
            topo = max(topo, v + num(ee, 0))
        for p in pos[~ok]:
            ax.text(p, base, "s/d", ha="center", va="bottom", fontsize=7.5, color="#888888")
    ax.set_xticks(x, grupos)
    ax.set_xlim(-0.6, n - 0.4)
    return topo


def grafico_comparativo(mods, saida, args):
    n = len(mods)
    fig = plt.figure(figsize=(max(12, 2.3 * n + 3), 11.5), constrained_layout=True)
    ax_t, ax_c = fig.subplots(2, 1, gridspec_kw={"height_ratios": [1, 1.1]})
    nomes = [rotulo(m) for m in mods]
    R = [m["res"] for m in mods]
    npp = next((r["pp_n"] for r in R if np.isfinite(num(r["pp_n"]))), None)
    ntg = next((r["tg_n"] for r in R if np.isfinite(num(r["tg_n"]))), None)

    topo = barras_agrupadas(ax_t, nomes, [
        (f"prompt (pp{npp})" if npp else "prompt", COR["pp"], [r["pp_tps"] for r in R], [r["pp_dp"] for r in R]),
        (f"geração (tg{ntg})" if ntg else "geração", COR["tg"], [r["tg_tps"] for r in R], [r["tg_dp"] for r in R]),
    ], casas=2, fonte=9.5)
    ax_t.set_ylim(0, topo * 1.18 if topo > 0 else 1)
    ax_t.set_ylabel("tokens por segundo")
    ax_t.set_title("Velocidade: tokens por segundo (média das rodadas ± desvio)", loc="left", fontsize=12.5)
    ax_t.legend(loc="upper right", fontsize=10, framealpha=0.95)
    estilo(ax_t)

    base = args.base_temp
    topo = barras_agrupadas(ax_c, nomes, [
        ("repouso", COR["repouso"], [r["repouso_C"] for r in R], None),
        ("média no prompt", COR["prompt"], [r["prompt_media_C"] for r in R], None),
        ("média na geração", COR["geracao"], [r["geracao_media_C"] for r in R], None),
        ("pico", COR["pico"], [r["pico_C"] for r in R], None),
    ], base=base, casas=0 if n > 4 else 1, fonte=8.5)
    ax_c.set_ylim(base, max(topo + 9, base + 10))
    if args.tjmax:
        ax_c.axhline(args.tjmax, color="black", ls=":", lw=0.9)
        ax_c.set_ylim(base, max(args.tjmax + 3, topo + 6))
        ax_c.text(1.0, args.tjmax, f"Tjunction {args.tjmax:g} °C ", transform=ax_c.get_yaxis_transform(),
                  ha="right", va="bottom", fontsize=9)
    ax_c.set_ylabel(f"°C, média dos 2 núcleos (eixo a partir de {base:g} °C)")
    ax_c.set_title("Temperatura dos núcleos por fase (pico = maior leitura de um núcleo)", loc="left", fontsize=12.5)
    ax_c.legend(loc="upper left", fontsize=9.5, ncol=4, framealpha=0.95)
    estilo(ax_c)

    fig.suptitle(f"{MAQUINA}, llama-bench - comparativo de {n} modelo{'s' if n != 1 else ''}", fontsize=14)
    salvar(fig, saida, args.dpi)


def curva_media(R, ate):
    a = max(-60.0, max(r["curva"].t.iloc[0] for r in R))
    b = min(min(r["curva"].t.iloc[-1] for r in R), ate)
    grade = np.arange(np.ceil(a), b, 2.0)
    pilha = np.vstack([np.interp(grade, r["curva"].t, r["curva"].core, left=np.nan, right=np.nan) for r in R])
    return grade, np.nanmean(pilha, axis=0)


def grafico_curvas(mods, saida, args):
    fig, ax = plt.subplots(figsize=(14, 7), constrained_layout=True)
    paleta = list(plt.cm.tab10.colors) + list(plt.cm.Dark2.colors)
    for i, m in enumerate(mods):
        r, c = m["res"], paleta[i % len(paleta)]
        t, v = curva_media(m["rodadas"], r["carga_s"] + args.resfriamento)
        ax.plot(t, v, color=c, lw=1.8, label=f"{rotulo(m, False)}  ({br(r['carga_s'], 0)} s de carga)")
        for x, mk in ((r["tg_ini_s"], "s"), (r["carga_s"], "o")):
            if np.isfinite(num(x)) and t[0] <= x <= t[-1]:
                ax.plot(x, np.interp(x, t, v), mk, color=c, ms=7, mec="white", mew=1.5, zorder=4)
    ax.axvline(0, color="#555555", ls=":", lw=1)
    ax.set_xlabel("Segundos desde o início do llama-bench   (■ = início da geração, ● = fim da carga)")
    ax.set_ylabel("Média dos núcleos (°C)")
    ax.set_title("Curvas de aquecimento (média das rodadas de cada modelo)", loc="left", fontsize=12.5)
    ax.legend(loc="lower right", fontsize=9, framealpha=0.92)
    estilo(ax, "both")
    fig.suptitle(f"{MAQUINA}, llama-bench", fontsize=14)
    salvar(fig, saida, args.dpi)


def grafico_modelo(mod, saida, args):
    res, R = mod["res"], mod["rodadas"]
    k = len(R)
    fig = plt.figure(figsize=(max(13, 1.6 * k + 7), 10), constrained_layout=True)
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.1], width_ratios=[1, 1.4])
    ax_t, ax_c, ax_v = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[1, :])
    rod = [f"v{i + 1}" for i in range(k)] + ["média"]
    M = [r["m"] for r in R]
    media = lambda key: [m[key] for m in M] + [res[key]]

    topo = barras_agrupadas(ax_t, rod, [
        (f"prompt (pp{res['pp_n']})" if np.isfinite(num(res["pp_n"])) else "prompt", COR["pp"], media("pp_tps"), None),
        (f"geração (tg{res['tg_n']})" if np.isfinite(num(res["tg_n"])) else "geração", COR["tg"], media("tg_tps"), None),
    ], casas=2)
    ax_t.set_ylim(0, topo * 1.3 if topo > 0 else 1)
    ax_t.set_ylabel("tokens por segundo")
    ax_t.set_title("Tokens por segundo por rodada", loc="left", fontsize=12)
    ax_t.legend(loc="upper center", fontsize=9, ncol=2, framealpha=0.95)
    estilo(ax_t)

    base = args.base_temp
    topo = barras_agrupadas(ax_c, rod, [
        ("repouso", COR["repouso"], media("repouso_C"), None),
        ("prompt", COR["prompt"], media("prompt_media_C"), None),
        ("geração", COR["geracao"], media("geracao_media_C"), None),
        ("pico", COR["pico"], media("pico_C"), None),
    ], base=base, casas=0 if k > 3 else 1, fonte=8)
    ax_c.set_ylim(base, topo + 10)
    ax_c.set_ylabel(f"°C (eixo a partir de {base:g} °C)")
    ax_c.set_title("Temperatura dos núcleos por fase", loc="left", fontsize=12)
    ax_c.legend(loc="upper left", fontsize=8.5, ncol=4, framealpha=0.95)
    estilo(ax_c)

    # curvas com as fases sombreadas (tempos médios)
    pp0, tg0, fim = num(res["pp_ini_s"], 0), num(res["tg_ini_s"]), res["carga_s"]
    faixas = [(0, pp0, "carregamento"), (pp0, tg0, "prompt"), (tg0, fim, "geracao")] if np.isfinite(tg0) \
        else [(0, fim, "prompt")]
    nomes_fase = {"carregamento": "carregamento", "prompt": f"prompt (pp{res['pp_n']})" if np.isfinite(tg0) else "carga",
                  "geracao": f"geração (tg{res['tg_n']})"}
    for a, b, f in faixas:
        if b > a:
            ax_v.axvspan(a, b, color=FUNDO[f], lw=0, zorder=0)
            if b - a > 0.06 * (fim + args.resfriamento):
                ax_v.text((a + b) / 2, 1.0, nomes_fase[f], transform=ax_v.get_xaxis_transform(),
                          ha="center", va="top", fontsize=9, color="#555555")
    tons = plt.cm.Greys(np.linspace(0.35, 0.65, max(k, 1)))
    for i, r in enumerate(R):
        c = r["curva"]
        c = c[(c.t >= -60) & (c.t <= r["m"]["carga_s"] + args.resfriamento)]
        ax_v.plot(c.t, c.core, color=tons[i], lw=0.9, label=f"rodada v{i + 1}")
    t, v = curva_media(R, fim + args.resfriamento)
    ax_v.plot(t, v, color="black", lw=2, label="média")
    ax_v.set_xlabel("Segundos desde o início do llama-bench")
    ax_v.set_ylabel("Média dos núcleos (°C)")
    ax_v.set_title("Aquecimento ao longo do tempo", loc="left", fontsize=12)
    ax_v.legend(loc="lower right", fontsize=9, ncol=2, framealpha=0.92)
    estilo(ax_v, "both")

    sub = (f"{k} rodada{'s' if k != 1 else ''} · prompt {br(res['pp_tps'], 2)} t/s · geração {br(res['tg_tps'], 2)} t/s · "
           f"pico {br(res['pico_C'], 0)} °C · ventoinha até {br(res['ventoinha_max_rpm'], 0)} rpm · "
           f"throttling: {'sim' if res['throttle'] else 'não'}")
    fig.suptitle(f"{MAQUINA}, llama-bench - {rotulo(mod, False)}\n{sub}", fontsize=13)
    salvar(fig, saida, args.dpi)


# ------------------------------------------------------------------ CLI

def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    p = argparse.ArgumentParser(description="Compara tokens/s e temperaturas de modelos do llama-bench.")
    p.add_argument("pastas", nargs="*", help="pasta(s) onde procurar as rodadas (padrão: pasta do script)")
    p.add_argument("-o", "--saida", type=Path, help=f"pasta de saída (padrão: {PASTA_SAIDA} dentro da 1ª pasta)")
    p.add_argument("--resfriamento", type=float, default=300, help="segundos de resfriamento nas curvas (300)")
    p.add_argument("--base-temp", type=float, default=40, help="°C onde começam as barras de temperatura (40)")
    p.add_argument("--tjmax", type=float, default=0, help="desenha a linha de Tjunction, ex.: 100 (0 = não)")
    p.add_argument("-r", "--reps", type=int, default=5,
                   help="repetições do llama-bench, só para rodadas antigas sem test_time (5)")
    p.add_argument("--dpi", type=int, default=100)
    args = p.parse_args()

    raizes = [Path(x) for x in args.pastas] or [Path(__file__).resolve().parent]
    for r in raizes:
        if not r.is_dir():
            raise SystemExit(f"Não é uma pasta: {r}")
    print("Procurando rodadas em: " + ", ".join(str(r) for r in raizes))
    rodadas = encontrar_rodadas(raizes, args)
    if not rodadas:
        raise SystemExit("Nenhum log de sensores (CSV com coluna epoch) encontrado.")
    mods = agrupar(rodadas)

    for m in mods:
        r = m["res"]
        print(f"\n{rotulo(m, False)}")
        print(f"  {r['rodadas']} rodada(s) | prompt {br(r['pp_tps'], 2)} t/s | geração {br(r['tg_tps'], 2)} t/s | "
              f"fases: {r['fases']}")
        print(f"  repouso {br(r['repouso_C'])} °C | prompt {br(r['prompt_media_C'])} °C | "
              f"geração {br(r['geracao_media_C'])} °C | pico {br(r['pico_C'], 0)} °C")

    saida = args.saida or (raizes[0] / PASTA_SAIDA)
    saida.mkdir(parents=True, exist_ok=True)
    print("\nArquivos:")
    grafico_comparativo(mods, saida / "comparativo_modelos.png", args)
    grafico_curvas(mods, saida / "curvas_aquecimento.png", args)
    for m in mods:
        arq = re.sub(r"[^\w.-]+", "_", m["nome"])
        grafico_modelo(m, saida / f"{arq}.png", args)

    cols = ["modelo", "quantizacao", "params_B", "tamanho_MiB", "rodadas", "pp_n", "pp_tps", "pp_dp",
            "tg_n", "tg_tps", "tg_dp", "carga_s", "repouso_C", "prompt_media_C", "geracao_media_C",
            "carga_media_C", "pico_C", "aquecimento_C", "dissipador_pico_C", "ventoinha_media_rpm",
            "ventoinha_max_rpm", "throttle", "fases"]
    salvar_csv(pd.DataFrame([m["res"] for m in mods])[cols].round(3), saida / "resumo_modelos.csv")
    linhas = []
    for m in mods:
        for i, r in enumerate(m["rodadas"], 1):
            d = {"modelo": m["nome"], "rodada": f"v{i}", "arquivo": str(r["arquivo"]),
                 "data": datetime.fromtimestamp(r["m"]["inicio"]).strftime("%d/%m/%Y %H:%M")}
            d.update({k: v for k, v in r["m"].items() if k != "inicio"})
            linhas.append(d)
    salvar_csv(pd.DataFrame(linhas).round(3), saida / "rodadas.csv")


if __name__ == "__main__":
    sys.exit(main())
