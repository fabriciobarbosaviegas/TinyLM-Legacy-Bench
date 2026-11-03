#!/usr/bin/env python3
"""Valida a estrutura e a consistência de uma pasta de execução.

Tipos reconhecidos (detecção automática):
  termico-v1   pasta `termico_*` do bench_termico v1/v2 (sem `script:` no meta.txt)
  termico-v3   pasta `termico_*` do bench_termico v3 (meta.txt com `script: bench_termico_v3.sh`)
  pipeline     rodada do pipeline (contém run_meta.txt e uma pasta por modelo)

Uso:
  python3 tools/validate_run.py <pasta> [<pasta> ...]
  python3 tools/validate_run.py --all data/raw        # percorre recursivamente

Códigos de saída: 0 = sem FAIL; 1 = pelo menos um FAIL. Avisos (WARN) não reprovam.
Somente biblioteca padrão.
"""
import argparse
import csv
import os
import sys

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"

FILES_V1 = ["bench.csv", "bench.err", "log.csv", "marcadores.csv", "meta.txt", "resumo_bench.txt"]
FILES_V3 = FILES_V1 + ["sensors_inicio.txt", "sensors_fim.txt"]
MARKERS_V1 = ["baseline_inicio", "bench_inicio", "bench_fim", "fim"]
MARKERS_V3 = ["espera_inicio", "espera_fim", "baseline_inicio", "bench_inicio", "bench_fim", "fim"]
META_KEYS = ["data", "kernel", "cpu", "modelo", "threads", "governor"]
MAX_GAP_S = 5.0


def read_kv(path):
    d = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if ":" in line:
                k, v = line.split(":", 1)
                d[k.strip()] = v.strip()
            elif "=" in line:
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    return d


def read_markers(path):
    out, order = {}, []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "," in line:
                k, v = line.split(",", 1)
                try:
                    out[k] = float(v)
                    order.append(k)
                except ValueError:
                    pass
    return out, order


def detect_kind(path):
    if os.path.exists(os.path.join(path, "run_meta.txt")):
        return "pipeline"
    meta = os.path.join(path, "meta.txt")
    if os.path.exists(meta) and "bench_termico_v3" in read_kv(meta).get("script", ""):
        return "termico-v3"
    if os.path.exists(meta):
        return "termico-v1"
    return None


def check_log(path, res, label="log.csv"):
    try:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
    except OSError as e:
        res.append((FAIL, f"{label}: não foi possível ler ({e})"))
        return None
    if len(rows) < 3:
        res.append((FAIL, f"{label}: poucas linhas ({len(rows)})"))
        return None
    header = rows[0]
    if header[0] != "epoch":
        res.append((FAIL, f"{label}: a primeira coluna deve ser 'epoch' (encontrado '{header[0]}')"))
    if not any(h.startswith("coretemp:Core") for h in header):
        res.append((FAIL, f"{label}: nenhuma coluna coretemp:Core*"))
    bad = [i for i, r in enumerate(rows[1:], 2) if len(r) != len(header)]
    if bad:
        res.append((FAIL, f"{label}: {len(bad)} linha(s) com nº de campos diferente do cabeçalho (ex.: linha {bad[0]})"))
        return None
    try:
        ep = [float(r[0]) for r in rows[1:]]
    except ValueError:
        res.append((FAIL, f"{label}: coluna epoch não numérica"))
        return None
    if any(b <= a for a, b in zip(ep, ep[1:])):
        res.append((FAIL, f"{label}: epoch não é estritamente crescente"))
    gaps = [b - a for a, b in zip(ep, ep[1:])]
    if gaps and max(gaps) > MAX_GAP_S:
        res.append((WARN, f"{label}: lacuna de amostragem de {max(gaps):.1f}s (> {MAX_GAP_S:g}s)"))
    else:
        res.append((PASS, f"{label}: {len(ep)} amostras, intervalo médio {sum(gaps) / len(gaps):.3f}s, maior lacuna {max(gaps):.3f}s"))
    return {"header": header, "epoch": ep, "rows": rows[1:]}


def check_markers(path, expected, log, res):
    try:
        mk, order = read_markers(path)
    except OSError as e:
        res.append((FAIL, f"marcadores.csv: não foi possível ler ({e})"))
        return
    missing = [m for m in expected if m not in mk]
    if missing:
        res.append((FAIL, f"marcadores.csv: faltam marcadores {missing}"))
        return
    seq = [mk[m] for m in expected]
    if any(b < a for a, b in zip(seq, seq[1:])):
        res.append((FAIL, "marcadores.csv: marcadores fora de ordem temporal"))
    else:
        res.append((PASS, "marcadores.csv: marcadores completos e em ordem"))
    if log:
        lo, hi = log["epoch"][0], log["epoch"][-1]
        if not (lo - 2 <= mk["bench_inicio"] <= hi + 2 and lo - 2 <= mk["bench_fim"] <= hi + 2):
            res.append((FAIL, "marcadores.csv: bench_inicio/bench_fim fora do intervalo do log.csv"))
        elif mk["bench_inicio"] - lo < 5:
            res.append((WARN, "log.csv: menos de 5 s de linha de base antes do benchmark"))


def check_bench_csv(path, res):
    try:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except OSError as e:
        res.append((FAIL, f"{os.path.basename(path)}: não foi possível ler ({e})"))
        return
    try:
        pp = [r for r in rows if int(r["n_prompt"]) > 0 and int(r["n_gen"]) == 0]
        tg = [r for r in rows if int(r["n_gen"]) > 0 and int(r["n_prompt"]) == 0]
    except (KeyError, ValueError):
        res.append((FAIL, f"{os.path.basename(path)}: colunas n_prompt/n_gen ausentes ou inválidas"))
        return
    if not pp or not tg:
        res.append((FAIL, f"{os.path.basename(path)}: precisa de ao menos uma linha de prompt (pp) e uma de geração (tg)"))
        return
    res.append((PASS, f"{os.path.basename(path)}: pp={float(pp[0]['avg_ts']):.3f} t/s, tg={float(tg[0]['avg_ts']):.3f} t/s"))


def check_meta(path, res, kind):
    meta = read_kv(path)
    missing = [k for k in META_KEYS if k not in meta]
    if missing:
        res.append((FAIL, f"meta.txt: faltam chaves {missing}"))
    else:
        res.append((PASS, "meta.txt: chaves obrigatórias presentes"))
    if meta.get("temperatura_ambiente_C", "nao_informada") == "nao_informada":
        res.append((WARN, "meta.txt: temperatura ambiente não informada"))
    h = [meta.get("sha256_modelo"), meta.get("sha256_leitura1"), meta.get("sha256_leitura2")]
    if meta.get("sha256_leitura1") and meta.get("sha256_leitura1") != meta.get("sha256_leitura2"):
        res.append((WARN, "meta.txt: sha256 do modelo difere entre as duas leituras"))
    if not any(h):
        res.append((WARN, "meta.txt: sem sha256 do modelo registrado"))
    if meta.get("hash_estavel") == "NAO":
        res.append((WARN, "meta.txt: hash_estavel = NAO"))
    if kind == "termico-v3":
        for k in ("gate_inicio_ok", "gate_fim_ok"):
            if meta.get(k) == "nao":
                res.append((WARN, f"meta.txt: {k} = nao (limite de espera atingido)"))
        if meta.get("ABORTADO_TERMICO"):
            res.append((FAIL, "meta.txt: execução abortada por temperatura (resultado parcial)"))
    return meta


def validate_termico(path, kind):
    res = []
    for f in (FILES_V3 if kind == "termico-v3" else FILES_V1):
        res.append((PASS if os.path.exists(os.path.join(path, f)) else FAIL, f"arquivo {f}"))
    if any(r[0] == FAIL for r in res):
        return [r for r in res if r[0] == FAIL]
    check_meta(os.path.join(path, "meta.txt"), res, kind)
    log = check_log(os.path.join(path, "log.csv"), res)
    check_markers(os.path.join(path, "marcadores.csv"), MARKERS_V3 if kind == "termico-v3" else MARKERS_V1, log, res)
    check_bench_csv(os.path.join(path, "bench.csv"), res)
    return res


def validate_pipeline(path):
    res = []
    for f in ("run_meta.txt", "models.csv"):
        res.append((PASS if os.path.exists(os.path.join(path, f)) else FAIL, f"arquivo {f}"))
    models = sorted(d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d)))
    if not models:
        res.append((FAIL, "nenhuma pasta de modelo"))
    for m in models:
        mdir = os.path.join(path, m)
        pre = f"[{m}] "
        for f in ("meta.txt", "status.txt", "marcadores.csv", "log.csv"):
            if not os.path.exists(os.path.join(mdir, f)):
                res.append((FAIL, pre + f"falta {f}"))
        if not os.path.exists(os.path.join(mdir, "meta.txt")) or not os.path.exists(os.path.join(mdir, "log.csv")):
            continue
        status = read_kv(os.path.join(mdir, "status.txt")).get("status", "?") if os.path.exists(os.path.join(mdir, "status.txt")) else "?"
        lvl = PASS if status == "ok" else WARN
        res.append((lvl, pre + f"status = {status}"))
        meta = read_kv(os.path.join(mdir, "meta.txt"))
        if meta.get("hash_estavel") == "NAO":
            res.append((WARN, pre + "hash_estavel = NAO"))
        if str(meta.get("hash_confere_manifesto", "")).startswith("NAO"):
            res.append((WARN, pre + "hash não confere com o manifesto"))
        sub = []
        log = check_log(os.path.join(mdir, "log.csv"), sub, label=pre + "log.csv")
        res.extend(sub)
        for b in sorted(f for f in os.listdir(mdir) if f.startswith("bench_t") and f.endswith(".csv")):
            check_bench_csv(os.path.join(mdir, b), res)
    return res


def validate(path):
    kind = detect_kind(path)
    if kind is None:
        return None, [(FAIL, "tipo de pasta não reconhecido (sem meta.txt nem run_meta.txt)")]
    if kind == "pipeline":
        return kind, validate_pipeline(path)
    return kind, validate_termico(path, kind)


def find_runs(root):
    runs = []
    for dp, dn, fn in os.walk(root):
        if "run_meta.txt" in fn or ("meta.txt" in fn and "log.csv" in fn and "marcadores.csv" in fn):
            runs.append(dp)
            dn[:] = []
    return sorted(runs)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--all", action="store_true", help="trata cada argumento como raiz e procura execuções dentro dela")
    ap.add_argument("--quiet", action="store_true", help="mostra só WARN e FAIL")
    a = ap.parse_args()
    targets = []
    for p in a.paths:
        targets.extend(find_runs(p) if a.all else [p])
    if not targets:
        print("Nenhuma execução encontrada.")
        return 1
    total_fail = 0
    for t in targets:
        kind, res = validate(t)
        fails = sum(1 for r in res if r[0] == FAIL)
        warns = sum(1 for r in res if r[0] == WARN)
        total_fail += fails
        print(f"\n{t}  [{kind}]  -> {'FAIL' if fails else 'OK'} ({fails} FAIL, {warns} WARN)")
        for lvl, msg in res:
            if a.quiet and lvl == PASS:
                continue
            print(f"  {lvl:4}  {msg}")
    print(f"\n{len(targets)} execução(ões) verificada(s); {total_fail} FAIL no total.")
    return 1 if total_fail else 0


if __name__ == "__main__":
    sys.exit(main())
