# nxt_lseg — 넥스트레이드(NEXTRADE / `.KNT`) 프리·애프터 가격 분석

LSEG Data Library(`lseg.data`)로 **넥스트레이드(NXT) 거래소**의 한국 종목을 받아,
**프리장(Pre)/정규장/애프터장(After)에서 가격이 튀는지**를 분석한다.

> 배경: 한국은 원래 한국거래소(KRX)뿐이었고 2025-03 넥스트레이드가 개시. KRX는 프리/애프터가
> 없고 **NXT에만 프리·애프터**가 있다. KRX `.KS`/`.KQ`엔 연장세션 데이터가 없으므로 **반드시 `.KNT`**.

## 일의 진행 순서 (3단계)

```
[1] Universe 확인      .KNT 넥스트레이드 종목 리스트 확보 (≈1,006종목)
        │              → code/nxt_universe.py            → docs: 1_NXT_UNIVERSE.md
        ▼
[2] 30분봉 수집        각 종목 30분봉 OHLCV 수집 (기간·컷 기준 포함)
        │              → code/collect_all.py             → docs: 2_NXT_PRICE_HISTORY.md
        ▼
[3] 분석              프리/정규/애프터 '튐' 지표 패널 산출 (A 갭·B 변동·C 되돌림·D 과민)
                       → code/metrics.py                 → docs: 3_NXT_ANALYSIS.md
```

| 단계 | 문서 | 코드 | 산출물 |
|---|---|---|---|
| **1. Universe** | [1_NXT_UNIVERSE.md](1_NXT_UNIVERSE.md) | [code/nxt_universe.py](code/nxt_universe.py) | `data/nxt_universe.csv` |
| **2. 30분봉 수집** | [2_NXT_PRICE_HISTORY.md](2_NXT_PRICE_HISTORY.md) | [code/collect_all.py](code/collect_all.py), [code/nxt_price_history.py](code/nxt_price_history.py) | `data/raw/{종목}.parquet` |
| **3. 분석** | [3_NXT_ANALYSIS.md](3_NXT_ANALYSIS.md) | [code/metrics.py](code/metrics.py) | `data/panel_sessions.{parquet,csv}` |

## 핵심 사실 (라이브 검증 — 2026-05-31, `lseg.data 2.1.1`, 계정 data01@krx.co.kr)

- 세션은 `ld.open_session()` — **LSEG Workspace 데스크톱 앱이 실행 중**이어야 로컬 세션 연결.
- venue 구분은 **RIC 접미사**: `.KS`=KRX(KOSPI), `.KQ`=KOSDAQ, **`.KNT`=넥스트레이드(NXT)**.
- ⚠️ **`.KNT`은 모두 `IsPrimaryRIC=False`** → universe 필터에 `IsPrimaryRIC eq true` 넣으면 0건. (§1)
- ⚠️ 30분봉은 **약 12개월만 보존**(가용 시작 ≈ KST 2025-06-02), 1회 **≈5,778봉** 한도, 초과분 **조용히 절단**.
  롤링이라 **빨리 수집할수록 과거 확보 ↑**. (§2)

## 빠른 시작

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1            # 정책 막히면: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt

python code/collect_all.py             # [2] 전체 수집 (Workspace 켜둘 것. 재개 가능)
python code/metrics.py                 # [3] 패널 생성 + 세션별 요약
```

## 기타

- [source_docs/](source_docs/) — 원본 프로젝트(`news_lseg`)의 LSEG API 문서 사본(한도·필드 참조).
- `data/collect_progress.json` — 수집 진행 상황(완료/빈결과/실패).
