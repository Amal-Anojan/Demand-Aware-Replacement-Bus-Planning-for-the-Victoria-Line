"""Read validated NUMBAT Victoria-line data without modifying source workbooks."""
from functools import lru_cache
import hashlib
import json
import re
import numpy as np
import pandas as pd
from config import DATA_DIR, CACHE_DIR, DAY_SOURCES, STATIONS

SHEETS = ("Link_Loads", "Link_Frequencies", "Station_Boarders", "Station_Alighters")
AUDIT_SHEETS = SHEETS + ("Station_Entries", "Station_Exits", "Station_Flows", "Line_Boarders")


def interval_columns(columns):
    return [c for c in columns if isinstance(c, str) and re.fullmatch(r"\d{4}-\d{4}", c)]


def minute_of_day(label):
    return int(label[:2]) * 60 + int(label[2:4])


def validate_intervals(columns):
    intervals = interval_columns(columns)
    if len(intervals) != 96 or len(set(intervals)) != 96:
        raise ValueError("Expected 96 distinct 15-minute NUMBAT intervals")
    starts = [minute_of_day(c) for c in intervals]
    for i, c in enumerate(intervals):
        if starts[i] % 15 or (minute_of_day(c[5:]) - starts[i]) % 1440 != 15:
            raise ValueError(f"Invalid interval: {c}")
        if (starts[(i + 1) % 96] - starts[i]) % 1440 != 15:
            raise ValueError("Intervals are not in service-day order")
    return intervals


def source_signature():
    return tuple((code, (DATA_DIR / f"NBT25{code}_Outputs.xlsx").stat().st_mtime_ns,
                  (DATA_DIR / f"NBT25{code}_Outputs.xlsx").stat().st_size)
                 for code in dict.fromkeys(DAY_SOURCES.values()))


def load_data():
    return _load_data(source_signature())


@lru_cache(maxsize=2)
def _load_data(signature):
    result = {}
    CACHE_DIR.mkdir(exist_ok=True)
    for code, mtime, size in signature:
        path = DATA_DIR / f"NBT25{code}_Outputs.xlsx"
        token = hashlib.sha256(f"v1:{mtime}:{size}".encode()).hexdigest()[:16]
        cache = CACHE_DIR / f"numbat_{code}_{token}.json"
        if cache.exists():
            raw = json.loads(cache.read_text(encoding="utf-8"))
            tables = {sheet: pd.DataFrame(rows) for sheet, rows in raw.items()}
        else:
            tables = {}
            with pd.ExcelFile(path) as book:
                missing = set(AUDIT_SHEETS) - set(book.sheet_names)
                if missing:
                    raise ValueError(f"{path.name}: missing sheets {missing}")
                for sheet in SHEETS:
                    df = pd.read_excel(book, sheet_name=sheet, header=2)
                    line = df["Line"].astype(str).str.strip().str.casefold()
                    tables[sheet] = df[line.eq("victoria" if sheet.startswith("Link") else "vic")].copy()
            cache.write_text(json.dumps({s: json.loads(d.to_json(orient="records", double_precision=15))
                                         for s, d in tables.items()}), encoding="utf-8")
        reference = None
        for sheet, df in tables.items():
            intervals = validate_intervals(df.columns)
            if reference is not None and intervals != reference:
                raise ValueError(f"{code}: mismatched intervals")
            reference = intervals
            values = df[intervals].to_numpy(dtype=float)
            if not np.isfinite(values).all() or (values < 0).any():
                raise ValueError(f"{code}/{sheet}: missing, negative or non-finite observations")
            if sheet.startswith("Link"):
                expected = {(a, b) for a, b in zip(STATIONS, STATIONS[1:])}
                expected |= {(b, a) for a, b in list(expected)}
                pairs = list(zip(df["From Station"], df["To Station"]))
                if len(pairs) != 30 or set(pairs) != expected or df["Link"].duplicated().any():
                    raise ValueError(f"{code}/{sheet}: expected exactly 30 Victoria directed links")
                for _, row in df.iterrows():
                    direction = "NB" if STATIONS.index(row["To Station"]) > STATIONS.index(row["From Station"]) else "SB"
                    if row["Dir"] != direction:
                        raise ValueError("Direction does not match station order")
            elif not set(df["Station"]).issubset(STATIONS):
                raise ValueError(f"Unexpected station in {code}/{sheet}")
        result[code] = tables
    return result


def link_row(data, day, sheet, origin, destination):
    df = data[DAY_SOURCES[day]][sheet]
    rows = df[(df["From Station"] == origin) & (df["To Station"] == destination)]
    if len(rows) != 1:
        raise ValueError(f"Expected one {sheet} row for {origin} -> {destination}")
    return rows.iloc[0]


def time_window(data, day, start, duration):
    """Follow workbook service days (05:00–04:45); advance day at 05:00.

    Midnight columns belong to the selected source service day. At the next
    05:00, switch to the next named day, including Sunday -> Monday.
    """
    intervals = interval_columns(data[DAY_SOURCES[day]]["Link_Loads"].columns)
    if start not in intervals or duration <= 0 or int(duration) != duration or duration > 1440:
        raise ValueError("Choose an available start and 1–1440 whole minutes")
    days = list(DAY_SOURCES)
    index = intervals.index(start)
    rows = []
    for offset in range((int(duration) + 14) // 15):
        rollover, position = divmod(index + offset, len(intervals))
        service_day = days[(days.index(day) + rollover) % 7]
        interval = intervals[position]
        rows.append({"minute": offset * 15, "interval_minutes": min(15, duration - offset * 15), "day": service_day,
                     "source": DAY_SOURCES[service_day], "interval": interval,
                     "label": f"{service_day} {interval}"})
    return rows
