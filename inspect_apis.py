#!/usr/bin/env python3
"""
运行这个脚本，把完整输出粘给我，我根据真实数据写最终代码。
"""
import akshare as ak

def show(name, fn):
    print(f"\n{'='*60}")
    print(f"函数: {name}")
    try:
        df = fn()
        print(f"行数: {len(df)}")
        print(f"列名: {df.columns.tolist()}")
        print(f"前3行:\n{df.head(3).to_string()}")
    except Exception as e:
        print(f"失败: {e}")

show("stock_info_sz_name_code(A股列表)",  lambda: ak.stock_info_sz_name_code(symbol="A股列表"))
show("stock_info_sh_name_code(主板A股)",  lambda: ak.stock_info_sh_name_code(symbol="主板A股"))
show("stock_info_sh_name_code(科创板)",   lambda: ak.stock_info_sh_name_code(symbol="科创板"))
show("stock_info_bj_name_code()",         lambda: ak.stock_info_bj_name_code())
show("stock_hk_main_board_spot_em()",     lambda: ak.stock_hk_main_board_spot_em())
show("stock_board_industry_name_em()",    lambda: ak.stock_board_industry_name_em())
show("stock_board_industry_cons_em(化学制药)", lambda: ak.stock_board_industry_cons_em(symbol="化学制药"))
