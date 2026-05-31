"""넥스트레이드(.KNT) 30분봉 OHLC 수집 + 프리/정규/애프터 세션 취합.

사용 예:
    import lseg.data as ld
    ld.open_session()
    df  = get_nxt_30min("005930", "2026-05-29", "2026-05-30")
    agg = aggregate_sessions(df)
    ld.close_session()
"""
import lseg.data as ld
import pandas as pd

OHLC_FIELDS = ["OPEN_PRC", "HIGH_1", "LOW_1", "TRDPRC_1", "ACVOL_UNS"]

# 넥스트레이드 세션 경계 (KST). NXT 공식 운영시간 기준으로 필요시 조정:
#   프리마켓 08:00~08:50 / 메인 09:00~15:30 / 애프터마켓 15:30~20:00
PRE_END = pd.Timestamp("09:00").time()
REG_END = pd.Timestamp("15:30").time()


def _session(ts):
    t = ts.time()
    if t < PRE_END:
        return "pre"
    if t < REG_END:
        return "regular"
    return "after"


def get_nxt_30min(code6: str, start: str, end: str) -> pd.DataFrame:
    """code6: '005930' 같은 6자리 코드. start/end: 'YYYY-MM-DD' 또는 ISO 문자열.

    반환: KST 인덱스 + OHLCV + 'session' 컬럼. 데이터 없으면 빈 DataFrame.
    """
    ric = f"{code6}.KNT"
    df = ld.get_history(
        universe=ric, fields=OHLC_FIELDS, interval="30min",
        start=start, end=end,
    )
    if df is None or df.empty:
        return pd.DataFrame()
    # lseg.data는 naive UTC로 반환 → KST 변환
    df.index = pd.to_datetime(df.index).tz_localize("UTC").tz_convert("Asia/Seoul")
    df = df.sort_index()
    df["session"] = [_session(ts) for ts in df.index]
    return df


def aggregate_sessions(df: pd.DataFrame) -> pd.DataFrame:
    """일자×세션별 open/high/low/close/volume 취합.

    open  = 세션 첫 봉의 OPEN_PRC
    high  = 세션 HIGH_1 의 max
    low   = 세션 LOW_1 의 min
    close = 세션 마지막 봉의 TRDPRC_1
    """
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["date"] = df.index.date
    g = df.groupby(["date", "session"])
    return pd.DataFrame({
        "open":   g["OPEN_PRC"].first(),
        "high":   g["HIGH_1"].max(),
        "low":    g["LOW_1"].min(),
        "close":  g["TRDPRC_1"].last(),
        "volume": g["ACVOL_UNS"].sum(),
        "bars":   g.size(),
    })


if __name__ == "__main__":
    ld.open_session()
    try:
        df = get_nxt_30min("005930", "2026-05-29", "2026-05-30")
        print("== 30분봉 ==")
        print(df[OHLC_FIELDS + ["session"]])
        print("\n== 세션 취합 ==")
        print(aggregate_sessions(df))
    finally:
        ld.close_session()
