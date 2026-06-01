"""[3단계-시각화] 기사용 케이스 차트: NXT 일중봉 + 플래시 강조 + KRX 정규장 오버레이.

한 장에 보여주는 것:
  - NXT 30분봉 고-저 band + 종가선 (프리/애프터 구간 음영)
  - 플래시 봉 강조(빨간 점 + 라벨)
  - KRX 정규장 종가선(주황) + KRX 당일 고저 band(초록) → 극단가가 KRX 범위 밖임을 시각화
  - NXT 극단가 수평선

입력 : data/jump_cases.csv, data/krx_cases.parquet
출력 : data/figs/news_*.png
실행 : python code/plot_cases.py [--top 12]
(matplotlib 한글 글리프 문제로 텍스트는 영문/숫자만 사용)
"""
import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates        # noqa: E402
import matplotlib.pyplot as plt          # noqa: E402
import pandas as pd                      # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from case_finder import _names           # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
CASES = ROOT / "data" / "jump_cases.csv"
KRX = ROOT / "data" / "krx_cases.parquet"
FIG_DIR = ROOT / "data" / "figs"


def plot(row, krx, names):
    code, date = row["code"], str(row["date"])
    df = pd.read_parquet(RAW_DIR / f"{code}.parquet")
    for col in ("OPEN_PRC", "HIGH_1", "LOW_1", "TRDPRC_1"):
        df[col] = df[col].astype("float64")
    day = df[df.index.date == pd.Timestamp(date).date()].sort_index()
    if day.empty:
        return None
    x = day.index

    fig, ax = plt.subplots(figsize=(11.5, 5.5))
    # 프리/애프터 음영
    sess = day["session"].values
    if (sess == "pre").any():
        ax.axvspan(x.min(), x[sess == "regular"][0] if (sess == "regular").any() else x.max(),
                   color="#fff3cd", alpha=.5, lw=0)
    if (sess == "after").any():
        ax.axvspan(x[sess == "after"][0], x.max(), color="#eeeeee", alpha=.7, lw=0)

    # NXT
    ax.fill_between(x, day["LOW_1"], day["HIGH_1"], color="#9ec5e8", alpha=.6,
                    step="mid", label="NXT high-low")
    ax.plot(x, day["TRDPRC_1"], color="#16324f", lw=1.5, label="NXT close")

    # KRX 정규장 오버레이
    k = krx[(krx["code"] == code) & (krx["date"] == date)].sort_values("ts_kst")
    if not k.empty:
        kx = pd.to_datetime(k["ts_kst"])
        klo, khi = k["LOW_1"].min(), k["HIGH_1"].max()
        ax.axhspan(klo, khi, color="#cdeccd", alpha=.45, lw=0,
                   label=f"KRX day range [{klo:,.0f}, {khi:,.0f}]")
        ax.plot(kx, k["TRDPRC_1"], color="#d97706", lw=1.6, label="KRX close (regular)")

    # 플래시 봉 + 극단가선
    ext = row["low"] if row["direction"] == "down" else row["high"]
    ts = x[x.strftime("%H:%M") == row["bar_time"]]
    if len(ts):
        ax.scatter(ts[0], ext, color="red", zorder=6, s=90)
        ax.annotate(f"{row['session']} flash {row['direction']} {row['spike']:.0%}\n"
                    f"to {ext:,.0f}", (ts[0], ext), textcoords="offset points",
                    xytext=(8, -2), color="red", fontsize=9, fontweight="bold")
    ax.axhline(ext, color="red", ls="--", lw=.9, alpha=.7)

    nm = names.get(code, code)
    krx_note = " — outside KRX range" if not k.empty and (
        ext < k["LOW_1"].min() or ext > k["HIGH_1"].max()) else ""
    ax.set_title(f"{nm} ({code})  {date}  |  NXT {row['session']} {row['direction']} "
                 f"{row['spike']:.0%}{krx_note}", fontsize=11.5)
    ax.set_ylabel("price (KRW)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=x.tz))
    ax.legend(fontsize=8, loc="best", framealpha=.9)
    ax.grid(alpha=.25)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / f"news_{row['spike']*1000:04.0f}_{code}_{date}_{row['session']}.png"
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()
    names = _names()
    cases = pd.read_csv(CASES, dtype={"code": str}).head(args.top)
    krx = pd.read_parquet(KRX) if KRX.exists() else pd.DataFrame(
        columns=["code", "date", "ts_kst", "LOW_1", "HIGH_1", "TRDPRC_1"])
    krx["code"] = krx["code"].astype(str)
    n = sum(plot(r, krx, names) is not None for _, r in cases.iterrows())
    print(f"plotted {n} news charts -> {FIG_DIR} (news_*.png)")


if __name__ == "__main__":
    main()
