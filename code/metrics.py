"""세션별 '튐' 지표 패널 생성: data/raw/*.parquet → data/panel_sessions.{parquet,csv}.

프리/정규/애프터 세션이 가격을 튀게 하는지 4축으로 측정한다:
  A 세션 간 갭   : 세션 전환 시 가격 점프(수익률)
  B 세션 내 변동 : range_pct=(고-저)/시, ret_std=봉별수익률 표준편차
  C 튀고 되돌림  : 연장세션 드리프트와 다음 정규장에서의 되돌림 비율
  D 거래량 과민  : Amihud = |세션수익률| / 거래대금

전제(실측 확인): ACVOL_UNS 는 '봉별' 거래량(누적 아님 — 값이 증감). 거래대금은
typical price(고+저+종/3)×거래량으로 근사.

산출: (code, date) 한 행에 세션별 within-지표 + 세션 간 갭/되돌림을 모두 붙인 wide 패널.

실행:
    python code/metrics.py            # data/raw 전체
    python code/metrics.py --codes 005930
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT_PARQUET = ROOT / "data" / "panel_sessions.parquet"
OUT_CSV = ROOT / "data" / "panel_sessions.csv"

SESSIONS = ["pre", "regular", "after"]


def _session_aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """봉 단위(df: KST 인덱스 + OHLCV + session) → (date, session) within-세션 지표."""
    df = df.copy()
    df["date"] = df.index.date
    df["typ"] = (df["HIGH_1"] + df["LOW_1"] + df["TRDPRC_1"]) / 3.0
    df["turnover"] = df["typ"] * df["ACVOL_UNS"]
    df["ret"] = df.groupby(["date", "session"])["TRDPRC_1"].pct_change()

    g = df.groupby(["date", "session"])
    agg = pd.DataFrame({
        "open":     g["OPEN_PRC"].first(),
        "high":     g["HIGH_1"].max(),
        "low":      g["LOW_1"].min(),
        "close":    g["TRDPRC_1"].last(),
        "volume":   g["ACVOL_UNS"].sum(),
        "turnover": g["turnover"].sum(),
        "bars":     g.size(),
        "ret_std":  g["ret"].std(),                     # B: 봉별 수익률 변동
        "vwap_num": g.apply(lambda x: (x["typ"] * x["ACVOL_UNS"]).sum(),
                            include_groups=False),
    })
    agg["vwap"] = agg["vwap_num"] / agg["volume"]
    agg = agg.drop(columns="vwap_num")
    agg["range_pct"] = (agg["high"] - agg["low"]) / agg["open"]     # B: 세션 내 폭
    sess_ret = agg["close"] / agg["open"] - 1.0
    agg["amihud"] = sess_ret.abs() / agg["turnover"].replace(0, np.nan)  # D
    return agg


def _to_wide(agg: pd.DataFrame) -> pd.DataFrame:
    """(date, session) long → date 행, 세션 prefix(pre_/reg_/aft_) wide."""
    pref = {"pre": "pre", "regular": "reg", "after": "aft"}
    wide = None
    for s, p in pref.items():
        sub = agg.xs(s, level="session") if s in agg.index.get_level_values("session") \
            else pd.DataFrame()
        sub = sub.add_prefix(f"{p}_")
        wide = sub if wide is None else wide.join(sub, how="outer")
    return wide.sort_index()


def _cross_session(wide: pd.DataFrame) -> pd.DataFrame:
    """세션 간 갭(A) + 드리프트/되돌림(C). prev/next 거래일은 인덱스 shift."""
    w = wide.sort_index()
    prev_reg_close = w["reg_close"].shift(1)
    next_reg_open = w["reg_open"].shift(-1)
    next_reg_close = w["reg_close"].shift(-1)

    # A: 세션 간 갭(수익률)
    w["gap_overnight_pre"] = w["pre_open"] / prev_reg_close - 1     # 전일정규종 → 프리시
    w["gap_pre_reg"]       = w["reg_open"] / w["pre_close"] - 1     # 프리종 → 정규시
    w["gap_reg_aft"]       = w["aft_open"] / w["reg_close"] - 1     # 정규종 → 애프터시
    w["gap_aft_nextreg"]   = next_reg_open / w["aft_close"] - 1     # 애프터종 → 익일정규시

    # C: 연장세션 드리프트(정규종가 기준) & 다음 정규장 되돌림 비율
    #   revert_frac = 드리프트 중 다음 정규 움직임이 되돌린 비율(1=완전 되돌림, 0=지속)
    aft_drift = w["aft_close"] / w["reg_close"] - 1
    aft_move_next = next_reg_open / w["aft_close"] - 1
    w["aft_drift"] = aft_drift
    w["aft_revert_frac"] = (-aft_move_next / aft_drift).where(aft_drift.abs() > 1e-9)

    pre_drift = w["pre_close"] / prev_reg_close - 1                 # 프리가 전일종가서 이동
    reg_move = w["reg_close"] / w["pre_close"] - 1                 # 당일 정규의 후속 움직임
    w["pre_drift"] = pre_drift
    w["pre_revert_frac"] = (-reg_move / pre_drift).where(pre_drift.abs() > 1e-9)
    return w


def build_panel(codes=None) -> pd.DataFrame:
    files = ([RAW_DIR / f"{c}.parquet" for c in codes] if codes
             else sorted(RAW_DIR.glob("*.parquet")))
    rows = []
    for f in files:
        if not f.exists():
            print(f"skip (missing): {f.name}")
            continue
        df = pd.read_parquet(f)
        if df.empty:
            continue
        agg = _session_aggregate(df)
        wide = _cross_session(_to_wide(agg))
        wide.insert(0, "code", f.stem)
        wide.index.name = "date"
        rows.append(wide.reset_index())
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def summarize(panel: pd.DataFrame) -> None:
    """세션별 분포 요약(중앙값/평균) — 프리/애프터가 정규보다 튀는지 한눈에."""
    print("\n== B 세션 내 변동성 (중앙값) ==")
    for p, name in [("pre", "프리"), ("reg", "정규"), ("aft", "애프터")]:
        rp = panel[f"{p}_range_pct"].median()
        rs = panel[f"{p}_ret_std"].median()
        print(f"  {name:4s} range_pct(중앙) {rp:.4%} | ret_std(중앙) {rs:.4%}")

    print("\n== A 세션 간 갭 (|수익률| 중앙값) ==")
    for col, name in [("gap_overnight_pre", "전일종→프리시"),
                      ("gap_pre_reg", "프리종→정규시"),
                      ("gap_reg_aft", "정규종→애프터시"),
                      ("gap_aft_nextreg", "애프터종→익일정규시")]:
        print(f"  {name:14s} {panel[col].abs().median():.4%}")

    print("\n== C 되돌림 (revert_frac 중앙값; 1=완전 되돌림) ==")
    print(f"  프리 드리프트 되돌림  {panel['pre_revert_frac'].median():.3f}")
    print(f"  애프터 드리프트 되돌림 {panel['aft_revert_frac'].median():.3f}")

    print("\n== D Amihud 비유동성 (중앙값; 클수록 거래량 대비 과민) ==")
    for p, name in [("pre", "프리"), ("reg", "정규"), ("aft", "애프터")]:
        print(f"  {name:4s} {panel[f'{p}_amihud'].median():.3e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", nargs="*")
    args = ap.parse_args()
    panel = build_panel(args.codes)
    if panel.empty:
        print("no data — data/raw 가 비어있음. collect_all.py 먼저 실행.")
        return
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(OUT_PARQUET)
    panel.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"panel: {len(panel)} rows ({panel['code'].nunique()} codes, "
          f"{panel['date'].min()} ~ {panel['date'].max()}) "
          f"-> {OUT_PARQUET.name}, {OUT_CSV.name}")
    summarize(panel)


if __name__ == "__main__":
    main()
