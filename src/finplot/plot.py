import finplot as fplt
import pandas as pd
from ta.momentum import RSIIndicator
import pyqtgraph as pg
import time

from binance_api import client, start_kline_socket, get_connection_status
import vars

# === 性能优化：RSI缓存和变更检测 ===
# 缓存每个图表的RSI计算结果，避免重复计算
_rsi_cache = {}  # {key: (last_length, rsi_series)}
# 记录每个图表的数据长度，用于检测是否有新数据
_data_length_cache = {}  # {key: last_length}


def _calculate_rsi_cached(df, key):
    """
    智能RSI计算：使用缓存避免重复计算
    只在数据变化时重新计算，否则返回缓存结果
    
    Args:
        df: 包含Close列的DataFrame
        key: 图表标识符（如 'BTCUSDT_1m'）
    
    Returns:
        RSI Series
    """
    current_length = len(df)
    
    # 检查缓存是否有效
    if key in _rsi_cache:
        cached_length, cached_rsi = _rsi_cache[key]
        # 如果数据长度未变，直接返回缓存
        if cached_length == current_length:
            return cached_rsi
    
    # 数据已变化，重新计算RSI
    try:
        rsi = RSIIndicator(close=df["Close"]).rsi()
        # 更新缓存
        _rsi_cache[key] = (current_length, rsi)
        return rsi
    except Exception as e:
        # 如果计算失败，返回缓存值（如果有）或空Series
        if key in _rsi_cache:
            return _rsi_cache[key][1]
        return pd.Series(dtype=float)


def add_plot(symbol, tf):
    """Adds a plot to the screen"""
    # Make axis
    ax, ax_rsi = fplt.create_plot_widget(vars.window, rows=2, init_zoom_periods=100)

    # Hide y-axis of chart graph
    ax.hideAxis("bottom")

    # ax.vb.setBackgroundColor(None)
    ax_rsi.vb.setBackgroundColor(None)

    ax.showGrid(True, True)
    ax_rsi.showGrid(True, True)

    vars.window.axs.append(ax)
    vars.window.axs.append(ax_rsi)

    key = f"{symbol}_{tf}"
    vars.axs_dict[key] = [ax, ax_rsi]

    # Add widgets to layout, top to bottom, left to right
    # addWidget (self, QWidget, row, column, rowSpan, columnSpan, Qt.Alignment alignment = 0)
    # 1 (rowSpan of ax) + 3 (rowSpan of ax_rsi) = 4, so that is the row of rsi plot widget
    vars.global_layout.addWidget(ax.ax_widget, vars.row, vars.col, 1, 1)
    vars.row += 4
    vars.global_layout.addWidget(ax_rsi.ax_widget, vars.row, vars.col, 3, 1)
    vars.row += 3

    vars.widget_counter += 2

    # After 11 reset the counter
    if vars.row > 11:
        vars.col += 1
        vars.row = 0

    start_kline_socket(symbol=symbol, interval=tf)
    update_plot(symbol, tf)

    # add_widgets(sym)


# Adds candles and volume
def update_plot(sym, timeframe):
    # Get the ax
    key = f"{sym}_{timeframe}"
    ax = vars.axs_dict[key][0]
    ax_rsi = vars.axs_dict[key][1]

    # Use latest 120 candles to fill up the plot
    hist_candles = client.get_klines(symbol=sym, interval=timeframe, limit=120)

    df = pd.DataFrame(hist_candles)

    # Only the columns containt the OHLCV data
    df.drop(columns=[6, 7, 8, 9, 10, 11], axis=1, inplace=True)

    # OHLCV
    df = df.rename(
        columns={0: "Time", 1: "Open", 2: "High", 3: "Low", 4: "Close", 5: "Volume"}
    )

    # Convert time in ms to datetime
    df = df.astype(
        {
            "Time": "datetime64[ms]",
            "Open": float,
            "High": float,
            "Low": float,
            "Close": float,
            "Volume": float,
        }
    )

    # 对于1m时间周期，使用实时价格线图而不是蜡烛图
    if timeframe == "1m":
        # 将分钟数据转换为次级数据点，以便与实时100ms数据衔接
        # 使用每分钟收盘价落在该分钟的最后100ms处，避免与实时桶重复
        df['Time'] = df['Time'] + pd.Timedelta(milliseconds=59000)  # 59s 位置
        df.set_index("Time", inplace=True)
        
        # plot实时价格线（不是蜡烛图）
        vars.plots[key + " price"] = fplt.plot(
            df["Close"], ax=ax, color="#2196F3", width=2, legend=f"{sym} 实时价格"
        )
        
        # === 添加日内均线（分钟级别） ===
        # 只显示MA60均线（60分钟移动平均）
        if len(df) >= 60:
            ma60 = df["Close"].rolling(window=60).mean()
            vars.plots[key + " ma60"] = fplt.plot(
                ma60, ax=ax, color="#FFD93D", width=2, legend="MA60"
            )
        
        # Add volume overlay（保持时间列存在）
        vars.plots[key + " volume"] = fplt.volume_ocv(
            df.reset_index()[["Time", "Open", "Close", "Volume"]], ax=ax.overlay()
        )
    else:
        # 其他时间周期使用蜡烛图
        # plot the candles
        vars.plots[key + " price"] = fplt.candlestick_ochl(
            df[["Time", "Open", "Close", "High", "Low"]], ax=ax
        )

        # Add volume overlay
        vars.plots[key + " volume"] = fplt.volume_ocv(
            df[["Time", "Open", "Close", "Volume"]], ax=ax.overlay()
        )

        df.set_index("Time", inplace=True)
        
        # === 添加均线（K线图） ===
        # 为5m、1h、1d图表添加MA25、MA7、MA99三条均线
        ma_configs = [
            (25, "#FF6B6B", "MA25"),  # 红色 - 25周期均线
            (7, "#4ECDC4", "MA7"),    # 青色 - 7周期均线
            (99, "#A8E6CF", "MA99"),  # 绿色 - 99周期均线
        ]
        
        for period, color, label in ma_configs:
            if len(df) >= period:
                ma = df["Close"].rolling(window=period).mean()
                vars.plots[key + f" ma{period}"] = fplt.plot(
                    ma, ax=ax, color=color, width=1.5, legend=label
                )

    # RSI overlay - 使用缓存计算
    rsi = _calculate_rsi_cached(df, key)
    vars.plots[key + " rsi"] = fplt.plot(rsi, ax=ax_rsi, color="#47c9d9")

    # Use symbol name as legend
    legend_text = f"{sym} - 实时" if timeframe == "1m" else f"{sym} - {timeframe}"
    fplt.add_legend(legend_text, ax=ax)

    # Save the data for this coin in the dictionary
    vars.symbol_data_dict[key] = df

    # Make elements that highlight the current price
    price_highlight(df, ax, ax_rsi)


def price_highlight(df, ax, ax_rsi):
    # Define color of price line
    current_price = df["Close"].iloc[-1]
    old_price = df["Close"].iloc[-2]

    # Define color of rectangle
    # Or save color of last candle in a dictionary [sym] = lastcol
    if current_price > old_price:
        rec_color = "#2e7871"
    if current_price == old_price:
        rec_color = "#4a4e59"
    if current_price < old_price:
        rec_color = "#e84752"

    # pgColor = pg.mkColor(rec_color)

    # Add current price line
    ax.price_line = pg.InfiniteLine(
        angle=0,
        movable=False,
        pen=fplt._makepen(fplt.candle_bull_body_color, style="--"),
    )
    ax.price_line.setPos(current_price)
    # ax.price_line.pen.setColor(pgColor)
    ax.addItem(ax.price_line, ignoreBounds=True)

    # If current_price is longer than 7 numbers make the font smaller
    # https://pyqtgraph.readthedocs.io/en/latest/graphicsItems/textitem.html
    ax.text = pg.TextItem(
        html=(
            '<b style="color:white; background-color:'
            + rec_color
            + '";>'
            + str(current_price)
            + "</b>"
        ),
        anchor=(0, 0.5),
    )
    # Set text at last candle
    ax.text.setPos(len(df.index), current_price)
    ax.addItem(ax.text, ignoreBounds=True)

    # Add lines to RSI
    ax_rsi.line70 = pg.InfiniteLine(
        angle=0, movable=False, pen=fplt._makepen("#ffffff", style="--")
    )
    ax_rsi.line70.setPos(70)
    ax_rsi.addItem(ax_rsi.line70, ignoreBounds=True)

    ax_rsi.line30 = pg.InfiniteLine(
        angle=0, movable=False, pen=fplt._makepen("#ffffff", style="--")
    )
    ax_rsi.line30.setPos(30)
    ax_rsi.addItem(ax_rsi.line30, ignoreBounds=True)

    # Hex as #RRGGBBAA + 1A is 10% opacity
    # 使用新的API名称
    try:
        fplt.add_horizontal_band(30, 70, color=pg.mkColor("#9c24ac1A"), ax=ax_rsi)
    except AttributeError:
        # 如果新API不可用，使用旧API
        fplt.add_band(30, 70, color=pg.mkColor("#9c24ac1A"), ax=ax_rsi)


# 性能监控统计
_perf_stats = {
    'last_update_time': 0,
    'avg_update_time': 0,
    'update_count': 0,
    'max_update_time': 0
}

# Update the plots
def realtime_update_plot():
    """Called at regular intervals by a timer. 优化版：只更新变化的数据"""
    
    # 性能监控开始
    start_time = time.time()

    # If call is too early
    if all(df.empty for df in vars.symbol_data_dict.values()):
        return

    # 获取连接状态
    conn_status = get_connection_status()
    status_color = "#2e7871" if conn_status['connected'] else "#e84752"
    status_text = "●" if conn_status['connected'] else "○"

    # 统计变更：用于性能监控
    updates_count = 0
    skipped_count = 0

    # first update all data, then graphics (for zoom rigidity)
    # key = 'SYMBOL_TIMEFRAME type' (e.g., 'BTCUSDT_1m price')
    for key in vars.plots:
        # Parse key: "BTCUSDT_1m price" -> ["BTCUSDT_1m", "price"]
        parts = key.rsplit(' ', 1)
        if len(parts) != 2:
            continue
            
        full_key = parts[0]  # e.g., "BTCUSDT_1m"
        plot_type = parts[1]  # e.g., "price"
        
        if full_key not in vars.symbol_data_dict:
            continue
            
        df = vars.symbol_data_dict[full_key]
        
        # === 变更检测：跳过未变化的数据 ===
        current_length = len(df)
        cached_length = _data_length_cache.get(full_key, -1)
        
        # 只处理price类型的plot来检测变更（避免重复检测）
        if plot_type == "price":
            if current_length == cached_length:
                # 数据未变化，跳过所有更新
                skipped_count += 1
                continue
            else:
                # 数据已变化，更新缓存
                _data_length_cache[full_key] = current_length
                updates_count += 1

        # Get correct ax, first is for the chart
        if full_key not in vars.axs_dict:
            continue
            
        axs = vars.axs_dict[full_key]
        ax = axs[0]
        ax_rsi = axs[1]
        
        # 检查是否是1m实时图
        is_realtime = full_key.endswith("_1m")

        try:
            if plot_type == "price":
                if is_realtime:
                    # 对于实时图，更新价格线（df索引为时间，500ms桶）
                    vars.plots[key].update_data(df["Close"])
                else:
                    # 对于蜡烛图，更新OCHL
                    vars.plots[key].update_data(df[["Open", "Close", "High", "Low"]])
            
            # 更新均线数据（用于所有图表）
            if plot_type.startswith("ma"):
                # 提取均线周期数：例如 "ma5" -> 5
                try:
                    period = int(plot_type[2:])
                    if len(df) >= period:
                        ma = df["Close"].rolling(window=period).mean()
                        vars.plots[key].update_data(ma)
                except (ValueError, KeyError):
                    pass  # 忽略无效的均线key

            if plot_type == "volume":
                # 对于实时图和蜡烛图，统一使用包含时间列的OV数据
                # 修复：DataFrame索引重置后，索引列名可能不是"Time"
                df_with_time = df.reset_index()
                # 确保第一列命名为Time（无论索引原来叫什么）
                time_col_name = df_with_time.columns[0]
                if time_col_name != "Time":
                    df_with_time = df_with_time.rename(columns={time_col_name: "Time"})
                vars.plots[key].update_data(df_with_time[["Time", "Open", "Close", "Volume"]])

            if plot_type == "rsi":
                # 使用缓存的RSI计算，避免重复计算
                rsi = _calculate_rsi_cached(df, full_key)
                vars.plots[key].update_data(rsi)
        except Exception as e:
            # 静默处理更新错误，避免刷屏
            if _perf_stats['update_count'] % 100 == 0:
                print(f"警告：更新图表 {key} 时出错: {e}")

        current_price = df["Close"].iloc[-1]
        old_price = df["Close"].iloc[-2] if len(df) > 1 else current_price

        if current_price > old_price:
            rec_color = "#2e7871"
        elif current_price == old_price:
            rec_color = "#4a4e59"
        else:
            rec_color = "#e84752"

        # Color of line
        ax.price_line.pen.setColor(pg.mkColor(rec_color))

        # Position of line
        ax.price_line.setPos(current_price)

        # Position of text
        ax.text.setPos(len(df.index), current_price)

        if "-" in vars.countdown:
            vars.countdown = "0:00:00"

        # 添加连接状态指示器
        ax.text.setHtml(
            (
                '<b style="color:white; background-color:'
                + rec_color
                + '";>'
                + str(current_price)
                + '</b> <body style="color:white; background-color:'
                + rec_color
                + '";>'
                + vars.countdown
                + f' <span style="color:{status_color};">{status_text}</span>'
                + "</body>"
            )
        )
    
    # 性能监控结束
    end_time = time.time()
    elapsed_ms = (end_time - start_time) * 1000
    
    # 更新性能统计
    _perf_stats['last_update_time'] = elapsed_ms
    _perf_stats['update_count'] += 1
    _perf_stats['max_update_time'] = max(_perf_stats['max_update_time'], elapsed_ms)
    
    # 计算平均值（滑动平均）
    alpha = 0.1  # 平滑系数
    if _perf_stats['avg_update_time'] == 0:
        _perf_stats['avg_update_time'] = elapsed_ms
    else:
        _perf_stats['avg_update_time'] = (
            alpha * elapsed_ms + (1 - alpha) * _perf_stats['avg_update_time']
        )
    
    # 每50次更新输出一次性能统计（避免日志刷屏）
    if _perf_stats['update_count'] % 50 == 0:
        print(f"[性能监控] 更新次数: {_perf_stats['update_count']}, "
              f"本次: {elapsed_ms:.1f}ms, "
              f"平均: {_perf_stats['avg_update_time']:.1f}ms, "
              f"最大: {_perf_stats['max_update_time']:.1f}ms, "
              f"实际更新: {updates_count}, 跳过: {skipped_count}")
