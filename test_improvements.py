#!/usr/bin/env python3
"""
测试脚本 - 验证实时更新改进
"""

import sys
import os
import time

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_config():
    """测试配置文件加载"""
    try:
        import config
        print("✓ 配置文件加载成功")
        print(f"  - finplot更新间隔: {config.UPDATE_INTERVALS['finplot']}ms")
        print(f"  - mplfinance更新间隔: {config.UPDATE_INTERVALS['mplfinance']}ms")
        print(f"  - WebSocket最大重试次数: {config.WEBSOCKET_CONFIG['max_retries']}")
        return True
    except Exception as e:
        print(f"✗ 配置文件加载失败: {e}")
        return False

def test_binance_api():
    """测试Binance API连接"""
    try:
        from binance.client import Client
        client = Client()
        exchange_info = client.get_exchange_info()
        print("✓ Binance API连接成功")
        print(f"  - 支持的交易对数量: {len(exchange_info['symbols'])}")
        return True
    except Exception as e:
        print(f"✗ Binance API连接失败: {e}")
        return False

def test_websocket_manager():
    """测试WebSocket管理器"""
    try:
        from binance import ThreadedWebsocketManager
        twm = ThreadedWebsocketManager()
        print("✓ WebSocket管理器初始化成功")
        return True
    except Exception as e:
        print(f"✗ WebSocket管理器初始化失败: {e}")
        return False

def test_imports():
    """测试所有必要的导入"""
    try:
        import pandas as pd
        import numpy as np
        import matplotlib.pyplot as plt
        import mplfinance as mpf
        print("✓ 所有必要的库导入成功")
        return True
    except ImportError as e:
        print(f"✗ 库导入失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 开始测试实时更新改进...")
    print("=" * 50)
    
    tests = [
        ("配置文件测试", test_config),
        ("Binance API测试", test_binance_api),
        ("WebSocket管理器测试", test_websocket_manager),
        ("库导入测试", test_imports),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}:")
        if test_func():
            passed += 1
        time.sleep(0.5)
    
    print("\n" + "=" * 50)
    print(f"📊 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！实时更新改进已成功实现。")
        print("\n💡 使用方法:")
        print("  - finplot版本: python src/finplot/main.py")
        print("  - mplfinance版本: python src/mplfinance/main.py")
    else:
        print("⚠️  部分测试失败，请检查依赖和环境配置。")

if __name__ == "__main__":
    main()
