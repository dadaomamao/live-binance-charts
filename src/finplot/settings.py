from os import path
import pickle

import vars


# Gets preferred settings at start up
def set_preferred():
    file = "settings.pkl"
    
    # 默认币种
    default_symbol = "BTCUSDT"
    
    # 四个不同的时间周期：1分钟、5分钟、1小时、日线
    timeframes = ["1m", "5m", "1h", "1d"]

    if path.exists(file):
        print("Found settings")

        # Get preffered pickle
        with open(file, "rb") as handle:
            preferred = pickle.load(handle)

        # 验证和修复格式
        first_key = list(preferred.keys())[0] if preferred else None
        if first_key:
            # 从key中提取币种名称（处理各种可能的格式）
            # 可能的格式：BTCUSDT, BTCUSDT_1m, BTCUSDT_1m_1m (错误)
            parts = first_key.split('_')
            if len(parts) >= 1:
                # 找到以USDT结尾的部分作为币种
                symbol_part = None
                for part in parts:
                    if part.endswith('USDT'):
                        symbol_part = part
                        break
                if symbol_part:
                    default_symbol = symbol_part
                else:
                    # 如果没找到USDT，使用第一部分
                    default_symbol = parts[0]
            
            # 重建正确格式的preferred
            preferred = {
                f"{default_symbol}_1m": "1m",
                f"{default_symbol}_5m": "5m",
                f"{default_symbol}_1h": "1h",
                f"{default_symbol}_1d": "1d",
            }

        print(preferred)

    else:
        print("No settings found, using default")
        # 默认显示BTCUSDT的四个时间周期
        preferred = {
            f"{default_symbol}_1m": "1m",
            f"{default_symbol}_5m": "5m",
            f"{default_symbol}_1h": "1h",
            f"{default_symbol}_1d": "1d",
        }
    
    vars.preferred = preferred
    vars.current_symbol = default_symbol  # 保存当前币种


# Do this if the save button is pressed
def save_settings():
    file = "settings.pkl"

    # Write currently prefferd as pickle
    with open(file, "wb") as handle:
        pickle.dump(vars.preferred, handle, protocol=pickle.HIGHEST_PROTOCOL)

    print("Saved settings")
