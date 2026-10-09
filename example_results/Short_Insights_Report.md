# YouTube Trending Videos — Data Cleaning & Insights

**Coverage:** 2017-11-14 to 2018-06-14 · 10 countries · historical YouTube trending snapshots.

## Cleaning results

- Source observations: **375,942**.
- Observations after same-country/video/day deduplication: **362,712**.
- Duplicate observations removed: **13,230** (3.52%).
- Invalid video IDs repaired using thumbnail URLs: **2,134**.
- Originally missing descriptions: **19,494** (kept blank and flagged).
- Category labels recovered by cross-country JSON fallback: **2,709** source observations.
- Observations with >=1 extreme metric flag: **3,923** (1.08%). Flagged, not deleted.

## Key insights

1. The most common category is **Entertainment** with **104,363** video-day observations.
2. **United Kingdom (GB)** has the highest median views per observation: **979,917**.
3. **89.1%** of captured observations occurred within seven days of upload.
4. **Russia (RU)** has the highest median engagement by the (likes+comments)/views formula: **4.61%**.
5. **Japan (JP)** has the highest comments-disabled share: **6.73%**.
6. Repeated video-day snapshots and uneven sample coverage mean cross-country chart totals are **not estimates of national viewership**.

## Visualizations

1. Trending observations by country: `01_trending_observations_by_country.png`
2. Most common video categories: `02_most_common_video_categories.png`
3. Median views by country: `03_median_views_by_country.png`
4. Median engagement by country: `04_median_engagement_by_country.png`
5. Trending activity over time: `05_trending_activity_over_time.png`
6. How quickly videos began trending: `06_how_quickly_videos_began_trending.png`
7. Comments disabled by country: `07_comments_disabled_by_country.png`
8. Views and likes move together: `08_views_and_likes_move_together.png`
9. Extreme-metric flag rate: `09_extreme_metric_flag_rate.png`

## Cleaning methodology

- **Missing values:** Preserve empty descriptions as blanks with `description_missing`. Avoid fabricated values.
- **Duplicates:** Repair video IDs first. Deduplicate within each country by video ID + trending date, preserving observations from different days. Same-day conflicting observations keep the maximum views, then likes/comments/dislikes.
- **Data types:** ISO date and UTC time formatting; integer counters; standardized boolean strings; derived numeric columns.
- **Categories:** Match country JSON then fallback to globally provided category mapping.
- **Outliers:** 99.5th-percentile, country-specific, high-end cutoff for each of views/likes/dislikes/comments; append flags and do not delete.
- **Encoding:** Decode invalid UTF-8 bytes with replacement; flag affected rows for manual inspection.

**Limitations:** This is a historical sample; results are video-day weighted. Comparisons reflect upload-to-trending age per captured day, not necessarily a video's first trending date.
