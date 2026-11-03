import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from tests._paths import ROOT
import eval_client as ec


def load_items():
    with open(os.path.join(ROOT, "pipeline", "questions_pt.jsonl"), encoding="utf-8") as f:
        return {j["id"]: j for j in (json.loads(l) for l in f if l.strip())}


class Normalize(unittest.TestCase):
    def test_accents_and_case(self):
        self.assertEqual(ec.norm("Brasília É a CAPITAL"), "brasilia e a capital")

    def test_whitespace(self):
        self.assertEqual(ec.norm("  a \n  b\t c "), "a b c")


class Scoring(unittest.TestCase):
    def setUp(self):
        self.q = load_items()

    def check(self, qid, text, expected):
        self.assertEqual(ec.is_correct(self.q[qid], text), expected, f"{qid}: {text!r}")

    def test_facts(self):
        self.check("f01", "Brasília é a capital.", True)
        self.check("f01", "São Paulo.", False)
        self.check("f06", "Machado de Assis", True)

    def test_number_word_boundary(self):
        self.check("a01", "O resultado é 4.", True)
        self.check("a01", "É 14.", False)
        self.check("a02", "56", True)
        self.check("a02", "65", False)

    def test_yes_no_must_start_with_yes(self):
        self.check("g05", "Sim.", True)
        self.check("g05", "Sim, o gelo é frio.", True)
        self.check("g05", "Não, sim.", False)

    def test_reverse_word(self):
        self.check("g01", "asac", True)
        self.check("g01", "casa", False)

    def test_local(self):
        self.check("l01", "Camaquã fica no Rio Grande do Sul.", True)
        self.check("l01", "Camaquã é uma cidade na Bahia.", False)

    def test_abstention(self):
        self.check("x01", "Não sei quem foi.", True)
        self.check("x01", "Esse país não existe.", True)
        self.check("x01", "O presidente foi João Silva.", False)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(n))
        assert body["temperature"] == 0 and body["seed"] == 42 and body["cache_prompt"] is False
        r = {"choices": [{"message": {"content": "Brasília."}, "finish_reason": "stop"}],
             "timings": {"prompt_n": 30, "predicted_n": 4, "prompt_per_second": 1.6, "predicted_per_second": 1.25}}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(r).encode())


class AskAgainstFakeServer(unittest.TestCase):
    def test_parses_timings(self):
        srv = HTTPServer(("127.0.0.1", 0), _Handler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            r = ec.ask(f"http://127.0.0.1:{srv.server_address[1]}", "chat", "sys", "Qual é a capital do Brasil?", 32, 10)
        finally:
            srv.shutdown()
        self.assertEqual(r["text"], "Brasília.")
        self.assertEqual(r["finish"], "stop")
        self.assertEqual(r["pred_n"], 4)
        self.assertAlmostEqual(r["pred_tps"], 1.25)


if __name__ == "__main__":
    unittest.main()
