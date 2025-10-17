# 配置文件 - 实时更新参数设置

# 更新频率设置（毫秒）
# 根据币安API文档：WebSocket数据是事件驱动的实时推送，无推送频率限制
# GUI更新频率只影响显示刷新，1000ms是最佳平衡点（实时性+性能）
UPDATE_INTERVALS = {
    'finplot': 1000,      # finplot版本更新间隔：1秒（最大实时性）
    'mplfinance': 1000,   # mplfinance版本更新间隔：1秒（最大实时性）
    'websocket_check': 30000,  # WebSocket健康检查间隔：30秒（降低开销）
}

# WebSocket设置
WEBSOCKET_CONFIG = {
    'max_retries': 5,           # 最大重试次数
    'retry_delay': 2,           # 重试延迟（秒）
    'connection_timeout': 30,   # 连接超时时间（秒）
    'reconnect_interval': 30,   # 重连检查间隔（秒）
}

# 图表设置
CHART_CONFIG = {
    'candle_limit': 100,        # 显示的K线数量
    'timeframe': '15m',         # 默认时间框架
    'show_volume': False,       # 是否显示成交量
    'show_rsi': True,           # 是否显示RSI指标
}

# 连接状态指示器
STATUS_INDICATORS = {
    'connected': '●',           # 连接状态指示器
    'disconnected': '○',       # 断开状态指示器
    'connected_color': '#2e7871',    # 连接状态颜色
    'disconnected_color': '#e84752', # 断开状态颜色
}

# 日志设置
LOGGING_CONFIG = {
    'level': 'INFO',            # 日志级别
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': 'binance_charts.log',  # 日志文件名
}

# 默认加密货币列表
DEFAULT_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", 
    "ADAUSDT", "DOTUSDT", "BCHUSDT", "LTCUSDT"
]

# API设置
API_CONFIG = {
    'rate_limit': 1200,        # API请求限制（每分钟）
    'timeout': 10,             # 请求超时时间（秒）
    'retry_attempts': 3,       # API请求重试次数
}
