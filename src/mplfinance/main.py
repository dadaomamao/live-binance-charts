# Third party libraries
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import mplfinance as mpf
import numpy as np
from binance.client import Client
from binance import ThreadedWebsocketManager
import time
import logging
from datetime import datetime

# Local dependencies
from BinanceData import fetchData
import keys
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# WebSocket管理器
twm = ThreadedWebsocketManager()

# 存储实时数据的字典
realtime_data = {}
connection_status = {'connected': False, 'last_update': None}

def ws_response(info):
    """处理WebSocket响应，更新实时数据"""
    try:
        if not info or 's' not in info or 'k' not in info:
            return
            
        symbol = info["s"]
        kline_data = info["k"]
        
        if symbol not in realtime_data:
            return
            
        # 更新实时数据
        realtime_data[symbol] = {
            'close': float(kline_data["c"]),
            'high': float(kline_data["h"]),
            'low': float(kline_data["l"]),
            'open': float(kline_data["o"]),
            'volume': float(kline_data["v"]),
            'timestamp': int(kline_data["t"])
        }
        
        connection_status['last_update'] = time.time()
        connection_status['connected'] = True
        
    except Exception as e:
        logger.error(f"Error processing WebSocket data: {e}")
        connection_status['connected'] = False

def start_websocket(symbol):
    """启动WebSocket连接"""
    try:
        twm.start_kline_socket(symbol=symbol, callback=ws_response, interval='1m')
        realtime_data[symbol] = {}
        logger.info(f"WebSocket started for {symbol}")
    except Exception as e:
        logger.error(f"Failed to start WebSocket for {symbol}: {e}")

# IDEAS:
# Trend lines (https://github.com/matplotlib/mplfinance/blob/master/examples/using_lines.ipynb)
# Plot stop loss hlines
# Use futures account positions

# Save your API keys in keys.py
# 如果没有有效的API密钥，将使用默认加密货币列表
try:
    # 检查API密钥是否有效
    if keys.public_key == 'public_key' or keys.private_key == 'private_key':
        raise ValueError("使用默认API密钥")
    
    client = Client(keys.public_key, keys.private_key)
    
    # Get current holdings and save in owned
    owned = []
    
    # Fill owned list
    assets = (client.get_account()).get('balances')
    for asset in assets:
        sym = asset.get('asset')
        available = float(asset.get('free')) + float(asset.get('locked'))
        # Have more than 0 available
        if available > 0.001 :
            if sym != 'USDT':
                symUSDT = sym + 'USDT' 
                try:
                    # Keep tracks of assets worth more than $10 in USDT
                    if available * float(client.get_symbol_ticker(symbol = symUSDT)['price']) > 10:
                        owned.append(symUSDT)
                except Exception as e: 
                    #Print out all the error information
                    print("Error adding: " + symUSDT)
except Exception as e:
    print(f"API密钥无效或网络错误: {e}")
    print("使用默认加密货币列表...")
    owned = []
    client = Client()  # 使用公共API客户端

# === Default list ===
# List to use when owned consists of less than 9 items
default = config.DEFAULT_SYMBOLS

# Add the default coins to owned
for sym in default:
    if sym not in owned:
        owned.append(sym)

# =========================
# =====   PLOTTING    =====
# =========================

# === TRADINGVIEW STYLE ===
# https://github.com/matplotlib/mplfinance/blob/master/examples/styles.ipynb
mc = mpf.make_marketcolors(up='#2e7871',down='#e84752',inherit=True)

s  = mpf.make_mpf_style(
                        base_mpf_style='nightclouds',
                        y_on_right=True,
                        marketcolors=mc,facecolor='#131722',
                        edgecolor='#4a4e59',
                        figcolor='#131722',
                        gridstyle='solid',
                        gridcolor='#1d202b')

fig = mpf.figure(style=s,figsize=(20,8))

# === CREATE PLOTS ===
#https://github.com/matplotlib/mplfinance/blob/master/examples/external_axes.ipynb

axs = []

# 9 plots
for x in range(1,10):
    axs.append(fig.add_subplot(3,3,x))

#https://github.com/matplotlib/mplfinance/blob/master/examples/plot_customizations.ipynb
#https://stackoverflow.com/questions/60599812/how-can-i-customize-mplfinance-plot

# This function gets called every x ms
def animate(frame):
    # Latest 100 candles
    i = 0

    for ax in axs:
        symbol = owned[i]

        # 获取历史数据（只在第一次或需要时）
        if symbol not in realtime_data or not realtime_data[symbol]:
            data = fetchData(symbol, 1, '15m')[-100:]
        else:
            # 使用缓存的历史数据，只更新最新价格
            data = fetchData(symbol, 1, '15m')[-100:]
            
            # 如果有实时数据，更新最新K线
            if symbol in realtime_data and realtime_data[symbol]:
                rt_data = realtime_data[symbol]
                data.iloc[-1, data.columns.get_loc('close')] = rt_data['close']
                data.iloc[-1, data.columns.get_loc('high')] = max(data.iloc[-1, data.columns.get_loc('high')], rt_data['high'])
                data.iloc[-1, data.columns.get_loc('low')] = min(data.iloc[-1, data.columns.get_loc('low')], rt_data['low'])
                data.iloc[-1, data.columns.get_loc('volume')] = rt_data['volume']

        # Clear old plot
        ax.clear()

        # Set title of every plot with connection status
        conn_indicator = "●" if connection_status['connected'] else "○"
        conn_color = "green" if connection_status['connected'] else "red"
        ax.set_title(f"{symbol} {conn_indicator}", color=conn_color)
        ax.yaxis.get_major_formatter().set_scientific(False)

        current_price = data['close'].iloc[-1]
        old_price = data['close'].iloc[-2]

        if current_price > old_price:
            color = 'green'
        elif current_price == old_price:
            color = 'gray'
        else:
            color = 'red'

        # Draw current price with timestamp
        current_time = datetime.now().strftime('%H:%M:%S')
        ax.text(101,
                current_price, 
                f"{np.format_float_positional(current_price)}\n{current_time}", 
                color="white", 
                ha="left", 
                va="center", 
                bbox=dict(facecolor=color, alpha=0.7))

        if i > 5:
            mpf.plot(
                    data,
                    ax=ax,
                    volume=False, 
                    type='hollow_and_filled',
                    #Plot time on x-axis
                    datetime_format='%H:%M', 
                    ylabel='', 
                    tight_layout=True, 
                    # Price Line
                    hlines=dict(hlines=current_price,linestyle='dashed',linewidths=(1)),
                    )
        else:
            mpf.plot(
                    data,
                    ax=ax,
                    volume=False,
                    type='hollow_and_filled',
                    datetime_format='',
                    ylabel='', 
                    tight_layout=True, 
                    hlines=dict(hlines=current_price,linestyle='dashed',linewidths=(1)),
                    )

        i = i+1

# 启动WebSocket连接
try:
    twm.start()
    for symbol in owned:
        start_websocket(symbol)
    logger.info("WebSocket connections started successfully")
except Exception as e:
    logger.error(f"Failed to start WebSocket connections: {e}")

# Update every 1 second for maximum real-time performance (1 sec = 1000ms)
# WebSocket数据实时推送，此处只是GUI刷新频率
ani = FuncAnimation(fig, animate, interval=1000, cache_frame_data=False)

plt.show()

# 清理资源
try:
    twm.stop()
except:
    pass