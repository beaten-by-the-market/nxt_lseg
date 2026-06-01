"""[3단계] 본 분석: 프리/정규/애프터가 정규장 대비 '튀는가'를 공정하게 검증.

3_NXT_ANALYSIS.md §4의 함정을 보정한다:
  (1) 봉당(30분당) 변동성으로 정규화 → 세션 길이 착시 제거 (B 공정 비교)
  (2) 유동성 3분위(상/중/하) 층화 → '얇을수록 튄다'(D) 검증
  (3) 연장세션 드리프트의 정규장 되돌림 분포 (C)
  (4) 세션 간 갭 분포 (A)

입력 : data/raw/*.parquet (봉단위), data/panel_sessions.parquet (세션단위)
출력 : data/analysis_summary.md (사람이 읽는 결과), data/analysis_*.csv (수치)
실행 : python code/analyze.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from case_finder import scan_file          # noqa: E402  (intra-bar 튐 케이스 스캔 재사용)

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PANEL = ROOT / "data" / "panel_sessions.parquet"
OUT_MD = ROOT / "data" / "analysis_summary.md"

SLABEL = {"pre": "프리", "regular": "정규", "after": "애프터"}
SPREF = {"pre": "pre", "regular": "reg", "after": "aft"}


def per_bar_volatility() -> pd.DataFrame:
    """봉단위 |30분 수익률|을 세션별로 풀링 → 길이 중립 변동성(B 공정)."""
    acc = {s: [] for s in SLABEL}
    for f in sorted(RAW_DIR.glob("*.parquet")):
        df = pd.read_parquet(f, columns=["TRDPRC_1", "session"])
        df["date"] = df.index.date
        r = df.groupby(["date", "session"])["TRDPRC_1"].pct_change().abs()
        for s in SLABEL:
            v = r[df["session"] == s].dropna().values
            if len(v):
                acc[s].append(v)
    rows = []
    for s in SLABEL:
        a = np.concatenate(acc[s]) if acc[s] else np.array([])
        rows.append({"session": s,
                     "bars": len(a),
                     "median": np.median(a) if len(a) else np.nan,
                     "mean": a.mean() if len(a) else np.nan,
                     "p90": np.quantile(a, 0.90) if len(a) else np.nan,
                     "p99": np.quantile(a, 0.99) if len(a) else np.nan})
    return pd.DataFrame(rows).set_index("session")


def liquidity_terciles(panel: pd.DataFrame) -> pd.Series:
    """종목별 정규장 일중앙 거래대금 → 3분위(low/mid/high) 라벨."""
    liq = panel.groupby("code")["reg_turnover"].median()
    q = liq.quantile([1/3, 2/3])
    def lab(x):
        if x <= q.iloc[0]:
            return "low"
        if x <= q.iloc[1]:
            return "mid"
        return "high"
    return liq.map(lab).rename("liq")


def fmt_pct(x):
    return "NA" if pd.isna(x) else f"{x:.3%}"


def fmt_sci(x):
    return "NA" if pd.isna(x) else f"{x:.3e}"


def flash_section() -> list:
    """E. 30분봉 intra-bar '튐'(flash) 케이스 — 전 종목 스캔 + 보강 산출물 요약."""
    cases = pd.concat([scan_file(f, ["pre", "after"])
                       for f in sorted(RAW_DIR.glob("*.parquet"))], ignore_index=True)
    md = ["\n## E. 30분봉 intra-bar '튐'(flash) 케이스",
          "한 30분봉 안에서 고/저가가 몸통(|시−종|) 밖으로 벗어난 폭(round-trip)=봉 내 급변 후 복원. "
          "→ [case_finder.py](../code/case_finder.py)\n",
          "| 임계 | 총 | 상승 | 하락 | 프리 | 애프터 |",
          "|---|---|---|---|---|---|"]
    for thr in [0.05, 0.10, 0.15, 0.20, 0.30]:
        s = cases[cases["spike"] >= thr]
        md.append(f"| ≥{int(thr*100)}% | {len(s):,} | {(s.direction=='up').sum():,} | "
                  f"{(s.direction=='down').sum():,} | {(s.session=='pre').sum():,} | "
                  f"{(s.session=='after').sum():,} |")
    md.append("\n→ 압도적 **프리장**, 중간강도는 상승 우세·극단(≥20%)은 하락 우세.")

    # 보강 산출물(있으면) 요약
    corr = ROOT / "data" / "krx_corroboration.csv"
    if corr.exists():
        cc = pd.read_csv(corr)
        have = cc["krx_low"].notna()
        n = cc.loc[have, "outside_krx"].eq(True).sum()
        md.append(f"- **KRX 대조**(≥10% 케이스): {int(n)}/{int(have.sum())}건이 NXT 극단가가 "
                  f"KRX 당일 정규장 범위 '밖' = NXT 연장세션 전용 현상.")
    jr = ROOT / "data" / "jumpiness_ranking.csv"
    if jr.exists():
        r = pd.read_csv(jr)
        md.append(f"- **빈도**(프리장): {int((r['days_ge_10'] >= 1).sum())}종목이 10%+ 플래시 1회 이상 "
                  f"(전 {len(r)}종목).")
    cm = ROOT / "data" / "cross_mktcap.csv"
    if cm.exists():
        c = pd.read_csv(cm)
        lo = c.iloc[0]["pct_flash"]; hi = c.iloc[-1]["pct_flash"]
        md.append(f"- **시총교차**: 소형 {lo:.0%} < 대형 {hi:.0%} — 소형주만의 문제 아님(중·대형도 빈번).")
    return md


def main():
    panel = pd.read_parquet(PANEL)
    md = ["# 분석 결과 — 넥스트레이드 프리/애프터 '튐' 검증",
          f"\n> 자동 생성. 종목 {panel['code'].nunique()}개, "
          f"{panel['date'].min()} ~ {panel['date'].max()}, 행 {len(panel):,}.\n"]

    # ---- B 공정 비교: 봉당 변동성 ----
    pv = per_bar_volatility()
    md.append("## B. 세션 내 변동성 (봉당 |30분 수익률| — 길이 중립)\n")
    md.append("| 세션 | 중앙값 | 평균 | p90 | p99 | 표본(봉) |")
    md.append("|---|---|---|---|---|---|")
    for s in SLABEL:
        r = pv.loc[s]
        md.append(f"| {SLABEL[s]} | {fmt_pct(r['median'])} | {fmt_pct(r['mean'])} | "
                  f"{fmt_pct(r['p90'])} | {fmt_pct(r['p99'])} | {int(r['bars']):,} |")
    reg_med = pv.loc["regular", "median"]
    md.append(f"\n→ 정규 대비 배수(중앙값): 프리 {pv.loc['pre','median']/reg_med:.2f}× · "
              f"애프터 {pv.loc['after','median']/reg_med:.2f}× "
              f"(p99: 프리 {pv.loc['pre','p99']/pv.loc['regular','p99']:.2f}× · "
              f"애프터 {pv.loc['after','p99']/pv.loc['regular','p99']:.2f}×)\n")

    # ---- A 세션 간 갭 ----
    md.append("## A. 세션 간 갭 (|수익률|)\n")
    md.append("| 전환 | 중앙값 | p90 | p99 |")
    md.append("|---|---|---|---|")
    for col, name in [("gap_overnight_pre", "전일정규종→프리시"),
                      ("gap_pre_reg", "프리종→정규시"),
                      ("gap_reg_aft", "정규종→애프터시"),
                      ("gap_aft_nextreg", "애프터종→익일정규시")]:
        a = panel[col].abs().dropna()
        md.append(f"| {name} | {fmt_pct(a.median())} | "
                  f"{fmt_pct(a.quantile(.9))} | {fmt_pct(a.quantile(.99))} |")
    md.append("")

    # ---- C 되돌림 (큰 드리프트만) ----
    md.append("## C. 연장세션 드리프트의 정규장 되돌림 (revert_frac; 1=완전 되돌림)\n")
    md.append("| 대상 | 조건 | 표본 | 되돌림 중앙값 | >0.5 되돌림 비율 |")
    md.append("|---|---|---|---|---|")
    for drift, frac, name in [("aft_drift", "aft_revert_frac", "애프터"),
                              ("pre_drift", "pre_revert_frac", "프리")]:
        for thr in [0.0, 0.01]:
            m = panel[drift].abs() > thr
            sub = panel.loc[m, frac].replace([np.inf, -np.inf], np.nan).dropna()
            cond = "전체" if thr == 0 else f"|드리프트|>{thr:.0%}"
            rev_share = (sub > 0.5).mean() if len(sub) else np.nan
            md.append(f"| {name} | {cond} | {len(sub):,} | "
                      f"{sub.median():.3f} | {fmt_pct(rev_share)} |")
    md.append("")

    # ---- D 유동성 층화 ----
    liq = liquidity_terciles(panel)
    p = panel.join(liq, on="code")
    md.append("## D. 유동성 3분위 × 세션 — Amihud 비유동성(클수록 거래량 대비 과민)\n")
    md.append("| 유동성 | 프리 | 정규 | 애프터 | 프리/정규 | 애프터/정규 |")
    md.append("|---|---|---|---|---|---|")
    for lv in ["high", "mid", "low"]:
        sub = p[p["liq"] == lv]
        a = {s: sub[f"{SPREF[s]}_amihud"].median() for s in SLABEL}
        md.append(f"| {lv} | {fmt_sci(a['pre'])} | {fmt_sci(a['regular'])} | "
                  f"{fmt_sci(a['after'])} | {a['pre']/a['regular']:.2f}× | "
                  f"{a['after']/a['regular']:.2f}× |")
    md.append("\n그리고 range%(세션 내 폭)도 유동성별로:\n")
    md.append("| 유동성 | 프리 range% | 정규 range% | 애프터 range% |")
    md.append("|---|---|---|---|")
    for lv in ["high", "mid", "low"]:
        sub = p[p["liq"] == lv]
        md.append(f"| {lv} | {fmt_pct(sub['pre_range_pct'].median())} | "
                  f"{fmt_pct(sub['reg_range_pct'].median())} | "
                  f"{fmt_pct(sub['aft_range_pct'].median())} |")

    md += flash_section()

    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    pv.to_csv(ROOT / "data" / "analysis_perbar_vol.csv", encoding="utf-8-sig")
    print(f"written -> {OUT_MD}")
    # ASCII-safe console echo (PowerShell 한글 깨짐 방지)
    print(f"per-bar |ret| median  pre={pv.loc['pre','median']:.4%} "
          f"reg={pv.loc['regular','median']:.4%} aft={pv.loc['after','median']:.4%}")


if __name__ == "__main__":
    main()
