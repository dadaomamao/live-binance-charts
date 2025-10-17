import pandas as pd
from PyQt6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QWidget,
    QLineEdit,
    QPushButton,
    QGridLayout,
    QLabel,
)
import pyqtgraph as pg
import finplot as fplt

# Local
import vars
from settings import save_settings, set_preferred
from binance_api import start_kline_socket, supported_symbols
from plot import add_plot, update_plot


def create_intial_GUI():
    set_preferred()
    # 为每个时间周期创建图表
    for key, tf in vars.preferred.items():
        symbol = key.rsplit('_', 1)[0]  # 从key中提取币种名称
        add_plot(symbol, tf)

    # Add control panel
    create_ctrl_panel()


def create_ctrl_panel():
    """Creates a simplified control panel for single coin with multiple timeframes."""
    panel = QWidget()
    vars.global_layout.addWidget(panel)
    layout = QGridLayout(panel)
    
    # 标签
    label = QLabel("币种选择:")
    label.setStyleSheet("color: white; font-size: 14px;")
    layout.addWidget(label, 0, 0)
    
    # 第一行：币种选择
    _create_coin_selector(panel, layout, 0, 1)
    
    # 保存按钮
    _create_save_button(panel, layout, 0, 2)
    
    # 第二行：显示当前的四个时间周期
    info_label = QLabel("显示时间周期: 即时行情 | 5分钟图 | 1小时图 | 日K线图")
    info_label.setStyleSheet("color: #888; font-size: 12px;")
    layout.addWidget(info_label, 1, 0, 1, 3)


def _create_coin_selector(panel, layout, row, col):
    """Creates a coin selector input."""
    panel.coin_input = QLineEdit(panel)
    panel.coin_input.setMaximumWidth(150)
    panel.coin_input.setText(vars.current_symbol)
    panel.coin_input.setPlaceholderText("输入币种 (如: BTCUSDT)")
    panel.coin_input.returnPressed.connect(change_coin)
    panel.coin_input.setStyleSheet("background-color: white; padding: 5px; font-size: 14px;")
    layout.addWidget(panel.coin_input, row, col)
    vars.coin_selector = panel.coin_input


def _create_save_button(panel, layout, row, col):
    """Creates a button to save settings."""
    panel.save = QPushButton(panel)
    panel.save.setText("保存设置")
    panel.save.clicked.connect(save_settings)
    panel.save.setMaximumWidth(100)
    panel.save.setStyleSheet("background-color: #4CAF50; color: white; padding: 5px; font-size: 14px;")
    layout.addWidget(panel.save, row, col)


def change_coin():
    """Changes the coin for all four timeframes."""
    new_symbol = vars.coin_selector.text().upper().strip()
    
    # 验证输入
    if not new_symbol:
        return
    
    # 如果不是以USDT结尾，自动添加
    if not new_symbol.endswith('USDT'):
        new_symbol += 'USDT'
    
    # 检查币种是否支持
    if new_symbol not in supported_symbols:
        print(f"币种 {new_symbol} 不支持")
        return
    
    # 如果是相同的币种，不做任何操作
    if new_symbol == vars.current_symbol:
        return
    
    print(f"切换币种: {vars.current_symbol} -> {new_symbol}")
    
    # 保存旧的preferred键
    old_keys = list(vars.preferred.keys())
    timeframes = ["1m", "5m", "1h", "1d"]
    
    # 更新每个时间周期的图表
    for i, (old_key, tf) in enumerate(zip(old_keys, timeframes)):
        old_symbol = old_key.rsplit('_', 1)[0]
        new_key = f"{new_symbol}_{tf}"
        
        # 获取对应的ax
        if old_key in vars.axs_dict:
            ax = vars.axs_dict[old_key]
            ax[0].reset()
            ax[1].reset()
            
            # 转移ax到新的key
            vars.axs_dict[new_key] = ax
            del vars.axs_dict[old_key]
            
            # 删除旧的plots
            if old_key + " price" in vars.plots:
                del vars.plots[old_key + " price"]
            if old_key + " volume" in vars.plots:
                del vars.plots[old_key + " volume"]
            if old_key + " rsi" in vars.plots:
                del vars.plots[old_key + " rsi"]
            
            # 删除旧的数据
            if old_key in vars.symbol_data_dict:
                del vars.symbol_data_dict[old_key]
        
        # 创建新的数据框
        vars.symbol_data_dict[new_key] = pd.DataFrame()
        
        # 更新图表数据
        update_plot(new_symbol, tf)
        
        # 启动新的WebSocket
        start_kline_socket(symbol=new_symbol, interval=tf)
    
    # 更新preferred字典
    new_preferred = {}
    for tf in timeframes:
        new_preferred[f"{new_symbol}_{tf}"] = tf
    vars.preferred = new_preferred
    
    # 更新当前币种
    vars.current_symbol = new_symbol
    vars.coin_selector.setText(new_symbol)
    
    # 刷新显示
    fplt.refresh()
    
    print(f"成功切换到 {new_symbol}")
