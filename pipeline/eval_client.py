#!/usr/bin/env python3
"""Cliente de avaliação para o llama-server (somente biblioteca padrão do Python 3).

Envia cada pergunta do arquivo JSONL (temperatura 0, seed 42, sem cache de prompt),
pontua a resposta por expressões regulares e grava:
  <out>/eval.csv           uma linha por pergunta
  <out>/eval.jsonl         registro completo (inclui resposta bruta)
  <out>/eval_summary.json  acerto geral, por categoria e velocidade média
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request


def norm(s: str) -> str:
    """minúsculas, sem acentos, espaços normalizados."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip()


def is_correct(item: dict, text: str) -> bool:
    n = norm(text)
    return any(re.search(p, n) for p in item["accept"])


def http(url, payload=None, timeout=60):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def alive(pid):
    if pid is None:
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def wait_ready(base, timeout, pid):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not alive(pid):
            print("ERRO: o llama-server encerrou antes de ficar pronto (veja server.log).", flush=True)
            return False
        try:
            status, _ = http(base + "/health", timeout=5)
            if status == 200:
                print(f"servidor pronto após {time.time() - t0:.0f}s", flush=True)
                return True
        except (urllib.error.URLError, OSError):
            pass  # 503 durante o carregamento do modelo, ou conexão recusada
        time.sleep(2)
    print("ERRO: tempo esgotado esperando o servidor.", flush=True)
    return False


def ask(base, endpoint, system, question, max_tokens, timeout):
    if endpoint == "chat":
        payload = {
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": question}],
            "temperature": 0, "seed": 42, "max_tokens": max_tokens, "cache_prompt": False, "stream": False,
        }
        path = "/v1/chat/completions"
    else:  # completion (modelos sem template de chat)
        payload = {
            "prompt": f"{system}\n\nPergunta: {question}\nResposta:",
            "temperature": 0, "seed": 42, "n_predict": max_tokens, "cache_prompt": False, "stream": False,
        }
        path = "/completion"
    t0 = time.time()
    _, body = http(base + path, payload, timeout=timeout)
    wall = time.time() - t0
    r = json.loads(body)
    if endpoint == "chat":
        ch = r["choices"][0]
        text, finish = ch["message"].get("content") or "", ch.get("finish_reason")
    else:
        text, finish = r.get("content", ""), r.get("stop_type") or r.get("stopped_limit")
    tm = r.get("timings", {}) or {}
    us = r.get("usage", {}) or {}
    return {
        "text": text, "finish": finish, "wall_s": wall,
        "prompt_n": tm.get("prompt_n", us.get("prompt_tokens")),
        "pred_n": tm.get("predicted_n", us.get("completion_tokens")),
        "prompt_tps": tm.get("prompt_per_second"),
        "pred_tps": tm.get("predicted_per_second"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--questions", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-tokens", type=int, default=64)
    ap.add_argument("--ready-timeout", type=int, default=900)
    ap.add_argument("--request-timeout", type=int, default=900)
    ap.add_argument("--pid", type=int, default=None, help="PID do llama-server (para detectar queda)")
    ap.add_argument("--system", default="Responda em português, de forma curta e direta, em uma frase.")
    ap.add_argument("--endpoint", choices=["chat", "completion"], default="chat")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()

    items = [json.loads(l) for l in open(a.questions, encoding="utf-8") if l.strip() and not l.startswith("#")]
    if a.limit:
        items = items[: a.limit]
    os.makedirs(a.out, exist_ok=True)
    if not wait_ready(a.url, a.ready_timeout, a.pid):
        return 3

    rows, errors, consecutive = [], 0, 0
    for i, it in enumerate(items, 1):
        try:
            r = ask(a.url, a.endpoint, a.system, it["q"], a.max_tokens, a.request_timeout)
            ok = is_correct(it, r["text"])
            consecutive = 0
        except Exception as e:  # noqa: BLE001
            r = {"text": f"[ERRO: {e}]", "finish": "erro", "wall_s": 0, "prompt_n": None, "pred_n": None,
                 "prompt_tps": None, "pred_tps": None}
            ok, errors, consecutive = False, errors + 1, consecutive + 1
        rec = {"id": it["id"], "cat": it["cat"], "q": it["q"], "correct": int(ok), **r}
        rows.append(rec)
        print(f"[{i}/{len(items)}] {it['id']} {'OK ' if ok else 'ERR'} {r['wall_s']:.0f}s | {r['text'][:70]!r}", flush=True)
        if consecutive >= 3 or not alive(a.pid):
            print("ERRO: falhas consecutivas ou servidor encerrado; interrompendo.", flush=True)
            break

    with open(os.path.join(a.out, "eval.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(a.out, "eval.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "cat", "correct", "prompt_n", "pred_n", "prompt_tps", "pred_tps", "wall_s", "finish", "answer"])
        for r in rows:
            w.writerow([r["id"], r["cat"], r["correct"], r["prompt_n"], r["pred_n"], r["prompt_tps"], r["pred_tps"],
                        f"{r['wall_s']:.2f}", r["finish"], r["text"].replace("\n", " ⏎ ")])

    valid = [r for r in rows if r["finish"] != "erro"]
    cats = {}
    for r in rows:
        c = cats.setdefault(r["cat"], [0, 0])
        c[0] += r["correct"]
        c[1] += 1
    tps = [r["pred_tps"] for r in valid if r["pred_tps"]]
    summary = {
        "n_perguntas": len(rows), "n_planejadas": len(items), "acertos": sum(r["correct"] for r in rows),
        "acuracia": (sum(r["correct"] for r in rows) / len(rows)) if rows else None,
        "erros_http": errors,
        "por_categoria": {k: {"acertos": v[0], "total": v[1], "acuracia": v[0] / v[1]} for k, v in cats.items()},
        "pred_tps_medio": (sum(tps) / len(tps)) if tps else None,
        "max_tokens": a.max_tokens, "endpoint": a.endpoint, "seed": 42, "temperatura": 0,
        "completo": len(rows) == len(items),
    }
    with open(os.path.join(a.out, "eval_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"acurácia: {summary['acertos']}/{summary['n_perguntas']}"
          + (f" | geração média {summary['pred_tps_medio']:.2f} t/s" if tps else ""), flush=True)
    return 0 if summary["completo"] and errors == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
