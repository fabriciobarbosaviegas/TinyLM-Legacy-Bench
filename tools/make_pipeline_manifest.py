#!/usr/bin/env python3
"""Converte o catálogo models/manifest.csv no manifesto do pipeline (name,file,quant,params_b,sha256,chat).

Uso: python3 tools/make_pipeline_manifest.py --models-dir /home/gaia/models [--status candidato,ativo] [-o models.csv]

Só entram modelos com `status` na lista pedida (padrão: ativo). A coluna sha256 do pipeline recebe o
hash publicado do catálogo (vazio = o pipeline só verifica a estabilidade entre leituras).
Os arquivos são procurados em --models-dir pelo campo `arquivo` do catálogo.
"""
import argparse
import csv
import os
import sys


def convert(catalog_rows, models_dir, statuses):
    out = []
    for r in catalog_rows:
        if r.get("status", "").strip() not in statuses:
            continue
        out.append({
            "name": r["nome"].strip(),
            "file": os.path.join(models_dir, r["arquivo"].strip()),
            "quant": r.get("quant", "").strip(),
            "params_b": r.get("params_b", "").strip(),
            "sha256": r.get("sha256_publicado", "").strip(),
            "chat": (r.get("chat", "") or "chat").strip(),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default=os.path.join(os.path.dirname(__file__), "..", "models", "manifest.csv"))
    ap.add_argument("--models-dir", required=True)
    ap.add_argument("--status", default="ativo")
    ap.add_argument("-o", "--saida", default="-")
    a = ap.parse_args()
    with open(a.catalog, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(l for l in f if not l.lstrip().startswith("#"))]
    conv = convert(rows, a.models_dir, {s.strip() for s in a.status.split(",")})
    if not conv:
        print("Nenhum modelo com esse status no catálogo.", file=sys.stderr)
        return 1
    out = sys.stdout if a.saida == "-" else open(a.saida, "w", newline="", encoding="utf-8")
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["name", "file", "quant", "params_b", "sha256", "chat"])
    for r in conv:
        w.writerow([r["name"], r["file"], r["quant"], r["params_b"], r["sha256"], r["chat"]])
    if out is not sys.stdout:
        out.close()
        print("Gerado:", a.saida, f"({len(conv)} modelo(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
