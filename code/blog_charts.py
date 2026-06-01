"""블로그용 차트 생성 (한글 라벨, 스틸블루 톤) → blog/images/.

- 임계별 flash 건수(상승/하락 그룹막대), 시총 5분위 flash 비율 막대
- 개별 케이스 차트: NXT 30분봉 일중(고-저 band + 종가) + KRX 당일 정규장 범위 오버레이 + 플래시 봉 강조
실행: python code/blog_charts.py   (LSEG 불필요 — data/raw, data/krx_cases.parquet 사용)
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates          # noqa: E402
import matplotlib.pyplot as plt            # noqa: E402
from matplotlib import rcParams            # noqa: E402
import pandas as pd                        # noqa: E402

# 스킬의 차트 헬퍼(Malgun Gothic·스틸블루) 재사용
sys.path.insert(0, r"C:\Users\Peter\.claude\skills\market-blog-post\scripts")
from make_chart import bar_chart, grouped_bar, STEELBLUE, set_style  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
KRX = ROOT / "data" / "krx_cases.parquet"
IMG = ROOT / "blog" / "images"

# 헤드라인 케이스: (코드, 날짜, 한글명, 파일명)
CASES = [
    ("042700", "2025-07-14", "한미반도체", "case_hanmi.png"),
    ("005380", "2025-06-16", "현대차", "case_hyundai.png"),
    ("067310", "2025-10-13", "하나마이크론", "case_hanamicron.png"),
]


def case_chart(code, date, kname, fname, krx):
    df = pd.read_parquet(RAW / f"{code}.parquet")
    for c in ("OPEN_PRC", "HIGH_1", "LOW_1", "TRDPRC_1"):
        df[c] = df[c].astype("float64")
    day = df[df.index.date == pd.Timestamp(date).date()].sort_index()
    pre = day[day["session"] == "pre"]
    # 프리장 플래시 봉(고/저가 몸통 밖 최대 이탈)
    o, c = pre["OPEN_PRC"], pre["TRDPRC_1"]
    up = (pre["HIGH_1"] - pd.concat([o, c], axis=1).max(axis=1)) / o
    dn = (pd.concat([o, c], axis=1).min(axis=1) - pre["LOW_1"]) / o
    if up.max() >= dn.max():
        ts, spike, ext, dir_ko = up.idxmax(), up.max(), pre.loc[up.idxmax(), "HIGH_1"], "급등"
    else:
        ts, spike, ext, dir_ko = dn.idxmax(), dn.max(), pre.loc[dn.idxmax(), "LOW_1"], "급락"

    set_style()
    fig, ax = plt.subplots(figsize=(9.5, 5))
    x = day.index
    s = day["session"].values
    ax.axvspan(x.min(), x[s == "regular"][0], color="#fff3cd", alpha=.5, lw=0)   # 프리
    ax.axvspan(x[s == "after"][0], x.max(), color="#f0f0f0", alpha=.8, lw=0)     # 애프터
    ax.fill_between(x, day["LOW_1"], day["HIGH_1"], color="#c6d9f1", alpha=.7,
                    step="mid", label="NXT 30분봉 고-저")
    ax.plot(x, day["TRDPRC_1"], color="#2f5d8a", lw=1.6, label="NXT 종가")

    k = krx[(krx["code"] == code) & (krx["date"] == date)].sort_values("ts_kst")
    if not k.empty:
        klo, khi = k["LOW_1"].min(), k["HIGH_1"].max()
        ax.axhspan(klo, khi, color="#cdeccd", alpha=.5, lw=0,
                   label=f"KRX 정규장 범위 ({klo:,.0f}~{khi:,.0f})")
        ax.plot(pd.to_datetime(k["ts_kst"]), k["TRDPRC_1"], color="#d97706",
                lw=1.7, label="KRX 종가(정규장)")

    ax.scatter([ts], [ext], color="#c0392b", zorder=6, s=90)
    ax.annotate(f"프리장 {dir_ko} {spike:.0%}\n→ {ext:,.0f}원", (ts, ext),
                textcoords="offset points", xytext=(10, 0), color="#c0392b",
                fontsize=11, fontweight="bold", va="center")
    ax.axhline(ext, color="#c0392b", ls="--", lw=.9, alpha=.6)

    ax.set_title(f"{kname}, 넥스트레이드 프리장 30분봉에서 {dir_ko} {spike:.0%} 후 복원 ({date})")
    ax.set_ylabel("가격 (원)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=x.tz))
    ax.legend(fontsize=9, loc="best", framealpha=.92)
    ax.grid(alpha=.25)
    fig.autofmt_xdate()
    plt.tight_layout()
    out = IMG / fname
    plt.savefig(out, dpi=150)
    plt.close()
    return out


def main():
    IMG.mkdir(parents=True, exist_ok=True)
    rcParams["font.family"] = "Malgun Gothic"
    rcParams["axes.unicode_minus"] = False

    # 1) 임계별 flash 건수 (상승/하락)
    grouped_bar(["±5%", "±10%", "±15%", "±20%"],
                {"상승": [1864, 260, 84, 34], "하락": [731, 141, 85, 61]},
                title="넥스트레이드 프리·애프터 intra-bar 플래시 건수 (1년)",
                ylabel="건수", out=str(IMG / "flash_by_threshold.png"))

    # 2) 시총 5분위별 프리장 10%+ 플래시 종목 비율
    bar_chart(["소형(Q1)", "Q2", "Q3", "Q4", "대형(Q5)"], [16, 27, 27, 33, 30],
              title="시총 분위별 프리장 10%+ 플래시 경험 종목 비율",
              ylabel="비율 (%)", out=str(IMG / "flash_by_mktcap.png"))

    # 3) 개별 케이스
    krx = pd.read_parquet(KRX)
    krx["code"] = krx["code"].astype(str)
    krx["date"] = krx["date"].astype(str)
    for code, date, kname, fname in CASES:
        case_chart(code, date, kname, fname, krx)

    print("saved charts ->", IMG)
    for p in sorted(IMG.glob("*.png")):
        print("  ", p.name)


if __name__ == "__main__":
    main()
