import csv
import datetime
import os
import shutil
import subprocess
import tempfile
import unittest

from tests._paths import ROOT
import make_pipeline_manifest as mpm


class Manifest(unittest.TestCase):
    def test_convert_filters_by_status(self):
        rows = [
            {"nome": "a", "arquivo": "a.gguf", "quant": "Q4_0", "params_b": "0.5", "sha256_publicado": "abc", "status": "ativo", "chat": ""},
            {"nome": "b", "arquivo": "b.gguf", "quant": "Q8_0", "params_b": "0.3", "sha256_publicado": "", "status": "candidato", "chat": "completion"},
        ]
        out = mpm.convert(rows, "/m", {"ativo"})
        self.assertEqual([r["name"] for r in out], ["a"])
        self.assertEqual(out[0]["file"], "/m/a.gguf")
        self.assertEqual(out[0]["sha256"], "abc")
        self.assertEqual(out[0]["chat"], "chat")
        both = mpm.convert(rows, "/m", {"ativo", "candidato"})
        self.assertEqual(both[1]["chat"], "completion")

    def test_catalog_file_is_valid(self):
        with open(os.path.join(ROOT, "models", "manifest.csv"), newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        names = [r["nome"] for r in rows]
        self.assertEqual(len(names), len(set(names)))
        for r in rows:
            self.assertIn(r["status"], {"ativo", "candidato", "descartado"})
            if r["sha256_publicado"]:
                self.assertEqual(len(r["sha256_publicado"]), 64)


class NewExperiment(unittest.TestCase):
    def test_scaffold_numbering_and_placeholders(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "tools"))
            shutil.copy(os.path.join(ROOT, "tools", "new_experiment.sh"), os.path.join(tmp, "tools"))
            shutil.copytree(os.path.join(ROOT, "experiments", "_template"), os.path.join(tmp, "experiments", "_template"))
            sh = os.path.join(tmp, "tools", "new_experiment.sh")
            ano = datetime.date.today().year
            subprocess.run(["bash", sh, "teste-um", "Teste Um"], check=True, capture_output=True)
            subprocess.run(["bash", sh, "teste-dois", "Teste Dois"], check=True, capture_output=True)
            d1 = os.path.join(tmp, "experiments", f"EXP-{ano}-001-teste-um")
            d2 = os.path.join(tmp, "experiments", f"EXP-{ano}-002-teste-dois")
            self.assertTrue(os.path.isdir(d1) and os.path.isdir(d2))
            txt = open(os.path.join(d1, "PREREGISTRO.md"), encoding="utf-8").read()
            self.assertIn(f"EXP-{ano}-001", txt)
            self.assertNotIn("{{", txt)
            bad = subprocess.run(["bash", sh, "Slug Inválido"], capture_output=True)
            self.assertNotEqual(bad.returncode, 0)
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
