"""Shared project constants; source paths are relative to this project."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / "cache"
OUTPUT_DIR = ROOT / "outputs"
DAY_SOURCES = dict(zip(
    ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    ("MON", "TWT", "TWT", "TWT", "FRI", "SAT", "SUN"),
))
STATIONS = (
    "Brixton LU", "Stockwell", "Vauxhall LU", "Pimlico", "Victoria LU",
    "Green Park", "Oxford Circus", "Warren Street", "Euston LU",
    "King's Cross St. Pancras", "Highbury & Islington", "Finsbury Park LU",
    "Seven Sisters", "Tottenham Hale LU", "Blackhorse Road", "Walthamstow Central",
)
ASSUMPTION = (
    "Hypothetical train-operation assumption: trains operate normally up to the "
    "closure boundaries; replacement buses connect those boundaries and onward "
    "train service resumes there. These are not verified TfL turnback arrangements."
)
