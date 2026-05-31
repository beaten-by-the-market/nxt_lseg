"""넥스트레이드(.KNT) 종목 리스트 수집.

Advanced Search(Exchange = NEXTRADE)를 ld.discovery.search 로 재현한다.

검증 결과 (2026-05-31):
  - 넥스트레이드 ExchangeCode = 'KNT'  (ExchangeName = 'NEXTRADE')
  - ★ .KNT RIC은 IsPrimaryRIC = False  (대표 RIC은 KRX .KS) →
    'IsPrimaryRIC eq true' 필터를 쓰면 0건이 나오므로 절대 쓰지 말 것.
  - 파생 RIC(예: 005930F.KNT) 제거는 IsPrimaryRIC 대신 RIC 패턴(6자리+.KNT)으로 한다.

사용 예:
    import lseg.data as ld
    ld.open_session()
    df = get_nxt_universe(ordinary_only=True)
    df.to_csv("nxt_universe.csv", index=False, encoding="utf-8-sig")
    ld.close_session()
"""
import re
import lseg.data as ld
import pandas as pd

NXT_EXCHANGE_CODE = "KNT"   # 검증 완료
SELECT = "RIC,DTSubjectName,ExchangeCode,ExchangeName,RCSTRBC2012Leaf,RCSAssetCategoryLeaf,AssetState"

# 6자리 숫자 코드 + .KNT (파생/대량매매 RIC 제외용)
_CLEAN_RIC = re.compile(r"^\d{6}\.KNT$")


def get_nxt_universe(ordinary_only: bool = True,
                     active_only: bool = True,
                     clean_ric_only: bool = True) -> pd.DataFrame:
    """넥스트레이드 종목 리스트를 DataFrame으로 반환.

    ordinary_only  : 보통주(Ordinary Share)만 (False면 우선주/ETF 등 모두 포함)
    active_only    : 현재 상장(AssetState='AC')만
    clean_ric_only : '005930.KNT'처럼 6자리+.KNT 형태만 (파생 RIC 제거)

    주의: IsPrimaryRIC 필터는 쓰지 않는다(.KNT는 모두 False).
    """
    conds = [f"ExchangeCode eq '{NXT_EXCHANGE_CODE}'"]
    if ordinary_only:
        conds.append("RCSAssetCategoryLeaf eq 'Ordinary Share'")
    if active_only:
        conds.append("AssetState eq 'AC'")
    flt = " and ".join(conds)

    df = ld.discovery.search(query="", filter=flt, top=10000, select=SELECT)
    if df is None or df.empty:
        return pd.DataFrame()

    if clean_ric_only:
        df = df[df["RIC"].str.match(_CLEAN_RIC)].reset_index(drop=True)
    return df


if __name__ == "__main__":
    ld.open_session()
    try:
        # 스크린샷의 'All'(약 1,006종목)에 대응:
        all_df = get_nxt_universe(ordinary_only=False, clean_ric_only=False)
        print(f"NEXTRADE 전체(All): {len(all_df)}")

        # 분석용 정제 리스트(보통주 + 현재상장 + 깨끗한 RIC):
        eq = get_nxt_universe(ordinary_only=True, active_only=True, clean_ric_only=True)
        print(f"보통주/상장/정제: {len(eq)}")
        print(eq.head(15).to_string())
        eq.to_csv("nxt_universe.csv", index=False, encoding="utf-8-sig")
        print("saved -> nxt_universe.csv")
    finally:
        ld.close_session()
