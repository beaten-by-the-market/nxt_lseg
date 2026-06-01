"""[3단계-랭킹] 종목별 프리/애프터 '튐' 빈도 랭킹 → 워치리스트.

case_finder.scan_file로 (종목×일×세션) 최대 spike를 모은 뒤, 종목별로
"지난 1년간 프리장 N% 플래시 며칠"을 집계한다. 기사용 '상습 튐' 종목 발굴.

출력: data/jumpiness_ranking.csv
실행: python code/jumpiness.py [--session pre|after] [--rank-thr 0.10]
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from case_finder import scan_file, _names, _liquidity_pct  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT = ROOT / "data" / "jumpiness_ranking.csv"
THRS = [0.05, 0.10, 0.20]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default="pre", choices=["pre", "after"])
    ap.add_argument("--rank-thr", type=float, default=0.10, help="랭킹 기준 임계(0.10=10%)")
    args = ap.parse_args()

    names, liq = _names(), _liquidity_pct()
    allc = [scan_file(f, [args.session]) for f in sorted(RAW_DIR.glob("*.parquet"))]
    cases = pd.concat([c for c in allc if not c.empty], ignore_index=True)

    rows = []
    for code, g in cases.groupby("code"):
        rec = {"code": code, "name": names.get(code, code),
               "sess_days": len(g),                    # 해당 세션 거래일 수
               "median_spike": float(g["spike"].median()),
               "max_spike": float(g["spike"].max()),
               "max_date": g.loc[g["spike"].idxmax(), "date"],
               "liq_pct": float(liq.get(code, float("nan")))}
        for t in THRS:
            rec[f"days_ge_{int(t*100)}"] = int((g["spike"] >= t).sum())
        rows.append(rec)
    rank = pd.DataFrame(rows)
    key = f"days_ge_{int(args.rank_thr*100)}"
    rank = rank.sort_values([key, "max_spike"], ascending=False).reset_index(drop=True)
    rank.to_csv(OUT, index=False, encoding="utf-8-sig")

    print(f"[{args.session}] 종목 {len(rank)} | saved -> {OUT.name}")
    print(f"== 상위 20: {args.session}장 {int(args.rank_thr*100)}%+ 플래시 빈도 ==")
    cols = ["name", "code", key, "days_ge_5", "max_spike", "max_date", "liq_pct"]
    print(rank.head(20)[cols].to_string(index=False))
    print(f"\n{args.session}장 {int(args.rank_thr*100)}%+ 플래시가 1회 이상인 종목: "
          f"{(rank[key] > 0).sum()} / {len(rank)}")


if __name__ == "__main__":
    main()
