"""
Refresh contact volume data for the Member Care v2 dashboard.

Pulls:
  - Contact actuals from VOLUME_30MIN_INTERVALS_V2 (monthly aggregates)
  - FCR from RESIDENTIAL_FCR (monthly)
  - Contact forecasts from MC_CONTACT_FORECASTS

Outputs:
  data/contacts.json

Usage:
    python scripts/refresh_contacts.py
"""
from __future__ import annotations
import json, os
from decimal import Decimal
from datetime import datetime
from pathlib import Path
import sys as _sys; _sys.path.insert(0, r"C:\Users\devin.lindsay\Documents\Claude\Projects\AI Implementation\Automation")  # noqa: E702
from config.snowflake_creds import load_snowflake_creds
import snowflake.connector

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

load_snowflake_creds()

EXCLUDED_LOBS = ("Freemotion", "UK OmniQueue", "Direct Response", "Other")
CHANNEL_ORDER = ["Phone", "Email", "Chat", "Message"]

FORECAST_TO_ACTUALS_LOB = {
    "Parts & Service":    ["Parts and Service", "Sales - Non-Warranty"],
    "iFIT Experience":    ["iFIT Experience"],
    "Service Coordinator":["Service"],
    "Billing & Returns":  ["Billing and Returns", "Product Tracking"],
    "Canada":             ["Canada"],
    "Mexico":             ["Mexico"],
    "Corporate":          ["Corporate"],
    "Product Replacement":["Product Resolution"],
}
ACTUALS_TO_FORECAST_LOB = {}
for _fc, _acts in FORECAST_TO_ACTUALS_LOB.items():
    for _a in _acts:
        ACTUALS_TO_FORECAST_LOB[_a] = _fc


def connect():
    return snowflake.connector.connect(
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "REPORTING_WAREHOUSE"),
        database="ANALYTICS",
    )


def to_float(v):
    if isinstance(v, Decimal):
        return float(v)
    return float(v) if v is not None else 0.0


def fiscal_from_date(d):
    m = d.month
    y = d.year
    if m >= 6:
        return y + 1, m - 5
    else:
        return y, m + 7


def main():
    print("\n=== Refresh contacts data ===")
    conn = connect()
    cur = conn.cursor()

    # 1. Contact actuals
    print("  contact actuals ... ", end="", flush=True)
    cur.execute("""
        SELECT
            DATE_TRUNC('month', DATE)::DATE AS MONTH,
            MEDIA_NAME,
            LOB_OR_QUEUE_GROUP AS LOB,
            SUM(HANDLED)          AS HANDLED,
            SUM(ABANDONS)         AS ABANDONS,
            SUM(QUEUED)           AS QUEUED,
            SUM(SPEED_OF_ANSWER)  AS TOTAL_SOA,
            SUM(HANDLE_TIME)      AS TOTAL_HT
        FROM ANALYTICS.ANALYTICS_MEM_CARE_MART.VOLUME_30MIN_INTERVALS_V2
        WHERE DIRECTION = 'Inbound'
          AND DATE >= '2023-06-01'
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3
    """)
    vol_rows = cur.fetchall()
    vol_cols = [c[0].lower() for c in cur.description]
    print(f"{len(vol_rows):,} rows")

    # 2. FCR
    print("  FCR ... ", end="", flush=True)
    cur.execute("""
        SELECT
            DATE_TRUNC('month', EDIT_DATE_NO_TIME)::DATE AS MONTH,
            AVG(CAST(FCR_BINARY AS FLOAT))                AS FCR_RATE,
            SUM(CASE WHEN FCR_BINARY = 1 THEN 1 ELSE 0 END) AS RESOLVED,
            COUNT(*)                                       AS TOTAL
        FROM ANALYTICS.ANALYTICS_MEM_CARE_MART.RESIDENTIAL_FCR
        WHERE EDIT_DATE_NO_TIME >= '2023-06-01'
        GROUP BY 1
        ORDER BY 1
    """)
    fcr_rows = cur.fetchall()
    print(f"{len(fcr_rows):,} rows")

    # 3. Contact forecasts
    print("  contact forecasts ... ", end="", flush=True)
    cur.execute("""
        SELECT MONTH, LOB, SUB_LOB, CHANNEL, VERSION, CONTACTS
        FROM ANALYTICS.ANALYTICS_GL_ANALYTICS_MART.MC_CONTACT_FORECASTS
        ORDER BY VERSION, MONTH, LOB, CHANNEL
    """)
    fc_rows = cur.fetchall()
    print(f"{len(fc_rows):,} rows")

    # 4. DOW × Hour heatmap — monthly granularity so dashboard can filter by month
    print("  heatmap (DOW×hour×month) ... ", end="", flush=True)
    cur.execute("""
        SELECT
            DATE_TRUNC('month', DATE)::DATE                            AS MONTH,
            DAYOFWEEK(DATE)                                            AS DOW,
            TRY_TO_NUMBER(SPLIT_PART(RANGE_30_MINUTES, ':', 1))        AS HOUR,
            MEDIA_NAME,
            SUM(HANDLED)          AS HANDLED,
            SUM(ABANDONS)         AS ABANDONS,
            SUM(QUEUED)           AS QUEUED,
            SUM(SPEED_OF_ANSWER)  AS TOTAL_SOA,
            SUM(HANDLE_TIME)      AS TOTAL_HT,
            COUNT(DISTINCT DATE)  AS DAYS
        FROM ANALYTICS.ANALYTICS_MEM_CARE_MART.VOLUME_30MIN_INTERVALS_V2
        WHERE DIRECTION = 'Inbound'
          AND DATE >= DATEADD('month', -12, CURRENT_DATE())
          AND LOB_OR_QUEUE_GROUP NOT IN ('Freemotion', 'UK OmniQueue')
        GROUP BY 1, 2, 3, 4
        ORDER BY 1, 2, 3, 4
    """)
    hm_rows = cur.fetchall()
    hm_cols = [c[0].lower() for c in cur.description]
    print(f"{len(hm_rows):,} rows")

    # 5. LOB × channel × month detail for drill-down
    print("  LOB detail ... ", end="", flush=True)
    cur.execute("""
        SELECT
            DATE_TRUNC('month', DATE)::DATE AS MONTH,
            MEDIA_NAME,
            LOB_OR_QUEUE_GROUP AS LOB,
            SUM(HANDLED)          AS HANDLED,
            SUM(ABANDONS)         AS ABANDONS,
            SUM(QUEUED)           AS QUEUED,
            SUM(SPEED_OF_ANSWER)  AS TOTAL_SOA,
            SUM(HANDLE_TIME)      AS TOTAL_HT
        FROM ANALYTICS.ANALYTICS_MEM_CARE_MART.VOLUME_30MIN_INTERVALS_V2
        WHERE DIRECTION = 'Inbound'
          AND DATE >= '2023-06-01'
          AND LOB_OR_QUEUE_GROUP NOT IN ('Freemotion', 'UK OmniQueue')
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3
    """)
    lob_rows = cur.fetchall()
    lob_cols = [c[0].lower() for c in cur.description]
    print(f"{len(lob_rows):,} rows")

    # 6. Abandon by hour × LOB (Phone only, last 12mo)
    print("  abandon heatmap ... ", end="", flush=True)
    cur.execute("""
        SELECT
            DATE_TRUNC('month', DATE)::DATE              AS MONTH,
            LOB_OR_QUEUE_GROUP                            AS LOB,
            TRY_TO_NUMBER(SPLIT_PART(RANGE_30_MINUTES, ':', 1)) AS HOUR,
            SUM(QUEUED)   AS QUEUED,
            SUM(ABANDONS) AS ABANDONS
        FROM ANALYTICS.ANALYTICS_MEM_CARE_MART.VOLUME_30MIN_INTERVALS_V2
        WHERE DIRECTION = 'Inbound'
          AND MEDIA_NAME = 'Phone'
          AND DATE >= DATEADD('month', -12, CURRENT_DATE())
          AND LOB_OR_QUEUE_GROUP NOT IN ('Freemotion', 'UK OmniQueue')
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3
    """)
    ab_rows = cur.fetchall()
    ab_cols = [c[0].lower() for c in cur.description]
    print(f"{len(ab_rows):,} rows")

    cur.close()
    conn.close()

    # ---- Actuals monthly ----
    monthly = {}
    for row in vol_rows:
        r = dict(zip(vol_cols, row))
        month_dt = r["month"]
        media = (r["media_name"] or "Other").strip()
        lob   = (r["lob"] or "Unknown").strip()
        if lob in EXCLUDED_LOBS:
            continue
        if media not in CHANNEL_ORDER:
            media = "Other"

        month_str = str(month_dt)[:10]
        fy, fm = fiscal_from_date(month_dt)

        m = monthly.setdefault(month_str, {
            "month": month_str, "fy": fy, "fm": fm,
            "handled": 0, "abandons": 0, "queued": 0,
            "by_channel": {}, "by_lob": {},
        })
        handled  = to_float(r["handled"])
        abandons = to_float(r["abandons"])
        queued   = to_float(r["queued"])
        soa      = to_float(r["total_soa"])
        ht       = to_float(r["total_ht"])

        m["handled"]  += handled
        m["abandons"] += abandons
        m["queued"]   += queued

        ch = m["by_channel"].setdefault(media, {
            "handled": 0, "abandons": 0, "queued": 0,
            "total_soa": 0, "total_ht": 0,
        })
        ch["handled"]  += handled
        ch["abandons"] += abandons
        ch["queued"]   += queued
        ch["total_soa"]+= soa
        ch["total_ht"] += ht

        m["by_lob"][lob] = m["by_lob"].get(lob, 0) + handled

    actuals = sorted(monthly.values(), key=lambda x: x["month"])
    for m in actuals:
        for ch in m["by_channel"].values():
            h = ch["handled"]
            ch["asa_sec"] = round(ch["total_soa"] / h, 1) if h > 0 else 0
            ch["aht_sec"] = round(ch["total_ht"]  / h, 1) if h > 0 else 0
            del ch["total_soa"]
            del ch["total_ht"]
        m["handled"]  = int(m["handled"])
        m["abandons"] = int(m["abandons"])
        m["queued"]   = int(m["queued"])
        for ch in m["by_channel"].values():
            ch["handled"]  = int(ch["handled"])
            ch["abandons"] = int(ch["abandons"])
            ch["queued"]   = int(ch["queued"])
        m["by_lob"] = {k: int(v) for k, v in m["by_lob"].items()}

    # ---- FCR ----
    fcr_list = []
    for month_dt, rate, resolved, total in fcr_rows:
        month_str = str(month_dt)[:10]
        fy, fm = fiscal_from_date(month_dt)
        fcr_list.append({
            "month": month_str, "fy": fy, "fm": fm,
            "rate": round(to_float(rate), 4),
            "resolved": int(to_float(resolved)),
            "total": int(to_float(total)),
        })

    # ---- Forecasts ----
    forecasts = {}
    for month_dt, lob, sub_lob, channel, version, contacts in fc_rows:
        month_str = str(month_dt)[:10]
        fy, fm = fiscal_from_date(month_dt)
        contacts = int(to_float(contacts))
        ver = forecasts.setdefault(version, {})
        vm = ver.setdefault(month_str, {
            "month": month_str, "fy": fy, "fm": fm,
            "total": 0, "by_channel": {}, "by_lob": {},
        })
        vm["total"] += contacts
        vm["by_channel"][channel] = vm["by_channel"].get(channel, 0) + contacts
        lob_entry = vm["by_lob"].setdefault(lob, {"total": 0, "by_sub_lob": {}})
        lob_entry["total"] += contacts
        if sub_lob:
            lob_entry["by_sub_lob"][sub_lob] = \
                lob_entry["by_sub_lob"].get(sub_lob, 0) + contacts

    fc_out = {}
    for ver, months in forecasts.items():
        fc_out[ver] = sorted(months.values(), key=lambda x: x["month"])

    # ---- Heatmap (DOW × hour × month) ----
    DOW_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    heatmap = {}
    for row in hm_rows:
        r = dict(zip(hm_cols, row))
        dow = int(to_float(r["dow"]))
        if r["hour"] is None:
            continue
        hour = int(to_float(r["hour"]))
        media = (r["media_name"] or "Other").strip()
        if media not in CHANNEL_ORDER:
            media = "Other"
        days = int(to_float(r["days"])) or 1
        handled = to_float(r["handled"])
        ht = to_float(r["total_ht"])
        month_str = str(r["month"])[:10]
        fy, fm = fiscal_from_date(r["month"])
        key = f"{month_str}_{dow}_{hour}_{media}"
        heatmap[key] = {
            "month": month_str, "fy": fy, "fm": fm,
            "dow": dow, "dow_label": DOW_LABELS[dow] if dow < 7 else "?",
            "hour": hour, "channel": media,
            "handled": int(handled),
            "avg_daily_handled": round(handled / days, 1),
            "aht_sec": round(ht / handled, 1) if handled > 0 else 0,
        }
    heatmap_list = sorted(heatmap.values(), key=lambda x: (x.get("fy",0), x.get("fm",0), x["dow"], x["hour"], x["channel"]))

    # ---- LOB detail (month × channel × LOB) ----
    lob_detail = []
    for row in lob_rows:
        r = dict(zip(lob_cols, row))
        media = (r["media_name"] or "Other").strip()
        lob = (r["lob"] or "Unknown").strip()
        if media not in CHANNEL_ORDER:
            media = "Other"
        month_str = str(r["month"])[:10]
        fy, fm = fiscal_from_date(r["month"])
        handled = to_float(r["handled"])
        abandons = to_float(r["abandons"])
        queued = to_float(r["queued"])
        soa = to_float(r["total_soa"])
        ht = to_float(r["total_ht"])
        lob_detail.append({
            "month": month_str, "fy": fy, "fm": fm,
            "channel": media, "lob": lob,
            "handled": int(handled),
            "abandons": int(abandons),
            "queued": int(queued),
            "asa_sec": round(soa / handled, 1) if handled > 0 else 0,
            "aht_sec": round(ht / handled, 1) if handled > 0 else 0,
        })

    # ---- Abandon heatmap (Phone: LOB × hour, by month) ----
    abandon_heat = []
    for row in ab_rows:
        r = dict(zip(ab_cols, row))
        month_str = str(r["month"])[:10]
        lob = (r["lob"] or "Unknown").strip()
        if r["hour"] is None:
            continue
        hour = int(to_float(r["hour"]))
        queued = int(to_float(r["queued"]))
        abandons = int(to_float(r["abandons"]))
        abandon_heat.append({
            "month": month_str, "lob": lob, "hour": hour,
            "queued": queued, "abandons": abandons,
            "abandon_pct": round(abandons / queued, 4) if queued > 0 else 0,
        })

    # ---- Output ----
    out = {
        "meta": {
            "refreshed_at": datetime.now().isoformat(timespec="seconds"),
            "channel_order": CHANNEL_ORDER,
            "excluded_lobs": list(EXCLUDED_LOBS),
            "forecast_to_actuals_lob": FORECAST_TO_ACTUALS_LOB,
            "actuals_to_forecast_lob": ACTUALS_TO_FORECAST_LOB,
        },
        "actuals": actuals,
        "fcr": fcr_list,
        "forecasts": fc_out,
        "heatmap": heatmap_list,
        "lob_detail": lob_detail,
        "abandon_heat": abandon_heat,
    }

    out_path = DATA / "contacts.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    size_kb = out_path.stat().st_size / 1024
    print(f"\nWrote {out_path}  ({size_kb:,.0f} KB)")
    print(f"  Actuals: {len(actuals)} months")
    print(f"  FCR: {len(fcr_list)} months")
    print(f"  Forecasts: {len(fc_out)} versions, "
          f"{sum(len(v) for v in fc_out.values())} month-records")
    print(f"  Heatmap: {len(heatmap_list)} cells")
    print(f"  LOB detail: {len(lob_detail)} rows")
    print(f"  Abandon heat: {len(abandon_heat)} cells")


if __name__ == "__main__":
    main()
