"""Small repeatable tests for the real cleaning rules.
Run: python -m unittest discover -s tests -v
"""
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from main import clean_country


class CleaningTests(unittest.TestCase):
    def test_repair_ids_before_removing_same_day_duplicates(self):
        valid_id = "-b0ww7L2MGU"
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "INvideos.csv"
            source = []
            for date, views, video_id in [
                ("17.14.11", 100, "#NAME?"),
                ("17.14.11", 300, "#NAME?"),
                ("17.15.11", 350, "#NAME?"),
            ]:
                source.append({
                    "video_id": video_id, "trending_date": date,
                    "title": "Test", "channel_title": "Channel",
                    "category_id": "24", "publish_time": "2017-11-13T16:00:00.000Z",
                    "tags": "", "views": views, "likes": 20,
                    "dislikes": 0, "comment_count": 10,
                    "thumbnail_link": f"https://i.ytimg.com/vi/{valid_id}/default.jpg",
                    "comments_disabled": False, "ratings_disabled": False,
                    "video_error_or_removed": False, "description": None,
                })
            pd.DataFrame(source).to_csv(path, index=False)
            cleaned, quality = clean_country("IN", Path(work), {}, {"24": "Entertainment"})
            self.assertEqual(quality["rows_before"], 3)
            self.assertEqual(quality["rows_after"], 2)
            self.assertEqual(quality["duplicates_removed"], 1)
            self.assertTrue((cleaned["video_id"] == valid_id).all())
            self.assertEqual(cleaned["views"].tolist(), [300, 350])
            self.assertTrue(cleaned["description_missing"].all())
            self.assertTrue((cleaned["category_name"] == "Entertainment").all())
            self.assertEqual(set(cleaned["trending_date"]), {"2017-11-14", "2017-11-15"})

    def test_missing_numeric_values_not_invented(self):
        with tempfile.TemporaryDirectory() as work:
            source = [{
                "video_id": "AbCd1234567", "trending_date": "17.14.11", "title": "Test",
                "channel_title": "Channel", "category_id": "10",
                "publish_time": "2017-11-13T16:00:00.000Z", "tags": "x",
                "views": 0, "likes": "", "dislikes": 0, "comment_count": 0,
                "thumbnail_link": "https://i.ytimg.com/vi/AbCd1234567/default.jpg",
                "comments_disabled": False, "ratings_disabled": False,
                "video_error_or_removed": False, "description": "",
            }]
            pd.DataFrame(source).to_csv(Path(work) / "USvideos.csv", index=False)
            cleaned, quality = clean_country("US", Path(work), {"10": "Music"}, {})
            self.assertTrue(pd.isna(cleaned.iloc[0]["likes"]))
            self.assertTrue(pd.isna(cleaned.iloc[0]["engagement_rate_pct"]))
            self.assertEqual(quality["invalid_numeric_count_before"]["likes"], 1)


if __name__ == "__main__":
    unittest.main()
