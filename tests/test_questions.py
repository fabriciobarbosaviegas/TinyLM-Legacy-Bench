import json
import os
import re
import unittest

from tests._paths import ROOT

PREFIX = {"f": "fatos", "l": "local", "a": "aritmetica", "g": "linguagem", "r": "raciocinio", "x": "abstencao"}


class QuestionsFile(unittest.TestCase):
    def setUp(self):
        path = os.path.join(ROOT, "pipeline", "questions_pt.jsonl")
        with open(path, encoding="utf-8") as f:
            self.items = [json.loads(l) for l in f if l.strip() and not l.startswith("#")]

    def test_not_empty(self):
        self.assertGreaterEqual(len(self.items), 20)

    def test_required_keys_and_types(self):
        for it in self.items:
            for k in ("id", "cat", "q", "accept"):
                self.assertIn(k, it, f"{it.get('id')}: falta {k}")
            self.assertIsInstance(it["accept"], list)
            self.assertTrue(it["accept"], f"{it['id']}: accept vazio")

    def test_ids_unique(self):
        ids = [it["id"] for it in self.items]
        self.assertEqual(len(ids), len(set(ids)))

    def test_prefix_matches_category(self):
        for it in self.items:
            self.assertEqual(PREFIX.get(it["id"][0]), it["cat"], f"{it['id']}: prefixo x categoria")

    def test_regex_compile_and_normalized(self):
        for it in self.items:
            for p in it["accept"]:
                re.compile(p)
                literal = re.sub(r"\\.", "", p)  # ignora escapes como \W e \b
                self.assertEqual(literal, literal.lower(), f"{it['id']}: padrão deve estar em minúsculas")

    def test_manual_sheet_has_20_rows(self):
        import csv
        with open(os.path.join(ROOT, "questions", "avaliacao_manual_cli", "planilha_avaliacao_cli.csv"), newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 20)
        self.assertEqual([int(r["id"]) for r in rows], list(range(1, 21)))


if __name__ == "__main__":
    unittest.main()
