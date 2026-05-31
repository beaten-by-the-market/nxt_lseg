# 기술 참조 문서 (Technical Reference)

## 1. API 제약 조건

### 1.1 LSEG Data Library 한도

| 항목 | 값 | 비고 |
|------|---|------|
| 초당 요청 수 | 5 req/sec | 모든 앱 합산 |
| 분당 데이터 | 50 MB | |
| 일일 요청 수 | 10,000 calls | 헤드라인 + 본문 합산 |
| 일일 데이터 | 5 GB | |
| 헤드라인 1회 최대 건수 | **100건** | LSEG 공식 한도. count>100 설정 시 라이브러리가 내부 자동 페이지네이션 수행 (서버 측 호출 수 증가) |
| 헤드라인 페이지네이션 | 커서 기반, 사실상 무제한 | `MAX_PAGES=10000` 설정으로 누락 방지 |
| 뉴스 기록 보존 기간 | ~15개월 (헤드라인, 표준 API window) | 본문(story)은 더 오래 보존될 수 있음. archive entitlement 시 소스별로 더 깊이 접근 가능 (아래 1.1.1 참고) |

### 1.1.1 사용 소스별 historical depth (RTRS / PRN / BSW / GNW 한정)

본 프로젝트는 `RTRS`, `PRN`, `BSW`, `GNW` 4개 소스만 사용한다.

| Source | 식별자 | LSEG 공식 archive 시작 | 본 계정 실측 시작 (`news_headlines` 기준) | 비고 |
|---|---|---|---|---|
| Reuters News | `NS:RTRS` | 1996년 | **2011-01-03** | 표준 API window는 ~15개월. 그 이전은 archive entitlement 필요. |
| PR Newswire | `NS:PRN` | 공식 정책 "back to 2003 for many other news sources" | **2019-05-01** | third-party newswire. 실측 cutoff = 2019-05경. |
| Business Wire | `NS:BSW` | 동일 (third-party 2003년 정책) | **2019-05-02** | 동일 |
| GlobeNewswire | `NS:GNW` | 동일 (third-party 2003년 정책) | **2019-05-01** | 동일 |

**해석**
- 4개 소스 **공통 분석 가능 시작점은 2019-05**. RTRS 단독 분석이면 2011년까지 가능.
- 공식 문서가 "third-party는 2003년부터"라고 명시하지만, 본 계정 entitlement 실측은 2019-05이 한계.
- 새로 수집할 때 archive 권한이 유지되어야 위 깊이까지 접근 가능. 권한이 변경되면 rolling 15개월(약 2025-02~)로 떨어질 수 있음.

**쿼리 문법**
```
R:<RIC> AND (Source:RTRS OR Source:PRN OR Source:BSW OR Source:GNW) AND Language:LEN
```

**출처**
- [News Service on Refinitiv Data Platform](https://developers.lseg.com/en/product/news/news_service_rdp): *"Five quarters of data available through API"* / *"Archives available — Reuters back to 1996, many other news sources back to 2003"*
- [Machine Readable News](https://www.lseg.com/en/data-analytics/financial-news-service/machine-readable-news): *"News archive offers access to historical news dating back to 1996, 25+ years"*

### 1.2 뉴스 헤드라인 API (`news.headlines.Definition`)

**라이브러리**: `lseg-data` (`import lseg.data as ld`)

**반환 컬럼 (4개)**:

| 컬럼 | 타입 | 설명 | 예시 |
|------|------|------|------|
| `versionCreated` | datetime64[ns, UTC] | 기사 생성/수정 시각 (UTC) | `2026-03-27 13:00:01+00:00` |
| `text` | string | 헤드라인 텍스트 | `"SAMSUNG Q4 PROFIT BEATS..."` |
| `storyId` | string | 본문 조회용 고유 ID | `urn:newsml:newswire.refinitiv.com:20260327:nL4N40F0CI:1` |
| `sourceCode` | string | 소스 코드 | `NS:RTRS`, `NS:PRN` |

**주의사항**:
- 언어(language) 필드는 헤드라인 API에서 직접 제공되지 않음
- 언어는 본문 HTML의 `lang` 속성에서 추출 가능: `<div class="storyContent" lang="ko">`
- 종목 RIC는 헤드라인 메타데이터에 포함되지 않음 (쿼리 파라미터로 필터링한 것만 알 수 있음)
- `versionCreated`는 UTC 기준. 한국(KST=UTC+9), 일본(JST=UTC+9), 대만(CST=UTC+8)

**쿼리 문법**:
```
R:<RIC> AND Language:LEN                              # 현재 사용 (영어, 전체 소스)
R:<RIC> AND Source:<SOURCE_CODE> AND Language:LEN      # 소스 지정 시
```

**언어 필터 코드**:

| 필터 | 언어 |
|------|------|
| `Language:LEN` | English (현재 사용) |
| `Language:LKO` | Korean |
| `Language:LJA` | Japanese |
| `Language:LZH` | Chinese |

**날짜 파라미터**:
- `date_from`, `date_to`: ISO 형식 문자열 `"2025-01-01"` 또는 `"2025-01-01T00:00:00"`
- datetime 객체를 넣으면 pandas 호환 에러 발생할 수 있으므로 문자열 사용 권장

**페이지네이션**:
- 1회 100건 반환 후, 응답의 `meta.next` 커서를 `extended_params={"cursor": next_cursor}`로 전달하여 다음 페이지 조회
- 기존 기간 분할 재귀 방식 대비 코드가 단순하고 누락 위험이 적음

### 1.3 뉴스 본문 API (`ld.news.get_story`)

- 입력: `storyId` (문자열)
- 반환: HTML 문자열 또는 `None`
- 언어 정보: `<div class="storyContent" lang="en">` 에서 추출
- 빈 기사: `<div class="storyContent" lang="en"></div>` (length=42) → 본문 없음으로 처리

### 1.4 종목 리스트 수집 (`ld.discovery.search`)

**수집 기준**: Active + IsPrimaryRIC (전 국가 동일)

```python
ld.discovery.search(
    query="",
    filter="ExchangeCode eq 'KSC' "
           "and RCSAssetCategoryLeaf eq 'Ordinary Share' "
           "and AssetState eq 'AC' "
           "and IsPrimaryRIC eq true",
    top=10000,
    select="RIC,DTSubjectName,ExchangeCode,AssetState",
)
```

- `IsPrimaryRIC eq true`로 파생 RIC(bl/stat/ta/F/S) 자동 제외
- `AssetState eq 'AC'`로 현재 상장 종목만 수집
- `listed_as_of` 컬럼에 조회일 기록
- 상폐 종목 관련 자료는 `archive/delisted_companies/`에 보관

### 1.5 종목 메타데이터 보강 (`ld.get_data`)

**호출 코드**:
```python
ld.get_data(
    ["005930.KS", "000660.KS", ...],    # RIC 리스트 (배치 1,000개)
    ["TR.InstrumentType", "TR.IPODate", "TR.DelistingDate"]
)
```

## 2. 국가별 거래소 코드

| 국가 | 거래소 | Exchange Code | RIC 접미사 | 통화 |
|------|--------|---------------|-----------|------|
| 한국 | KOSPI | KSC | .KS | KRW |
| 한국 | KOSDAQ | KOE | .KQ | KRW |
| 일본 | TSE | TYO | .T | JPY |
| 대만 | TWSE | TAI | .TW | TWD |
| 대만 | TPEx | TWO | .TWO | TWD |

## 3. 수집 설정

- **언어**: 영어만 (`Language:LEN`)
- **소스**: 필터 없음 (전체 소스 수집, `sourceCode`로 사후 분류)
- **쿼리**: `R:{ric} AND Language:LEN`

주요 소스 (참고):

| 소스 코드 | 소스명 | 분류 |
|-----------|--------|------|
| RTRS | Reuters News | 독립 보도 |
| PRN | PR Newswire | 기업 보도자료 |
| BSW | Business Wire | 기업 보도자료 |
| DJN | Dow Jones Newswires | 독립 보도 |
| GRN | GlobeNewswire | 기업 보도자료 |
| WSJ | Wall Street Journal | 독립 보도 |

## 4. 수집 실행 계획

### 4.1 일일 한도 시뮬레이션

헤드라인 수집 시 1회 호출 = 종목 1개 × 전체 소스 (커서 페이지네이션으로 100건 이상 자동 수집):

| 국가 | Equities 종목 수 | 수집 종목 | 헤드라인 건수 | 비고 |
|------|:---:|:---:|:---:|------|
| 한국 | 2,671 | 2,572 | 5,516,228 | 페이지네이션 포함 |
| 일본 | 3,994 | 3,927 | 1,267,836 | |
| 대만 | 2,314 | 2,226 | 2,083,528 | |
| **합계** | **8,979** | **8,725** | **8,867,592** | |

일일 한도(9,500 calls) 기준, 페이지네이션(종목당 평균 ~25회 호출) 감안 시 **약 10~12일** 소요 (2026-04-08 ~ 04-22 실측).

### 4.2 실행 명령어

```bash
# Phase 0: 종목 리스트 수집 (1회)
python master_build/01_01_collect_companies.py

# Phase 1: 헤드라인 수집 (자동 재개)
python headlines/run_headlines.py

# Phase 2: 본문 수집 (헤드라인 완료 후)
python stories/run_stories.py                    # 전체 국가
python stories/run_stories.py --country KR JP    # 한국/일본만
```

## 5. 장애 대응 (Fallback)

### 5.1 진행 상태 추적

- `logs/runner_progress.json`: 국가/소스/종목별 수집 진행 위치
- DB `collection_log` 테이블: 모든 API 호출 기록
- DB `api_usage` 테이블: 일별 API 사용량

### 5.2 재시작 시 동작

1. `runner_progress.json`에서 마지막 완료 위치 확인
2. `collection_log`에서 이미 수집된 (ric, source) 조합 건너뜀
3. 에러 로그는 실행 시 삭제되어 자동 재시도 대상으로 전환

### 5.3 에러 유형별 처리

| 에러 | 원인 | 처리 |
|------|------|------|
| `400 Bad Request` | count > 100 또는 잘못된 쿼리 | count=100으로 제한 |
| `429 Too Many Requests` | 일일 한도 초과 또는 단기 rate limit | 즉시 중단, 진행 저장, 다음 날 재개. count>100 시 내부 자동 페이지네이션으로 실제 호출 수 증가에 주의 |
| `408 Timeout` | 서버 응답 지연 | 5초 대기 후 재시도 |
| `1404` / `No datapoint` | 종목 없음 / 데이터 없음 | 건너뜀, 로그 기록 |
| `datetime64` 에러 | pandas 호환 이슈 | 빈 결과로 처리 |
| `500 Server Error` | 서버 에러 | 1회 재시도 후 건너뜀 |
| 네트워크 끊김 | Workspace 연결 끊김 | 30초 대기, 재연결 시도 |

## 6. 데이터 품질 체크리스트

수집 완료 후 확인할 사항:
- [ ] 국가별 종목 수 vs 헤드라인 보유 종목 수 비교
- [ ] 소스별(sourceCode) 건수 분포
- [ ] 연도별 건수 추이 (급감/급증 구간 확인)
- [ ] 중복 storyId 확인
- [ ] 본문 없는 헤드라인 비율
- [ ] 언어 분포 (en/ko/ja/zh)

`IsPrimaryRIC` / `AssetState` 필터를 풀고 미국 거래소까지 확장한 다운로드의 **종목 리스트(`companies` 테이블) 정제 체크리스트**는 별도로 정리되어 있음 → [POST_DOWNLOAD_REVIEW.md](POST_DOWNLOAD_REVIEW.md).
