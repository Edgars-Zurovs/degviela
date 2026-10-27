import unittest
from collector.parsers import parse_circlek, parse_virsi, parse_addresses
from collector.geo import addresses_match, haversine_km, nearest_town, assign_city

CK = ("Degvielas cenas Zemākās cenas Rīgā Cenas spēkā no 26.10.2026 "
      "95miles 1.954 EUR Brīvības gatve 265, Brīvības gatve 203 "
      "98miles+ 2.054 EUR Krasta iela 93 "
      "Dmiles 2.134 EUR Brīvības gatve 265 "
      "Dmiles+ 2.264 EUR Brīvības gatve 265 "
      "miles+ XTL 2.490 EUR Krasta iela 93 "
      "Autogāze 1.065 EUR vienāda visos DUS "
      "Degvielas cenu ietekmējošie faktori 95miles 9.999 EUR")

VI = ("Degvielas cenas atjaunotas 26.10.2026 "
      "DD 2.087 Brīvības gatve 297, Rīga, LV-1006 "
      "AD 1.700 Kāda iela 5 "
      "95E 1.889 Brīvības gatve 297, Rīga, LV-1006 "
      "98E 1.959 Brīvības gatve 297, Rīga "
      "CBG 2.195 Krasta iela 93 "
      "LPG 1.065 Visā Viršu tīklā "
      "AdBLUE 1.2 Elektrouzlādes cenas 0.5")


class Parsers(unittest.TestCase):
    def test_circlek(self):
        r = parse_circlek(CK)
        self.assertEqual(r.source_date, "2026-10-26")
        self.assertEqual(r.fuels["95"]["price"], 1.954)
        self.assertEqual(r.fuels["95"]["addresses"], ["Brīvības gatve 265", "Brīvības gatve 203"])
        self.assertEqual(r.fuels["D"]["price"], 2.134)
        self.assertEqual(r.fuels["DP"]["price"], 2.264)
        self.assertEqual(r.fuels["XTL"]["price"], 2.49)
        self.assertEqual(r.fuels["98"]["price"], 2.054)
        self.assertTrue(r.fuels["LPG"]["uniform"])
        self.assertEqual(len(r.fuels), 6)

    def test_virsi(self):
        r = parse_virsi(VI)
        self.assertEqual(r.source_date, "2026-10-26")
        self.assertEqual(r.fuels["D"]["price"], 2.087)
        self.assertEqual(r.fuels["95"]["addresses"], ["Brīvības gatve 297"])
        self.assertTrue(r.fuels["LPG"]["uniform"])
        self.assertEqual(r.fuels["CNG"]["price"], 2.195)
        self.assertNotIn("AD", r.fuels)
        self.assertEqual(set(r.fuels), {"D", "95", "98", "CNG", "LPG"})

    def test_empty(self):
        self.assertFalse(parse_circlek("nothing here").ok)
        self.assertFalse(parse_virsi("nothing here").ok)

    def test_price_range(self):
        r = parse_virsi("atjaunotas 1.1.2026 95E 9.999 Kāda iela 5")
        self.assertFalse(r.ok)

    def test_addresses(self):
        self.assertEqual(parse_addresses("Krasta iela 93, Rīga, LV-1001"), ["Krasta iela 93"])


class Geo(unittest.TestCase):
    def test_match(self):
        self.assertTrue(addresses_match("Brīvības gatve 265", "Brivibas gatve 265"))
        self.assertTrue(addresses_match("Umaņa iela 3", "Umanas iela 3"))
        self.assertFalse(addresses_match("Brīvības gatve 265", "Brīvības gatve 203"))
        self.assertFalse(addresses_match("Brīvības iela 265", "Brīvības gatve 265"))

    def test_distance(self):
        d = haversine_km(56.9496, 24.1052, 56.5047, 21.0108)  # Рига-Лиепая ~ 190 км
        self.assertTrue(185 < d < 200, d)

    def test_city(self):
        self.assertEqual(nearest_town(56.929389, 24.153103), "Rīga")
        self.assertEqual(assign_city({"addr:city": "Riga"}, 0, 0), "Rīga")
        self.assertEqual(nearest_town(58.5, 22.0), "Cita vieta")


if __name__ == "__main__":
    unittest.main()
