from datetime import datetime
import time
import logging
import threading

import pandas as pd

from binance.client import Client
from binance import ThreadedWebsocketManager
from binance.exceptions import BinanceAPIException, BinanceRequestException

import vars

# 实时交易聚合粒度（毫秒）。500ms 平衡实时性和性能
# 100ms太频繁会导致UI卡顿，500ms = 每秒2次更新足够流畅
TRADE_BUCKET_MS = 500

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 日志节流（防刷屏）
LOG_THROTTLE_WINDOW = 5  # seconds
_throttle_last = {}
_throttle_suppressed = {}

def log_throttled(level: int, key: str, message: str) -> None:
    now = time.time()
    last = _throttle_last.get(key, 0.0)
    if now - last >= LOG_THROTTLE_WINDOW:
        suppressed = _throttle_suppressed.pop(key, 0)
        _throttle_last[key] = now
        if suppressed:
            message = f"{message} (suppressed {suppressed} repeats)"
        logger.log(level, message)
    else:
        _throttle_suppressed[key] = _throttle_suppressed.get(key, 0) + 1

class SubstringThrottleFilter(logging.Filter):
    """简单的基于子串匹配的日志节流过滤器。"""
    def __init__(self, substring: str, window_seconds: int = 5, name: str = ""):
        super().__init__(name)
        self.substring = substring
        self.window = window_seconds
        self._last = 0.0
        self._suppressed = 0

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if self.substring not in msg:
            return True
        now = time.time()
        if now - self._last >= self.window:
            if self._suppressed:
                # 将抑制次数附加到首次放行的日志上
                record.msg = f"{record.getMessage()} (suppressed {self._suppressed} repeats)"
                record.args = ()
                self._suppressed = 0
            self._last = now
            return True
        else:
            self._suppressed += 1
            return False

def configure_logging_filters() -> None:
    """为第三方库日志添加节流过滤器，减少刷屏。"""
    try:
        ws_logger = logging.getLogger("binance.ws.threaded_stream")
        ws_logger.addFilter(SubstringThrottleFilter("Read loop has been closed", window_seconds=5))
    except Exception as e:
        logger.debug(f"Failed to configure ws logger filter: {e}")

configure_logging_filters()

# WebSocket配置
WEBSOCKET_CONFIG = {
    'max_retries': 3,  # 减少重试次数
    'retry_delay': 2,
    'connection_timeout': 30,
    'max_queue_size': 1000,  # 进一步增加队列大小
    'reconnect_delay': 5,  # 重连延迟
    'health_check_interval': 30,  # 健康检查间隔
}

# 创建客户端，禁用SSL验证以避免连接问题
try:
    client = Client()
    # 使用自定义配置创建WebSocket管理器
    twm = ThreadedWebsocketManager(
        api_key=None,
        api_secret=None,
        testnet=False,
        max_queue_size=WEBSOCKET_CONFIG['max_queue_size']
    )
except Exception as e:
    logger.warning(f"Failed to initialize Binance client: {e}")
    logger.info("Attempting to initialize with SSL verification disabled...")
    try:
        import ssl
        import requests
        # 禁用SSL验证
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        # 创建自定义session
        session = requests.Session()
        session.verify = False
        
        client = Client()
        client.session = session
        twm = ThreadedWebsocketManager(
            api_key=None,
            api_secret=None,
            testnet=False,
            max_queue_size=WEBSOCKET_CONFIG['max_queue_size']
        )
    except Exception as e2:
        logger.error(f"Failed to initialize Binance client even with SSL disabled: {e2}")
        logger.info("Continuing without Binance API connection...")
        client = None
        twm = None

# WebSocket管理器锁，防止并发问题
twm_lock = threading.Lock()

# 活跃的WebSocket连接跟踪
active_sockets = {}  # {key: socket_name}

# 连接状态跟踪
connection_status = {
    'connected': False,
    'last_update': None,
    'retry_count': 0,
    'max_retries': WEBSOCKET_CONFIG['max_retries'],
    'is_reconnecting': False
}

# Get list of currently supported symbols
try:
    if client is not None:
        supported_symbols = [d["symbol"] for d in client.get_exchange_info().get("symbols")]
        connection_status['connected'] = True
        connection_status['last_update'] = time.time()
    else:
        logger.warning("Client is None, using default symbols")
        supported_symbols = []
except Exception as e:
    logger.error(f"Failed to get supported symbols: {e}")
    supported_symbols = []


def start_kline_socket(symbol, interval):
    """启动K线WebSocket连接，带重试机制和更好的错误处理"""
    if twm is None:
        logger.error("WebSocket manager is not initialized")
        return
    
    key = f"{symbol}_{interval}"
    
    # 使用锁防止并发问题
    with twm_lock:
        # 如果该连接已存在，先停止它
        if key in active_sockets:
            try:
                twm.stop_socket(active_sockets[key])
                logger.debug(f"Stopped existing socket for {key}")
                del active_sockets[key]
            except Exception as e:
                logger.warning(f"Error stopping existing socket for {key}: {e}")
        
        # 对于1m，使用实时交易流而不是K线
        if interval == "1m":
            try:
                socket_name = twm.start_trade_socket(symbol=symbol, callback=ws_trade_response)
                active_sockets[key] = socket_name
                logger.info(f"Trade WebSocket started for {symbol} (real-time)")
                connection_status['retry_count'] = 0
                connection_status['connected'] = True
                connection_status['last_update'] = time.time()
            except Exception as e:
                logger.error(f"Failed to start trade WebSocket for {symbol}: {e}")
                if connection_status['retry_count'] < connection_status['max_retries']:
                    connection_status['retry_count'] += 1
                    logger.info(f"Retrying trade WebSocket connection for {symbol} (attempt {connection_status['retry_count']})")
                    time.sleep(WEBSOCKET_CONFIG['retry_delay'])
                    start_kline_socket(symbol, interval)
        else:
            try:
                # Make a new websocket for this asset
                socket_name = twm.start_kline_socket(symbol=symbol, callback=ws_response, interval=interval)
                active_sockets[key] = socket_name
                logger.info(f"WebSocket started for {symbol} {interval}")
                connection_status['retry_count'] = 0
                connection_status['connected'] = True
                connection_status['last_update'] = time.time()
            except Exception as e:
                logger.error(f"Failed to start WebSocket for {symbol}: {e}")
                if connection_status['retry_count'] < connection_status['max_retries']:
                    connection_status['retry_count'] += 1
                    logger.info(f"Retrying WebSocket connection for {symbol} (attempt {connection_status['retry_count']})")
                    time.sleep(WEBSOCKET_CONFIG['retry_delay'])
                    start_kline_socket(symbol, interval)


# === Websocket interpreter ===
def ws_trade_response(info):
    """处理实时交易WebSocket响应（用于即时行情图）- 100ms级实时更新
    
    Binance Trade Stream 格式:
    {
        "e": "trade",     // 事件类型
        "E": 123456789,   // 事件时间
        "s": "BNBBTC",    // 交易对
        "t": 12345,       // 交易ID
        "p": "0.001",     // 价格
        "q": "100",       // 数量
        "T": 123456785,   // 交易时间
        ...
    }
    """
    try:
        # 快速验证响应数据 - 检查事件类型
        if not isinstance(info, dict):
            log_throttled(logging.DEBUG, "trade_invalid_type", f"Invalid response type: {type(info)}")
            return
            
        # 处理错误消息
        if 'e' in info and info['e'] == 'error':
            # 节流错误日志
            log_throttled(logging.ERROR, "ws_read_loop_closed", f"WebSocket error: {info}")
            return
        
        # 验证必需字段
        required_fields = ['s', 'p', 'q', 'T']
        missing_fields = [f for f in required_fields if f not in info]
        if missing_fields:
            # 不记录每次失败，避免日志刷屏
            log_throttled(logging.DEBUG, "trade_missing_fields", f"Trade message missing fields: {missing_fields}")
            return
        
        sym = info["s"]
        key = f"{sym}_1m"  # 1m使用实时交易数据
        
        # Skip response if symbol is not in dict
        if key not in vars.symbol_data_dict:
            return
        
        df = vars.symbol_data_dict[key]
        
        if df.empty:
            return
        
        # 获取当前价格和时间
        price = float(info["p"])
        quantity = float(info["q"])
        trade_time = int(info["T"])  # 交易时间（毫秒）
        
        # 使用100ms级时间戳，将交易聚合到固定时间桶，提升刷新频率
        trade_dt = pd.Timestamp(trade_time, unit='ms')
        trade_bucket = trade_dt.floor(f'{TRADE_BUCKET_MS}ms')
        
        # 获取最后一个数据点的时间
        last_time = df.index[-1]
        
        # 如果进入新的时间桶，则添加新的数据点（实时推进）
        if trade_bucket > last_time:
            # 创建新的数据点
            new_row = pd.DataFrame({
                'Open': [price],
                'High': [price],
                'Low': [price],
                'Close': [price],
                'Volume': [quantity]
            }, index=[trade_bucket])
            
            # 使用更高效的追加方式，避免频繁concat
            df = pd.concat([df, new_row])
            
            # 保持合理的历史长度：约3分钟的500ms级数据 -> 3*60*2 = 360
            # 进一步减少数据点以提升性能
            MAX_REALTIME_POINTS = 360
            if len(df) > MAX_REALTIME_POINTS:
                df = df.iloc[-MAX_REALTIME_POINTS:]
        else:
            # 更新当前时间桶的数据点
            df.loc[last_time, "Close"] = price
            df.loc[last_time, "High"] = max(df.loc[last_time, "High"], price)
            df.loc[last_time, "Low"] = min(df.loc[last_time, "Low"], price)
            df.loc[last_time, "Volume"] += quantity
        
        # 更新字典
        vars.symbol_data_dict[key] = df
        
        # 更新连接状态
        connection_status['last_update'] = time.time()
        connection_status['connected'] = True
        
    except KeyError as e:
        log_throttled(logging.DEBUG, "trade_missing_key", f"Missing key in trade response: {e}")
    except ValueError as e:
        logger.warning(f"Data conversion error in trade response: {e}")
    except Exception as e:
        logger.error(f"Error handling trade websocket response: {e}")
        connection_status['connected'] = False


def ws_response(info):
    """处理WebSocket响应，带错误处理和数据验证"""
    try:
        # 验证响应数据
        if not info or 's' not in info or 'k' not in info:
            log_throttled(logging.DEBUG, "kline_invalid_format", "Invalid WebSocket response format")
            return
            
        sym = info["s"]
        tf = info["k"]["i"]
        key = f"{sym}_{tf}"  # 使用正确的key格式

        # Skip response if symbol is not in dict
        if key not in vars.symbol_data_dict:
            return

        if tf != vars.preferred[key]:
            return

        df = vars.symbol_data_dict[key]
        
        # 验证K线数据
        kline_data = info["k"]
        required_fields = ['c', 'h', 'l', 'o', 'v', 't', 'T']
        if not all(field in kline_data for field in required_fields):
            log_throttled(logging.DEBUG, "kline_missing_fields", f"Missing required fields in kline data for {sym}")
            return

        close = float(kline_data["c"])
        high = float(kline_data["h"])
        low = float(kline_data["l"])
        volume = float(kline_data["v"])

        # t is the timestamp in ms
        t = int(kline_data["t"])

        # Use int(info['k']['T']) - current time to calculate time until next candle
        d1 = int(kline_data["T"])
        converted_d1 = datetime.fromtimestamp(round(d1 / 1000))
        current_time = datetime.now()
        td = converted_d1 - current_time
        vars.countdown = str(td).split(".")[0]

        # 检查数据有效性
        if df.empty or len(df) < 2:
            log_throttled(logging.DEBUG, "kline_insufficient_data", f"Insufficient data for {sym}")
            return

        t0 = int(df.index[-2].timestamp()) * 1000
        t1 = int(df.index[-1].timestamp()) * 1000
        t2 = t1 + (t1 - t0)

        # Update line corresponding with symbol
        if t < t2:
            # update last candle
            i = df.index[-1]
            df.loc[i, "Close"] = close
            df.loc[i, "High"] = max(df.loc[i, "High"], high)
            df.loc[i, "Low"] = min(df.loc[i, "Low"], low)
            df.loc[i, "Volume"] = volume
        else:
            # Add it all together, OCHLV
            data = [t] + [float(kline_data["o"])] + [close] + [high] + [low] + [volume]
            candle = pd.DataFrame(
                [data], columns="Time Open Close High Low Volume".split()
            ).astype({"Time": "datetime64[ms]"})
            candle.set_index("Time", inplace=True)

            # Add to dataframe
            df = pd.concat([df, candle])

        # Symbol_dict consists of all ohlcv data
        vars.symbol_data_dict[key] = df
        
        # 更新连接状态
        connection_status['last_update'] = time.time()
        connection_status['connected'] = True
        
    except ValueError as e:
        logger.error(f"Data conversion error for {sym}: {e}")
    except Exception as e:
        logger.error(f"Error handling websocket response for {sym}: {e}")
        connection_status['connected'] = False


def check_connection_health():
    """检查连接健康状态，必要时重新连接"""
    if twm is None:
        logger.warning("WebSocket manager is not initialized, skipping health check")
        return
    
    # 防止并发重连
    if connection_status.get('is_reconnecting', False):
        logger.debug("Reconnection already in progress, skipping...")
        return
        
    current_time = time.time()
    
    # 如果超过配置的超时时间没有更新，认为连接有问题
    if (connection_status['last_update'] and 
        current_time - connection_status['last_update'] > WEBSOCKET_CONFIG['health_check_interval']):
        
        logger.warning("Connection appears to be stale, attempting to restart all sockets...")
        connection_status['connected'] = False
        connection_status['is_reconnecting'] = True
        
        try:
            # 使用延迟重连，避免过于频繁的重连
            time.sleep(WEBSOCKET_CONFIG['reconnect_delay'])
            
            # 不重新创建管理器，只重启所有已知的 socket
            # 复制一份以避免在迭代时修改字典
            sockets_to_restart = list(vars.preferred.items())
            
            logger.info(f"Restarting {len(sockets_to_restart)} connections individually...")
            reconnect_count = 0
            for key, timeframe in sockets_to_restart:
                try:
                    symbol = key.rsplit('_', 1)[0]
                    # start_kline_socket 会处理停止旧 socket 和启动新 socket 的逻辑
                    start_kline_socket(symbol, timeframe)
                    reconnect_count += 1
                    # 添加小延迟避免同时启动太多连接
                    time.sleep(0.5)
                except Exception as e:
                    logger.error(f"Failed to restart connection for {key}: {e}")
            
            if reconnect_count > 0:
                logger.info(f"Finished restarting {reconnect_count} WebSocket connections")
                connection_status['last_update'] = time.time()
            else:
                logger.warning("No connections were restarted.")

        except Exception as e:
            logger.error(f"An unexpected error occurred during the socket restart process: {e}")
        finally:
            connection_status['is_reconnecting'] = False


def get_connection_status():
    """获取当前连接状态"""
    return {
        'connected': connection_status['connected'],
        'last_update': connection_status['last_update'],
        'retry_count': connection_status['retry_count'],
        'active_sockets': len(active_sockets)
    }


def shutdown_websockets():
    """优雅地关闭所有WebSocket连接"""
    global twm
    
    logger.info("Shutting down WebSocket connections...")
    
    with twm_lock:
        if twm is None:
            logger.info("WebSocket manager already closed")
            return
        
        try:
            # 停止WebSocket管理器，它会负责关闭所有子socket
            logger.info("Stopping WebSocket manager...")
            twm.stop()
            twm = None
            
            active_sockets.clear()
            connection_status['connected'] = False
            logger.info("All WebSocket connections closed successfully")
            
        except Exception as e:
            logger.error(f"Error during WebSocket shutdown: {e}")
