# API 필드 및 파라미터 레퍼런스

각 수집 단계에서 호출하는 API, 전달하는 파라미터, 사용 가능한 필드, 실제로 사용하는 필드를 정리한다.

모든 API는 `lseg-data` 라이브러리(`import lseg.data as ld`)를 사용한다.

---

## Phase 0: 종목 리스트 수집 (`01_01_collect_companies.py`)

### 0-1. `ld.discovery.search` — 종목 검색

**호출 코드**:
```python
# 거래소별 순회 호출 (Active + IsPrimaryRIC only)
for exchange in ["KSC", "KOE"]:         # 국가별 거래소 목록
    ld.discovery.search(
        query="",
        filter=f"ExchangeCode eq '{exchange}'
                and RCSAssetCategoryLeaf eq 'Ordinary Share'
                and AssetState eq 'AC'
                and IsPrimaryRIC eq true",
        top=10000,
        select="RIC,DTSubjectName,ExchangeCode,AssetState",
    )
```

한국의 경우 2번 호출된다: KSC, KOE. 전 국가 동일 로직.

#### 호출 파라미터

| 파라미터 | 값 | 설명 |
|---------|---|------|
| `query` | `""` | 자유 텍스트 검색어. 빈 문자열 = 전체 검색 |
| `filter` | OData 표현식 | 아래 필터 조건 참조 |
| `top` | `10000` | 1회 최대 반환 건수. **LSEG 하드 제한: top + skip ≤ 10,000** |
| `skip` | (미사용) | 페이지네이션용. top + skip ≤ 10,000 제약 있음 |
| `select` | 쉼표 구분 문자열 | 반환받을 컬럼 목록 |

#### filter 조건으로 사용 가능한 필드

| 필드 | 타입 | 예시 값 | 설명 |
|------|------|--------|------|
| `ExchangeCode` | string | `'KSC'`, `'KOE'`, `'TYO'`, `'TAI'`, `'TWO'` | 거래소 코드 |
| `RCSAssetCategoryLeaf` | string | `'Ordinary Share'`, `'Equity ETFs'`, `'Bond ETFs'` 등 | 자산 유형 말단 분류 |
| `AssetState` | string | `'AC'` (Active), `'DC'` (Delisted) | 상장/상폐 상태 |
| `IsPrimaryRIC` | boolean | `true` / `false` | 대표 RIC 여부. 아래 "primary 필드 의미" 참조 |
| `PrimaryRIC` | string | `'005930.KS'`, `'IBM'` | 이 RIC이 속한 자산의 진짜 primary RIC 값(forward pointer) |
| `IsPrimaryQuote` | boolean | (equity 아님) | FX/지수 등 비-equity quote의 primary 표시. equity에는 모두 false → 우리 용도엔 무관 |
| `IsPrimary` | boolean | (지수 아님) | Index(`.RUT`, `.MIWO00000PUS` 등)에서만 true → 우리 용도엔 무관 |
| `startswith(RIC, 'prefix')` | 함수 | `startswith(RIC,'0')` | RIC 접두사 필터 (10,000건 초과 시 분할용) |

##### "primary 필드"의 정확한 의미 (probe 결과 기반)

- **`IsPrimaryRIC`은 회사·자산종류 단위 boolean**. 한 회사가 발행한 같은 자산종류(예: Ordinary Share) 내에서 1개의 RIC만 true.
  - 같은 회사의 다른 자산종류(채권, ETF 발행 등)는 각자 별도의 IsPrimaryRIC=true RIC을 가짐.
  - 따라서 IsPrimaryRIC=true는 "회사당 1개"가 아니라 "(회사, 자산종류)당 1개".
- **상폐(AssetState='DC')는 항상 false.** 파생 chain(`0#...`, F/Spread 등)도 false.
- **우선주(Preference Share)는 보통주의 부속물로 취급됨.** 우선주 자체는 IsPrimaryRIC=false이고, `PrimaryRIC` 값이 같은 회사 보통주 RIC을 가리킴.
- 본국 + 타국 듀얼리스팅: 거래량(volume)이 가장 많은 venue가 IsPrimaryRIC=true.
- `PrimaryRIC` 컬럼은 "자기 자산의 primary는 누구냐"의 forward pointer. 자기가 primary면 자기 RIC, 아니면 다른 RIC을 가리킴.

###### Primary 필드별 케이스 예시 (실제 probe 결과)

| RIC | 자산 | IsPrimaryRIC | PrimaryRIC |
|---|---|---|---|
| `005930.KS` 삼성 보통주 | Ordinary Share | True | `005930.KS` (자기) |
| `005935.KS` 삼성 우선주 | Preference Share | False | `005930.KS` (보통주 가리킴) |
| `IBM.N` NYSE 거래 | Ordinary Share | False | `IBM` (composite) |
| `IBM.MX` 멕시코 | Ordinary Share | False | `IBM` |
| `IBM.F` 프랑크푸르트 | Ordinary Share | False | `IBM` |
| `0#KS2HI:` KOSPI200 중공업 future chain | Equity Future | False | — |

→ 미국 종목은 `IBM`처럼 거래소 suffix 없는 composite RIC이 primary로 마킹되므로, `ExchangeCode eq 'NYS'`로 거르면 IsPrimaryRIC=true가 한 건도 안 잡힐 수 있음. 한국·일본·대만은 거래소가 primary venue 자체이므로 이 함정 없음.

###### `TR.*` 네임스페이스와의 차이

DIB에 있는 `TR.PrimaryRICCode`, `TR.IsPrimaryInstrument`, `TR.IsPrimaryQuote`, `TR.IsCountryPrimaryQuote` 등은 **`ld.get_data` 전용**이고, `ld.discovery.search`의 filter/select에는 사용할 수 없음. probe로 확인된 `discovery.search` 가용 primary 필드는 위 4개(`IsPrimaryRIC`, `PrimaryRIC`, `IsPrimaryQuote`, `IsPrimary`)뿐.

#### select로 반환 가능한 컬럼 (확인 완료)

| 컬럼 | 반환 예시 | 설명 | 사용 여부 |
|------|---------|------|:---:|
| `RIC` | `005930.KS` | 종목 코드 | **O** |
| `DTSubjectName` | `Samsung Electronics Co Ltd` | 회사명 | **O** |
| `ExchangeCode` | `KSC` | 거래소 코드 | **O** |
| `AssetState` | `AC` | 상장/상폐 상태 | **O** |
| `IsPrimaryRIC` | `True` | 대표 RIC 여부 | X (filter에만 사용) |
| `PrimaryRIC` | `005930.KS` | 진짜 primary RIC 값 (forward pointer). 우선주 → 보통주, IBM.N → IBM | X (필요시 추가 가능) |
| `SearchAllCategoryv3` | `Equities` | 자산 대분류 | X |
| `RCSAssetCategoryLeaf` | `Ordinary Share` | 자산 세분류 | X (filter에만 사용) |
| `RCSAssetCategoryGenealogy` | `['A:1\\A:1L']` | 자산 분류 계층 (인코딩) | X |
| `PermID` | `55834588913` | LSEG 영구 식별자 | X |
| `PI` | `1140725` | 내부 식별자 | X |
| `BusinessEntity` | `QUOTExEQUITY` | 비즈니스 엔티티 유형 | X |
| `DocumentTitle` | `Samsung Electronics..., Korea Exchange - KSE` | 전체 설명 | X |
| `RCSCurrency` | `C:H` | 통화 (인코딩됨) | X |
| `RCSExchangeCountry` | `G:AE` | 거래소 소재국 (인코딩됨) | X |
| `RCSTRBC2012Leaf` | `Phones & Handheld Devices (NEC)` | TRBC 업종 (말단) | X |
| `RCSTRBC2012Name` | `Technology\Technology Equipment\...` | TRBC 업종 (전체 경로) | X |
| `AssetCategory` | `['ORD']` | 자산 유형 코드 | X |
| `AssetType` | `['EQUITY']` | 자산 타입 코드 | X |
| `IssuerOAPermID` | `4295882451` | 발행사 PermID | X |

#### select 요청했으나 반환되지 않는 컬럼 (미지원)

`RCSCountryHeadquarters`, `RCSCountryOfIncorporation`, `RCSRegion`,
`UltimateParentOAPermID`, `UltimateParentOrganisationName`,
`IPODate`, `RetireDate`, `FirstTradeDate`

→ 이 필드들은 `ld.get_data`로 보강해야 함.

#### 제약 사항

- `top + skip ≤ 10,000` 하드 제한. 초과 시 `400 Invalid result window` 에러
- 현재는 Active + IsPrimaryRIC만 수집하므로 10,000건 초과 가능성 낮음
- 상폐 종목 관련 자료는 `archive/delisted_companies/`에 보관

---

### 0-2. `ld.get_data` — 종목 메타데이터 보강

**호출 코드**:
```python
ld.get_data(
    ["005930.KS", "000660.KS", ...],    # RIC 리스트 (배치 1,000개)
    ["TR.InstrumentType", "TR.IPODate", "TR.DelistingDate"]
)
```

#### 호출 파라미터

| 파라미터 | 값 | 설명 |
|---------|---|------|
| universe | RIC 리스트 | 최대 ~1,000개/배치 안정적 |
| fields | TR 필드 리스트 | 아래 참조 |

`ld.get_data`는 **종목별 순회 호출이 아니라 배치 호출**임. universe에 RIC을 N개 넣으면 한 번의 HTTP 요청으로 N×len(fields) 셀을 한꺼번에 받음. `utils\api.py:394-400`이 1,000개씩 끊어 호출하는 패턴 사용. 따라서 N=10,000 종목 × 3 필드 = 10번의 HTTP 요청. discovery.search와 동일하게 "한방 호출"의 이점을 누릴 수 있음.

#### 사용하는 TR 필드 (3개)

| 필드 | 반환 컬럼명 | 예시 값 | 설명 |
|------|-----------|--------|------|
| `TR.InstrumentType` | `Instrument Type` | `Ordinary Shares`, `Equity ETFs` | 상품 유형 |
| `TR.IPODate` | `IPO Date` | `1975-06-11` | 상장일 |
| `TR.DelistingDate` | `Delisting Date` | `2015-09-01` | 상장폐지일 (NULL이면 현재 상장) |

#### 사용 가능하지만 사용하지 않는 TR 필드 (참고)

| 필드 | 설명 | 미사용 사유 |
|------|------|-----------|
| `TR.CompanyName` | 회사명 | discovery.search의 DTSubjectName 사용 |
| `TR.ExchangeCode` | 거래소 코드 | discovery.search에서 이미 확보 |
| `TR.RIC` | RIC | discovery.search에서 이미 확보 |
| `TR.MarketCapitalization` | 시가총액 | 수집 대상 아님 |
| `TR.GICSSector` | GICS 섹터 | 수집 대상 아님 |
| `TR.BusinessSummary` | 사업 개요 | 수집 대상 아님 |
| `TR.AssetCategory` | 자산 분류 | TR.InstrumentType이 더 세분화 |

#### RIC 파생 변형 (주의)

하나의 종목에 대해 discovery.search가 여러 RIC을 반환한다:

| RIC | 유형 | 용도 |
|-----|------|------|
| `005930.KS` | 기본 (Primary) | **뉴스 수집에 사용** |
| `005930bl.KS` | Block Trade | 대량매매 |
| `005930F.KS` | Foreign | 외국인 투자자용 |
| `005930S.KS` | Short Selling | 공매도용 |
| `005930stat.KS` | Statistics | 통계용 |
| `005930ta.KS` | Technical Analysis | 기술적 분석용 |
| `000030.KS^B19` | Delisted | 상폐 종목 (^코드 = 상폐 시점 식별) |

뉴스 수집 시에는 기본 RIC만 사용해야 중복 호출을 방지할 수 있다.

---

## Phase 1: 뉴스 헤드라인 수집 (`run_headlines.py`)

### 1-1. `news.headlines.Definition` — 뉴스 헤드라인

**라이브러리**: `lseg-data` (content layer)

```python
from lseg.data.content import news

response = news.headlines.Definition(
    query="R:005930.KS AND Source:RTRS",
    date_from="2011-01-01",
    date_to="2025-12-31",
    count=100,
).get_data()

# 커서 페이지네이션 (100건 이상 자동 수집)
next_cursor = response.data.raw[0]["meta"]["next"]
response2 = news.headlines.Definition(
    query="R:005930.KS AND Source:RTRS",
    date_from="2011-01-01",
    date_to="2025-12-31",
    count=100,
    extended_params={"cursor": next_cursor},
).get_data()
```

**종목 조회 (DB)**:

`get_active_companies(conn, country)` — 전 국가 동일 로직:

```sql
SELECT id, ric, company_name, exchange_code, is_active
FROM companies
WHERE country = %s AND is_active = 1
ORDER BY ric
```

종목은 `01_01_collect_companies.py`에서 `IsPrimaryRIC eq true` 기준으로 사전 수집된 상태이므로, 헤드라인 수집 시에는 `search_all_category = 'Equities'`만 확인하면 된다.

이전 방식(CSV 매칭, SQL 패턴 필터)의 상세 내용은 `archive/delisted_companies/README.md` 참조.

**수집 흐름**:
```python
# 국가 → 종목 순으로 2중 순회 (전 국가 동일, 소스/언어 필터 쿼리에 포함)
for country in ["KR", "JP", "TW"]:
    companies = get_active_companies(conn, country)  # Equities만

    for company in companies:
        # query = "R:{ric} AND Language:LEN" (전체 소스, 영어만)
        api.get_headlines(company['ric'], date_from, date_to)
```

`run_headlines.py`가 이 순회를 자동으로 수행하며, 일일 한도 도달 시 중단 → 다음 날 재개.

#### 호출 파라미터

| 파라미터 | 값 | 설명 |
|---------|---|------|
| `query` | `"R:<RIC> AND Language:LEN"` | 종목 + 영어 (전체 소스) |
| `count` | `100` | 1페이지 최대 반환 건수 |
| `date_from` | `"2011-01-01"` | 시작일 (ISO 문자열) |
| `date_to` | 오늘 날짜 | 종료일 (ISO 문자열) |
| `extended_params` | `{"cursor": "..."}` | 페이지네이션 커서 (2페이지 이상 시) |

#### query 문법

```
R:<RIC>                         종목 태깅된 뉴스
Source:<SOURCE_CODE>             소스 필터 (선택)
Language:<LANG_CODE>             언어 필터
AND / OR / NOT                  논리 연산자

현재 사용:
  "R:005930.KS AND Language:LEN"                       # 전체 소스, 영어만

기타 예시:
  "R:005930.KS AND Source:RTRS AND Language:LEN"       # 특정 소스 지정
  "R:005930.KS AND (Language:LEN OR Language:LKO)"     # 다국어
```

#### DataFrame 반환 컬럼 (4개)

| 컬럼 | 위치 | 타입 | 예시 값 | DB 저장 |
|------|------|------|--------|:---:|
| `versionCreated` | 인덱스 | datetime64 | `2026-04-07 16:26:52` | O → `news_datetime_utc` |
| `headline` | 컬럼 | string | `"GLOBAL MARKETS-Stocks fall..."` | O → `headline_text` |
| `storyId` | 컬럼 | string | `urn:newsml:reuters.com:...` | O → `story_id` |
| `sourceCode` | 컬럼 | string | `NS:RTRS` | O → `source_code` |

#### Raw JSON 추가 필드 (headline별 저장)

| 필드 경로 | 설명 |
|----------|------|
| `newsItem._version` | 기사 버전 |
| `newsItem.contentMeta.language[0]._tag` | 언어 (`en`) |
| `newsItem.contentMeta.urgency.$` | 긴급도 (1=속보 ~ 5=일반) |
| `newsItem.contentMeta.audience` | 대상 독자 코드 |
| `newsItem.contentMeta.subject` | 주제/토픽 코드 |
| `newsItem.itemMeta.firstCreated.$` | 최초 생성 시각 |
| `newsItem.itemMeta.versionCreated.$` | 버전 생성 시각 |

전체 raw JSON은 `news_headlines.raw_json` 컬럼에 저장된다.

#### 제약 사항

- 1페이지 최대 100건 (LSEG 공식 한도. count>100 설정 시 라이브러리가 내부 자동 페이지네이션 수행하여 서버 측 호출 수 증가)
- 커서 페이지네이션으로 자동 연속 조회, `MAX_PAGES=10000`으로 사실상 무제한 (누락 방지)
- 뉴스 0건인 종목은 빈 결과로 처리
- 뉴스 기록 보존 기간: 헤드라인 ~15개월 (표준 API window = 5 quarters rolling)
- 단, archive entitlement가 부여된 계정은 소스별로 더 깊이 접근 가능
- 본 프로젝트 사용 소스(`RTRS`/`PRN`/`BSW`/`GNW`)의 실측 가능 범위는 [TECHNICAL_REFERENCE.md §1.1.1](TECHNICAL_REFERENCE.md#111-사용-소스별-historical-depth-rtrs--prn--bsw--gnw-한정) 참고. 요약: RTRS는 2011년~, 그 외 3개 third-party는 2019-05~.

---

## Phase 2: 뉴스 본문 수집 (`run_stories.py`)

### 2-1. `ld.news.get_story` — 뉴스 본문

**호출 코드**:
```python
# DB에서 아직 본문 미수집인 storyId를 조회하여 1건씩 순회
for story_id in get_headlines_without_stories(conn, batch_size=9000):
    ld.news.get_story(story_id)
```

`run_stories.py`가 이 순회를 자동으로 수행하며, 일일 한도 도달 시 중단 → 다음 날 재개.

#### 호출 파라미터

| 파라미터 | 값 | 설명 |
|---------|---|------|
| `story_id` | storyId 문자열 | Phase 1에서 수집한 `storyId` |

#### 반환값

| 항목 | 타입 | 설명 |
|------|------|------|
| 반환값 | string 또는 None | 뉴스 본문 HTML |

#### HTML 구조

```html
<div class="storyContent" lang="en">
  <style type="text/css">...</style>
  <p class="tr-story-p1">
    <span class="tr-dateline">SEOUL, March 27 (Reuters)</span>
    본문 텍스트...
  </p>
</div>
```

#### HTML에서 추출하는 정보

| 추출 대상 | 추출 방법 | DB 저장 컬럼 |
|----------|---------|------------|
| 언어 | `lang` 속성 파싱 (`lang="en"`) | `news_stories.language` |
| 본문 텍스트 | HTML 태그 제거 (style/script 제외) | `news_stories.story_text` |
| 원본 HTML | 그대로 저장 | `news_stories.story_html` |
| 문자 수 | `len(story_text)` | `news_stories.char_count` |
| 빈 기사 여부 | `char_count < 20` | `news_stories.is_empty` |

#### 확인된 언어 코드

| lang 값 | 언어 |
|---------|------|
| `en` | 영어 |
| `ko` | 한국어 |
| `ja` | 일본어 |
| `es` | 스페인어 |
| `hi` | 힌디어 |
| `zh` | 중국어 (대만 기사) |

---

## API 제약 사항 요약

| 항목 | 한도 | 적용 API |
|------|------|---------|
| 초당 요청 수 | 5 req/sec | 모든 LSEG API |
| 일일 요청 수 | 10,000 calls | 모든 LSEG API |
| 일일 데이터량 | 5 GB | 모든 LSEG API |
| 분당 데이터량 | 50 MB | 모든 LSEG API |
| 헤드라인 1페이지 최대 | 100건 | `news.headlines.Definition` |
| 헤드라인 페이지네이션 | 커서 기반, MAX_PAGES=10000 (사실상 무제한) | `news.headlines.Definition` |
| discovery.search 상한 | top + skip ≤ 10,000 | `ld.discovery.search` |
| get_data 배치 | ~1,000 RIC/배치 안정 | `ld.get_data` |
