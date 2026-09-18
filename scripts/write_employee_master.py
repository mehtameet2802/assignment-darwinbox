from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "demo" / "employee_master.xlsx"

ROWS = [
    {
        "Employee ID": "E001",
        "Full Name": "Meet Mehta",
        "Joining Date": "2024-05-12",
        "Work Email": "meet@example.com",
        "Department": "Engineering",
        "Office": "Mumbai",
    },
    {
        "Employee ID": "E002",
        "Full Name": "Ravi Shah",
        "Joining Date": "2023-06-01",
        "Work Email": "ravi.work@example.com",
        "Department": "Product",
        "Office": "Pune",
    },
    {
        "Employee ID": "E005",
        "Full Name": "John Patel",
        "Joining Date": "2024-10-20",
        "Work Email": "john@example.com",
        "Department": "Engineering",
        "Office": "Hyderabad",
    },
    {
        "Employee ID": "E006",
        "Full Name": "Priya Desai",
        "Joining Date": "2024-09-15",
        "Work Email": "priya@example.com",
        "Department": "HR",
        "Office": "Mumbai",
    },
]


def write_employee_master(path: Path = OUTPUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(ROWS)
    frame.to_excel(path, index=False)
    return path


if __name__ == "__main__":
    write_employee_master()
    print(f"Wrote {OUTPUT}")
