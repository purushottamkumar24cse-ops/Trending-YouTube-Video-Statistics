"""YouTube Trending Videos: data cleaning, EDA, and reporting.

Examples:
    python main.py --input /path/to/raw/files --output results
    python main.py --input . --output results --skip-cleaned-csv

Inputs: {CA,DE,FR,GB,IN,JP,KR,MX,RU,US}videos.csv and
        {COUNTRY}_category_id.json (the uploaded YouTube Trending dataset).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # allows running without a display / on servers
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

COUNTRIES = {
    "CA": "Canada", "DE": "Germany", "FR": "France",
    "GB": "United Kingdom", "IN": "India", "JP": "Japan",
    "KR": "South Korea", "MX": "Mexico", "RU": "Russia",
    "US": "United States",
}
METRICS = ("views", "likes", "dislikes", "comment_count")
BOOLEAN_COLUMNS = ("comments_disabled", "ratings_disabled", "video_error_or_removed")
TEXT_COLUMNS = ("video_id", "title", "channel_title", "tags", "thumbnail_link", "description")
VIDEO_ID_REGEX = r"[A-Za-z0-9_-]{11}"
THUMBNAIL_REGEX = r"/vi/([A-Za-z0-9_-]{11})(?:/|$)"


def category_maps(folder: Path) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """Use country-specific labels first; other supplied JSONs as fallback."""
    local: dict[str, dict[str, str]] = {}
    common: dict[str, str] = {}
    for country in COUNTRIES:
        path = folder / f"{country}_category_id.json"
        with path.open("r", encoding="utf-8") as file:
            items = json.load(file)["items"]
        local[country] = {
            str(item["id"]): item["snippet"]["title"]
            for item in items if item.get("snippet", {}).get("title")
        }
        for category_id, label in local[country].items():
            common.setdefault(category_id, label)
    return local, common


def clean_country(
    country: str, raw_folder: Path, local_categories: dict[str, str],
    common_categories: dict[str, str]
) -> tuple[pd.DataFrame, dict]:
    """Clean one country without collapsing distinct trending days."""
    path = raw_folder / f"{country}videos.csv"
    df = pd.read_csv(path, encoding="utf-8", encoding_errors="replace",
                     dtype={"video_id": "string", "category_id": "string"},
                     low_memory=False)
    original_count = len(df)

    # 1. Capture missing text before data transformations.
    df["description_missing"] = (
        df["description"].isna() |
        df["description"].astype("string").str.strip().eq("").fillna(False)
    ).astype(bool)
    missing_descriptions = int(df["description_missing"].sum())
    for name in TEXT_COLUMNS:
        df[name] = df[name].astype("string")

    df["encoding_replacement"] = False
    for name in TEXT_COLUMNS:
        df["encoding_replacement"] |= df[name].str.contains("\ufffd", regex=False, na=False)
    encoding_affected = int(df["encoding_replacement"].sum())

    # 2. Recover YouTube IDs corrupted by spreadsheet software (#NAME?, etc).
    valid = df["video_id"].str.fullmatch(VIDEO_ID_REGEX, na=False)
    candidates = df["thumbnail_link"].str.extract(THUMBNAIL_REGEX, expand=False)
    can_recover = (~valid) & candidates.notna()
    df.loc[can_recover, "video_id"] = candidates.loc[can_recover]
    df["video_id_recovered"] = can_recover
    still_invalid = ~df["video_id"].str.fullmatch(VIDEO_ID_REGEX, na=False)
    # Keep unrecovered rows without merging unrelated records on identical bad IDs.
    df["video_id_unrecovered"] = still_invalid
    df.loc[still_invalid, "video_id"] = [
        f"UNRECOVERED_{country}_{i}" for i in df.index[still_invalid]
    ]

    # 3. Parse the unusual YY.DD.MM format, normal UTC publication timestamps.
    df["trending_date"] = pd.to_datetime(
        df["trending_date"], format="%y.%d.%m", errors="coerce"
    )
    df["publish_time"] = pd.to_datetime(
        df["publish_time"], utc=True, errors="coerce"
    )
    # 4. Numeric, boolean, category data types.
    invalid_metrics = {}
    for name in METRICS:
        df[name] = pd.to_numeric(df[name], errors="coerce")
        invalid_metrics[name] = int(df[name].isna().sum())
        df[name] = df[name].astype("Int64")
    for name in BOOLEAN_COLUMNS:
        if df[name].dtype == bool:
            df[name] = df[name].astype("boolean")
        else:
            df[name] = df[name].astype("string").str.strip().str.lower().map(
                {"true": True, "false": False, "1": True, "0": False}
            ).astype("boolean")

    df["category_id"] = df["category_id"].astype("string").str.strip()
    df["category_name"] = df["category_id"].map(local_categories).astype("string")
    local_missing = df["category_name"].isna()
    fallback_name = df["category_id"].map(common_categories)
    fallback_used = local_missing & fallback_name.notna()
    df.loc[fallback_used, "category_name"] = fallback_name.loc[fallback_used].astype("string")
    df["category_source"] = np.select(
        [~local_missing, fallback_used], ["country_json", "other_supplied_json"],
        default="unmapped",
    )
    df["category_name"] = df["category_name"].fillna("Unknown")
    df["country"] = country
    df["country_name"] = COUNTRIES[country]
    fallback_count = int(fallback_used.sum())

    # 5. Keep the most complete, largest-view snapshot on identical
    # (country, video, trending day) keys; DO NOT remove other days.
    df = df.sort_values(list(METRICS), ascending=False, na_position="last", kind="stable")
    df = df.drop_duplicates(["video_id", "trending_date"], keep="first").copy()
    df = df.sort_values(["trending_date", "video_id"], kind="stable")
    duplicates_removed = original_count - len(df)

    # 6. Derived features; zero views produce missing engagement, not infinity.
    upload_day = df["publish_time"].dt.tz_convert(None).dt.normalize()
    df["days_to_trend"] = (df["trending_date"] - upload_day).dt.days.astype("Int64")
    v = df["views"].astype("float64")
    df["engagement_rate_pct"] = (
        100 * (df["likes"].astype("float64") +
               df["comment_count"].astype("float64")) / v.where(v > 0)
    ).round(4)

    # 7. Flag (do not delete) the top 0.5% of observations in each country.
    thresholds = {}
    for name in METRICS:
        threshold = float(df[name].dropna().quantile(0.995))
        thresholds[name] = threshold
        df[f"{name}_outlier"] = df[name].gt(threshold).fillna(False).astype(bool)
    flag_names = [f"{name}_outlier" for name in METRICS]
    df["any_metric_outlier"] = df[flag_names].any(axis=1)

    # Write dates in portable ISO format, readable in Excel/Python.
    df["trending_date"] = df["trending_date"].dt.strftime("%Y-%m-%d")
    df["publish_time"] = df["publish_time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    audit = {
        "country": country,
        "country_name": COUNTRIES[country],
        "rows_before": original_count,
        "rows_after": int(len(df)),
        "duplicates_removed": int(duplicates_removed),
        "missing_descriptions_original": missing_descriptions,
        "recovered_ids_retained": int(df["video_id_recovered"].sum()),
        "unrecovered_ids_retained": int(df["video_id_unrecovered"].sum()),
        "category_global_fallback_original": fallback_count,
        "rows_with_encoding_replacement_original": encoding_affected,
        "outliers_flagged": int(df["any_metric_outlier"].sum()),
        "outlier_thresholds_99_5pct": thresholds,
        "invalid_numeric_count_before": invalid_metrics,
        "median_views": float(df["views"].median()),
        "median_engagement_pct": float(df["engagement_rate_pct"].median()) if df["engagement_rate_pct"].notna().any() else None,
        "comments_disabled_pct": float(df["comments_disabled"].mean() * 100),
    }
    return df, audit


def slim_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only columns necessary for the charts so RAM use stays modest."""
    use = ["country", "country_name", "category_name", "trending_date", "views",
           "likes", "dislikes", "comment_count", "engagement_rate_pct",
           "days_to_trend", "comments_disabled", "any_metric_outlier"]
    return df[use].copy()


def save_figure(output: Path, stem: str) -> None:
    plt.tight_layout(pad=1.5)
    plt.savefig(output / (stem + ".png"), dpi=170, bbox_inches="tight", facecolor="white")
    plt.close()


def make_charts(df: pd.DataFrame, chart_dir: Path) -> list[tuple[str, str]]:
    chart_dir.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", context="notebook")
    charts: list[tuple[str, str]] = []

    def record(name: str, caption: str) -> None:
        save_figure(chart_dir, name)
        charts.append((name + ".png", caption))

    # CHART 1: country observations
    counts = df["country"].value_counts().sort_values()
    plt.figure(figsize=(10, 5.7))
    sns.barplot(x=counts.values, y=counts.index, orient="h", color="#286f9d")
    plt.xlabel("Video-country-day observations")
    plt.ylabel("Country")
    plt.title("1. Trending observations by country")
    record("01_trending_observations_by_country", "Country counts reflect available snapshots, not national viewership.")

    # CHART 2: top 10 categories
    counts = df["category_name"].value_counts().head(10).sort_values()
    plt.figure(figsize=(11, 6))
    sns.barplot(x=counts.values, y=counts.index, orient="h", color="#286f9d")
    plt.xlabel("Trending observations")
    plt.ylabel("Category")
    plt.title("2. Most frequent video categories")
    record("02_most_common_video_categories", "Entertainment is the leading category by number of observations.")

    # CHART 3: medians protect against a few huge viral hits
    med = df.groupby("country")["views"].median().sort_values()
    plt.figure(figsize=(10, 5.7))
    sns.barplot(x=med.to_numpy(dtype=float) / 1e6, y=med.index, orient="h", color="#286f9d")
    plt.xlabel("Median views (millions)")
    plt.ylabel("Country")
    plt.title("3. Median views per trending observation")
    record("03_median_views_by_country", "Median views are more robust than the mean to viral outliers.")

    # CHART 4: median likes + comments / views
    med = df.groupby("country")["engagement_rate_pct"].median().sort_values()
    plt.figure(figsize=(10, 5.7))
    sns.barplot(x=med.to_numpy(dtype=float), y=med.index, orient="h", color="#286f9d")
    plt.xlabel("Median (likes + comments) / views (%)")
    plt.ylabel("Country")
    plt.title("4. Median engagement by country")
    record("04_median_engagement_by_country", "Engagement reflects observed likes and comments; disabled metrics affect interpretation.")

    # CHART 5: aggregate monthly snapshots
    dates = pd.to_datetime(df["trending_date"], errors="coerce")
    months = dates.dt.to_period("M").value_counts().sort_index()
    plt.figure(figsize=(11, 5))
    plt.plot(months.index.astype(str).tolist(), months.to_numpy(), marker="o", linewidth=2)
    plt.xlabel("Trending month")
    plt.ylabel("Observations")
    plt.title("5. Monthly trending activity in the supplied sample")
    plt.xticks(rotation=35)
    record("05_trending_activity_over_time", "Month totals change with the number of observed days and countries.")

    # CHART 6: days from upload to observed trending snapshot (0..30)
    age = pd.to_numeric(df["days_to_trend"], errors="coerce")
    sample = age[(age >= 0) & (age <= 30)].dropna()
    plt.figure(figsize=(10, 5.7))
    plt.hist(sample, bins=np.arange(-0.5, 31.5, 1), edgecolor="white")
    plt.xlabel("Days from publication to observed trending date")
    plt.ylabel("Observations")
    plt.title("6. How quickly videos were observed trending (0–30 days)")
    record("06_how_quickly_videos_began_trending", "This is NOT the exact first day each video originally trended.")

    # CHART 7: comments disabled proportion
    proportion = df.groupby("country")["comments_disabled"].mean().mul(100).sort_values()
    plt.figure(figsize=(10, 5.7))
    sns.barplot(x=proportion.to_numpy(dtype=float), y=proportion.index, orient="h", color="#286f9d")
    plt.xlabel("Observations with comments disabled (%)")
    plt.ylabel("Country")
    plt.title("7. Comments disabled by country")
    record("07_comments_disabled_by_country", "Comments are not equally available on all videos.")

    # CHART 8: sampled scatter, log scales, for clarity/performance
    points = df.loc[(df["views"] > 0) & (df["likes"] > 0), ["views", "likes"]]
    points = points.sample(n=min(len(points), 16000), random_state=42)
    plt.figure(figsize=(9, 6))
    plt.scatter(points["views"].astype(float), points["likes"].astype(float),
                alpha=0.16, s=9, linewidths=0)
    plt.xscale("log"); plt.yscale("log")
    plt.xlabel("Views (log scale)")
    plt.ylabel("Likes (log scale)")
    plt.title("8. Views and likes tend to increase together")
    record("08_views_and_likes_move_together", "Dots are a reproducible random sample; association does not prove causality.")

    # CHART 9: extreme-metric rate
    percentage = df.groupby("country")["any_metric_outlier"].mean().mul(100).sort_values()
    plt.figure(figsize=(10, 5.7))
    sns.barplot(x=percentage.to_numpy(dtype=float), y=percentage.index, orient="h", color="#286f9d")
    plt.xlabel("At least one metric above its country's 99.5th percentile (%)")
    plt.ylabel("Country")
    plt.title("9. Share of observations flagged as extreme")
    record("09_extreme_metric_flag_rate", "Extreme engagement was flagged for review, not automatically discarded.")
    return charts


def format_number(number: float | int) -> str:
    return f"{number:,.0f}"


def make_report(df: pd.DataFrame, audits: dict, charts: list, output: Path) -> None:
    totals = {
        "source_records": sum(a["rows_before"] for a in audits.values()),
        "cleaned_records": sum(a["rows_after"] for a in audits.values()),
        "duplicates_removed": sum(a["duplicates_removed"] for a in audits.values()),
        "repaired_video_ids_retained": sum(a["recovered_ids_retained"] for a in audits.values()),
        "missing_descriptions_original": sum(a["missing_descriptions_original"] for a in audits.values()),
        "outliers_flagged": sum(a["outliers_flagged"] for a in audits.values()),
    }
    categories = df["category_name"].value_counts()
    top_country_views = df.groupby("country")["views"].median().idxmax()
    top_country_engage = df.groupby("country")["engagement_rate_pct"].median().idxmax()
    top_disabled = df.groupby("country")["comments_disabled"].mean().idxmax()
    lag = pd.to_numeric(df["days_to_trend"], errors="coerce")
    pct_week = float(lag.between(0, 7).mean() * 100)
    date_start, date_end = df["trending_date"].min(), df["trending_date"].max()

    summary = df.groupby(["country", "country_name"]).agg(
        observations=("views", "size"), median_views=("views", "median"),
        median_engagement_pct=("engagement_rate_pct", "median"),
        comments_disabled_pct=("comments_disabled", "mean"),
        extreme_metric_pct=("any_metric_outlier", "mean"),
    ).reset_index()
    summary["comments_disabled_pct"] *= 100
    summary["extreme_metric_pct"] *= 100
    summary.to_csv(output / "country_summary.csv", index=False, float_format="%.4f")

    insights = [
        f"**{categories.index[0]}** was the most common category: {format_number(categories.iloc[0])} observations.",
        f"**{COUNTRIES[top_country_views]} ({top_country_views})** had the highest median views "
        f"({format_number(df.loc[df.country == top_country_views, 'views'].median())}).",
        f"**{pct_week:.1f}%** of records were observed within 0–7 days of publication.",
        f"**{COUNTRIES[top_country_engage]} ({top_country_engage})** had the highest median engagement: "
        f"{df.loc[df.country == top_country_engage, 'engagement_rate_pct'].median():.2f}%.",
        f"**{COUNTRIES[top_disabled]} ({top_disabled})** had the largest comments-disabled percentage: "
        f"{df.loc[df.country == top_disabled, 'comments_disabled'].mean() * 100:.2f}%.",
    ]

    lines = [
        "# YouTube Trending Videos — Data Cleaning & Insights",
        "",
        f"**Scope:** {date_start} to {date_end}; 10 countries; historical trending snapshots.",
        "",
        "## Cleaning results",
        "",
        f"- Original video-day records: **{format_number(totals['source_records'])}**.",
        f"- Cleaned video-day records: **{format_number(totals['cleaned_records'])}**.",
        f"- Duplicate country/video/day records removed: **{format_number(totals['duplicates_removed'])}**.",
        f"- Corrupted YouTube IDs recovered in retained records: **{format_number(totals['repaired_video_ids_retained'])}**.",
        f"- Original missing descriptions (left blank + flagged): **{format_number(totals['missing_descriptions_original'])}**.",
        f"- Rows flagged for extreme values (retained): **{format_number(totals['outliers_flagged'])}**.",
        "",
        "## Short insights", "",
        *[f"{i}. {value}" for i, value in enumerate(insights, 1)], "",
        "## Visualizations", "",
        *[f"{i}. `{filename}` — {caption}" for i, (filename, caption) in enumerate(charts, 1)],
        "", "## Cleaning methods and limitations", "",
        "- Missing descriptions are preserved as blanks and flagged. Numeric missing values are not fabricated.",
        "- Malformed video IDs are repaired using the video thumbnail URL *before* deduplication.",
        "- Only repeated country/video/trending-date rows are removed, preserving legitimate multi-day appearances.",
        "- Trending date parsed as YY.DD.MM; publish time standardized to UTC; flags and counts get consistent types.",
        "- Video category IDs are matched to the relevant country JSON with fallback to other uploaded country JSONs.",
        "- Outliers are values above the 99.5th percentile per country for any of four engagement metrics.",
        "- Video-country-day observations are not unique video counts. Countries have uneven snapshot coverage.",
        "- These are historical 2017–2018 data, not today's YouTube trends.",
        "- The publication-to-observation lag is not necessarily time to a video's *first* trending appearance.",
    ]
    (output / "Short_Insights_Report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "quality_audit.json").write_text(
        json.dumps({"totals": totals, "by_country": audits}, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output / "insights.json").write_text(json.dumps({
        "insights": insights, "pct_within_7_days": pct_week,
        "top_category": str(categories.index[0]),
    }, indent=2), encoding="utf-8")
    print("\nSUMMARY")
    for key, value in totals.items():
        print(f"{key:31s} {format_number(value)}")
    print("Charts:", len(charts))
    print("\n".join(insights))


def run(raw_folder: Path, output: Path, save_cleaned: bool = True) -> None:
    output.mkdir(parents=True, exist_ok=True)
    if save_cleaned:
        (output / "cleaned").mkdir(exist_ok=True)
    local, common = category_maps(raw_folder)
    audits = {}
    thin_frames = []
    for country in COUNTRIES:
        df, audit = clean_country(country, raw_folder, local[country], common)
        audits[country] = audit
        if save_cleaned:
            df.to_csv(output / "cleaned" / f"{country}_cleaned.csv", index=False)
        thin_frames.append(slim_frame(df))
        print(f"{country}: {audit['rows_before']:,} raw -> {audit['rows_after']:,} cleaned; "
              f"{audit['duplicates_removed']:,} duplicates removed", flush=True)
        del df

    combined = pd.concat(thin_frames, ignore_index=True)
    charts = make_charts(combined, output / "charts")
    make_report(combined, audits, charts, output)
    print(f"\nGenerated output: {output.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("."),
                        help="Folder with 10 original CSVs and 10 category JSONs")
    parser.add_argument("--output", type=Path, default=Path("results"),
                        help="Folder for cleaned CSV, PNG charts, and the report")
    parser.add_argument("--skip-cleaned-csv", action="store_true",
                        help="Generate charts/reports without large cleaned CSV outputs")
    args = parser.parse_args()
    run(args.input, args.output, save_cleaned=not args.skip_cleaned_csv)


if __name__ == "__main__":
    main()
