import unittest
import pandas as pd

from utils import build_recommendations, infer_recurring_activities, classify_programme_type


class TestDashboardHelpers(unittest.TestCase):
    def test_infer_recurring_activities_from_sheets(self):
        df = pd.DataFrame({"activity": ["Yoga", "Yoga", "Cooking"], "__sheet__": ["S1", "S2", "S1"]})
        self.assertEqual(infer_recurring_activities(df), ["Yoga"])

    def test_classify_programme_type_uses_multiple_dates(self):
        df = pd.DataFrame({"activity": ["Yoga", "Yoga", "Cooking"], "date": ["2024-01-01", "2024-01-08", "2024-01-01"]})
        result = classify_programme_type(df).tolist()
        self.assertEqual(result, ["Recurring", "Recurring", "One-Time"])

    def test_build_recommendations_returns_reason(self):
        stats = pd.DataFrame({
            "activity": ["Yoga", "Art"],
            "programme_type": ["Recurring", "One-Time"],
            "total_attendances": [100, 10],
            "unique_seniors": [40, 5],
            "retention_score": [2.5, 1.0],
            "male_pct": [0.3, 0.1],
        })
        recs = build_recommendations(stats)
        self.assertIn("reason", recs.columns)
        self.assertEqual(len(recs), 2)


if __name__ == "__main__":
    unittest.main()
