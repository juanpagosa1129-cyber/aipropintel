import unittest

from backend.propintel.scoring import score_process


class ScoringTest(unittest.TestCase):
    def test_high_risk_for_auction_ready_mortgage_case(self):
        result = score_process({
            "tipo_proceso": "Ejecutivo hipotecario",
            "estado": "Remate fijado",
            "edad_meses": 60,
            "demandados": 2,
            "acreedores": 1,
        })
        self.assertGreaterEqual(result["score"], 70)
        self.assertEqual(result["risk"], "alto")

    def test_archived_case_is_low_risk(self):
        result = score_process({
            "tipo_proceso": "Pertenencia",
            "estado": "Archivo",
            "edad_meses": 12,
            "demandados": 1,
            "acreedores": 1,
        })
        self.assertEqual(result["risk"], "bajo")


if __name__ == "__main__":
    unittest.main()
