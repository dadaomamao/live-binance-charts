import sys
import ctypes
import finplot as fplt
from PyQt6.QtWidgets import QGraphicsView, QGridLayout, QApplication
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtCore import QCoreApplication


# Local imports
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 更新频率配置（毫秒）
# 根据币安WebSocket API文档：
# - Trade Stream: 实时推送每笔交易，无频率限制
# - 我们只需要控制GUI刷新频率
# - 优化后：1000ms平衡流畅度和性能，配合变更检测机制
UPDATE_INTERVALS = {
    'finplot': 1000,       # GUI更新间隔：1000毫秒 = 每秒1次更新（平衡性能和实时性）
    'websocket_check': 30,  # WebSocket健康检查：30秒（与binance_api.py中的配置保持一致）
}
import vars
from binance_api import twm, check_connection_health, get_connection_status, shutdown_websockets

from gui import create_intial_GUI
from plot import realtime_update_plot


class CustomGraphicsView(QGraphicsView):
    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle the close event of the main window."""
        print("Closing application, shutting down connections...")
        
        # 使用新的优雅关闭函数
        shutdown_websockets()
        
        # Ensure the application quits properly
        QCoreApplication.quit()
        event.accept()


if __name__ == "__main__":
    # Make PyQt6 related stuff
    app = QApplication([])
    vars.window = CustomGraphicsView()

    # Layout for the charts
    vars.global_layout = QGridLayout()
    vars.window.setLayout(vars.global_layout)
    vars.window.setWindowTitle("Charts")

    # Background color surrounding the plots
    vars.window.setStyleSheet("background-color:" + fplt.background)
    width = ctypes.windll.user32.GetSystemMetrics(0)
    height = ctypes.windll.user32.GetSystemMetrics(1)
    vars.window.resize(int(width * 0.7), int(height * 0.7))

    # Finplot requres this property
    vars.window.axs = []
    fplt.autoviewrestore()

    # Start binance sockets
    if twm is not None:
        try:
            twm.start()
            print("WebSocket manager started successfully")
        except Exception as e:
            print(f"Failed to start WebSocket manager: {e}")
            print("Running in offline mode")
    else:
        print("Warning: WebSocket manager not initialized, running in offline mode")

    # Create the 4 plots + control panel
    create_intial_GUI()

    # Gets called every configured interval for better real-time updates
    # finplot的timer_callback使用秒为单位，所以需要转换
    fplt.timer_callback(realtime_update_plot, UPDATE_INTERVALS['finplot'] / 1000)
    
    # Check connection health every configured interval
    fplt.timer_callback(check_connection_health, UPDATE_INTERVALS['websocket_check'] / 1000)

    # prepares plots when they're all set up
    fplt.show(qt_exec=False)
    vars.window.show()
    sys.exit(app.exec())
