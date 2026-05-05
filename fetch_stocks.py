#!/usr/bin/env python3
"""
Fetch A-share (A股) and HK-listed (港股) companies with industry classification.

A股  : CSRC industry (证监会行业) and SW industry (申银万国/申万行业)
       — both fetched from CNINFO (巨潮资讯) in a single call each.
港股  : Hang Seng industry classification via East Money (东方财富).

Output: CSV files written to ./output/
"""

import logging
import time
from datetime import date
from pathlib import Path

import akshare as ak
import pandas as pd

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path("output")

HEALTHCARE_SW_L1      = {"医药生物"}
HEALTHCARE_CSRC_CODES = {"C27"}          # 医药制造业
HEALTHCARE_HK_KEYWORDS = [
    "医疗", "医药", "健康", "生物", "制药", "药业", "药品",
    "health", "pharma", "bio", "medical",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _retry(fn, retries: int = 3, base_delay: float = 1.0):
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:
            if attempt == retries - 1:
                raise
            wait = base_delay * (attempt + 1)
            log.warning(f"Attempt {attempt + 1} failed ({exc}); retrying in {wait:.0f}s")
            time.sleep(wait)


def _find_col(df: pd.DataFrame, keywords: list) -> str | None:
    """Return the first column name whose text contains any keyword."""
    for col in df.columns:
        if any(kw.lower() in str(col).lower() for kw in keywords):
            return col
    return None


# ---------------------------------------------------------------------------
# A股 — CSRC industry (证监会行业分类标准)
# ---------------------------------------------------------------------------

def fetch_a_csrc() -> pd.DataFrame:
    """
    Fetch all A-share stocks with CSRC industry from CNINFO in one call.
    Returns: stock_code, company_name, csrc_industry_code, csrc_industry_name
    """
    log.info("=== Fetching A股 CSRC industry (CNINFO 证监会行业分类标准) ===")
    try:
        raw = _retry(lambda: ak.stock_industry_category_cninfo(symbol="证监会行业分类标准"))
    except Exception as exc:
        log.error(f"  CSRC fetch failed: {exc}")
        return pd.DataFrame(columns=["stock_code", "company_name",
                                     "csrc_industry_code", "csrc_industry_name"])

    log.info(f"  Rows: {len(raw):,} | Columns: {raw.columns.tolist()}")
    n = raw.shape[1]

    # CNINFO CSRC columns (typical):
    #   0: 证券代码  1: 证券简称
    #   2: 行业门类代码  3: 行业门类         (e.g. C / 制造业)
    #   4: 行业大类代码  5: 行业大类         (e.g. C27 / 医药制造业)  ← we want this
    #   6: 行业中类代码  7: 行业中类  (optional)
    if n >= 6:
        code_idx, name_idx = 4, 5   # 行业大类 (most useful level)
    elif n >= 4:
        code_idx, name_idx = 2, 3   # fall back to 行业门类
    else:
        code_idx, name_idx = 2, 3

    result = pd.DataFrame({
        "stock_code":         raw.iloc[:, 0].astype(str).str.strip().str.zfill(6),
        "company_name":       raw.iloc[:, 1].astype(str).str.strip(),
        "csrc_industry_code": raw.iloc[:, code_idx].astype(str).str.strip(),
        "csrc_industry_name": raw.iloc[:, name_idx].astype(str).str.strip(),
    })
    result = result[result["stock_code"].str.fullmatch(r"\d{6}")]
    log.info(f"  Valid records: {len(result):,}")
    return result


# ---------------------------------------------------------------------------
# A股 — SW industry (申银万国行业分类标准, i.e. 申万行业)
# ---------------------------------------------------------------------------

def fetch_a_sw() -> pd.DataFrame:
    """
    Fetch all A-share stocks with SW (申银万国) industry from CNINFO in one call.
    Returns: stock_code, sw_industry_l1, sw_industry_l2
    """
    log.info("=== Fetching A股 SW industry (CNINFO 申银万国行业分类标准) ===")
    try:
        raw = _retry(lambda: ak.stock_industry_category_cninfo(symbol="申银万国行业分类标准"))
    except Exception as exc:
        log.error(f"  SW fetch failed: {exc}")
        return pd.DataFrame(columns=["stock_code", "sw_industry_l1", "sw_industry_l2"])

    log.info(f"  Rows: {len(raw):,} | Columns: {raw.columns.tolist()}")
    n = raw.shape[1]

    # CNINFO SW columns (typical):
    #   0: 证券代码  1: 证券简称
    #   2: 一级行业代码  3: 一级行业名称    (e.g. 医药生物)   ← L1
    #   4: 二级行业代码  5: 二级行业名称    (e.g. 化学制药)   ← L2
    #   6: 三级行业代码  7: 三级行业名称  (optional)
    if n >= 6:
        l1_idx, l2_idx = 3, 5   # L1 name + L2 name
    elif n >= 4:
        l1_idx, l2_idx = 3, 3   # only L1
    else:
        l1_idx, l2_idx = 2, 2

    result = pd.DataFrame({
        "stock_code":     raw.iloc[:, 0].astype(str).str.strip().str.zfill(6),
        "sw_industry_l1": raw.iloc[:, l1_idx].astype(str).str.strip(),
        "sw_industry_l2": raw.iloc[:, l2_idx].astype(str).str.strip(),
    })
    result = result[result["stock_code"].str.fullmatch(r"\d{6}")]
    log.info(f"  Valid records: {len(result):,}")
    return result


# ---------------------------------------------------------------------------
# A股 — merge into final DataFrame
# ---------------------------------------------------------------------------

def build_a_stocks(csrc_df: pd.DataFrame, sw_df: pd.DataFrame) -> pd.DataFrame:
    if csrc_df.empty and sw_df.empty:
        log.error("Both CSRC and SW data are empty — no A-share data to process")
        return pd.DataFrame()

    if csrc_df.empty:
        log.warning("CSRC data empty; using SW data as base (company_name will be empty)")
        base = sw_df.copy()
        base["company_name"]       = ""
        base["csrc_industry_code"] = ""
        base["csrc_industry_name"] = ""
    elif sw_df.empty:
        log.warning("SW data empty; sw_industry columns will be empty")
        base = csrc_df.copy()
        base["sw_industry_l1"] = ""
        base["sw_industry_l2"] = ""
    else:
        base = csrc_df.merge(
            sw_df[["stock_code", "sw_industry_l1", "sw_industry_l2"]],
            on="stock_code", how="left",
        )
        base["sw_industry_l1"] = base["sw_industry_l1"].fillna("")
        base["sw_industry_l2"] = base["sw_industry_l2"].fillna("")

    base["market"]      = "A"
    base["hk_industry"] = ""

    # Vectorized healthcare flag — avoids empty-DataFrame apply() bug
    sw_hc   = base["sw_industry_l1"].isin(HEALTHCARE_SW_L1)
    csrc_hc = base["csrc_industry_code"].astype(str).str.startswith(
        tuple(HEALTHCARE_CSRC_CODES), na=False
    )
    base["is_healthcare"] = (sw_hc | csrc_hc).astype(int)
    base["updated_at"]    = date.today().isoformat()

    return base[[
        "stock_code", "company_name", "market",
        "sw_industry_l1", "sw_industry_l2",
        "csrc_industry_code", "csrc_industry_name",
        "hk_industry", "is_healthcare", "updated_at",
    ]]


# ---------------------------------------------------------------------------
# 港股 — stock list
# ---------------------------------------------------------------------------

def fetch_hk_stocks() -> pd.DataFrame:
    """Fetch all HK-listed stocks from East Money."""
    log.info("=== Fetching 港股 stock list (东方财富) ===")
    try:
        df = _retry(lambda: ak.stock_hk_spot_em())
        log.info(f"  HK stocks: {len(df):,} | columns: {df.columns.tolist()}")
    except Exception as exc:
        log.error(f"  HK stock list failed: {exc}")
        return pd.DataFrame()

    result = pd.DataFrame({
        "stock_code":   df.iloc[:, 0].astype(str).str.strip(),
        "company_name": df.iloc[:, 1].astype(str).str.strip(),
    })
    industry_col = _find_col(df, ["行业", "板块", "industry", "sector"])
    result["hk_industry"] = df[industry_col].astype(str).str.strip() if industry_col else ""
    if industry_col:
        log.info(f"  Industry column found in spot data: '{industry_col}'")
    return result


# ---------------------------------------------------------------------------
# 港股 — industry classification via East Money HK boards
# ---------------------------------------------------------------------------

def fetch_hk_industry_map() -> dict:
    """
    Build HK stock_code → industry mapping via East Money HK industry boards.
    Falls back silently if the API is unavailable in this akshare version.
    """
    log.info("=== Fetching 港股 industry boards (东方财富) ===")
    code_map: dict = {}

    try:
        boards   = _retry(lambda: ak.stock_hk_board_industry_name_em())
        name_col = boards.columns[1] if len(boards.columns) > 1 else boards.columns[0]
        board_names = boards[name_col].astype(str).tolist()
        log.info(f"  HK industry boards: {len(board_names)}")

        for i, board in enumerate(board_names, 1):
            try:
                cons = _retry(lambda b=board: ak.stock_hk_board_industry_cons_em(symbol=b))
                # Locate the code column by name to avoid using the rank (序号) column
                code_col = _find_col(cons, ["代码", "code", "Code"]) or cons.columns[0]
                for code in cons[code_col].astype(str).str.strip():
                    if code and code != "nan":
                        code_map[code] = board
            except Exception as exc:
                log.warning(f"  HK board '{board}' failed: {exc}")

            if i % 10 == 0 or i == len(board_names):
                log.info(f"  Progress: {i}/{len(board_names)} boards | {len(code_map):,} stocks")
            time.sleep(0.3)

    except AttributeError:
        log.info("  stock_hk_board_industry_name_em not available in this akshare version")
    except Exception as exc:
        log.warning(f"  HK board fetch failed: {exc}")

    log.info(f"  HK industry mapped: {len(code_map):,} stocks")
    return code_map


# ---------------------------------------------------------------------------
# 港股 — build final DataFrame
# ---------------------------------------------------------------------------

def build_hk_stocks(hk_df: pd.DataFrame, industry_map: dict) -> pd.DataFrame:
    if hk_df.empty:
        return pd.DataFrame()

    df = hk_df.copy()
    if df["hk_industry"].eq("").all() and industry_map:
        df["hk_industry"] = df["stock_code"].map(industry_map).fillna("")

    df["market"]             = "HK"
    df["sw_industry_l1"]     = ""
    df["sw_industry_l2"]     = ""
    df["csrc_industry_code"] = ""
    df["csrc_industry_name"] = ""

    low = df["hk_industry"].str.lower().fillna("")
    df["is_healthcare"] = low.apply(
        lambda x: int(any(kw.lower() in x for kw in HEALTHCARE_HK_KEYWORDS))
    )
    df["updated_at"] = date.today().isoformat()

    return df[[
        "stock_code", "company_name", "market",
        "sw_industry_l1", "sw_industry_l2",
        "csrc_industry_code", "csrc_industry_name",
        "hk_industry", "is_healthcare", "updated_at",
    ]]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    today = date.today().isoformat()

    log.info("=" * 60)
    log.info("Stock Data Fetcher — A股 + 港股")
    log.info("=" * 60)

    # ── A股 ──────────────────────────────────────────────────────────────
    csrc_df = fetch_a_csrc()
    sw_df   = fetch_a_sw()
    a_df    = build_a_stocks(csrc_df, sw_df)

    # ── 港股 ─────────────────────────────────────────────────────────────
    hk_raw          = fetch_hk_stocks()
    hk_industry_map = fetch_hk_industry_map()
    hk_df           = build_hk_stocks(hk_raw, hk_industry_map)

    # ── Merge & save ─────────────────────────────────────────────────────
    all_df = pd.concat([a_df, hk_df], ignore_index=True)

    a_path   = OUTPUT_DIR / f"a_stocks_{today}.csv"
    hk_path  = OUTPUT_DIR / f"hk_stocks_{today}.csv"
    all_path = OUTPUT_DIR / f"all_stocks_{today}.csv"

    a_df.to_csv(a_path,    index=False, encoding="utf-8")
    hk_df.to_csv(hk_path,  index=False, encoding="utf-8")
    all_df.to_csv(all_path, index=False, encoding="utf-8")

    # ── Summary ──────────────────────────────────────────────────────────
    a_hc  = int(a_df["is_healthcare"].sum())  if not a_df.empty  else 0
    hk_hc = int(hk_df["is_healthcare"].sum()) if not hk_df.empty else 0

    log.info("")
    log.info("=" * 60)
    log.info("Summary")
    log.info("=" * 60)
    log.info(f"{'市场':<6} {'医疗':>6} {'非医疗':>8} {'合计':>8}")
    log.info("-" * 32)
    if not a_df.empty:
        log.info(f"{'A股':<6} {a_hc:>6,} {len(a_df)-a_hc:>8,} {len(a_df):>8,}")
    if not hk_df.empty:
        log.info(f"{'港股':<6} {hk_hc:>6,} {len(hk_df)-hk_hc:>8,} {len(hk_df):>8,}")
    total = len(all_df)
    total_hc = a_hc + hk_hc
    log.info(f"{'合计':<6} {total_hc:>6,} {total-total_hc:>8,} {total:>8,}")
    log.info("")
    log.info(f"Output: {OUTPUT_DIR.resolve()}/")
    for p in (a_path, hk_path, all_path):
        log.info(f"  {p.name}")


if __name__ == "__main__":
    main()
