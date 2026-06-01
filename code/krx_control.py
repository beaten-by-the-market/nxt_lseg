"""[3단계-대조군] 선별 케이스의 KRX(.KS/.KQ) 정규장 데이터 타깃 수집.

프리/애프터 플래시가 'NXT 연장세션만의 유동성 artifact'임을 보강한다:
같은 날 KRX 정규장(09:00~15:30)에서는 그 극단가에 닿지 않았음을 보인다.
(KRX엔 프리/애프터가 없어 같은 시각 비교는 불가 → 정규장 범위로 대조)

재개(resume): 기존 data/krx_cases.parquet에 있는 (code,date)는 다시 받지 않고 신규만 수집·append.
→ --top을 늘려가며 여러 번 돌려도 추가분만 호출(--refetch로 강제 전체 재수집).

입력 : data/jump_cases.csv (상위 케이스)
출력 : data/krx_cases.parquet (KRX 30분봉, 누적·차트 오버레이용)
       data/krx_corroboration.csv (케이스별 NXT극단가 vs KRX범위, outside_krx 플래그)
실행 : python code/krx_control.py [--top 400] [--refetch]
       (LSEG Workspace 실행 필요)
"""
import argparse
import sys
import time
from pathlib import Path

import lseg.data as ld
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nxt_price_history import OHLC_FIELDS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "data" / "jump_cases.csv"
OUT = ROOT / "data" / "krx_cases.parquet"

_suffix_cache = {}


def krx_ric(code6: str, probe_start: str, probe_end: str) -> str | None:
    """.KS(KOSPI) 먼저, 없으면 .KQ(KOSDAQ). 둘 다 없으면 None."""
    if code6 in _suffix_cache:
        return _suffix_cache[code6]
    for suf in (".KS", ".KQ"):
        try:
            df = ld.get_history(universe=code6 + suf, fields=["TRDPRC_1"],
                                interval="30min", start=probe_start, end=probe_end)
            time.sleep(0.3)
            if df is not None and not df.empty:
                _suffix_cache[code6] = code6 + suf
                return code6 + suf
        except Exception:                                # noqa: BLE001
            pass
    _suffix_cache[code6] = None
    return None


def fetch_krx_day(ric: str, date: str) -> pd.DataFrame:
    end = (pd.Timestamp(date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    df = ld.get_history(universe=ric, fields=OHLC_FIELDS, interval="30min",
                        start=date, end=end)
    time.sleep(0.3)
    if df is None or df.empty:
        return pd.DataFrame()
    df.index = pd.to_datetime(df.index).tz_localize("UTC").tz_convert("Asia/Seoul")
    df = df[df.index.date == pd.Timestamp(date).date()].sort_index()
    for col in OHLC_FIELDS:                       # 빈 구간 NA 봉 제거(float 변환 안전)
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["OPEN_PRC", "HIGH_1", "LOW_1", "TRDPRC_1"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--refetch", action="store_true", help="캐시 무시하고 전부 재수집")
    args = ap.parse_args()

    cases = pd.read_csv(CASES, dtype={"code": str}).head(args.top)
    cases["date"] = cases["date"].astype(str)

    # 재개(resume): 기존 krx_cases.parquet에 있는 (code,date)는 다시 받지 않는다
    kcols = ["code", "date", "ric", "ts_kst",
             "OPEN_PRC", "HIGH_1", "LOW_1", "TRDPRC_1", "ACVOL_UNS"]
    existing = pd.read_parquet(OUT) if OUT.exists() else pd.DataFrame(columns=kcols)
    if not existing.empty:
        existing["code"] = existing["code"].astype(str)
        existing["date"] = existing["date"].astype(str)
    done = set() if args.refetch else set(
        map(tuple, existing[["code", "date"]].drop_duplicates().to_numpy()))

    req = list(dict.fromkeys(zip(cases["code"], cases["date"])))   # 순서유지 unique
    todo = [k for k in req if k not in done]
    print(f"요청 {len(req)} (code,date) | 캐시재사용 {len(req) - len(todo)} | 신규수집 {len(todo)}")

    new_rows = []
    ld.open_session()
    try:
        for i, (code, date) in enumerate(todo, 1):
            try:
                ric = krx_ric(code, date,
                              (pd.Timestamp(date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
                if not ric:
                    print(f"[{i}/{len(todo)}] {code} {date} KRX NOT FOUND")
                    continue
                k = fetch_krx_day(ric, date)
            except Exception as e:                       # noqa: BLE001
                msg = repr(e)
                print(f"[{i}/{len(todo)}] {code} {date} FAIL {msg[:80]}")
                if "429" in msg or "too many" in msg.lower():
                    print(">>> 한도 추정 — 안전 중단(여기까지 저장).")
                    break
                continue
            if k.empty:
                print(f"[{i}/{len(todo)}] {code} {date} empty")
                continue
            for ts, r in k.iterrows():
                new_rows.append({"code": code, "date": date, "ric": ric, "ts_kst": ts,
                                 "OPEN_PRC": float(r["OPEN_PRC"]), "HIGH_1": float(r["HIGH_1"]),
                                 "LOW_1": float(r["LOW_1"]), "TRDPRC_1": float(r["TRDPRC_1"]),
                                 "ACVOL_UNS": float(r["ACVOL_UNS"])})
            if i % 25 == 0:
                print(f"[{i}/{len(todo)}] ... 신규 {len(new_rows)}행")
    finally:
        ld.close_session()

    # 누적 저장 (기존 ∪ 신규) — 다음 실행에서 그대로 재사용
    parts = [d for d in (existing, pd.DataFrame(new_rows, columns=kcols)) if not d.empty]
    combined = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=kcols)
    if not combined.empty:
        combined = combined.sort_values("ts_kst").drop_duplicates(["code", "date", "ts_kst"])
        combined.to_parquet(OUT)
    ncase = combined[["code", "date"]].drop_duplicates().shape[0]
    print(f"\n신규 {len(new_rows)}행 추가 | 누적 {len(combined)}행 ({ncase} 케이스일) -> {OUT.name}")

    # 보강 리포트 (요청 상위 케이스 기준): NXT 극단가 vs KRX 당일 정규장 범위
    rng = (combined.groupby(["code", "date"])
           .agg(krx_open=("OPEN_PRC", "first"), krx_low=("LOW_1", "min"),
                krx_high=("HIGH_1", "max")).reset_index())
    m = cases.copy()
    m["nxt_extreme"] = np.where(m["direction"] == "down", m["low"], m["high"])
    m = m.merge(rng, on=["code", "date"], how="left")
    m["outside_krx"] = (m["nxt_extreme"] < m["krx_low"]) | (m["nxt_extreme"] > m["krx_high"])
    cols = ["name", "code", "date", "session", "direction", "spike",
            "nxt_extreme", "krx_open", "krx_low", "krx_high", "outside_krx"]
    corr = ROOT / "data" / "krx_corroboration.csv"
    m[cols].to_csv(corr, index=False, encoding="utf-8-sig")
    have = m["krx_low"].notna()
    n = m.loc[have, "outside_krx"].eq(True).sum()
    print(f"saved -> {corr.name}")
    print(f"NXT 극단가가 KRX 당일 정규장 범위 '밖': {int(n)} / {int(have.sum())} "
          f"({n / max(int(have.sum()), 1):.0%})")
    print("\n== 상위 15 ==")
    print(m[cols].head(15).to_string(index=False))


if __name__ == "__main__":
    main()
