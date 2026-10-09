# YouTube Trending Videos — Python Data Cleaning Project

**Language:** Python 3.10+  
**Libraries:** pandas, NumPy, Matplotlib, Seaborn (all free and open source)  
**Data:** 10 historical country YouTube Trending CSV datasets plus category JSON files.

## What this project does

1. **Missing values:** records missing descriptions in `description_missing`; preserves missing text rather than inventing text; reports malformed metrics.
2. **Corrupted IDs:** repairs spreadsheet-created IDs such as `#NAME?` using the video ID embedded in each thumbnail URL.
3. **Duplicates:** removes repeated `country + video_id + trending_date` records **after** repairing IDs. It keeps videos seen on different trending days.
4. **Data types:** converts dates, metrics, boolean flags, and category IDs; translates category IDs with the supplied JSON mappings.
5. **Outliers:** flags high values above the country-specific 99.5th percentile for views, likes, dislikes, or comments; **does not delete** viral videos.
6. **Visualizations:** generates 9 labeled, high-resolution PNG charts.
7. **Insights:** generates `Short_Insights_Report.md`, `country_summary.csv`, `quality_audit.json`, and `insights.json`.

## How to run on Windows

Install Python 3.10+ from python.org (check **Add Python to PATH** at installation). In a Windows terminal:

```powershell
cd C:\path\to\YouTube_Trending_Python_Project
py -m pip install -r requirements.txt
```

Put all **20 original files** into a folder named `data` next to `main.py`, e.g.:

```text
YouTube_Trending_Python_Project/
|-- main.py
|-- requirements.txt
|-- README.md
|-- YouTube_Trending_Analysis.ipynb
|-- data/
|   |-- USvideos.csv
|   |-- US_category_id.json
|   |-- INvideos.csv
|   |-- IN_category_id.json
|   |-- ... files for CA, DE, FR, GB, JP, KR, MX, RU
|-- results/                  <-- created automatically
    |-- cleaned/             <-- ten cleaned CSV files
    |-- charts/              <-- nine PNG charts
    |-- Short_Insights_Report.md
    |-- country_summary.csv
    |-- quality_audit.json
    |-- insights.json
```

Run:

```powershell
py main.py --input data --output results
```

If disk space is limited, skip writing the large cleaned CSVs (cleaning and analysis are still performed):

```powershell
py main.py --input data --output results --skip-cleaned-csv
```

You can also run the notebook after generating results:

```powershell
py -m pip install jupyter
py -m notebook
```

## Charts created

1. `01_trending_observations_by_country.png` — number of records per country
2. `02_most_common_video_categories.png` — top video categories
3. `03_median_views_by_country.png` — median view count
4. `04_median_engagement_by_country.png` — likes + comments / views
5. `05_trending_activity_over_time.png` — activity by month
6. `06_how_quickly_videos_began_trending.png` — time from publication to observed trending date
7. `07_comments_disabled_by_country.png` — share with comments disabled
8. `08_views_and_likes_move_together.png` — log-scale association
9. `09_extreme_metric_flag_rate.png` — share flagged as extreme

## Simple viva / project explanation

**Q: Why pandas?** For reading, cleaning, grouping, and analyzing tabular CSV data.  
**Q: Why NumPy?** For numerical operations and chart histogram bins.  
**Q: Why Matplotlib and Seaborn?** To produce the 9 charts.  
**Q: Why not remove all large outliers?** A YouTube video can genuinely go viral; large engagement isn't necessarily an error.  
**Q: What is a duplicate?** The same video's observation on the **same day in the same country**, rather than every repeated video across multiple days.  
**Q: How is engagement calculated?** `(likes + comment_count) / views * 100`, only if views > 0.  
**Q: Are these current trends?** No. This source is a historical dataset from 2017–2018.

## Limits

Country observations are not necessarily comparable in coverage. Data is video-day weighted, not unique-video weighted. Published-to-observed-trending duration doesn't necessarily indicate a video's first trending day.

## Test the Python code

```powershell
py -m unittest discover -s tests -v
```
