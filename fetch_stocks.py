#!/usr/bin/env python3
"""
Fetch A-share (A股) and HK-listed (港股) companies with industry classification.

Data sources (verified from AKShare documentation):
  A股 list   : stock_zh_a_spot_em()           — 沪深京全部A股，一次调用
                columns: 序号, 代码, 名称, ...
  A股 SW行业 : stock_board_industry_cons_em()  — 行业板块成分股
                columns: 序号, 代码, 名称, ... (序号在第0列，代码在第1列)
  港股 list  : stock_hk_spot_em()             — 全部港股
                columns: 序号, 代码, 名称, ... (无行业列)
  港股行业   : 东方财富暂无可用行业分类接口，用公司名关键词兜底

Output: CSV files in ./output/
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

# 申万二级行业 → 申万一级行业（2021版）
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
    # *** 医药生物 *** ← 医疗行业
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

# 港股无申万行业，用公司名/行业名关键词识别
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


# ---------------------------------------------------------------------------
# A股 — 股票列表
# 文档确认：stock_zh_a_spot_em() 一次返回全部沪深京A股
# 列名确认：序号(col 0), 代码(col 1), 名称(col 2), ...
# ---------------------------------------------------------------------------

def fetch_a_basic() -> pd.DataFrame:
    log.info("=== Fetching A股 stock list (stock_zh_a_spot_em) ===")
    try:
        df = _retry(lambda: ak.stock_zh_a_spot_em())
        log.info(f"  返回行数: {len(df):,} | 列名: {df.columns.tolist()[:5]}")
    except Exception as exc:
        log.error(f"  失败: {exc}")
        return pd.DataFrame(columns=["stock_code", "company_name"])

    result = pd.DataFrame({
        "stock_code":   df["代码"].astype(str).str.strip().str.zfill(6),
        "company_name": df["名称"].astype(str).str.strip(),
    })
    result = result[result["stock_code"].str.fullmatch(r"\d{6}")]
    log.info(f"  有效A股: {len(result):,}")
    return result


# ---------------------------------------------------------------------------
# A股 — 申万行业（通过东方财富行业板块成分股）
# 文档确认：stock_board_industry_cons_em() 列名 序号(0), 代码(1), 名称(2)
# 策略：只遍历 SW_L2_TO_L1 中已知的申万二级行业板块，跳过概念板块
# ---------------------------------------------------------------------------

def fetch_sw_map() -> dict[str, tuple[str, str]]:
    log.info("=== Fetching A股 SW行业 (stock_board_industry_cons_em, 仅申万L2板块) ===")

    # 先拿全部板块列表，确认哪些名称实际存在
    try:
        boards = _retry(lambda: ak.stock_board_industry_name_em())
        log.info(f"  board列名: {boards.columns.tolist()}")
    except Exception as exc:
        log.error(f"  获取板块列表失败: {exc}")
        return {}

    # 板块名称列（东方财富通常叫"板块名称"）
    name_col  = "板块名称" if "板块名称" in boards.columns else boards.columns[1]
    all_names = set(boards[name_col].astype(str).tolist())

    # 只处理与申万二级名称精确匹配的板块
    sw_names  = [b for b in SW_L2_TO_L1 if b in all_names]
    missed    = [b for b in SW_L2_TO_L1 if b not in all_names]

    log.info(f"  东方财富板块总数: {len(all_names)} | SW L2匹配: {len(sw_names)} | 未匹配: {len(missed)}")
    if missed:
        log.info(f"  未匹配的SW L2名称（可能板块改名）: {missed}")

    code_map: dict[str, tuple[str, str]] = {}
    for i, l2 in enumerate(sw_names, 1):
        l1 = SW_L2_TO_L1[l2]
        try:
            cons = _retry(lambda b=l2: ak.stock_board_industry_cons_em(symbol=b))
            # 文档确认：序号在col 0，代码在col 1
            # 直接用列名"代码"，比位置索引更可靠
            added = 0
            for code in cons["代码"].astype(str).str.strip().str.zfill(6):
                if code.isdigit() and len(code) == 6:
                    code_map[code] = (l1, l2)
                    added += 1
            log.info(f"  [{i:>2}/{len(sw_names)}] {l2:14s} → {l1}  ({added} stocks)")
        except Exception as exc:
            log.warning(f"  板块 '{l2}' 失败: {exc}")
        time.sleep(0.3)

    log.info(f"  SW行业映射完成: {len(code_map):,} 只股票")
    return code_map


# ---------------------------------------------------------------------------
# A股 — 合并
# ---------------------------------------------------------------------------

def build_a_stocks(basic_df: pd.DataFrame,
                   sw_map: dict[str, tuple[str, str]]) -> pd.DataFrame:
    if basic_df.empty:
        log.error("A股基础数据为空")
        return pd.DataFrame()

    df = basic_df.copy()
    df["sw_industry_l1"] = df["stock_code"].map(lambda c: sw_map.get(c, ("", ""))[0])
    df["sw_industry_l2"] = df["stock_code"].map(lambda c: sw_map.get(c, ("", ""))[1])
    df["market"]             = "A"
    df["csrc_industry_code"] = ""
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
# 港股 — 股票列表
# 文档确认：stock_hk_spot_em() 列名 序号(0), 代码(1), 名称(2), ... 无行业列
# ---------------------------------------------------------------------------

def fetch_hk_stocks() -> pd.DataFrame:
    log.info("=== Fetching 港股 stock list (stock_hk_spot_em) ===")
    try:
        df = _retry(lambda: ak.stock_hk_spot_em())
        log.info(f"  返回行数: {len(df):,} | 列名: {df.columns.tolist()}")
    except Exception as exc:
        log.error(f"  失败: {exc}")
        return pd.DataFrame()

    # 文档确认列名为"代码"和"名称"（非位置索引）
    return pd.DataFrame({
        "stock_code":   df["代码"].astype(str).str.strip(),
        "company_name": df["名称"].astype(str).str.strip(),
        "hk_industry":  "",   # 东方财富港股无行业列
    })


# ---------------------------------------------------------------------------
# 港股 — 行业（用公司名关键词兜底，因AKShare无专用港股行业接口）
# ---------------------------------------------------------------------------

def build_hk_stocks(hk_df: pd.DataFrame) -> pd.DataFrame:
    if hk_df.empty:
        return pd.DataFrame()

    df = hk_df.copy()
    df["market"]             = "HK"
    df["sw_industry_l1"]     = ""
    df["sw_industry_l2"]     = ""
    df["csrc_industry_code"] = ""
    df["csrc_industry_name"] = ""

    # 用公司名做关键词匹配（港股行业数据暂不可用时的兜底方案）
    name_lower = df["company_name"].str.lower().fillna("")
    df["is_healthcare"] = name_lower.apply(
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

    # A股
    basic_df = fetch_a_basic()
    sw_map   = fetch_sw_map()
    a_df     = build_a_stocks(basic_df, sw_map)

    # 港股
    hk_raw = fetch_hk_stocks()
    hk_df  = build_hk_stocks(hk_raw)

    # 合并保存
    all_df = pd.concat([a_df, hk_df], ignore_index=True)

    a_path   = OUTPUT_DIR / f"a_stocks_{today}.csv"
    hk_path  = OUTPUT_DIR / f"hk_stocks_{today}.csv"
    all_path = OUTPUT_DIR / f"all_stocks_{today}.csv"

    a_df.to_csv(a_path,    index=False, encoding="utf-8")
    hk_df.to_csv(hk_path,  index=False, encoding="utf-8")
    all_df.to_csv(all_path, index=False, encoding="utf-8")

    # 汇总
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
    log.info("")
    log.info(f"文件保存至: {OUTPUT_DIR.resolve()}/")
    for p in (a_path, hk_path, all_path):
        log.info(f"  {p.name}")


if __name__ == "__main__":
    main()
