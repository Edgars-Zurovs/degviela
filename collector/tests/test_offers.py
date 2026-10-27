import unittest
from collector.collector import build_offers, update_source_state
from collector.parsers import parse_circlek, parse_virsi
from collector.tests.test_parsers import CK, VI


def st(i, brand, addr, city, lpg=False, cng=False):
    return {"id": i, "brand": brand, "name": brand, "lat": 56.9, "lon": 24.1,
            "address": addr, "city": city, "lpg": lpg, "cng": cng}


def stations():
    return [
        st("n1", "circlek", "Brīvības gatve 265", "Rīga"),
        st("n2", "circlek", "Tērbatas iela 1", "Rīga", lpg=True),
        st("n3", "circlek", "Rūpniecības iela 4", "Liepāja"),
        st("n4", "virsi", "Brīvības gatve 297", "Rīga", lpg=True, cng=True),
        st("n5", "virsi", "Uzvaras iela 2", "Jelgava"),
    ]


class Offers(unittest.TestCase):
    def setUp(self):
        self.state = {}
        update_source_state(self.state, "circlek", parse_circlek(CK), None, "2026-10-27T08:00:00+00:00")
        update_source_state(self.state, "virsi", parse_virsi(VI), None, "2026-10-27T08:00:00+00:00")

    def test_kinds(self):
        s, um = build_offers(stations(), self.state)
        by = {x["id"]: x["offers"] for x in s}
        self.assertEqual(by["n1"]["95"]["kind"], "here")
        self.assertEqual(by["n2"]["95"]["kind"], "min")      # Рига, но не в списке
        self.assertEqual(by["n3"]["95"]["kind"], "ref")       # вне региона данных - только ориентир
        self.assertEqual(by["n2"]["LPG"]["kind"], "uniform")
        self.assertNotIn("LPG", by["n1"])                     # нет тега LPG
        self.assertEqual(by["n4"]["D"]["kind"], "here")
        self.assertEqual(by["n4"]["LPG"]["kind"], "uniform")
        self.assertNotIn("CNG", by["n5"])
        self.assertIn("Krasta iela 93", " ".join(sum(um.values(), [])))

    def test_change_detection(self):
        build_offers(stations(), self.state)
        self.state["sources"]["circlek"]["fuels"]["95"]["price"] = 1.9
        self.state["sources"]["circlek"]["fetched_at"] = "2026-10-27T11:00:00+00:00"
        s, _ = build_offers(stations(), self.state)
        o = {x["id"]: x["offers"] for x in s}["n1"]["95"]
        self.assertEqual(o["changed_at"], "2026-10-27T11:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
