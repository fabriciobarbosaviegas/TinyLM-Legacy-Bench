import csv
import os
import tempfile
import unittest

from tests._paths import ROOT  # noqa: F401
import aggregate as ag

BENCH_HDR = ["build_commit", "model_type", "model_size", "n_threads", "n_prompt", "n_gen", "avg_ts", "stddev_ts"]


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class Parsers(unittest.TestCase):
    def test_parse_ppl(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "ppl.txt")
            write(p, "lixo\nFinal estimate: PPL = 17.4321 +/- 0.5123\n")
            self.assertEqual(ag.parse_ppl(p), (17.4321, 0.5123))
            write(p, "sem resultado")
            self.assertEqual(ag.parse_ppl(p), (None, None))
            self.assertEqual(ag.parse_ppl(os.path.join(d, "nao_existe")), (None, None))

    def test_read_kv_and_markers(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "m.txt"), "a: 1\nb=2\nc: x: y\n")
            kv = ag.read_kv(os.path.join(d, "m.txt"))
            self.assertEqual((kv["a"], kv["b"], kv["c"]), ("1", "2", "x: y"))
            write(os.path.join(d, "mk.csv"), "inicio,10.5\nfim,20\nruim,abc\n")
            self.assertEqual(ag.markers(os.path.join(d, "mk.csv")), {"inicio": 10.5, "fim": 20.0})

    def test_thermal_stats(self):
        rows = [
            {"epoch": "1", "coretemp:Core_0_C": "50", "coretemp:Core_1_C": "52", "applesmc:TC0H_C": "45.0",
             "applesmc:Master__rpm": "1500", "throttle_count": "0", "mem_avail_kB": "2048", "swap_used_kB": "0", "proc_hwm_kB": "1024", "freq_cpu0_kHz": "1000000"},
            {"epoch": "2", "coretemp:Core_0_C": "80", "coretemp:Core_1_C": "84", "applesmc:TC0H_C": "60.5",
             "applesmc:Master__rpm": "1700", "throttle_count": "2", "mem_avail_kB": "1024", "swap_used_kB": "512", "proc_hwm_kB": "4096", "freq_cpu0_kHz": "1666000"},
        ]
        s = ag.thermal_stats(rows)
        self.assertEqual(s["core_temp_max_C"], 84)
        self.assertEqual(s["tc0h_max_C"], 60.5)
        self.assertEqual(s["fan_max_rpm"], 1700)
        self.assertEqual(s["throttle_delta"], 2)
        self.assertAlmostEqual(s["mem_avail_min_MB"], 1.0)
        self.assertAlmostEqual(s["pico_rss_MB"], 4.0)
        self.assertAlmostEqual(s["swap_max_MB"], 0.5)

    def test_throttle_empty_is_none(self):
        rows = [{"epoch": "1", "coretemp:Core_0_C": "50", "throttle_count": ""}, {"epoch": "2", "coretemp:Core_0_C": "51", "throttle_count": ""}]
        self.assertIsNone(ag.thermal_stats(rows)["throttle_delta"])


class CollectSyntheticRun(unittest.TestCase):
    def test_collect_energy_formula(self):
        with tempfile.TemporaryDirectory() as run:
            m = os.path.join(run, "modelo-x")
            os.makedirs(m)
            write(os.path.join(m, "meta.txt"), "nome: modelo-x\nquant: Q4_0\nparams_B: 0.5\nhash_estavel: sim\n")
            write(os.path.join(m, "status.txt"), "status=ok\n")
            write(os.path.join(m, "marcadores.csv"), "bench_t2_inicio,100\nbench_t2_fim,200\n")
            with open(os.path.join(m, "log.csv"), "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["epoch", "coretemp:Core_0_C", "throttle_count"])
                for t in range(95, 206, 5):
                    w.writerow([t, 60 + (t - 95) / 5, 0])
            with open(os.path.join(m, "bench_t2.csv"), "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(BENCH_HDR)
                w.writerow(["abc", "x", 516238848, 2, 64, 0, 1.6, 0.01])
                w.writerow(["abc", "x", 516238848, 2, 0, 32, 1.25, 0.01])
            rows, evals = ag.collect(run, 31.0, 1.0)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["threads"], r["pp_tps"], r["tg_tps"]), (2, 1.6, 1.25))
        self.assertAlmostEqual(r["J_por_token"], 31.0 / 1.25)
        self.assertAlmostEqual(r["tokens_por_J"], 1.25 / 31.0)
        self.assertAlmostEqual(r["R$_por_milhao_tokens"], (31.0 / 1.25) * 1e6 / 3.6e6 * 1.0)
        self.assertGreaterEqual(r["core_temp_max_C"], 60)
        self.assertEqual(evals, {})


if __name__ == "__main__":
    unittest.main()
