# [1단계] 넥스트레이드(`.KNT`) 종목 리스트(Universe) 확인

> 진행 순서: **[1] Universe(이 문서)** → [2] 30분봉 수집([2_NXT_PRICE_HISTORY.md](2_NXT_PRICE_HISTORY.md)) → [3] 분석([3_NXT_ANALYSIS.md](3_NXT_ANALYSIS.md)).
>
> 스크린샷의 **Advanced Search → Equities, Exchange = NEXTRADE (1,006 종목)** 화면을
> API로 재현하는 방법. 이 리스트가 모든 수집의 출발점이다.
>
> **상태: 라이브 검증 완료** (2026-05-31, `lseg.data 2.1.1`)

## 1. 어떤 API인가

LSEG Workspace의 **Advanced Search**(고급 검색) = `lseg.data`의 **`ld.discovery.search`**.
기존 `news_lseg` 프로젝트가 KOSPI/KOSDAQ universe를 모으던 것과 **완전히 동일한 함수**이며,
거래소 조건만 넥스트레이드로 바꾸면 된다.
→ [source_docs/API_FIELDS_REFERENCE.md](source_docs/API_FIELDS_REFERENCE.md) "Phase 0" 참고.

스크린샷 컬럼(Issuer / RIC / Exchange / TRBC Sector / Type of Equity)은 각각
`DTSubjectName` / `RIC` / `ExchangeName` / `RCSTRBC2012Leaf` / `RCSAssetCategoryLeaf` 에 대응한다.

## 2. 거래소 식별값 (검증 완료)

`005930.KNT`의 메타데이터를 조회한 실측 결과:

| 필드 | 값 |
|---|---|
| `ExchangeCode` | **`KNT`** |
| `ExchangeName` | `NEXTRADE` |
| `RCSExchangeCountry` | `G:AE` |
| `IsPrimaryRIC` | **`False`** ← 중요 (아래 참고) |

후보 코드 검증: `ExchangeCode eq 'KNT'` → 넥스트레이드 RIC 반환 ✅ /
`'NXT'` → 0건 / `'NEX'` → 캐나다 TSX-V(.V) / `'KNX'` → 별개(.KN). → **`KNT`가 정답.**

## 3. ⚠️ IsPrimaryRIC 함정 (가장 중요)

기존 KOSPI/KOSDAQ 수집은 `IsPrimaryRIC eq true`로 파생 RIC을 걸렀지만,
**넥스트레이드 RIC(`.KNT`)은 전부 `IsPrimaryRIC = False`** 다.
(한 종목의 대표 RIC은 거래량이 가장 많은 KRX `.KS`/`.KQ`이고, `.KNT`는 같은 자산의 보조 quote)

→ **`ExchangeCode eq 'KNT' and IsPrimaryRIC eq true` 를 쓰면 결과가 0건**이 된다.
   넥스트레이드 universe에는 **IsPrimaryRIC 필터를 절대 넣지 말 것.**

→ 파생 RIC(예: `005930F.KNT` 외국인용, `005930S.KNT` 공매도용 등) 제거는
   **RIC 패턴**(`^\d{6}\.KNT$`, 6자리 숫자 + `.KNT`)으로 후처리한다.

## 4. 권장 쿼리

```python
import lseg.data as ld
import re

ld.open_session()

# 보통주 + 현재상장. (IsPrimaryRIC 필터 없음!)
df = ld.discovery.search(
    query="",
    filter=("ExchangeCode eq 'KNT' "
            "and RCSAssetCategoryLeaf eq 'Ordinary Share' "
            "and AssetState eq 'AC'"),
    top=10000,
    select="RIC,DTSubjectName,ExchangeCode,ExchangeName,RCSTRBC2012Leaf,RCSAssetCategoryLeaf,AssetState",
)

# 파생 RIC 제거: 6자리코드.KNT 형태만 남김
clean = df[df["RIC"].str.match(r"^\d{6}\.KNT$")].reset_index(drop=True)
```

### 필터 조건 의미

| 조건 | 의미 |
|---|---|
| `ExchangeCode eq 'KNT'` | 거래소 = 넥스트레이드 |
| `RCSAssetCategoryLeaf eq 'Ordinary Share'` | 보통주만(우선주/ETF 제외). 전체를 원하면 생략 |
| `AssetState eq 'AC'` | 현재 상장(Active)만 |
| ~~`IsPrimaryRIC eq true`~~ | **사용 금지** (.KNT는 모두 False → 0건) |

### 필터별 실측 건수 (2026-05-31)

| 필터 | 건수 |
|---|---|
| `ExchangeCode eq 'KNT'` (전체) | 1,012 |
| `... and AssetState eq 'AC'` | **1,006** ← 스크린샷의 1,006과 정확히 일치 |
| `... and Ordinary Share and AC` | 1,006 |
| `... and IsPrimaryRIC eq true` | **0** ← (함정 확인) |

→ 스크린샷의 **1,006 = 현재 상장(Active) 넥스트레이드 종목**.

## 5. 제약

- `top + skip ≤ 10,000` 하드 제한. 넥스트레이드는 종목 수가 적어(≈1,000) 1회 호출로 충분.
- `select` 가능 컬럼·반환 형태는 [source_docs/API_FIELDS_REFERENCE.md](source_docs/API_FIELDS_REFERENCE.md) 0-1절 참고.
- 일부 메타데이터(국가, IPO일 등)는 `discovery.search`로 안 나오므로 `ld.get_data`로 보강(동 문서 0-2절).

## 6. 구현

- **[code/nxt_universe.py](code/nxt_universe.py)** — 위 로직 (`get_nxt_universe()`).
  거래소코드 `KNT` / `IsPrimaryRIC=False` 함정 / 6자리 RIC 패턴 정제까지 검증 반영.
- 실제 수집 시엔 [code/collect_all.py](code/collect_all.py)가 이 함수를 호출해
  `data/nxt_universe.csv`(`code6` 컬럼 포함)로 저장하고 [2단계] 수집의 입력으로 쓴다.

## 7. 다음 단계 (전체 파이프라인 3단계)

```
[1] Universe       code/nxt_universe.py   → data/nxt_universe.csv (.KNT RIC ≈1,006)   ← 이 문서
        │
        ▼
[2] 30분봉 수집     code/collect_all.py    → data/raw/{종목}.parquet                    → 2_NXT_PRICE_HISTORY.md
        │
        ▼
[3] 분석           code/metrics.py        → data/panel_sessions.{parquet,csv}          → 3_NXT_ANALYSIS.md
```
