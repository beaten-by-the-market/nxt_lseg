"""[3단계-케이스] 프리/애프터 '튀고 즉시 복원' 사례 발굴 + 시각화 (intra-bar 방식).

정규장 기준선을 쓰지 않는다(방향성 급락/급등·기업행위·수능 순연에 오염되던 옛 방식 폐기).
대신 **봉 자체의 모양**으로 '튀었다 제자리'를 잡는다:

  (1) intra-bar 꼬리(round-trip): 한 30분봉 안에서 고가/저가가 몸통(|시-종|) 밖으로
      크게 벗어났다 = 그 30분 안에 급변했다가 되돌아옴.
        up_wick   = (HIGH - max(시,종)) / 시
        down_wick = (min(시,종) - LOW) / 시
        spike     = max(up_wick, down_wick)            ← 되돌아온 폭(몸통 제외)
  (2) 인접봉 V자: 봉 N 종가가 양옆 봉(N-1,N+1)에서 크게 벗어났고 양옆은 서로 비슷
      = 30분 경계를 걸친 플래시(튀고 다음 봉에 복귀).

두 점수의 max로 랭킹. 외부 기준선·세션경계에 의존하지 않아 견고하다.

출력: data/jump_cases.csv, data/figs/case_*.png
실행: python code/case_finder.py [--min-exc 0.05] [--top 40] [--plot 12] [--sessions pre after]
"""
import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402
import pandas as pd                      # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
FIG_DIR = ROOT / "data" / "figs"
UNIV = ROOT / "data" / "nxt_universe.csv"
OUT_CSV = ROOT / "data" / "jump_cases.csv"


def _names() -> dict:
    if not UNIV.exists():
        return {}
    d = pd.read_csv(UNIV, dtype=str)
    return dict(zip(d["code6"], d["DTSubjectName"]))


def _liquidity_pct() -> pd.Series:
    p = ROOT / "data" / "panel_sessions.parquet"
    if not p.exists():
        return pd.Series(dtype=float)
    liq = pd.read_parquet(p, columns=["code", "reg_turnover"]) \
        .groupby("code")["reg_turnover"].median()
    return liq.rank(pct=True)


def scan_file(path: Path, sessions) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    for col in ("OPEN_PRC", "HIGH_1", "LOW_1", "TRDPRC_1", "ACVOL_UNS"):
        df[col] = df[col].astype("float64")
    df["date"] = df.index.date
    o, h, l, c = df["OPEN_PRC"], df["HIGH_1"], df["LOW_1"], df["TRDPRC_1"]
    base = o.where(o > 0)
    body_hi = np.maximum(o, c)
    body_lo = np.minimum(o, c)
    df["up_wick"] = (h - body_hi) / base
    df["down_wick"] = (body_lo - l) / base
    df["intrabar"] = df[["up_wick", "down_wick"]].max(axis=1)
    df["ib_dir"] = np.where(df["up_wick"] >= df["down_wick"], "up", "down")

    # 인접봉 V자: 세션 안에서만 (그룹 경계 넘지 않게)
    grp = df.groupby(["date", "session"])
    prevc = grp["TRDPRC_1"].shift(1)
    nextc = grp["TRDPRC_1"].shift(-1)
    neigh = (prevc + nextc) / 2
    dev = ((c - neigh).abs() / base).to_numpy(dtype="float64", na_value=np.nan)
    disagree = ((prevc - nextc).abs() / base).to_numpy(dtype="float64", na_value=np.nan)
    df["vscore"] = np.where((dev > 0) & (disagree < dev), dev, 0.0)
    df["v_dir"] = np.where(c.to_numpy() >= neigh.to_numpy(), "up", "down")

    # 봉별 최종 점수 = max(intrabar, vscore)
    df["spike"] = df[["intrabar", "vscore"]].max(axis=1)
    df["kind"] = np.where(df["intrabar"] >= df["vscore"], "intrabar", "vshape")
    df["direction"] = np.where(df["kind"] == "intrabar", df["ib_dir"], df["v_dir"])

    reg_vol = df[df["session"] == "regular"].groupby("date")["ACVOL_UNS"].sum()

    rows = []
    sub = df[df["session"].isin(sessions)]
    for (date, sess), g in sub.groupby(["date", "session"]):
        g = g.dropna(subset=["spike"])
        if g.empty:
            continue
        ts = g["spike"].idxmax()
        b = g.loc[ts]
        rows.append({
            "code": path.stem, "date": str(date), "session": sess,
            "kind": b["kind"], "direction": b["direction"],
            "spike": float(b["spike"]),
            "bar_time": ts.strftime("%H:%M"),
            "open": float(b["OPEN_PRC"]), "high": float(b["HIGH_1"]),
            "low": float(b["LOW_1"]), "close": float(b["TRDPRC_1"]),
            "bar_vol": int(b["ACVOL_UNS"]),
            "bar_vol_vs_reg": float(b["ACVOL_UNS"] / max(reg_vol.get(date, 1), 1)),
        })
    return pd.DataFrame(rows)


def plot_case(row, names, fig_dir: Path):
    df = pd.read_parquet(RAW_DIR / f"{row['code']}.parquet")
    day = df[df.index.date == pd.Timestamp(row["date"]).date()].sort_index()
    if day.empty:
        return None
    x = day.index
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.fill_between(x, day["LOW_1"], day["HIGH_1"], color="#bcd", alpha=.55,
                    step="mid", label="high-low")
    ax.plot(x, day["TRDPRC_1"], color="#234", lw=1.3, label="close")
    # 세션 경계(라벨 바뀌는 지점) — 특수일도 자동 반영
    chg = day.index[day["session"].values != day["session"].shift().values][1:]
    for t in chg:
        ax.axvline(t, color="0.6", ls=":", lw=1)
    # 튐 봉 표시
    ext_ts = day.index[day.index.strftime("%H:%M") == row["bar_time"]]
    if len(ext_ts):
        yext = row["low"] if row["direction"] == "down" else row["high"]
        ax.scatter(ext_ts[0], yext, color="red", zorder=5, s=80)
        ax.annotate(f"{row['session']} {row['kind']} {row['direction']} {row['spike']:.1%}",
                    (ext_ts[0], yext), textcoords="offset points", xytext=(6, 6),
                    color="red", fontsize=9)
    nm = names.get(row["code"], row["code"])
    ax.set_title(f"{nm} ({row['code']}.KNT)  {row['date']}  "
                 f"O{row['open']:,.0f} H{row['high']:,.0f} "
                 f"L{row['low']:,.0f} C{row['close']:,.0f}", fontsize=11)
    ax.set_ylabel("price (KRW)")
    ax.legend(fontsize=8, loc="best")
    ax.grid(alpha=.3)
    fig.autofmt_xdate()
    fig_dir.mkdir(parents=True, exist_ok=True)
    out = fig_dir / (f"case_{row['spike']*1000:04.0f}_{row['code']}_"
                     f"{row['date']}_{row['session']}.png")
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--plot", type=int, default=12)
    ap.add_argument("--min-exc", type=float, default=0.05, help="최소 스파이크(0.05=5%)")
    ap.add_argument("--sessions", nargs="*", default=["pre", "after"],
                    help="대상 세션 (기본: pre after)")
    args = ap.parse_args()

    names, liqpct = _names(), _liquidity_pct()
    allc = [scan_file(f, args.sessions) for f in sorted(RAW_DIR.glob("*.parquet"))]
    cases = pd.concat([c for c in allc if not c.empty], ignore_index=True)
    cases = cases[cases["spike"] >= args.min_exc].copy()
    cases.insert(1, "name", cases["code"].map(names).fillna(cases["code"]))
    cases["liq_pct"] = cases["code"].map(liqpct)
    cases = cases.sort_values("spike", ascending=False).reset_index(drop=True)

    cases.head(args.top).to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"cases(spike>={args.min_exc:.0%}, {args.sessions}): {len(cases)} "
          f"| saved top {min(args.top,len(cases))} -> {OUT_CSV.name}\n")
    print("== 상위 15 '튀고 복원' (spike=몸통 밖 되돌아온 폭) ==")
    print(cases.head(15)[["name", "code", "date", "session", "kind", "direction",
                          "spike", "bar_vol_vs_reg", "liq_pct"]].to_string(index=False))

    n = sum(plot_case(r, names, FIG_DIR) is not None
            for _, r in cases.head(args.plot).iterrows())
    print(f"\nplotted {n} charts -> {FIG_DIR}")


if __name__ == "__main__":
    main()
