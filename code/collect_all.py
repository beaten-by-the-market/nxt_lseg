"""넥스트레이드(.KNT) 전체 종목 30분봉 일괄 수집기 (재개 가능).

왜 지금 받나: 30분봉은 롤링 ~12개월만 보존(가용 시작 ≈ KST 2025-06-02). floor가
매일 전진하므로 빨리 받을수록 과거 확보가 늘어난다. → 2_NXT_PRICE_HISTORY.md §2.2.

설계:
  - 가용 전체(~12개월)는 1회 한도(≈5,778봉)에 거의 꽉 차므로 6개월/회로 분할.
  - 절단 가드: 반환 봉이 한도 근처(>=5,700)면 윈도우를 반으로 쪼개 재귀 호출.
  - 종목당 결과를 data/raw/{code}.parquet 로 저장 → 이미 있으면 건너뜀(재개).
  - 스로틀(요청 간 sleep)·429(일일 한도) 시 안전 중단 후 다음 실행에서 재개.

실행 (LSEG Workspace 데스크톱 앱 실행 필요):
    python code/collect_all.py            # 전체
    python code/collect_all.py --limit 3  # 앞 3종목만 (스모크 테스트)
    python code/collect_all.py --codes 005930 000660
"""
import argparse
import json
import sys
import time
from pathlib import Path

import lseg.data as ld
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nxt_universe import get_nxt_universe          # noqa: E402
from nxt_price_history import OHLC_FIELDS, _session  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
UNIV_CSV = ROOT / "data" / "nxt_universe.csv"
PROGRESS = ROOT / "data" / "collect_progress.json"

# 가용 구간(KST 2025-06-02 ~). 6개월 청크 2개. 경계 1일 겹침 → 인덱스로 dedup.
CHUNKS = [("2025-06-01", "2025-12-02"), ("2025-12-01", "2026-05-30")]
BAR_CAP = 5700          # 이 이상이면 절단 의심 → 윈도우 분할
THROTTLE_SEC = 0.4      # 요청 간 대기 (5req/s 한도 + 데이터량 한도 여유)


def fetch_chunk(ric: str, start: str, end: str, depth: int = 0) -> pd.DataFrame:
    """단일 윈도우 30분봉. 한도 근처면 반으로 쪼개 재귀(절단 방지)."""
    df = ld.get_history(universe=ric, fields=OHLC_FIELDS, interval="30min",
                        start=start, end=end)
    time.sleep(THROTTLE_SEC)
    if df is None or df.empty:
        return pd.DataFrame()
    if len(df) >= BAR_CAP and depth < 4:
        mid = (pd.Timestamp(start) + (pd.Timestamp(end) - pd.Timestamp(start)) / 2)
        mid = mid.strftime("%Y-%m-%d")
        if mid != start and mid != end:
            left = fetch_chunk(ric, start, mid, depth + 1)
            right = fetch_chunk(ric, mid, end, depth + 1)
            return pd.concat([left, right])
    return df


def fetch_ric(code6: str) -> pd.DataFrame:
    """종목 전체 가용 구간 → KST 인덱스 OHLCV + session. dedup."""
    ric = f"{code6}.KNT"
    parts = [fetch_chunk(ric, s, e) for s, e in CHUNKS]
    parts = [p for p in parts if not p.empty]
    if not parts:
        return pd.DataFrame()
    df = pd.concat(parts)
    df.index = pd.to_datetime(df.index)
    df = df[~df.index.duplicated(keep="first")].sort_index()
    df.index = df.index.tz_localize("UTC").tz_convert("Asia/Seoul")
    df.index.name = "ts_kst"
    df["session"] = [_session(ts) for ts in df.index]
    return df


def load_universe() -> list[str]:
    if UNIV_CSV.exists():
        codes = pd.read_csv(UNIV_CSV, dtype=str)["code6"].tolist()
        print(f"universe (cached): {len(codes)}")
        return codes
    # active + 깨끗한 6자리 RIC (보통주 외 우선주/ETF 포함 — 캡처 시점 최대 확보)
    df = get_nxt_universe(ordinary_only=False, active_only=True, clean_ric_only=True)
    df["code6"] = df["RIC"].str.slice(0, 6)
    UNIV_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(UNIV_CSV, index=False, encoding="utf-8-sig")
    print(f"universe fetched & saved: {len(df)} -> {UNIV_CSV}")
    return df["code6"].tolist()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="앞 N종목만(테스트)")
    ap.add_argument("--codes", nargs="*", help="특정 6자리 코드만")
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ld.open_session()
    try:
        codes = args.codes or load_universe()
        if args.limit:
            codes = codes[:args.limit]

        done, empty, failed = [], [], []
        t0 = time.time()
        for i, code in enumerate(codes, 1):
            out = RAW_DIR / f"{code}.parquet"
            if out.exists():
                continue
            try:
                df = fetch_ric(code)
            except Exception as e:                       # noqa: BLE001
                msg = repr(e)
                failed.append({"code": code, "error": msg})
                print(f"[{i}/{len(codes)}] {code} FAIL {msg}")
                if "429" in msg or "Too Many" in msg.lower():
                    print(">>> 일일 한도 추정. 안전 중단 — 다음 실행에서 재개됨.")
                    break
                continue
            if df.empty:
                empty.append(code)
                print(f"[{i}/{len(codes)}] {code} empty")
                continue
            df.to_parquet(out)
            done.append(code)
            if i % 25 == 0 or i == len(codes):
                rate = i / max(time.time() - t0, 1e-9)
                print(f"[{i}/{len(codes)}] {code} {len(df)}봉 saved "
                      f"| {rate:.1f} stk/s")

        PROGRESS.write_text(json.dumps(
            {"done": len(done), "empty": empty, "failed": failed,
             "total_files": len(list(RAW_DIR.glob('*.parquet')))},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n== 완료 ==  saved={len(done)} empty={len(empty)} "
              f"failed={len(failed)} | total files={len(list(RAW_DIR.glob('*.parquet')))}")
    finally:
        ld.close_session()


if __name__ == "__main__":
    main()
