import os
import shutil
import tempfile
import unittest

from tests._paths import ROOT
import validate_run as vr

RAW = os.path.join(ROOT, "data", "raw")


class RealData(unittest.TestCase):
    def test_all_raw_runs_have_no_fail(self):
        runs = vr.find_runs(RAW)
        self.assertGreaterEqual(len(runs), 3)
        for r in runs:
            kind, res = vr.validate(r)
            fails = [m for lvl, m in res if lvl == vr.FAIL]
            self.assertEqual(fails, [], f"{r}: {fails}")

    def test_kinds_detected(self):
        kinds = {vr.detect_kind(r) for r in vr.find_runs(RAW)}
        self.assertEqual(kinds, {"termico-v1", "termico-v3"})


class Corruptions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        src = [r for r in vr.find_runs(RAW) if "_v3_" in r][0]
        self.dst = os.path.join(self.tmp, "run")
        shutil.copytree(src, self.dst)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def fails(self):
        return [m for lvl, m in vr.validate(self.dst)[1] if lvl == vr.FAIL]

    def test_baseline_ok(self):
        self.assertEqual(self.fails(), [])

    def test_missing_file(self):
        os.remove(os.path.join(self.dst, "log.csv"))
        self.assertTrue(any("log.csv" in m for m in self.fails()))

    def test_markers_out_of_order(self):
        p = os.path.join(self.dst, "marcadores.csv")
        out = []
        for line in open(p).read().splitlines():
            k, v = line.split(",", 1)
            out.append(f"{k},1791068500.0" if k == "bench_fim" else line)  # bench_fim antes de bench_inicio
        open(p, "w").write("\n".join(out) + "\n")
        self.assertTrue(any("fora de ordem" in m for m in self.fails()))

    def test_epoch_not_increasing(self):
        p = os.path.join(self.dst, "log.csv")
        lines = open(p).read().splitlines()
        lines[10], lines[11] = lines[11], lines[10]
        open(p, "w").write("\n".join(lines) + "\n")
        self.assertTrue(any("crescente" in m for m in self.fails()))

    def test_ragged_row(self):
        p = os.path.join(self.dst, "log.csv")
        with open(p, "a") as f:
            f.write("1,2,3\n")
        self.assertTrue(any("campos" in m for m in self.fails()))

    def test_unknown_folder(self):
        empty = os.path.join(self.tmp, "vazia")
        os.makedirs(empty)
        self.assertEqual(vr.validate(empty)[0], None)


if __name__ == "__main__":
    unittest.main()
