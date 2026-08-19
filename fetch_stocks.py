#!/usr/bin/env python3
"""
Fetch A-share and HK-listed companies with industry classification.

A股 数据来源（官方交易所挂牌列表）:
  深交所: stock_info_sz_name_code(symbol="A股列表")
          → 板块, A股代码, A股简称, A股上市日期, A股总股本, A股流通股本, 所属行业
  上交所: stock_info_sh_name_code(symbol="主板A股"|"科创板")
          → 证券代码, 证券简称, 证券全称, 公司简称, 公司全称, 上市日期  (无行业列)
  北交所: stock_info_bj_name_code()
          → 证券代码, 证券简称, 总股本, 流通股本, 上市日期, 所属行业, 地区, 报告日期

港股 数据来源:
  HKEX 官方 ListOfSecurities.xlsx（含 Sub-Sector 行业分类）
  → https://www.hkex.com.hk/eng/services/trading/securities/securitieslists/ListOfSecurities.xlsx
  备用: stock_hk_main_board_spot_em()

Output: ./output/
"""

import io
import logging
import time
from datetime import date
from pathlib import Path

import akshare as ak
import pandas as pd
import requests

OUTPUT_DIR = Path("output")

# 申万二级行业 → 申万一级行业（2021版）
SW_L2_TO_L1: dict[str, str] = {
    "种植业与林业": "农林牧渔", "养殖业": "农林牧渔", "渔业": "农林牧渔", "农业综合": "农林牧渔",
    "化学原料": "基础化工", "化学制品": "基础化工", "化学纤维": "基础化工",
    "橡胶": "基础化工", "塑料": "基础化工", "化工合成材料": "基础化工",
    "农化": "基础化工", "涂料油墨": "基础化工", "化工新材料": "基础化工", "其他化工": "基础化工",
    "普钢": "钢铁", "特钢": "钢铁",
    "工业金属": "有色金属", "能源金属": "有色金属", "贵金属": "有色金属",
    "小金属": "有色金属", "金属新材料": "有色金属",
    "半导体": "电子", "光学光电子": "电子", "消费电子": "电子",
    "元件": "电子", "其他电子": "电子", "电子化学品": "电子",
    "乘用车": "汽车", "商用车": "汽车", "汽车零部件": "汽车", "汽车销售及服务": "汽车",
    "白色家电": "家用电器", "小家电": "家用电器", "厨卫电器": "家用电器",
    "黑色家电": "家用电器", "家电零部件": "家用电器",
    "白酒": "食品饮料", "啤酒": "食品饮料", "饮料乳品": "食品饮料",
    "食品加工": "食品饮料", "调味发酵品": "食品饮料", "休闲食品": "食品饮料",
    "纺织制造": "纺织服装", "服装家纺": "纺织服装",
    "造纸": "轻工制造", "包装印刷": "轻工制造", "家具": "轻工制造", "其他轻工制造": "轻工制造",
    # *** 医药生物 ***
    "化学制药": "医药生物", "生物制品": "医药生物", "医疗器械": "医药生物",
    "医疗服务": "医药生物", "中药": "医药生物", "医药商业": "医药生物",
    "电力": "公用事业", "燃气": "公用事业", "水务": "公用事业", "环境": "公用事业",
    "航空": "交通运输", "公路": "交通运输", "铁路": "交通运输",
    "港口": "交通运输", "航运": "交通运输", "物流": "交通运输",
    "房地产开发": "房地产", "房地产服务": "房地产",
    "一般零售": "商贸零售", "专业连锁": "商贸零售", "贸易": "商贸零售",
    "酒店餐饮": "社会服务", "旅游及景区": "社会服务", "教育": "社会服务",
    "专业服务": "社会服务", "体育": "社会服务",
    "国有大型银行": "银行", "股份制银行": "银行", "城商行": "银行", "农商行及农村银行": "银行",
    "证券": "非银金融", "保险": "非银金融", "多元金融": "非银金融",
    "综合": "综合",
    "水泥": "建筑材料", "玻璃玻纤": "建筑材料", "建材": "建筑材料",
    "房屋建设": "建筑装饰", "基础建设": "建筑装饰", "专业工程": "建筑装饰", "装修装饰": "建筑装饰",
    "电池": "电力设备", "光伏设备": "电力设备", "风电设备": "电力设备",
    "高低压设备": "电力设备", "输变电设备": "电力设备", "其他电力设备": "电力设备",
    "通用机械": "机械设备", "专用机械": "机械设备", "仪器仪表": "机械设备",
    "工程机械": "机械设备", "轨交设备": "机械设备",
    "航空装备": "国防军工", "航天装备": "国防军工", "地面武器装备": "国防军工",
    "船舶制造": "国防军工", "军工电子": "国防军工",
    "软件开发": "计算机", "IT服务": "计算机", "计算机设备": "计算机",
    "游戏": "传媒", "影视院线": "传媒", "互联网媒体": "传媒", "出版": "传媒", "广告营销": "传媒",
    "通信服务": "通信", "通信设备": "通信",
    "煤炭开采": "煤炭", "焦炭": "煤炭",
    "油气开采": "石油石化", "炼化及贸易": "石油石化", "油气设备服务": "石油石化",
    "环保工程及服务": "环保", "资源利用": "环保",
    "化妆品": "美容护理", "医疗美容": "美容护理", "个护用品": "美容护理",
}

HEALTHCARE_SW_L1   = {"医药生物"}
HEALTHCARE_CSRC_KW = ["医药", "医疗", "卫生"]
# HKEX Sub-Sector 中属于医疗/制药的分类（ICB体系）
HEALTHCARE_HK_SECTORS = {
    "Pharmaceuticals & Biotechnology",
    "Health Care Equipment & Services",
    "Pharmaceuticals, Biotechnology & Life Sciences",
    "Health Care",
    "Biotechnology",
    "Pharmaceuticals",
    "Medical Equipment & Services",
    "Biotechnology & Medical Research",
}

HKEX_XLSX_URL = (
    "https://www.hkex.com.hk/eng/services/trading/securities/"
    "securitieslists/ListOfSecurities.xlsx"
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def _retry(fn, retries=3, base_delay=1.0):
    for i in range(retries):
        try:
            return fn()
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(base_delay * (i + 1))
            log.warning(f"重试 {i+1}: {e}")


# ---------------------------------------------------------------------------
# A股 官方挂牌列表
# ---------------------------------------------------------------------------

def fetch_a_official() -> pd.DataFrame:
    log.info("=== A股 官方挂牌列表 ===")
    frames = []

    # 深交所 (有行业)
    try:
        df = _retry(lambda: ak.stock_info_sz_name_code(symbol="A股列表"))
        log.info(f"  深交所: {len(df):,} 家 | 列: {df.columns.tolist()}")
        frames.append(pd.DataFrame({
            "stock_code":         df["A股代码"].astype(str).str.zfill(6),
            "company_name":       df["A股简称"].astype(str),
            "csrc_industry_name": df["所属行业"].astype(str),
            "exchange":           "SZ",
        }))
    except Exception as e:
        log.error(f"  深交所 失败: {e}")

    # 上交所 主板 + 科创板 (无行业)
    for segment in ["主板A股", "科创板"]:
        try:
            df = _retry(lambda s=segment: ak.stock_info_sh_name_code(symbol=s))
            log.info(f"  上交所 {segment}: {len(df):,} 家 | 列: {df.columns.tolist()}")
            frames.append(pd.DataFrame({
                "stock_code":         df["证券代码"].astype(str).str.zfill(6),
                "company_name":       df["证券简称"].astype(str),
                "csrc_industry_name": "",
                "exchange":           "SH",
            }))
        except Exception as e:
            log.error(f"  上交所 {segment} 失败: {e}")

    # 北交所 (有行业)
    try:
        df = _retry(lambda: ak.stock_info_bj_name_code())
        log.info(f"  北交所: {len(df):,} 家 | 列: {df.columns.tolist()}")
        frames.append(pd.DataFrame({
            "stock_code":         df["证券代码"].astype(str).str.zfill(6),
            "company_name":       df["证券简称"].astype(str),
            "csrc_industry_name": df["所属行业"].astype(str),
            "exchange":           "BJ",
        }))
    except Exception as e:
        log.error(f"  北交所 失败: {e}")

    if not frames:
        return pd.DataFrame(columns=["stock_code", "company_name", "csrc_industry_name", "exchange"])

    result = pd.concat(frames, ignore_index=True).drop_duplicates("stock_code")
    result = result[result["stock_code"].str.fullmatch(r"\d{6}")]
    log.info(f"  A股合计: {len(result):,} 家")
    return result


# ---------------------------------------------------------------------------
# A股 申万行业
# ---------------------------------------------------------------------------

def fetch_sw_map() -> dict[str, tuple[str, str]]:
    """stock_code → (sw_l1, sw_l2)"""
    log.info("=== A股 申万行业板块 ===")
    try:
        boards = _retry(lambda: ak.stock_board_industry_name_em())
        log.info(f"  板块列表列名: {boards.columns.tolist()}")
    except Exception as e:
        log.error(f"  获取板块列表失败: {e}")
        return {}

    name_col  = "板块名称" if "板块名称" in boards.columns else boards.columns[1]
    all_names = set(boards[name_col].astype(str).tolist())
    sw_names  = [b for b in SW_L2_TO_L1 if b in all_names]
    missed    = [b for b in SW_L2_TO_L1 if b not in all_names]
    log.info(f"  总板块: {len(all_names)} | SW二级匹配: {len(sw_names)} | 未匹配: {missed}")

    code_map: dict[str, tuple[str, str]] = {}
    for i, l2 in enumerate(sw_names, 1):
        l1 = SW_L2_TO_L1[l2]
        try:
            cons = _retry(lambda b=l2: ak.stock_board_industry_cons_em(symbol=b))
            for code in cons["代码"].astype(str).str.zfill(6):
                if code.isdigit():
                    code_map[code] = (l1, l2)
            log.info(f"  [{i:>2}/{len(sw_names)}] {l2:14s}({l1}) {len(cons)}只")
        except Exception as e:
            log.warning(f"  板块 '{l2}' 失败: {e}")
        time.sleep(0.3)

    log.info(f"  SW行业映射: {len(code_map):,} 只")
    return code_map


# ---------------------------------------------------------------------------
# A股 合并
# ---------------------------------------------------------------------------

def build_a_stocks(official_df: pd.DataFrame, sw_map: dict) -> pd.DataFrame:
    if official_df.empty:
        return pd.DataFrame()

    df = official_df.copy()
    df["sw_industry_l1"] = df["stock_code"].map(lambda c: sw_map.get(c, ("", ""))[0])
    df["sw_industry_l2"] = df["stock_code"].map(lambda c: sw_map.get(c, ("", ""))[1])
    df["market"]             = "A"
    df["csrc_industry_code"] = ""
    df["hk_industry"]        = ""

    sw_hc   = df["sw_industry_l1"].isin(HEALTHCARE_SW_L1)
    csrc_hc = df["csrc_industry_name"].apply(
        lambda x: any(kw in str(x) for kw in HEALTHCARE_CSRC_KW)
    )
    df["is_healthcare"] = (sw_hc | csrc_hc).astype(int)
    df["updated_at"]    = date.today().isoformat()

    return df[[
        "stock_code", "company_name", "market",
        "sw_industry_l1", "sw_industry_l2",
        "csrc_industry_code", "csrc_industry_name",
        "hk_industry", "is_healthcare", "updated_at",
    ]]


# ---------------------------------------------------------------------------
# 港股 — 首选: HKEX 官方 ListOfSecurities.xlsx（含 Sub-Sector 行业）
# ---------------------------------------------------------------------------

def _find_header_row(raw: pd.DataFrame) -> int:
    """找到包含 'Stock Code' 或 '股份代號' 的行号作为表头"""
    for i, row in raw.iterrows():
        vals = [str(v).strip() for v in row.values if pd.notna(v)]
        if any("Stock Code" in v or "股份代號" in v for v in vals):
            return i
    raise ValueError(f"找不到表头行，前5行内容:\n{raw.head(5).to_string()}")


def _find_col(df: pd.DataFrame, *keywords) -> str | None:
    """在 df.columns 中找第一个包含任意关键词的列名"""
    for col in df.columns:
        c = str(col).strip()
        if any(kw.lower() in c.lower() for kw in keywords):
            return col
    return None


def fetch_hk_from_hkex() -> pd.DataFrame:
    """
    从 HKEX 官方 ListOfSecurities.xlsx 获取港股列表及行业分类。
    文件包含所有上市证券（股票/权证/牛熊证/ETF等），过滤到 Equity 类型。
    Sub-Sector 列为 HKEX 行业分类（ICB 体系）。
    """
    log.info(f"  下载 HKEX ListOfSecurities.xlsx ...")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*",
        "Referer": "https://www.hkex.com.hk/",
    }
    resp = requests.get(HKEX_XLSX_URL, headers=headers, timeout=60)
    resp.raise_for_status()
    log.info(f"  下载成功: {len(resp.content):,} bytes")

    content = resp.content

    # 先读全文不带表头，找表头所在行
    raw = pd.read_excel(io.BytesIO(content), header=None, sheet_name=0)
    log.info(f"  原始表格: {raw.shape[0]} 行 × {raw.shape[1]} 列")
    log.info(f"  前4行内容:\n{raw.head(4).to_string()}")

    header_row = _find_header_row(raw)
    log.info(f"  表头在第 {header_row} 行")

    df = pd.read_excel(io.BytesIO(content), header=header_row, sheet_name=0)
    log.info(f"  解析后列名: {df.columns.tolist()}")

    # 定位各列
    code_col     = _find_col(df, "Stock Code", "股份代號")
    name_en_col  = _find_col(df, "Name of Listed Company")
    category_col = _find_col(df, "Category", "類別")
    sector_col   = _find_col(df, "Sub-Sector", "Sub Sector", "Subsector", "行業")

    log.info(f"  code={code_col}, name={name_en_col}, category={category_col}, sector={sector_col}")

    if not code_col:
        raise ValueError(f"找不到股份代號列，实际列名: {df.columns.tolist()}")

    # 过滤到 Equity Securities（股票），排除权证/牛熊证/ETF等
    if category_col:
        equity_mask = df[category_col].astype(str).str.contains(
            r"Equity|股份", case=False, na=False
        )
        df = df[equity_mask].reset_index(drop=True)
        log.info(f"  过滤 Equity 后: {len(df):,} 家")

    codes = df[code_col].astype(str).str.strip().str.extract(r"(\d+)")[0].str.zfill(5)

    result = pd.DataFrame({
        "stock_code":   codes,
        "company_name": df[name_en_col].astype(str).str.strip() if name_en_col else "",
        "hk_industry":  df[sector_col].astype(str).str.strip() if sector_col else "",
    })

    result = result[result["stock_code"].str.fullmatch(r"\d{5}")]
    result = result[result["stock_code"] != "00000"]
    result = result.drop_duplicates("stock_code").reset_index(drop=True)

    log.info(f"  港股（Equity）: {len(result):,} 家")
    if sector_col:
        top_sectors = result["hk_industry"].value_counts().head(10)
        log.info(f"  行业分布前10:\n{top_sectors.to_string()}")

    return result


def fetch_hk_stocks() -> pd.DataFrame:
    """
    港股列表 + 行业分类。
    优先从 HKEX 官方 xlsx 获取（含真实 Sub-Sector 行业）。
    失败时退回 AKShare stock_hk_main_board_spot_em()（无行业列）。
    """
    log.info("=== 港股 挂牌列表 ===")

    try:
        return fetch_hk_from_hkex()
    except Exception as e:
        log.warning(f"  HKEX xlsx 失败: {e}")
        log.warning("  退回 AKShare stock_hk_main_board_spot_em()（无行业分类）...")

    try:
        df = _retry(lambda: ak.stock_hk_main_board_spot_em())
        log.info(f"  AKShare 港股主板: {len(df):,} 家 | 列: {df.columns.tolist()}")
        return pd.DataFrame({
            "stock_code":   df["代码"].astype(str).str.strip().str.zfill(5),
            "company_name": df["名称"].astype(str).str.strip(),
            "hk_industry":  "",
        })
    except Exception as e2:
        log.error(f"  AKShare 港股接口也失败: {e2}")
        return pd.DataFrame()


def build_hk_stocks(hk_df: pd.DataFrame) -> pd.DataFrame:
    if hk_df.empty:
        return pd.DataFrame()

    df = hk_df.copy()
    df["market"]             = "HK"
    df["sw_industry_l1"]     = ""
    df["sw_industry_l2"]     = ""
    df["csrc_industry_code"] = ""
    df["csrc_industry_name"] = ""

    if df["hk_industry"].str.strip().ne("").any():
        df["is_healthcare"] = df["hk_industry"].isin(HEALTHCARE_HK_SECTORS).astype(int)
        log.info(f"  港股医疗（Sub-Sector 精确匹配）: {df['is_healthcare'].sum():,} 家")
    else:
        df["is_healthcare"] = 0
        log.warning("  港股行业数据为空，is_healthcare 全部设为 0")

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

def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    today = date.today().isoformat()

    log.info("=" * 60)
    log.info("Stock Data Fetcher — A股 + 港股")
    log.info("=" * 60)

    official_df = fetch_a_official()
    sw_map      = fetch_sw_map()
    a_df        = build_a_stocks(official_df, sw_map)

    hk_raw = fetch_hk_stocks()
    hk_df  = build_hk_stocks(hk_raw)

    all_df = pd.concat([a_df, hk_df], ignore_index=True)

    a_path   = OUTPUT_DIR / f"a_stocks_{today}.csv"
    hk_path  = OUTPUT_DIR / f"hk_stocks_{today}.csv"
    all_path = OUTPUT_DIR / f"all_stocks_{today}.csv"
    a_df.to_csv(a_path,    index=False, encoding="utf-8-sig")
    hk_df.to_csv(hk_path,  index=False, encoding="utf-8-sig")
    all_df.to_csv(all_path, index=False, encoding="utf-8-sig")

    a_hc  = int(a_df["is_healthcare"].sum())  if not a_df.empty  else 0
    hk_hc = int(hk_df["is_healthcare"].sum()) if not hk_df.empty else 0
    total = len(all_df)

    log.info("")
    log.info("=" * 60)
    log.info("汇总")
    log.info("=" * 60)
    log.info(f"{'市场':<6} {'医疗':>6} {'非医疗':>8} {'合计':>8}")
    log.info("-" * 34)
    if not a_df.empty:
        log.info(f"{'A股':<6} {a_hc:>6,} {len(a_df)-a_hc:>8,} {len(a_df):>8,}")
    if not hk_df.empty:
        log.info(f"{'港股':<6} {hk_hc:>6,} {len(hk_df)-hk_hc:>8,} {len(hk_df):>8,}")
    log.info(f"{'合计':<6} {a_hc+hk_hc:>6,} {total-(a_hc+hk_hc):>8,} {total:>8,}")
    log.info(f"\n文件已保存至: {OUTPUT_DIR.resolve()}/")
    log.info(f"  {a_path.name}")
    log.info(f"  {hk_path.name}")
    log.info(f"  {all_path.name}")


if __name__ == "__main__":
    main()
