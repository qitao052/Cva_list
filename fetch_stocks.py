#!/usr/bin/env python3
"""
Fetch A-share (A股) and HK-listed (港股) companies with industry classification.

A股  : CSRC industry (证监会行业, from CNINFO 巨潮资讯)
       SW   industry (申万行业,   from East Money 东方财富 industry boards)
港股  : Hang Seng industry classification (恒生行业, from East Money)

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

# SW L2 → L1 mapping (covers all 31 SW-2021 first-level industries)
SW_L2_TO_L1: dict[str, str] = {
    # 农林牧渔
    "种植业": "农林牧渔", "林业": "农林牧渔", "养殖业": "农林牧渔",
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
    "造纸": "轻工制造", "包装印刷": "轻工制造", "家具": "轻工制造",
    "其他轻工制造": "轻工制造",
    # *** 医药生物 *** (healthcare)
    "化学制药": "医药生物", "生物制品": "医药生物", "医疗器械": "医药生物",
    "医疗服务": "医药生物", "中药": "医药生物", "医药商业": "医药生物",
    # 公用事业
    "电力": "公用事业", "燃气": "公用事业", "水务": "公用事业", "环境": "公用事业",
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
    "国有大型银行": "银行", "股份制银行": "银行", "城商行": "银行", "农商行及农村银行": "银行",
    # 非银金融
    "证券": "非银金融", "保险": "非银金融", "多元金融": "非银金融",
    # 综合
    "综合": "综合",
    # 建筑材料
    "水泥": "建筑材料", "玻璃玻纤": "建筑材料", "建材": "建筑材料",
    # 建筑装饰
    "房屋建设": "建筑装饰", "基础建设": "建筑装饰", "专业工程": "建筑装饰",
    "装修装饰": "建筑装饰",
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
    "游戏": "传媒", "影视院线": "传媒", "互联网媒体": "传媒", "出版": "传媒", "广告营销": "传媒",
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

# Healthcare identification rules
HEALTHCARE_SW_L1      = {"医药生物"}
HEALTHCARE_CSRC_CODES = {"C27"}           # 医药制造业
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

def _is_healthcare(sw_l1: str = "", csrc_code: str = "", hk_industry: str = "") -> int:
    if sw_l1 in HEALTHCARE_SW_L1:
        return 1
    if csrc_code and any(csrc_code.startswith(c) for c in HEALTHCARE_CSRC_CODES):
        return 1
    if hk_industry:
        low = hk_industry.lower()
        if any(kw.lower() in low for kw in HEALTHCARE_HK_KEYWORDS):
            return 1
    return 0


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


# ---------------------------------------------------------------------------
# A股 — CSRC industry (证监会行业)
# ---------------------------------------------------------------------------

def fetch_a_csrc() -> pd.DataFrame:
    """
    Fetch all A-share stocks with CSRC industry from CNINFO (巨潮资讯).
    Returns normalised DataFrame: stock_code, company_name,
                                   csrc_industry_code, csrc_industry_name
    """
    log.info("=== Fetching A股 CSRC industry (CNINFO 巨潮资讯) ===")
    frames: list[pd.DataFrame] = []

    for market in ["沪市A股", "深市A股", "北交所A股"]:
        try:
            df = _retry(lambda m=market: ak.stock_industry_category_cninfo(symbol=m))
            frames.append(df)
            log.info(f"  {market}: {len(df):,} stocks")
        except Exception as exc:
            log.warning(f"  {market} unavailable: {exc}")
        time.sleep(1.0)

    if not frames:
        log.error("  No CSRC data obtained — returning empty DataFrame")
        return pd.DataFrame(columns=["stock_code", "company_name",
                                     "csrc_industry_code", "csrc_industry_name"])

    raw = pd.concat(frames, ignore_index=True)
    log.info(f"  CNINFO columns: {raw.columns.tolist()}")

    # CNINFO returns: 证券代码, 证券简称, [门类代码, 门类名], [大类代码, 大类名], [中类代码, 中类名]
    # We use 行业大类 (index 4/5) as it corresponds to e.g. C27 医药制造业.
    # Fall back to 门类 (index 2/3) if the table is shorter.
    n = raw.shape[1]
    code_idx  = 4 if n >= 6 else 2
    name_idx  = 5 if n >= 6 else 3

    result = pd.DataFrame({
        "stock_code":         raw.iloc[:, 0].astype(str).str.strip().str.zfill(6),
        "company_name":       raw.iloc[:, 1].astype(str).str.strip(),
        "csrc_industry_code": raw.iloc[:, code_idx].astype(str).str.strip(),
        "csrc_industry_name": raw.iloc[:, name_idx].astype(str).str.strip(),
    })
    return result


# ---------------------------------------------------------------------------
# A股 — SW industry (申万行业)
# ---------------------------------------------------------------------------

def fetch_sw_map() -> dict[str, tuple[str, str]]:
    """
    Build stock_code → (sw_l1, sw_l2) mapping by iterating East Money industry
    boards (东方财富行业板块).  East Money boards correspond to SW L2 categories.
    """
    log.info("=== Fetching A股 SW industry (东方财富行业板块) ===")

    try:
        boards = _retry(lambda: ak.stock_board_industry_name_em())
    except Exception as exc:
        log.error(f"  Cannot fetch board list: {exc}")
        return {}

    name_col = "板块名称" if "板块名称" in boards.columns else boards.columns[1]
    board_names: list[str] = boards[name_col].astype(str).tolist()
    log.info(f"  Industry boards found: {len(board_names)}")

    code_map: dict[str, tuple[str, str]] = {}
    for i, l2 in enumerate(board_names, 1):
        l1 = SW_L2_TO_L1.get(l2, l2)   # unknown boards default to L1 = L2
        try:
            cons     = _retry(lambda b=l2: ak.stock_board_industry_cons_em(symbol=b))
            code_col = cons.columns[0]
            for code in cons[code_col].astype(str).str.strip().str.zfill(6):
                if code and code != "nan":
                    code_map[code] = (l1, l2)
        except Exception as exc:
            log.warning(f"  Board '{l2}' failed: {exc}")

        if i % 20 == 0 or i == len(board_names):
            log.info(f"  Progress: {i}/{len(board_names)} boards | {len(code_map):,} stocks mapped")
        time.sleep(0.3)

    log.info(f"  SW mapping complete: {len(code_map):,} stocks")
    return code_map


# ---------------------------------------------------------------------------
# A股 — build final DataFrame
# ---------------------------------------------------------------------------

def build_a_stocks(csrc_df: pd.DataFrame,
                   sw_map: dict[str, tuple[str, str]]) -> pd.DataFrame:
    df = csrc_df.copy()
    df["sw_industry_l1"] = df["stock_code"].map(lambda c: sw_map.get(c, ("", ""))[0])
    df["sw_industry_l2"] = df["stock_code"].map(lambda c: sw_map.get(c, ("", ""))[1])
    df["market"]      = "A"
    df["hk_industry"] = ""
    df["is_healthcare"] = df.apply(
        lambda r: _is_healthcare(
            sw_l1=r["sw_industry_l1"],
            csrc_code=r["csrc_industry_code"],
        ),
        axis=1,
    )
    df["updated_at"] = date.today().isoformat()
    return df[[
        "stock_code", "company_name", "market",
        "sw_industry_l1", "sw_industry_l2",
        "csrc_industry_code", "csrc_industry_name",
        "hk_industry", "is_healthcare", "updated_at",
    ]]


# ---------------------------------------------------------------------------
# 港股 — stock list + industry
# ---------------------------------------------------------------------------

def fetch_hk_stocks() -> pd.DataFrame:
    """
    Fetch HK-listed stocks from East Money (东方财富).
    Tries to capture industry column if present in the spot data.
    """
    log.info("=== Fetching 港股 stock list (东方财富) ===")
    try:
        df = _retry(lambda: ak.stock_hk_spot_em())
        log.info(f"  HK stocks: {len(df):,} | columns: {df.columns.tolist()}")
    except Exception as exc:
        log.error(f"  HK stock list unavailable: {exc}")
        return pd.DataFrame()

    code_col = df.columns[0]
    name_col = df.columns[1]

    result = pd.DataFrame({
        "stock_code":   df[code_col].astype(str).str.strip(),
        "company_name": df[name_col].astype(str).str.strip(),
    })

    # Look for an industry column by keyword
    industry_col = next(
        (c for c in df.columns if any(k in str(c).lower() for k in ["行业", "板块", "industry", "sector"])),
        None,
    )
    if industry_col:
        result["hk_industry"] = df[industry_col].astype(str).str.strip()
        log.info(f"  Industry column found: '{industry_col}'")
    else:
        result["hk_industry"] = ""
        log.info("  No industry column in spot data; will fetch separately")

    return result


def fetch_hk_industry_map() -> dict[str, str]:
    """
    Build HK stock_code → industry mapping via East Money HK industry boards.
    Falls back silently if the API endpoint is unavailable.
    """
    log.info("=== Fetching 港股 industry boards (东方财富) ===")
    code_map: dict[str, str] = {}

    # East Money exposes HK industry boards through this pair of functions.
    # If they are absent in the installed akshare version the AttributeError
    # is caught and we fall through with an empty map.
    try:
        boards   = _retry(lambda: ak.stock_hk_board_industry_name_em())
        name_col = boards.columns[1] if len(boards.columns) > 1 else boards.columns[0]
        board_names: list[str] = boards[name_col].astype(str).tolist()
        log.info(f"  HK industry boards: {len(board_names)}")

        for i, board in enumerate(board_names, 1):
            try:
                cons     = _retry(lambda b=board: ak.stock_hk_board_industry_cons_em(symbol=b))
                code_col = cons.columns[0]
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
        log.warning(f"  HK industry board fetch failed: {exc}")

    log.info(f"  HK industry mapped: {len(code_map):,} stocks")
    return code_map


# ---------------------------------------------------------------------------
# 港股 — build final DataFrame
# ---------------------------------------------------------------------------

def build_hk_stocks(hk_df: pd.DataFrame,
                    industry_map: dict[str, str]) -> pd.DataFrame:
    if hk_df.empty:
        return pd.DataFrame()

    df = hk_df.copy()

    # Supplement industry from board map if spot data had none
    if df["hk_industry"].eq("").all() and industry_map:
        df["hk_industry"] = df["stock_code"].map(industry_map).fillna("")

    df["market"]            = "HK"
    df["sw_industry_l1"]    = ""
    df["sw_industry_l2"]    = ""
    df["csrc_industry_code"] = ""
    df["csrc_industry_name"] = ""
    df["is_healthcare"] = df["hk_industry"].apply(
        lambda i: _is_healthcare(hk_industry=i)
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
    sw_map  = fetch_sw_map()
    a_df    = build_a_stocks(csrc_df, sw_map)

    # ── 港股 ─────────────────────────────────────────────────────────────
    hk_raw          = fetch_hk_stocks()
    hk_industry_map = fetch_hk_industry_map()
    hk_df           = build_hk_stocks(hk_raw, hk_industry_map)

    # ── Merge & save ─────────────────────────────────────────────────────
    all_df = pd.concat([a_df, hk_df], ignore_index=True)

    a_path   = OUTPUT_DIR / f"a_stocks_{today}.csv"
    hk_path  = OUTPUT_DIR / f"hk_stocks_{today}.csv"
    all_path = OUTPUT_DIR / f"all_stocks_{today}.csv"

    a_df.to_csv(a_path,   index=False, encoding="utf-8")
    hk_df.to_csv(hk_path,  index=False, encoding="utf-8")
    all_df.to_csv(all_path, index=False, encoding="utf-8")

    # ── Summary ──────────────────────────────────────────────────────────
    log.info("")
    log.info("=" * 60)
    log.info("Summary")
    log.info("=" * 60)
    log.info(f"A股  : {len(a_df):>5,} stocks | healthcare: {a_df['is_healthcare'].sum():>4}")
    log.info(f"港股 : {len(hk_df):>5,} stocks | healthcare: {hk_df['is_healthcare'].sum():>4}")
    log.info(f"Total: {len(all_df):>5,} stocks | healthcare: {all_df['is_healthcare'].sum():>4}")
    log.info("")
    log.info(f"Output directory: {OUTPUT_DIR.resolve()}/")
    log.info(f"  {a_path.name}")
    log.info(f"  {hk_path.name}")
    log.info(f"  {all_path.name}")


if __name__ == "__main__":
    main()
