"""Source files for the financials table: import from scratch, load with hash check."""
import csv
import hashlib
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

BSE_URL = "https://www.bseindia.com/xml-data/corpfiling/AttachHis/"
COLS = ["symbol", "period_end", "kind", "basis", "file", "url", "sha256"]


@dataclass
class Source:
    symbol: str
    period_end: date
    kind: str            # INDAS | BANKING | NBFC_INDAS | LI | PDF
    basis: str | None    # None for PDFs (may hold both)
    path: Path
    url: str
    sha256: str

    @property
    def rel(self) -> str:
        return f"{self.symbol}/{self.path.name}"


def parse_manifest_date(s: str) -> date:
    for fmt in ("%d-%m-%Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError(f"bad date: {s!r}")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _month_end(y: int, m: int) -> date:
    nxt = date(y + m // 12, m % 12 + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1)


def import_scratch(xbrl_manifest: Path, xbrl_cache: Path, results_dir: Path,
                   links_csv: Path, out_dir: Path) -> int:
    rows = []
    with open(xbrl_manifest, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            end = parse_manifest_date(r["period_end"])
            basis = r["basis"].strip().lower()
            dst = out_dir / r["symbol"] / f"{end:%Y-%m}_{basis}.html"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(xbrl_cache / r["url"].rsplit("/", 1)[1], dst)
            rows.append([r["symbol"], end.isoformat(), r["kind"], basis,
                         f"{r['symbol']}/{dst.name}", r["url"], _sha(dst)])
    with open(links_csv, newline="", encoding="utf-8") as f:
        for sym, mon, pname in csv.reader(f):
            m, y = (int(x) for x in mon.split("/"))
            end = _month_end(y, m)
            dst = out_dir / sym / f"{end:%Y-%m}.pdf"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(results_dir / sym / dst.name, dst)
            rows.append([sym, end.isoformat(), "PDF", "", f"{sym}/{dst.name}",
                         pname if pname.startswith("http") else BSE_URL + pname.split("=", 1)[1],
                         _sha(dst)])
    with open(out_dir / "sources.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(COLS)
        w.writerows(sorted(rows))
    return len(rows)


def load_sources(out_dir: Path) -> list[Source]:
    out = []
    with open(Path(out_dir) / "sources.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            p = Path(out_dir) / r["file"]
            if not p.exists() or _sha(p) != r["sha256"]:
                raise ValueError(f"missing or changed source file: {r['file']}")
            out.append(Source(r["symbol"], date.fromisoformat(r["period_end"]), r["kind"],
                              r["basis"] or None, p, r["url"], r["sha256"]))
    return out


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2] / ".superpowers"
    n = import_scratch(root / "xbrl-discovery" / "manifest.csv", root / "xbrl-discovery" / "cache",
                       root / "results-q", root / "results-q" / "links.csv",
                       Path(__file__).resolve().parents[1] / "data" / "quarterly")
    print(f"{n} files")
