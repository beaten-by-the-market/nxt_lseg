"""[3단계-교차] 프리장 '튐' 빈도 × 시총/섹터.

어떤 종목군(시총대·섹터)이 프리장 플래시에 취약한지 본다.
입력 : data/jumpiness_ranking.csv (종목별 프리 플래시 빈도; jumpiness.py --session pre 산출)
       종목 메타(시총·섹터)는 LSEG에서 받아 data/stock_meta.csv 로 캐싱(재실행 시 재사용).
출력 : data/cross_sector.csv, data/cross_mktcap.csv + 콘솔표
실행 : python code/cross_analysis.py        (메타 캐시 없으면 LSEG Workspace 필요)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
RANK = ROOT / "data" / "jumpiness_ranking.csv"
META = ROOT / "data" / "stock_meta.csv"
UNIV = ROOT / "data" / "nxt_universe.csv"


def load_meta(codes) -> pd.DataFrame:
    """code → (mktcap, sector). 회사 전체 시총은 .KS/.KQ 기준(.KNT는 NXT 한정 float)."""
    if META.exists():
        m = pd.read_csv(META, dtype={"code": str})
        print(f"meta (cached): {len(m)}")
        return m
    import lseg.data as ld
    FIELDS = ["TR.CompanyMarketCap", "TR.TRBCEconomicSector"]
    ld.open_session()
    try:
        def fetch(suffix):
            d = ld.get_data([c + suffix for c in codes], FIELDS)
            d = d.rename(columns={"Instrument": "ric",
                                  "Company Market Cap": "mktcap",
                                  "TRBC Economic Sector Name": "sector"})
            d["code"] = d["ric"].str.slice(0, 6)
            return d[["code", "mktcap", "sector"]]
        ks = fetch(".KS")
        miss = ks[ks["mktcap"].isna()]["code"].tolist()
        kq = fetch(".KQ") if miss else pd.DataFrame(columns=["code", "mktcap", "sector"])
        # .KS 우선, 없으면 .KQ로 보강
        m = ks.set_index("code")
        kq = kq.set_index("code")
        for c in miss:
            if c in kq.index and pd.notna(kq.loc[c, "mktcap"]):
                m.loc[c] = kq.loc[c]
        m = m.reset_index()
    finally:
        ld.close_session()
    m["mktcap"] = pd.to_numeric(m["mktcap"], errors="coerce")
    m.to_csv(META, index=False, encoding="utf-8-sig")
    print(f"meta fetched & saved: {len(m)} -> {META.name}")
    return m


def main():
    rank = pd.read_csv(RANK, dtype={"code": str})
    meta = load_meta(rank["code"].tolist())
    df = rank.merge(meta, on="code", how="left")
    df["flash"] = df["days_ge_10"] >= 1            # 프리 10%+ 플래시 1회 이상

    # ---- 섹터 교차 ----
    sec = (df.groupby("sector")
           .agg(stocks=("code", "size"),
                flash_stocks=("flash", "sum"),
                flash_days=("days_ge_10", "sum"),
                median_maxspike=("max_spike", "median"))
           .reset_index())
    sec["pct_flash"] = sec["flash_stocks"] / sec["stocks"]
    sec = sec.sort_values("pct_flash", ascending=False)
    sec.to_csv(ROOT / "data" / "cross_sector.csv", index=False, encoding="utf-8-sig")

    # ---- 시총 5분위 교차 (랭킹 기준; 1=소형 … 5=대형) ----
    d = df.dropna(subset=["mktcap"]).copy()
    d["mktcap_q"] = pd.qcut(d["mktcap"].rank(method="first"), 5,
                            labels=["Q1(소형)", "Q2", "Q3", "Q4", "Q5(대형)"])
    cap = (d.groupby("mktcap_q", observed=True)
           .agg(stocks=("code", "size"),
                flash_stocks=("flash", "sum"),
                flash_days=("days_ge_10", "sum"),
                median_maxspike=("max_spike", "median"),
                mktcap_median=("mktcap", "median"))
           .reset_index())
    cap["pct_flash"] = cap["flash_stocks"] / cap["stocks"]
    cap.to_csv(ROOT / "data" / "cross_mktcap.csv", index=False, encoding="utf-8-sig")

    pd.options.display.float_format = lambda x: f"{x:,.3f}"
    print("\n== 섹터별 프리장 10%+ 플래시 (취약 순) ==")
    print(sec[["sector", "stocks", "flash_stocks", "pct_flash",
               "flash_days", "median_maxspike"]].to_string(index=False))
    print("\n== 시총 5분위별 (1=소형 … 5=대형) ==")
    print(cap[["mktcap_q", "stocks", "flash_stocks", "pct_flash",
               "flash_days", "median_maxspike", "mktcap_median"]].to_string(index=False))


if __name__ == "__main__":
    main()
