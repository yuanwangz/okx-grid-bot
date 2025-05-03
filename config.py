import os
from dotenv import load_dotenv
import logging
import re

# 配置日志格式
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('config')

# 清理环境变量值的函数，去除引号和注释
def clean_env_value(value):
    """清理环境变量的值，移除引号和注释"""
    if value is None:
        return None
    
    # 转成字符串进行统一处理
    value_str = str(value).strip()
    
    # 移除前后引号
    if (value_str.startswith('"') and value_str.endswith('"')) or \
       (value_str.startswith("'") and value_str.endswith("'")):
        value_str = value_str[1:-1]
    
    # 移除注释（如果有）
    if '#' in value_str:
        value_str = value_str.split('#')[0].strip()
    
    # 移除空白字符
    value_str = value_str.strip()
    
    if value_str.lower() == 'none' or value_str == '':
        return None
    
    return value_str

def _format_price(price):
    """格式化价格，避免科学记数法，保留足够精度"""
    if price is None:
        return "N/A"
        
    # 如果价格非常小（小于0.0001），使用更多小数位
    if abs(price) < 0.0001:
        # 计算需要的小数位数
        precision = 10  # 默认至少10位
        
        # 如果非常小的数，找到第一个非零数字并多显示3位
        if price != 0:
            temp_price = abs(price)
            count = 0
            while temp_price < 1:
                temp_price *= 10
                count += 1
            precision = max(count + 3, precision)
            
        # 使用f-string并指定精度，确保不使用科学计数法
        return f"{price:.{precision}f}"
    elif abs(price) < 0.01:
        return f"{price:.8f}"
    elif abs(price) < 1:
        return f"{price:.6f}"
    elif abs(price) < 1000:
        return f"{price:.4f}"
    else:
        return f"{price:.2f}"

# 加载.env文件
logger.info("正在加载.env配置文件...")
load_dotenv(verbose=True)

# 读取并验证基本配置
BASE_SYMBOL = clean_env_value(os.getenv('BASE_SYMBOL'))
if not BASE_SYMBOL:
    BASE_SYMBOL = 'OKB'  # 默认值
    logger.warning(f"未找到BASE_SYMBOL配置，使用默认值: {BASE_SYMBOL}")
else:
    logger.info(f"加载BASE_SYMBOL配置: {BASE_SYMBOL}")

QUOTE_SYMBOL = clean_env_value(os.getenv('QUOTE_SYMBOL'))
if not QUOTE_SYMBOL:
    QUOTE_SYMBOL = 'USDT'  # 默认值
    logger.warning(f"未找到QUOTE_SYMBOL配置，使用默认值: {QUOTE_SYMBOL}")
else:
    logger.info(f"加载QUOTE_SYMBOL配置: {QUOTE_SYMBOL}")

# 构建交易对
SYMBOL = f"{BASE_SYMBOL}-{QUOTE_SYMBOL}"
logger.info(f"构建交易对: {SYMBOL}")
BASE_CURRENCY = BASE_SYMBOL

# 读取交易模式
FLAG = clean_env_value(os.getenv('FLAG', '1'))
logger.info(f"交易模式: {'模拟' if FLAG == '1' else '实盘'}")

# 从环境变量读取初始网格大小，默认2.0
try:
    INITIAL_GRID = float(clean_env_value(os.getenv('INITIAL_GRID', '2.0')))
    logger.info(f"初始网格大小: {INITIAL_GRID}")
except ValueError:
    INITIAL_GRID = 2.0
    logger.warning("无效的INITIAL_GRID配置，已使用默认值2.0")

FLIP_THRESHOLD = lambda grid_size: (grid_size / 5) / 100  # 网格大小的1/5的1%
POSITION_SCALE_FACTOR = 0.2  # 仓位调整系数（20%）

# 从环境变量读取最小交易金额，默认20.0
try:
    MIN_TRADE_AMOUNT = float(clean_env_value(os.getenv('MIN_TRADE_AMOUNT', '20.0')))
    logger.info(f"最小交易金额: {MIN_TRADE_AMOUNT}")
except ValueError:
    MIN_TRADE_AMOUNT = 20.0
    logger.warning("无效的MIN_TRADE_AMOUNT配置，已使用默认值20.0")

MIN_POSITION_PERCENT = 0.05  # 最小交易比例（总资产的5%）
MAX_POSITION_PERCENT = 0.15  # 最大交易比例（总资产的15%）
COOLDOWN = 60
SAFETY_MARGIN = 0.95

# 从环境变量读取最大回撤，默认-0.15
try:
    MAX_DRAWDOWN = float(clean_env_value(os.getenv('MAX_DRAWDOWN', '-0.15')))
    logger.info(f"最大回撤: {MAX_DRAWDOWN}")
except ValueError:
    MAX_DRAWDOWN = -0.15
    logger.warning("无效的MAX_DRAWDOWN配置，已使用默认值-0.15")

# 从环境变量读取每日亏损限制，默认-0.05
try:
    DAILY_LOSS_LIMIT = float(clean_env_value(os.getenv('DAILY_LOSS_LIMIT', '-0.05')))
    logger.info(f"每日亏损限制: {DAILY_LOSS_LIMIT}")
except ValueError:
    DAILY_LOSS_LIMIT = -0.05
    logger.warning("无效的DAILY_LOSS_LIMIT配置，已使用默认值-0.05")

# 从环境变量读取最大仓位比例，默认0.9 (90%)
try:
    MAX_POSITION_RATIO = float(clean_env_value(os.getenv('MAX_POSITION_RATIO', '0.9')))
    logger.info(f"最大仓位比例: {MAX_POSITION_RATIO}")
except ValueError:
    MAX_POSITION_RATIO = 0.9
    logger.warning("无效的MAX_POSITION_RATIO配置，已使用默认值0.9")

# 从环境变量读取最小仓位比例，默认0.1 (10%)
try:
    MIN_POSITION_RATIO = float(clean_env_value(os.getenv('MIN_POSITION_RATIO', '0.1')))
    logger.info(f"最小仓位比例: {MIN_POSITION_RATIO}")
except ValueError:
    MIN_POSITION_RATIO = 0.1
    logger.warning("无效的MIN_POSITION_RATIO配置，已使用默认值0.1")

# Web界面密码，如果未设置则默认为空（表示不需要密码）
WEB_PASSWORD = clean_env_value(os.getenv('WEB_PASSWORD', ''))

# 其他配置
PUSHPLUS_TOKEN = clean_env_value(os.getenv('PUSHPLUS_TOKEN'))
TELEGRAM_BOT_TOKEN = clean_env_value(os.getenv('TELEGRAM_BOT_TOKEN'))
TELEGRAM_CHAT_ID = clean_env_value(os.getenv('TELEGRAM_CHAT_ID'))
LOG_LEVEL = logging.INFO
DEBUG_MODE = False
API_TIMEOUT = 10000
RECV_WINDOW = 5000
RISK_CHECK_INTERVAL = 300

# 读取初始基准价格
try:
    INITIAL_BASE_PRICE = float(clean_env_value(os.getenv('INITIAL_BASE_PRICE', '0')))
    logger.info(f"初始基准价格: {_format_price(INITIAL_BASE_PRICE)}")
except ValueError:
    INITIAL_BASE_PRICE = 0
    logger.warning("无效的INITIAL_BASE_PRICE配置，已重置为0")

MAX_RETRIES = 5
RISK_FACTOR = 0.1
VOLATILITY_WINDOW = 24

# 从环境变量读取初始本金
try:
    INITIAL_PRINCIPAL = float(clean_env_value(os.getenv('INITIAL_PRINCIPAL', '0')))
    if INITIAL_PRINCIPAL <= 0:
        logger.warning("INITIAL_PRINCIPAL 必须为正数，已重置为0")
        INITIAL_PRINCIPAL = 0
    else:
        logger.info(f"初始本金: {INITIAL_PRINCIPAL}")
except ValueError:
    INITIAL_PRINCIPAL = 0
    logger.warning("无效的INITIAL_PRINCIPAL配置，已重置为0")

# 配置加载完成，输出汇总信息
logger.info(f"配置加载完成。交易对: {SYMBOL}, 网格大小: {INITIAL_GRID}%, 最小交易金额: {MIN_TRADE_AMOUNT} USDT")

class TradingConfig:
    RISK_PARAMS = {
        'max_drawdown': MAX_DRAWDOWN,
        'daily_loss_limit': DAILY_LOSS_LIMIT,
        'position_limit': MAX_POSITION_RATIO
    }
    GRID_PARAMS = {
        'initial': INITIAL_GRID,
        'min': 1.0,
        'max': 4.0,
        'volatility_threshold': {
            'ranges': [
                {'range': [0, 0.20], 'grid': 1.0},     # 波动率 0-20%，网格1.0%
                {'range': [0.20, 0.40], 'grid': 1.5},  # 波动率 20-40%，网格1.5%
                {'range': [0.40, 0.60], 'grid': 2.0},  # 波动率 40-60%，网格2.0%
                {'range': [0.60, 0.80], 'grid': 2.5},  # 波动率 60-80%，网格2.5%
                {'range': [0.80, 1.00], 'grid': 3.0},  # 波动率 80-100%，网格3.0%
                {'range': [1.00, 1.20], 'grid': 3.5},  # 波动率 100-120%，网格3.5%
                {'range': [1.20, 999], 'grid': 4.0}    # 波动率 >120%，网格4.0%
            ]
        }
    }
    
    DYNAMIC_INTERVAL_PARAMS = {
        'volatility_to_interval_hours': [
            {'range': [0, 0.20], 'interval_hours': 1.0},
            {'range': [0.20, 0.40], 'interval_hours': 0.5},
            {'range': [0.40, 0.80], 'interval_hours': 0.25},
            {'range': [0.80, 999], 'interval_hours': 0.125},
        ],
        'default_interval_hours': 1.0
    }
    
    SYMBOL = SYMBOL
    BASE_SYMBOL = BASE_SYMBOL
    INITIAL_BASE_PRICE = INITIAL_BASE_PRICE
    RISK_CHECK_INTERVAL = RISK_CHECK_INTERVAL
    MAX_RETRIES = MAX_RETRIES
    RISK_FACTOR = RISK_FACTOR
    BASE_AMOUNT = 50.0
    MIN_TRADE_AMOUNT = MIN_TRADE_AMOUNT
    MAX_POSITION_RATIO = MAX_POSITION_RATIO
    MIN_POSITION_RATIO = MIN_POSITION_RATIO
    VOLATILITY_WINDOW = VOLATILITY_WINDOW
    INITIAL_GRID = INITIAL_GRID
    POSITION_SCALE_FACTOR = POSITION_SCALE_FACTOR
    COOLDOWN = COOLDOWN
    SAFETY_MARGIN = SAFETY_MARGIN
    API_TIMEOUT = API_TIMEOUT
    RECV_WINDOW = RECV_WINDOW
    MIN_POSITION_PERCENT = MIN_POSITION_PERCENT
    MAX_POSITION_PERCENT = MAX_POSITION_PERCENT
    INITIAL_PRINCIPAL = INITIAL_PRINCIPAL
    BASE_CURRENCY = BASE_CURRENCY
    WEB_PASSWORD = WEB_PASSWORD

    def __init__(self):
        # 添加配置验证
        if self.MIN_POSITION_RATIO >= self.MAX_POSITION_RATIO:
            raise ValueError("底仓比例不能大于或等于最大仓位比例")
        
        if self.GRID_PARAMS['min'] > self.GRID_PARAMS['max']:
            raise ValueError("网格最小值不能大于最大值")
            
        logger.info("交易配置初始化完成")

# End of class definition 
