#!/usr/bin/env python3
"""
Fetch A-share (A股) and HK-listed (港股) companies with industry classification.

A股  : Stock list from East Money spot data (SH + SZ + BJ)
       SW industry (申万行业) from East Money industry boards
       — only known SW L2 board names are iterated (concept boards skipped)
港股  : Stock list from East Money; industry via HK board API if available

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

# SW L2 → L1 mapping (申万二级 → 申万一级, 2021版)
# Keys must exactly match East Money industry board names
SW_L2_TO_L1: dict[str, str] = {
    # 农林牧渔
    "种植业与林业": "农林牧渔", "养殖业": "农林牧渔",
    "渔业": "农林牧渔", "农业综合": "农林牧渔",
    # 基础化工
    "化学原料": "基础化工", "化学制品": "基础化工", "化学纤维": "基础化工",
    "橡胶": "基础化工", "塑料": "基础化工", "化工合成材料": "基础化工",
    "农化": "基础化工", "涂料油墨": "基础化工", "化工新材料": "基础化工",
    "其他化工": "基础化工",
    # 钢铁
    "普钢": "钢铁", "特钢": "钢铁",
    # 有色金属
    "工业金属": "有色金属", "能源金属": "有色金属", "贵金属": "有色金属",
    "小金属": "有色金属", "金属新材料": "有色金属",
    # 电子
    "半导体": "电子", "光学光电子": "电子", "消费电子": "电子",
    "元件": "电子", "其他电子": "电子", "电子化学品": "电子",
    # 汽车
    "乘用车": "汽车", "商用车": "汽车", "汽车零部件": "汽车",
    "汽车销售及服务": "汽车",
    # 家用电器
    "白色家电": "家用电器", "小家电": "家用电器", "厨卫电器": "家用电器",
    "黑色家电": "家用电器", "家电零部件": "家用电器",
    # 食品饮料
    "白酒": "食品饮料", "啤酒": "食品饮料", "饮料乳品": "食品饮料",
    "食品加工": "食品饮料", "调味发酵品": "食品饮料", "休闲食品": "食品饮料",
    # 纺织服装
    "纺织制造": "纺织服装", "服装家纺": "纺织服装",
    # 轻工制造
    "造纸": "轻工制造", "包装印刷": "轻工制造",
    "家具": "轻工制造", "其他轻工制造": "轻工制造",
    # *** 医药生物 *** ← healthcare
    "化学制药": "医药生物", "生物制品": "医药生物", "医疗器械": "医药生物",
    "医疗服务": "医药生物", "中药": "医药生物", "医药商业": "医药生物",
    # 公用事业
    "电力": "公用事业", "燃气": "公用事业",
    "水务": "公用事业", "环境": "公用事业",
    # 交通运输
    "航空": "交通运输", "公路": "交通运输", "铁路": "交通运输",
    "港口": "交通运输", "航运": "交通运输", "物流": "交通运输",
    # 房地产
    "房地产开发": "房地产", "房地产服务": "房地产",
    # 商贸零售
    "一般零售": "商贸零售", "专业连锁": "商贸零售", "贸易": "商贸零售",
    # 社会服务
    "酒店餐饮": "社会服务", "旅游及景区": "社会服务", "教育": "社会服务",
    "专业服务": "社会服务", "体育": "社会服务",
    # 银行
    "国有大型银行": "银行", "股份制银行": "银行",
    "城商行": "银行", "农商行及农村银行": "银行",
    # 非银金融
    "证券": "非银金融", "保险": "非银金融", "多元金融": "非银金融",
    # 综合
    "综合": "综合",
    # 建筑材料
    "水泥": "建筑材料", "玻璃玻纤": "建筑材料", "建材": "建筑材料",
    # 建筑装饰
    "房屋建设": "建筑装饰", "基础建设": "建筑装饰",
    "专业工程": "建筑装饰", "装修装饰": "建筑装饰",
    # 电力设备
    "电池": "电力设备", "光伏设备": "电力设备", "风电设备": "电力设备",
    "高低压设备": "电力设备", "输变电设备": "电力设备", "其他电力设备": "电力设备",
    # 机械设备
    "通用机械": "机械设备", "专用机械": "机械设备", "仪器仪表": "机械设备",
    "工程机械": "机械设备", "轨交设备": "机械设备",
    # 国防军工
    "航空装备": "国防军工", "航天装备": "国防军工", "地面武器装备": "国防军工",
    "船舶制造": "国防军工", "军工电子": "国防军工",
    # 计算机
    "软件开发": "计算机", "IT服务": "计算机", "计算机设备": "计算机",
    # 传媒
    "游戏": "传媒", "影视院线": "传媒", "互联网媒体": "传媒",
    "出版": "传媒", "广告营销": "传媒",
    # 通信
    "通信服务": "通信", "通信设备": "通信",
    # 煤炭
    "煤炭开采": "煤炭", "焦炭": "煤炭",
    # 石油石化
    "油气开采": "石油石化", "炼化及贸易": "石油石化", "油气设备服务": "石油石化",
    # 环保
    "环保工程及服务": "环保", "资源利用": "环保",
    # 美容护理
    "化妆品": "美容护理", "医疗美容": "美容护理", "个护用品": "美容护理",
}

HEALTHCARE_SW_L1 = {"医药生物"}
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
    """Return the first column whose name contains any keyword (case-insensitive)."""
    for col in df.columns:
        if any(kw.lower() in str(col).lower() for kw in keywords):
            return col
    return None


# ---------------------------------------------------------------------------
# A股 — stock list from East Money spot data
# ---------------------------------------------------------------------------

def fetch_a_basic() -> pd.DataFrame:
    """
    Fetch all A-share stocks (code + name) from East Money.
    Covers Shanghai (SH), Shenzhen (SZ), and Beijing (BJ) exchanges.
    """
    log.info("=== Fetching A股 stock list (东方财富) ===")
    frames = []
    sources = [
        ("沪市A股", lambda: ak.stock_sh_a_spot_em()),
        ("深市A股", lambda: ak.stock_sz_a_spot_em()),
        ("北交所",  lambda: ak.stock_bj_a_spot_em()),
    ]
    for market_name, fn in sources:
        try:
            df = _retry(fn)
            log.info(f"  {market_name}: {len(df):,} stocks | columns: {df.columns.tolist()[:5]}")
            # Columns are ['序号', '代码', '名称', ...] — must find by name, not position
            code_col = _find_col(df, ["代码"]) or df.columns[1]
            name_col = _find_col(df, ["名称"]) or df.columns[2]
            frames.append(pd.DataFrame({
                "stock_code":   df[code_col].astype(str).str.strip().str.zfill(6),
                "company_name": df[name_col].astype(str).str.strip(),
            }))
        except Exception as exc:
            log.warning(f"  {market_name} failed: {exc}")

    if not frames:
        log.error("  All A股 spot endpoints failed")
        return pd.DataFrame(columns=["stock_code", "company_name"])

    result = pd.concat(frames, ignore_index=True).drop_duplicates("stock_code")
    result = result[result["stock_code"].str.fullmatch(r"\d{6}")]
    log.info(f"  Total unique A股: {len(result):,}")
    return result


# ---------------------------------------------------------------------------
# A股 — SW industry via East Money industry boards (filtered + fixed)
# ---------------------------------------------------------------------------

def fetch_sw_map() -> dict[str, tuple[str, str]]:
    """
    Build stock_code → (sw_l1, sw_l2) by iterating only known SW L2 industry boards.

    Key fixes vs. the naive approach:
    - Filter 496 total boards down to ~30 known SW L2 names (skip concept boards)
    - Use the '代码' column for stock codes, NOT columns[0] which is '序号' (rank)
    """
    log.info("=== Fetching A股 SW industry (东方财富, SW L2 boards only) ===")

    try:
        boards = _retry(lambda: ak.stock_board_industry_name_em())
    except Exception as exc:
        log.error(f"  Failed to get board list: {exc}")
        return {}

    name_col  = _find_col(boards, ["板块名称"]) or boards.columns[1]
    all_names = boards[name_col].astype(str).tolist()
    sw_names  = [b for b in all_names if b in SW_L2_TO_L1]

    log.info(f"  Total boards: {len(all_names)} | SW L2 matched: {len(sw_names)}")
    unmatched = set(SW_L2_TO_L1.keys()) - set(sw_names)
    if unmatched:
        log.info(f"  SW L2 names not found in boards (may need dict update): {sorted(unmatched)}")

    code_map: dict[str, tuple[str, str]] = {}
    for i, l2 in enumerate(sw_names, 1):
        l1 = SW_L2_TO_L1[l2]
        try:
            cons     = _retry(lambda b=l2: ak.stock_board_industry_cons_em(symbol=b))
            # '序号' is always columns[0]; find '代码' by name
            code_col = _find_col(cons, ["代码"]) or cons.columns[1]
            added = 0
            for code in cons[code_col].astype(str).str.strip().str.zfill(6):
                if code and code != "nan" and code.isdigit():
                    code_map[code] = (l1, l2)
                    added += 1
            log.info(f"  [{i:>2}/{len(sw_names)}] {l2:12s} ({l1}) → {added} stocks")
        except Exception as exc:
            log.warning(f"  Board '{l2}' failed: {exc}")
        time.sleep(0.3)

    log.info(f"  SW mapping complete: {len(code_map):,} unique stocks")
    return code_map


# ---------------------------------------------------------------------------
# A股 — build final DataFrame
# ---------------------------------------------------------------------------

def build_a_stocks(basic_df: pd.DataFrame,
                   sw_map: dict[str, tuple[str, str]]) -> pd.DataFrame:
    if basic_df.empty:
        log.error("A股 basic data is empty — nothing to build")
        return pd.DataFrame()

    df = basic_df.copy()
    df["sw_industry_l1"] = df["stock_code"].map(lambda c: sw_map.get(c, ("", ""))[0])
    df["sw_industry_l2"] = df["stock_code"].map(lambda c: sw_map.get(c, ("", ""))[1])
    df["market"]             = "A"
    df["csrc_industry_code"] = ""   # CNINFO API changed; not available via free API
    df["csrc_industry_name"] = ""
    df["hk_industry"]        = ""
    df["is_healthcare"]      = df["sw_industry_l1"].isin(HEALTHCARE_SW_L1).astype(int)
    df["updated_at"]         = date.today().isoformat()

    return df[[
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

    # Columns: ['序号', '代码', '名称', '最新价', ...]
    # MUST use column names — '序号' at index 0 is NOT the stock code
    code_col = _find_col(df, ["代码"]) or df.columns[1]
    name_col = _find_col(df, ["名称"]) or df.columns[2]

    result = pd.DataFrame({
        "stock_code":   df[code_col].astype(str).str.strip(),
        "company_name": df[name_col].astype(str).str.strip(),
    })
    industry_col = _find_col(df, ["行业", "板块", "industry", "sector"])
    result["hk_industry"] = df[industry_col].astype(str).str.strip() if industry_col else ""
    return result


# ---------------------------------------------------------------------------
# 港股 — industry classification
# ---------------------------------------------------------------------------

def fetch_hk_industry_map() -> dict[str, str]:
    """
    Build HK stock_code → industry via East Money HK industry boards.
    Falls back silently if the API is unavailable.
    """
    log.info("=== Fetching 港股 industry boards (东方财富) ===")
    code_map: dict[str, str] = {}

    try:
        boards   = _retry(lambda: ak.stock_hk_board_industry_name_em())
        name_col = _find_col(boards, ["板块名称"]) or boards.columns[1]
        board_names = boards[name_col].astype(str).tolist()
        log.info(f"  HK boards: {len(board_names)}")

        for i, board in enumerate(board_names, 1):
            try:
                cons     = _retry(lambda b=board: ak.stock_hk_board_industry_cons_em(symbol=b))
                code_col = _find_col(cons, ["代码"]) or cons.columns[1]
                for code in cons[code_col].astype(str).str.strip():
                    if code and code != "nan":
                        code_map[code] = board
            except Exception as exc:
                log.warning(f"  HK board '{board}' failed: {exc}")
            if i % 10 == 0 or i == len(board_names):
                log.info(f"  Progress: {i}/{len(board_names)} | {len(code_map):,} stocks mapped")
            time.sleep(0.3)

    except AttributeError:
        log.info("  stock_hk_board_industry_name_em not in this akshare version — industry will be empty")
    except Exception as exc:
        log.warning(f"  HK industry board fetch failed: {exc}")

    log.info(f"  HK industry mapped: {len(code_map):,} stocks")
    return code_map


# ---------------------------------------------------------------------------
# 港股 — build final DataFrame
# ---------------------------------------------------------------------------

def build_hk_stocks(hk_df: pd.DataFrame, industry_map: dict[str, str]) -> pd.DataFrame:
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
    df["is_healthcare"] = df["hk_industry"].str.lower().fillna("").apply(
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
    basic_df = fetch_a_basic()
    sw_map   = fetch_sw_map()
    a_df     = build_a_stocks(basic_df, sw_map)

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
    total = len(all_df)

    log.info("")
    log.info("=" * 60)
    log.info("Summary")
    log.info("=" * 60)
    log.info(f"{'市场':<6} {'医疗':>6} {'非医疗':>8} {'合计':>8}")
    log.info("-" * 34)
    if not a_df.empty:
        log.info(f"{'A股':<6} {a_hc:>6,} {len(a_df)-a_hc:>8,} {len(a_df):>8,}")
    if not hk_df.empty:
        log.info(f"{'港股':<6} {hk_hc:>6,} {len(hk_df)-hk_hc:>8,} {len(hk_df):>8,}")
    log.info(f"{'合计':<6} {a_hc+hk_hc:>6,} {total-(a_hc+hk_hc):>8,} {total:>8,}")
    log.info("")
    log.info(f"Output: {OUTPUT_DIR.resolve()}/")
    for p in (a_path, hk_path, all_path):
        log.info(f"  {p.name}")


if __name__ == "__main__":
    main()
