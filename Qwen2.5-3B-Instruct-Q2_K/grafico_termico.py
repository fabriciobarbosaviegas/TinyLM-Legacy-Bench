#!/usr/bin/env python3
"""
Gera o gráfico térmico (3 painéis) do llama-bench a partir dos CSV de log dos
sensores (coretemp + applesmc), no estilo da "rodada v3".

Com vários CSV (uma rodada por arquivo), o padrão é UM gráfico com a MÉDIA das
rodadas: cada rodada é alinhada pelo início do bench (t = 0), reamostrada a cada
1 s e as leituras de cada sensor são promediadas ponto a ponto.

Uso:
    python grafico_termico.py                 (usa os CSV da pasta do script)
    python grafico_termico.py PASTA           (todos os CSV da pasta e subpastas)
    python grafico_termico.py log1.csv log2.csv log3.csv -o media.png

Exemplos:
    # média com a divisão prompt/geração em 157 s após o início
    python3 grafico_termico.py log*.csv --tg 157 -o media.png

    # média com faixa mínimo–máximo entre as rodadas atrás de cada linha
    python3 grafico_termico.py log*.csv --faixa -o media.png

    # um gráfico por rodada, como antes
    python3 grafico_termico.py log*.csv --separado -o pasta_saida/

    # início/fim informados à mão (epoch, um valor por CSV, em ordem cronológica)
    python3 grafico_termico.py a.csv b.csv c.csv --inicio 1791933048 1791935715 1791938535

Fases sombreadas:
    linha de base  -> antes do início do bench
    prompt (pp)    -> do início até --tg (ou até o fim, se --tg não for dado)
    geração (tg)   -> de --tg até o fim do bench
    resfriamento   -> depois do fim, até o final do log

Início e fim de cada rodada são detectados pela frequência das CPUs (trecho com
as duas na frequência máxima de forma sustentada). Na média, o fim do bench é a
média das durações. Por padrão a média só cobre o intervalo de tempo presente em
todas as rodadas; --cobertura parcial estende até onde houver pelo menos uma.

Requisitos: pandas, matplotlib, numpy.
"""

import argparse
import glob
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

TITULO_BASE = "Mac mini 1,1 (Core Duo T2300), llama-bench {modelo}, 2 threads"
MODELO_PADRAO = "Qwen2.5 0.5B Q5_K_M"
TITULO_MEDIA = TITULO_BASE + " - média de {k} rodadas"
TITULO_RODADA = TITULO_BASE + " - rodada v{n}"

# (sufixo da coluna, rótulo na legenda, cor, estilo de linha)
PAINEL_CPU = [
    ("Core_0_C", "Core 0 (coretemp)", "tab:blue", "-"),
    ("Core_1_C", "Core 1 (coretemp)", "tab:red", "-"),
    ("TC0D_C", "TC0D (SMC)", "gray", "--"),
]
PAINEL_SMC = [
    ("TC0H_C", "TC0H (dissipador?)", "tab:green", "-"),
    ("TC0P_C", "TC0P", "tab:purple", "-"),
    ("TC1P_C", "TC1P", "tab:brown", "-"),
    ("TA0P_C", "TA0P (ar interno?)", "tab:pink", "-"),
    ("TN0P_C", "TN0P", "tab:olive", "-"),
    ("TN1P_C", "TN1P", "tab:cyan", "-"),
]
COR_FASE = {"base": "#efefef", "pp": "#e8f1fc", "tg": "#fdebd9", "resfr": "#ebf5ea"}


# ---------------------------------------------------------------- dados

def achar_coluna(df, sufixo):
    """Encontra a coluna cujo nome termina com o sufixo (ignora o prefixo do chip)."""
    for c in df.columns:
        if c.endswith(sufixo):
            return c
    return None


def detectar_bench(df, min_seg=10):
    """Retorna (inicio, fim) em epoch do trecho com as CPUs na frequência máxima."""
    fcols = [c for c in df.columns if c.startswith("freq_cpu")]
    if not fcols:
        raise SystemExit("Sem colunas freq_cpu*: informe --inicio e --fim.")
    fmax = df[fcols].max().min()
    cheio = (df[fcols] >= 0.97 * fmax).all(axis=1)
    # mediana móvel para ignorar picos isolados de frequência no repouso
    sustentado = cheio.astype(float).rolling(min_seg, center=True, min_periods=1).median() >= 0.5
    if not sustentado.any():
        raise SystemExit("Não encontrei trecho de carga sustentada: informe --inicio e --fim.")
    idx = np.flatnonzero(sustentado.to_numpy())
    return float(df["epoch"].iloc[idx[0]]), float(df["epoch"].iloc[idx[-1]])


def carregar(csv, inicio=None, fim=None):
    """Lê um CSV e devolve (df com coluna 't' relativa ao início, duração do bench em s)."""
    df = pd.read_csv(csv)
    if "epoch" not in df.columns:
        raise SystemExit(f"{csv}: coluna 'epoch' não encontrada.")
    df = df.sort_values("epoch").reset_index(drop=True)
    ini_auto, fim_auto = detectar_bench(df)
    t0 = inicio if inicio is not None else ini_auto
    t_fim = fim if fim is not None else fim_auto
    df["t"] = df["epoch"] - t0
    print(f"  {csv.name}: início {t0:.1f}, fim {t_fim:.1f}, carga {t_fim - t0:.0f} s, "
          f"log de {df['t'].iloc[0]:.0f} a {df['t'].iloc[-1]:.0f} s")
    return df, t_fim - t0


def media_rodadas(rodadas, antes, cobertura):
    """Alinha as rodadas em t=0, reamostra a cada 1 s e tira média/mín/máx de cada coluna."""
    inicios = [d["t"].iloc[0] for d, _ in rodadas]
    finais = [d["t"].iloc[-1] for d, _ in rodadas]
    if cobertura == "total":
        a, b = max(inicios), min(finais)
    else:
        a, b = min(inicios), max(finais)
    if antes >= 0:
        a = max(a, -antes)
    grade = np.arange(np.ceil(a), np.floor(b) + 1, 1.0)

    colunas = [c for c in rodadas[0][0].columns
               if c not in ("epoch", "t") and pd.api.types.is_numeric_dtype(rodadas[0][0][c])]
    med, mn, mx = {"t": grade}, {"t": grade}, {"t": grade}
    for c in colunas:
        pilha = []
        for d, _ in rodadas:
            if c not in d.columns:
                continue
            v = np.interp(grade, d["t"], d[c], left=np.nan, right=np.nan)
            pilha.append(v)
        pilha = np.vstack(pilha)
        med[c] = np.nanmean(pilha, axis=0)
        mn[c] = np.nanmin(pilha, axis=0)
        mx[c] = np.nanmax(pilha, axis=0)
    duracao = float(np.mean([dur for _, dur in rodadas]))
    return pd.DataFrame(med), pd.DataFrame(mn), pd.DataFrame(mx), duracao


# ---------------------------------------------------------------- gráfico

def plotar(df, fim_rel, saida, titulo, args, faixa=None, tg=None, rotulos=None):
    """df tem coluna 't' (segundos desde o início). faixa = (df_min, df_max) opcional."""
    if args.antes >= 0:
        df = df[df["t"] >= -args.antes]
        if faixa:
            faixa = tuple(f[f["t"] >= -args.antes] for f in faixa)
    t = df["t"].to_numpy()
    x_min, x_max = t[0], t[-1]

    rot_pp, rot_tg = rotulos or (args.rotulo_pp, args.rotulo_tg)
    if tg is not None and 0 < tg < fim_rel:
        carga = [(0, tg, "pp", rot_pp), (tg, fim_rel, "tg", rot_tg)]
    else:
        carga = [(0, fim_rel, "pp", "carga (pp + tg)")]
    fases = [(x_min, 0, "base", "linha de base")] + carga + [(fim_rel, x_max, "resfr", "resfriamento")]

    fig, axs = plt.subplots(
        3, 1, figsize=(13, 12.4), dpi=100, sharex=True,
        gridspec_kw={"height_ratios": [1.25, 1.0, 0.75], "hspace": 0.12},
    )
    ax_cpu, ax_smc, ax_fan = axs
    for ax in axs:
        for a, b, chave, _ in fases:
            if b > a:
                ax.axvspan(a, b, color=COR_FASE[chave], zorder=0, lw=0)

    def linha(ax, suf, rot, cor, ls, lw, degraus=False):
        c = achar_coluna(df, suf)
        if not c:
            return
        if faixa:
            ax.fill_between(t, faixa[0][c], faixa[1][c], color=cor, alpha=0.15, lw=0,
                            step="post" if degraus else None)
        ax.plot(t, df[c], color=cor, ls=ls, lw=lw, label=rot,
                drawstyle="steps-post" if degraus else "default")

    # --- painel 1: núcleos + die ---
    for suf, rot, cor, ls in PAINEL_CPU:
        linha(ax_cpu, suf, rot, cor, ls, 1.6 if ls == "-" else 1.3, degraus=suf.startswith("Core"))
    topo = (args.tjmax + 2) if args.tjmax else None
    if args.tjmax:
        ax_cpu.axhline(args.tjmax, color="black", ls=":", lw=0.9)
        ax_cpu.text(0.985, args.tjmax - 2, f"Tjunction/crit = {args.tjmax:g} °C",
                    transform=ax_cpu.get_yaxis_transform(), ha="right", va="top", fontsize=9.5)
    ax_cpu.set_ylim(40, topo)
    ax_cpu.set_ylabel("Temperatura (°C)", fontsize=11)
    ax_cpu.legend(loc="center right", fontsize=10, framealpha=0.9)
    y_rot = 40 + (ax_cpu.get_ylim()[1] - 40) * 0.03
    for a, b, _, rot in fases:
        a2, b2 = max(a, x_min), min(b, x_max)
        if b2 - a2 > (x_max - x_min) * 0.04:
            ax_cpu.text((a2 + b2) / 2, y_rot, rot, ha="center", va="bottom", fontsize=9.5)

    # --- painel 2: demais sensores SMC ---
    for suf, rot, cor, ls in PAINEL_SMC:
        linha(ax_smc, suf, rot, cor, ls, 1.4)
    if args.gate:
        ax_smc.axhline(args.gate, color="tab:green", ls=":", lw=0.9)
        ax_smc.text(0.985, args.gate, f"gate TC0H = {args.gate:g} °C",
                    transform=ax_smc.get_yaxis_transform(), ha="right", va="bottom",
                    fontsize=9.5, color="tab:green")
    ax_smc.set_ylabel("Temperatura (°C)", fontsize=11)
    ax_smc.legend(loc="upper right", ncol=2, fontsize=8.5, framealpha=0.9)

    # --- painel 3: ventoinha ---
    c_fan = achar_coluna(df, "Master__rpm") or achar_coluna(df, "rpm")
    if c_fan:
        suav = lambda s: s.rolling(args.suavizar, center=True, min_periods=1).mean() if args.suavizar > 1 else s
        if faixa:
            ax_fan.fill_between(t, suav(faixa[0][c_fan]), suav(faixa[1][c_fan]),
                                color="black", alpha=0.10, lw=0)
        ax_fan.plot(t, suav(df[c_fan]), color="black", lw=1.4)
    ax_fan.set_ylabel("Ventoinha (rpm)", fontsize=11)
    ax_fan.set_xlabel("Segundos desde o início do llama-bench", fontsize=11)

    for ax in axs:
        ax.grid(True, color="#888888", alpha=0.25, lw=0.8)
        ax.tick_params(labelsize=11)
        ax.set_xlim(x_min, x_max)

    fig.suptitle(titulo, fontsize=14, y=0.985)
    fig.subplots_adjust(left=0.08, right=0.985, top=0.955, bottom=0.06)
    saida = Path(saida)
    try:
        fig.savefig(saida, dpi=args.dpi)
    except OSError as e:
        # no Windows isso acontece quando o PNG está aberto em outro programa
        alternativa = saida.with_name(f"{saida.stem}_{time.strftime('%H%M%S')}{saida.suffix}")
        print(f"AVISO: não consegui gravar {saida.name} ({e.strerror}). "
              f"Ele está aberto em outro programa? Salvando como {alternativa.name}.")
        fig.savefig(alternativa, dpi=args.dpi)
        saida = alternativa
    plt.close(fig)
    print(f"-> {saida}")


# ---------------------------------------------------------------- CLI

RE_MD = re.compile(r"\|\s*(pp|tg)(\d+)\b[^|]*\|\s*([\d.]+)\s*(?:±|\+/-)")


def ler_llama_bench(arquivo):
    """Lê uma saída do llama-bench (md/txt, csv, json ou jsonl).
    Devolve lista de dicts {tipo: 'pp'|'tg', n: tokens, tps: tokens/s, reps: int|None}."""
    testes = []
    try:
        texto = arquivo.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return testes

    def de_registro(r):
        npp, ntg = int(r.get("n_prompt", 0) or 0), int(r.get("n_gen", 0) or 0)
        tps = r.get("avg_ts")
        if tps is None or (npp > 0) == (ntg > 0):
            return
        amostras = r.get("samples_ns")
        reps = len(amostras) if isinstance(amostras, list) else r.get("repetitions")
        testes.append({"tipo": "pp" if npp else "tg", "n": npp or ntg, "tps": float(tps),
                       "reps": int(reps) if reps else None})

    suf = arquivo.suffix.lower()
    if suf in (".json", ".jsonl"):
        try:
            dados = json.loads(texto)
            dados = dados if isinstance(dados, list) else [dados]
        except json.JSONDecodeError:
            dados = []
            for linha in texto.splitlines():
                try:
                    dados.append(json.loads(linha))
                except json.JSONDecodeError:
                    pass
        for r in dados:
            if isinstance(r, dict):
                de_registro(r)
    elif suf == ".csv":
        try:
            df = pd.read_csv(arquivo)
        except Exception:
            return testes
        if {"n_prompt", "n_gen", "avg_ts"} <= set(df.columns):
            for r in df.to_dict("records"):
                de_registro(r)
    else:  # tabela markdown impressa no terminal
        for m in RE_MD.finditer(texto):
            testes.append({"tipo": m.group(1), "n": int(m.group(2)), "tps": float(m.group(3)), "reps": None})
    return testes


def resolver_divisao(args, pastas, arquivos_sensor):
    """Calcula a fração do bench gasta no prompt. Devolve (fração, rotulos) ou (None, None)."""
    if args.pp_tps and args.tg_tps:
        testes = [{"tipo": "pp", "n": args.n_prompt, "tps": args.pp_tps, "reps": None},
                  {"tipo": "tg", "n": args.n_gen, "tps": args.tg_tps, "reps": None}]
        origem = "valores informados (--pp-tps / --tg-tps)"
    else:
        candidatos = []
        for p in pastas or {f.parent for f in arquivos_sensor}:
            for ext in ("*.json", "*.jsonl", "*.csv", "*.md", "*.txt", "*.log"):
                candidatos += [f for f in p.rglob(ext) if f not in arquivos_sensor]
        testes, achados = [], []
        for f in sorted(set(candidatos)):
            t = ler_llama_bench(f)
            if t:
                testes += t
                achados.append(f.name)
        if not testes:
            return None, None
        origem = "saída do llama-bench: " + ", ".join(achados)

    def tempo(tipo):
        ts = [t for t in testes if t["tipo"] == tipo]
        if not ts:
            return None, None
        tot = 0.0
        for t in ts:
            reps = t["reps"] or args.reps
            extra = 1 if (tipo == "pp" and not args.sem_warmup) else 0  # aquecimento repete o prompt
            tot += (reps + extra) * t["n"] / t["tps"]
        return tot / len(ts), ts[0]["n"]

    (t_pp, n_pp), (t_tg, n_tg) = tempo("pp"), tempo("tg")
    if not t_pp or not t_tg:
        return None, None
    frac = t_pp / (t_pp + t_tg)
    print(f"Divisão prompt/geração a partir de {origem}")
    print(f"  tempo estimado: pp{n_pp} {t_pp:.0f} s, tg{n_tg} {t_tg:.0f} s -> prompt = {frac:.1%} da carga")
    rot = (args.rotulo_pp if args.rotulo_pp != "auto" else f"prompt (pp{n_pp})",
           args.rotulo_tg if args.rotulo_tg != "auto" else f"geração (tg{n_tg})")
    return frac, rot


def expandir_entradas(entradas):
    """Aceita arquivos, pastas (procura *.csv dentro, inclusive em subpastas) e curingas."""
    arquivos, pastas = [], []
    for e in entradas:
        p = Path(e)
        if p.is_dir():
            pastas.append(p)
            arquivos += sorted(p.rglob("*.csv"))
        elif any(ch in e for ch in "*?["):
            arquivos += sorted(Path(x) for x in glob.glob(e))
        else:
            arquivos.append(p)
    # descarta arquivos repetidos (mesmo conteúdo em lugares diferentes, ex.: cópia
    # na pasta do modelo e original na subpasta da rodada)
    unicos, vistos = [], set()
    for f in arquivos:
        if not f.is_file():
            continue
        h = hashlib.md5(f.read_bytes()).hexdigest()
        if h in vistos:
            print(f"  (ignorando cópia repetida: {f})")
            continue
        vistos.add(h)
        unicos.append(f)
    if not unicos:
        raise SystemExit("Nenhum CSV encontrado em: " + ", ".join(entradas))
    return unicos, pastas


def main():
    try:
        sys.stdout.reconfigure(errors="replace")  # console do Windows
    except Exception:
        pass
    p = argparse.ArgumentParser(description="Gráfico térmico do llama-bench a partir dos CSV de sensores.")
    p.add_argument("csv", nargs="*",
                   help="CSVs (uma rodada por arquivo), uma pasta com os CSVs ou um curinga como *.csv. "
                        "Sem nada, usa a pasta onde está este script")
    p.add_argument("--modelo", help="nome do modelo no título (padrão: nome da pasta informada)")
    p.add_argument("-o", "--saida", type=Path,
                   help="PNG de saída (pasta, com --separado). Padrão: media_rodadas.png ao lado do 1º CSV")
    p.add_argument("--separado", action="store_true", help="um gráfico por rodada em vez da média")
    p.add_argument("--faixa", action="store_true", help="na média, sombreia o mínimo–máximo entre as rodadas")
    p.add_argument("--cobertura", choices=["total", "parcial"], default="total",
                   help="total: só o intervalo presente em todas as rodadas; parcial: onde houver ao menos uma")
    p.add_argument("--titulo", help="título; {n} = nº da rodada, {k} = nº de rodadas, {arquivo} = nome do CSV")
    p.add_argument("--inicio", type=float, nargs="+", help="epoch do início do bench, um por CSV (padrão: detectado)")
    p.add_argument("--fim", type=float, nargs="+", help="epoch do fim do bench, um por CSV (padrão: detectado)")
    p.add_argument("--tg", type=float, help="segundos após o início em que começa a geração (tg)")
    p.add_argument("--pp-tps", type=float, help="t/s do teste de prompt (coluna t/s da linha ppN do llama-bench)")
    p.add_argument("--tg-tps", type=float, help="t/s do teste de geração (linha tgN do llama-bench)")
    p.add_argument("--n-prompt", type=int, default=64, help="tokens do teste de prompt (o N de ppN)")
    p.add_argument("--n-gen", type=int, default=32, help="tokens do teste de geração (o N de tgN)")
    p.add_argument("-r", "--reps", type=int, default=5, help="repetições do llama-bench (-r), padrão 5")
    p.add_argument("--sem-warmup", action="store_true", help="o llama-bench rodou com --no-warmup")
    p.add_argument("--rotulo-pp", default="auto", help="rótulo da fase de prompt (auto = prompt (ppN))")
    p.add_argument("--rotulo-tg", default="auto", help="rótulo da fase de geração (auto = geração (tgN))")
    p.add_argument("--antes", type=float, default=60,
                   help="segundos de linha de base mostrados antes do início (-1 = tudo que houver)")
    p.add_argument("--tjmax", type=float, default=100, help="linha de Tjunction em °C (0 desativa)")
    p.add_argument("--gate", type=float, default=47, help="linha do gate TC0H em °C (0 desativa)")
    p.add_argument("--suavizar", type=int, default=5, help="janela da média móvel da ventoinha, em amostras")
    p.add_argument("--dpi", type=int, default=100)
    args = p.parse_args()

    if not args.csv:  # ex.: botão "Run" do VS Code, sem argumentos
        args.csv = [str(Path(__file__).resolve().parent)]
        print(f"Sem arquivos informados; usando a pasta do script: {args.csv[0]}")
    arquivos, pastas = expandir_entradas(args.csv)
    arquivos = [f for f in arquivos if "epoch" in pd.read_csv(f, nrows=0).columns]
    if not arquivos:
        raise SystemExit("Nenhum CSV com a coluna 'epoch' foi encontrado.")
    arquivos = sorted(arquivos, key=lambda f: float(pd.read_csv(f, nrows=1)["epoch"].iloc[0]))
    k = len(arquivos)
    modelo = args.modelo or (pastas[0].resolve().name if pastas else MODELO_PADRAO)
    base_saida = pastas[0] if pastas else arquivos[0].parent
    for nome in ("inicio", "fim"):
        v = getattr(args, nome)
        if v is not None and len(v) != k:
            raise SystemExit(f"--{nome} precisa de {k} valores (um por CSV, em ordem cronológica).")
    pega = lambda lst, i: lst[i] if lst else None

    print("Rodadas (em ordem cronológica):")
    rodadas = [carregar(f, pega(args.inicio, i), pega(args.fim, i)) for i, f in enumerate(arquivos)]

    frac, rotulos = (None, None) if args.tg is not None else resolver_divisao(args, pastas, set(arquivos))
    if args.tg is not None:
        rotulos = (args.rotulo_pp if args.rotulo_pp != "auto" else f"prompt (pp{args.n_prompt})",
                   args.rotulo_tg if args.rotulo_tg != "auto" else f"geração (tg{args.n_gen})")
    elif frac is None:
        print("AVISO: sem a saída do llama-bench não dá para separar prompt e geração.\n"
              "  Coloque o arquivo de saída do bench na pasta ou informe --pp-tps e --tg-tps\n"
              "  (valores da coluna t/s das linhas ppN e tgN). Ou use --tg SEGUNDOS.")
    divisao = lambda dur: args.tg if args.tg is not None else (frac * dur if frac else None)

    if args.separado or k == 1:
        destino = args.saida
        if destino and k > 1:
            destino.mkdir(parents=True, exist_ok=True)
        for n, (f, (df, dur)) in enumerate(zip(arquivos, rodadas), start=1):
            if destino and k == 1:
                saida = destino
            elif destino:
                saida = destino / f"rodada_v{n}.png"
            else:
                saida = base_saida / f"rodada_v{n}.png"
            titulo = (args.titulo or TITULO_RODADA).format(n=n, k=k, arquivo=f.name, modelo=modelo)
            print(f"  rodada v{n}: geração começa em {divisao(dur) or 0:.0f} s")
            plotar(df, dur, saida, titulo, args, tg=divisao(dur), rotulos=rotulos)
        return

    med, mn, mx, dur = media_rodadas(rodadas, args.antes, args.cobertura)
    print(f"Média: {k} rodadas, de {med['t'].iloc[0]:.0f} a {med['t'].iloc[-1]:.0f} s, "
          f"duração média do bench {dur:.0f} s")
    saida = args.saida or (base_saida / "media_rodadas.png")
    titulo = (args.titulo or TITULO_MEDIA).format(n="", k=k, arquivo="", modelo=modelo)
    if divisao(dur):
        print(f"  geração começa em {divisao(dur):.0f} s (de {dur:.0f} s de carga)")
    plotar(med, dur, saida, titulo, args, faixa=(mn, mx) if args.faixa else None,
           tg=divisao(dur), rotulos=rotulos)


if __name__ == "__main__":
    sys.exit(main())
