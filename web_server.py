from aiohttp import web
import os
from helpers import LogConfig
import aiofiles
import logging
from datetime import datetime
import psutil
import secrets
import hashlib
from config import WEB_PASSWORD  # 导入密码配置

# 生成随机密钥用于会话
SECRET_KEY = secrets.token_hex(32)
# 存储会话数据
SESSION_DATA = {}

class IPLogger:
    def __init__(self):
        self.ip_records = []  # 存储IP访问记录
        self.max_records = 100  # 最多保存100条记录
        self._log_cache = {'content': None, 'timestamp': 0}  # 添加日志缓存
        self._cache_ttl = 2  # 缓存有效期（秒）

    def add_record(self, ip, path):
        # 查找是否存在相同IP的记录
        for record in self.ip_records:
            if record['ip'] == ip:
                # 如果找到相同IP，只更新时间
                record['time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                record['path'] = path  # 更新访问路径
                return
        
        # 如果是新IP，添加新记录
        record = {
            'ip': ip,
            'path': path,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        self.ip_records.append(record)
        
        # 如果超出最大记录数，删除最早的记录
        if len(self.ip_records) > self.max_records:
            self.ip_records.pop(0)

    def get_records(self):
        return self.ip_records

def get_system_stats():
    """获取系统资源使用情况"""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    memory_used = memory.used / (1024 * 1024 * 1024)  # 转换为GB
    memory_total = memory.total / (1024 * 1024 * 1024)
    return {
        'cpu_percent': cpu_percent,
        'memory_used': round(memory_used, 2),
        'memory_total': round(memory_total, 2),
        'memory_percent': memory.percent
    }

async def _read_log_content():
    """公共的日志读取函数"""
    log_path = os.path.join(LogConfig.LOG_DIR, 'trading_system.log')
    if not os.path.exists(log_path):
        return None
        
    async with aiofiles.open(log_path, mode='r', encoding='utf-8') as f:
        content = await f.read()
        
    # 将日志按行分割
    lines = content.strip().split('\n')
    
    # 过滤掉包含 [httpx] INFO: HTTP Request: GET 的行
    filtered_lines = [line for line in lines if '[httpx] INFO: HTTP Request: GET' not in line]
    
    # 只保留最新的100行
    filtered_lines = filtered_lines[-100:]
    
    # 倒序排列
    filtered_lines.reverse()
    
    return '\n'.join(filtered_lines)

async def handle_login(request):
    """处理登录请求"""
    if request.method == 'POST':
        try:
            form = await request.post()
            password = form.get('password', '')
            
            if password == WEB_PASSWORD:
                # 创建会话
                session_id = secrets.token_hex(16)
                SESSION_DATA[session_id] = {
                    'authenticated': True, 
                    'login_time': datetime.now().isoformat()
                }
                
                # 设置会话cookie
                response = web.HTTPFound('/')
                response.set_cookie('session_id', session_id, httponly=True)
                return response
            else:
                return web.Response(
                    text='''
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>登录失败</title>
                        <meta charset="utf-8">
                        <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
                    </head>
                    <body class="bg-gray-100 flex items-center justify-center h-screen">
                        <div class="bg-white p-8 rounded-lg shadow-md w-full max-w-md">
                            <h1 class="text-2xl font-bold text-center text-red-600 mb-6">登录失败</h1>
                            <p class="text-center mb-6">密码错误，请重试</p>
                            <div class="text-center">
                                <a href="/login" class="inline-block bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded">
                                    返回登录
                                </a>
                            </div>
                        </div>
                    </body>
                    </html>
                    ''',
                    content_type='text/html'
                )
        except Exception as e:
            logging.error(f"登录处理错误: {str(e)}", exc_info=True)
            return web.HTTPInternalServerError(text=f"登录处理错误: {str(e)}")
    
    # GET请求，显示登录表单
    return web.Response(
        text='''
        <!DOCTYPE html>
        <html>
        <head>
            <title>网格交易监控系统 - 登录</title>
            <meta charset="utf-8">
            <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
        </head>
        <body class="bg-gray-100 flex items-center justify-center h-screen">
            <div class="bg-white p-8 rounded-lg shadow-md w-full max-w-md">
                <h1 class="text-2xl font-bold text-center text-gray-800 mb-6">网格交易监控系统</h1>
                <form method="post" action="/login">
                    <div class="mb-4">
                        <label class="block text-gray-700 text-sm font-bold mb-2" for="password">
                            请输入密码:
                        </label>
                        <input class="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:shadow-outline" 
                               id="password" name="password" type="password" placeholder="输入访问密码">
                    </div>
                    <div class="flex items-center justify-center">
                        <button class="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline" 
                                type="submit">
                            登录
                        </button>
                    </div>
                </form>
            </div>
        </body>
        </html>
        ''',
        content_type='text/html'
    )

async def handle_logout(request):
    """处理退出登录请求"""
    session_id = request.cookies.get('session_id')
    if session_id and session_id in SESSION_DATA:
        del SESSION_DATA[session_id]
    
    response = web.HTTPFound('/login')
    response.del_cookie('session_id')
    return response

async def handle_log(request):
    try:
        # 记录IP访问
        ip = request.remote
        request.app['ip_logger'].add_record(ip, request.path)
        
        # 获取系统资源状态
        system_stats = get_system_stats()
        
        # 读取日志内容
        content = await _read_log_content()
        if content is None:
            return web.Response(text="日志文件不存在", status=404)
        
        # 预先构建IP访问记录HTML
        ip_records_html = ""
        for record in list(reversed(request.app['ip_logger'].get_records()))[:5]:
            ip_records_html += f"""
            <tr class="border-b">
                <td class="px-6 py-4">{record["time"]}</td>
                <td class="px-6 py-4">{record["ip"]}</td>
                <td class="px-6 py-4">{record["path"]}</td>
            </tr>
            """
            
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>网格交易监控系统</title>
            <meta charset="utf-8">
            <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
            <style>
                .grid-container {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                    gap: 1rem;
                    padding: 1rem;
                }}
                .card {{
                    background: white;
                    border-radius: 0.5rem;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    padding: 1rem;
                }}
                .status-value {{
                    font-size: 1.5rem;
                    font-weight: bold;
                    color: #2563eb;
                }}
                .profit {{ color: #10b981; }}
                .loss {{ color: #ef4444; }}
                .log-container {{
                    height: calc(100vh - 400px);
                    overflow-y: auto;
                    background: #1e1e1e;
                    color: #d4d4d4;
                    padding: 1rem;
                    border-radius: 0.5rem;
                }}
            </style>
        </head>
        <body class="bg-gray-100">
            <div class="container mx-auto px-4 py-8">
                <div class="flex justify-between items-center mb-8">
                    <h1 class="text-3xl font-bold text-gray-800">网格交易监控系统</h1>
                    <a href="/logout" class="bg-red-500 hover:bg-red-700 text-white font-bold py-2 px-4 rounded">
                        退出登录
                    </a>
                </div>
                
                <!-- 状态卡片 -->
                <div class="grid-container mb-8">
                    <div class="card">
                        <h2 class="text-lg font-semibold mb-4">基本信息 & S1</h2>
                        <div class="space-y-2">
                            <div class="flex justify-between">
                                <span>交易对</span>
                                <span class="status-value">{request.app['trader'].symbol}</span>
                            </div>
                            <div class="flex justify-between">
                                <span>基准价格</span>
                                <span class="status-value" id="base-price">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>当前价格 (USDT)</span>
                                <span class="status-value" id="current-price">--</span>
                            </div>
                            <div class="flex justify-between pt-2 border-t mt-2">
                                <span>52日最高价 (S1)</span>
                                <span class="status-value" id="s1-high">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>52日最低价 (S1)</span>
                                <span class="status-value" id="s1-low">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>当前仓位 (%)</span>
                                <span class="status-value" id="position-percentage">--</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h2 class="text-lg font-semibold mb-4">网格参数</h2>
                        <div class="space-y-2">
                            <div class="flex justify-between">
                                <span>网格大小</span>
                                <span class="status-value" id="grid-size">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>当前上轨 (USDT)</span>
                                <span class="status-value" id="grid-upper-band">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>当前下轨 (USDT)</span>
                                <span class="status-value" id="grid-lower-band">--</span>
                            </div>    
                            <div class="flex justify-between">
                                <span>触发阈值</span>
                                <span class="status-value" id="threshold">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>目标委托金额</span>
                                <span class="status-value" id="target-order-amount">--</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h2 class="text-lg font-semibold mb-4">资金状况</h2>
                        <div class="space-y-2">
                            <div class="flex justify-between">
                                <span>总资产(USDT)</span>
                                <span class="status-value" id="total-assets">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>USDT余额</span>
                                <span class="status-value" id="usdt-balance">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>{request.app['trader'].base_symbol}余额</span>
                                <span class="status-value" id="base-balance">--</span>
                            </div>
                            <div class="flex justify-between pt-2 border-t mt-2">
                                <span>初始本金</span>
                                <span class="status-value" id="initial-principal">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>总盈亏(USDT)</span>
                                <span class="status-value" id="total-pnl">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>总收益率</span>
                                <span class="status-value" id="total-roi">--</span>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 交易统计信息 -->
                <div class="mb-8">
                    <h2 class="text-2xl font-bold mb-4 text-gray-800">交易统计</h2>
                    <div class="bg-white p-4 rounded-lg shadow">
                        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <div>
                                <p class="text-gray-600">总交易次数</p>
                                <p class="text-lg font-semibold" id="total-trades">--</p>
                            </div>
                            <div>
                                <p class="text-gray-600">胜率</p>
                                <p class="text-lg font-semibold" id="win-rate">--</p>
                            </div>
                            <div>
                                <p class="text-gray-600">最大盈利</p>
                                <p class="text-lg font-semibold text-green-500" id="max-profit">--</p>
                            </div>
                            <div>
                                <p class="text-gray-600">最大亏损</p>
                                <p class="text-lg font-semibold text-red-500" id="max-loss">--</p>
                            </div>
                            <div>
                                <p class="text-gray-600">平均盈利</p>
                                <p class="text-lg font-semibold" id="avg-profit">--</p>
                            </div>
                            <div>
                                <p class="text-gray-600">连续盈利</p>
                                <p class="text-lg font-semibold" id="consecutive-wins">--</p>
                            </div>
                            <div>
                                <p class="text-gray-600">连续亏损</p>
                                <p class="text-lg font-semibold" id="consecutive-losses">--</p>
                            </div>
                            <div>
                                <p class="text-gray-600">盈亏比</p>
                                <p class="text-lg font-semibold" id="profit-factor">--</p>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 系统资源使用情况 -->
                <div class="mb-8">
                    <h2 class="text-2xl font-bold mb-4 text-gray-800">系统资源</h2>
                    <div class="bg-white p-4 rounded-lg shadow">
                        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <div>
                                <p class="text-gray-600">CPU 使用率</p>
                                <p class="text-lg font-semibold">{system_stats['cpu_percent']}%</p>
                            </div>
                            <div>
                                <p class="text-gray-600">内存使用</p>
                                <p class="text-lg font-semibold">{system_stats['memory_used']} / {system_stats['memory_total']} GB</p>
                            </div>
                            <div>
                                <p class="text-gray-600">内存使用率</p>
                                <p class="text-lg font-semibold">{system_stats['memory_percent']}%</p>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- 最近交易记录 -->
                <div class="mb-8">
                    <h2 class="text-2xl font-bold mb-4 text-gray-800">最近交易</h2>
                    <div class="bg-white p-4 rounded-lg shadow overflow-x-auto">
                        <table class="min-w-full">
                            <thead>
                                <tr class="border-b">
                                    <th class="text-left py-2">时间</th>
                                    <th class="text-left py-2">方向</th>
                                    <th class="text-left py-2">价格</th>
                                    <th class="text-left py-2">数量</th>
                                    <th class="text-left py-2">金额(USDT)</th>
                                    <th class="text-left py-2">盈亏</th>
                                </tr>
                            </thead>
                            <tbody id="trade-history">
                                <!-- 交易记录将通过JavaScript动态插入 -->
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- IP访问记录 -->
                <div class="mb-8">
                    <h2 class="text-2xl font-bold mb-4 text-gray-800">访问记录</h2>
                    <div class="bg-white p-4 rounded-lg shadow overflow-x-auto">
                        <table class="min-w-full">
                            <thead>
                                <tr class="bg-gray-50">
                                    <th class="px-6 py-3 text-left">时间</th>
                                    <th class="px-6 py-3 text-left">IP地址</th>
                                    <th class="px-6 py-3 text-left">访问路径</th>
                                </tr>
                            </thead>
                            <tbody>
                                {ip_records_html}
                            </tbody>
                        </table>
                    </div>
                </div>
                
                <!-- 日志容器 -->
                <div class="mb-8">
                    <h2 class="text-2xl font-bold mb-4 text-gray-800">系统日志</h2>
                    <div class="log-container font-mono text-sm" id="log-container">
                        <pre>{content}</pre>
                    </div>
                </div>
            </div>

            <script>
                // 每5秒自动更新状态和日志
                async function updateStatus() {{
                    try {{
                        const response = await fetch('/api/status');
                        const data = await response.json();
                        
                        // 更新价格信息
                        const formatPrice = (price) => {{
                            // 直接使用科学计数法转换为字符串
                            const priceStr = price.toString();
                            
                            // 检查是否为科学计数法表示
                            if (priceStr.includes('e-')) {{
                                // 科学计数法，需要精确显示
                                // 对于像 1.617e-10 这样的数字，我们需要完整显示
                                const [mantissa, exponent] = priceStr.split('e-');
                                const exponentNum = parseInt(exponent, 10);
                                
                                // 将小数点移动到正确位置
                                let result = '0.';
                                for (let i = 1; i < exponentNum; i++) {{
                                    result += '0';
                                }}
                                
                                // 添加尾数部分（去掉小数点）
                                result += mantissa.replace('.', '');
                                return result;
                            }} else if (price < 0.0001) {{
                                // 非常小但不是科学计数法表示的数字
                                // 显示至少8位小数
                                return price.toFixed(10).replace(/0+$/, '');
                            }}
                            
                            // 标准价格，使用4位小数
                            return price.toFixed(4);
                        }};

                        document.getElementById('base-price').textContent = formatPrice(data.base_price);
                        document.getElementById('current-price').textContent = formatPrice(data.current_price);
                        document.getElementById('s1-high').textContent = data.s1_high ? formatPrice(data.s1_high) : '--';
                        document.getElementById('s1-low').textContent = data.s1_low ? formatPrice(data.s1_low) : '--';
                        document.getElementById('position-percentage').textContent = data.position_percentage.toFixed(2) + '%';
                        
                        // 更新网格信息
                        document.getElementById('grid-size').textContent = data.grid_size.toFixed(2) + '%';
                        document.getElementById('grid-upper-band').textContent = formatPrice(data.upper_band);
                        document.getElementById('grid-lower-band').textContent = formatPrice(data.lower_band);
                        document.getElementById('threshold').textContent = data.threshold.toFixed(4) + '%';
                        document.getElementById('target-order-amount').textContent = data.target_order_amount.toFixed(2) + ' USDT';
                        
                        // 更新资金状况
                        document.getElementById('total-assets').textContent = data.total_assets.toFixed(2);
                        document.getElementById('usdt-balance').textContent = data.usdt_balance.toFixed(2);
                        document.getElementById('base-balance').textContent = data.base_balance.toFixed(4);
                        document.getElementById('initial-principal').textContent = data.initial_principal.toFixed(2);
                        
                        // 更新盈亏信息
                        const pnlElement = document.getElementById('total-pnl');
                        pnlElement.textContent = data.total_pnl.toFixed(2);
                        pnlElement.className = 'status-value ' + (data.total_pnl >= 0 ? 'profit' : 'loss');
                        
                        const roiElement = document.getElementById('total-roi');
                        roiElement.textContent = data.total_roi.toFixed(2) + '%';
                        roiElement.className = 'status-value ' + (data.total_roi >= 0 ? 'profit' : 'loss');
                        
                        // 更新交易统计信息
                        if (data.statistics) {{
                            document.getElementById('total-trades').textContent = data.statistics.total_trades;
                            document.getElementById('win-rate').textContent = (data.statistics.win_rate * 100).toFixed(2) + '%';
                            document.getElementById('max-profit').textContent = data.statistics.max_profit.toFixed(2);
                            document.getElementById('max-loss').textContent = data.statistics.max_loss.toFixed(2);
                            document.getElementById('avg-profit').textContent = data.statistics.avg_profit.toFixed(2);
                            document.getElementById('consecutive-wins').textContent = data.statistics.consecutive_wins;
                            document.getElementById('consecutive-losses').textContent = data.statistics.consecutive_losses;
                            document.getElementById('profit-factor').textContent = data.statistics.profit_factor.toFixed(2);
                        }}
                        
                        // 更新交易历史
                        if (data.trade_history && data.trade_history.length > 0) {{
                            document.getElementById('trade-history').innerHTML = data.trade_history.map(trade => `
                                <tr class="border-b">
                                    <td class="py-2">${{trade.timestamp}}</td>
                                    <td class="py-2 ${{trade.side === 'buy' ? 'text-green-500' : 'text-red-500'}}">
                                        ${{trade.side === 'buy' ? '买入' : '卖出'}}
                                    </td>
                                    <td class="py-2">${{formatPrice(parseFloat(trade.price))}}</td>
                                    <td class="py-2">${{parseFloat(trade.amount).toFixed(4)}}</td>
                                    <td class="py-2">${{(parseFloat(trade.price) * parseFloat(trade.amount)).toFixed(2)}}</td>
                                    <td class="py-2 ${{parseFloat(trade.profit) >= 0 ? 'text-green-500' : 'text-red-500'}}">
                                        ${{parseFloat(trade.profit).toFixed(2)}}
                                    </td>
                                </tr>
                            `).join('');
                        }}
                    }} catch (error) {{
                        console.error('更新状态失败:', error);
                    }}
                }}
                
                async function updateLog() {{
                    try {{
                        const response = await fetch('/api/logs');
                        const logContent = await response.text();
                        document.getElementById('log-container').innerHTML = `<pre>${{logContent}}</pre>`;
                    }} catch (error) {{
                        console.error('更新日志失败:', error);
                    }}
                }}
                
                // 立即更新一次
                updateStatus();
                
                // 设置定时更新
                setInterval(updateStatus, 5000);
                setInterval(updateLog, 10000);
            </script>
        </body>
        </html>
        """
        return web.Response(text=html, content_type='text/html')
    except Exception as e:
        logging.error(f"渲染页面失败: {str(e)}", exc_info=True)
        return web.Response(text=f"渲染页面失败: {str(e)}", status=500)

async def handle_status(request):
    try:
        trader = request.app['trader']
        
        # 获取各项数据
        base_price = trader.base_price
        current_price = trader.current_price or await trader._get_latest_price()
        
        # 获取网格参数
        grid_size = trader.grid_size
        upper_band = trader._get_upper_band()
        lower_band = trader._get_lower_band()
        threshold = trader.config.GRID_PARAMS['initial'] / 5 / 100  # 简化计算，使用初始网格大小
        
        # 获取仓位信息
        position = await trader._get_position_ratio()
        position_percentage = position * 100
        
        # 获取资金状况
        await trader._update_total_assets()  # 确保总资产已更新
        total_assets = trader.total_assets
        
        # 获取各种余额
        try:
            balance = await trader.exchange.fetch_balance()
            funding_balance = await trader.exchange.fetch_funding_balance()
            
            usdt_balance = (
                float(balance.get('free', {}).get('USDT', 0)) +
                float(funding_balance.get('USDT', 0))
            )
            
            base_balance = (
                float(balance.get('free', {}).get(trader.base_symbol, 0)) +
                float(funding_balance.get(trader.base_symbol, 0))
            )
        except Exception as e:
            logging.error(f"获取余额失败: {str(e)}")
            usdt_balance = 0
            base_balance = 0
        
        # 计算盈亏
        initial_principal = trader.config.INITIAL_PRINCIPAL
        total_pnl = initial_principal > 0 and total_assets - initial_principal or 0
        total_roi = initial_principal > 0 and (total_pnl / initial_principal) * 100 or 0
        
        # 计算目标委托金额，基于资产的10%作为示例
        target_order_amount = total_assets * 0.1
        
        # 获取S1策略的数据
        s1_high = getattr(trader.position_controller_s1, 's1_daily_high', None)
        s1_low = getattr(trader.position_controller_s1, 's1_daily_low', None)
        
        # 获取交易历史
        trade_history = []
        statistics = {}
        if hasattr(trader, 'order_tracker'):
            # 获取交易历史记录
            trades = trader.order_tracker.get_trade_history()
            trade_history = [{
                'timestamp': datetime.fromtimestamp(trade['timestamp']).strftime('%Y-%m-%d %H:%M:%S'),
                'side': trade.get('side', '--'),
                'price': trade.get('price', 0),
                'amount': trade.get('amount', 0),
                'profit': trade.get('profit', 0)
            } for trade in trades[-10:]]  # 只取最近10笔交易
            
            # 获取交易统计数据
            try:
                statistics = trader.order_tracker.get_statistics()
                if not statistics:
                    statistics = {
                        'total_trades': 0,
                        'win_rate': 0,
                        'total_profit': 0,
                        'avg_profit': 0,
                        'max_profit': 0,
                        'max_loss': 0,
                        'profit_factor': 0,
                        'consecutive_wins': 0,
                        'consecutive_losses': 0
                    }
            except Exception as e:
                logging.error(f"获取交易统计信息失败: {str(e)}")
                statistics = {
                    'total_trades': len(trades),
                    'win_rate': 0,
                    'total_profit': 0,
                    'avg_profit': 0,
                    'max_profit': 0,
                    'max_loss': 0,
                    'profit_factor': 0,
                    'consecutive_wins': 0,
                    'consecutive_losses': 0
                }
        
        return web.json_response({
            'base_price': base_price,
            'current_price': current_price,
            's1_high': s1_high,
            's1_low': s1_low,
            'grid_size': grid_size,
            'upper_band': upper_band,
            'lower_band': lower_band,
            'threshold': threshold * 100,  # 转为百分比
            'position_percentage': position_percentage,
            'total_assets': total_assets,
            'usdt_balance': usdt_balance,
            'base_balance': base_balance,
            'initial_principal': initial_principal,
            'total_pnl': total_pnl,
            'total_roi': total_roi,
            'target_order_amount': target_order_amount,
            'trade_history': trade_history,
            'statistics': statistics
        })
    except Exception as e:
        logging.error(f"获取状态数据失败: {str(e)}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500)

async def start_web_server(trader):
    app = web.Application()
    
    # 中间件检查身份验证（如果设置了密码）
    @web.middleware
    async def auth_middleware(request, handler):
        # 如果未设置密码，则不需要验证
        if not WEB_PASSWORD:
            return await handler(request)
            
        # 登录页面和登录处理不需要验证
        if request.path == '/login':
            return await handler(request)
            
        # 检查会话是否有效
        session_id = request.cookies.get('session_id')
        if session_id and session_id in SESSION_DATA and SESSION_DATA[session_id].get('authenticated'):
            return await handler(request)
        else:
            # 未认证，重定向到登录页
            return web.HTTPFound('/login')
    
    # 添加错误处理中间件
    @web.middleware
    async def error_middleware(request, handler):
        try:
            return await handler(request)
        except web.HTTPException as ex:
            return web.json_response(
                {"error": str(ex)},
                status=ex.status,
                headers={'Access-Control-Allow-Origin': '*'}
            )
        except Exception as e:
            return web.json_response(
                {"error": "Internal Server Error"},
                status=500,
                headers={'Access-Control-Allow-Origin': '*'}
            )
    
    # 添加中间件
    app.middlewares.append(auth_middleware)
    app.middlewares.append(error_middleware)
    
    app['trader'] = trader
    app['ip_logger'] = IPLogger()
    
    # 禁用访问日志
    logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
    
    # 定义路由
    app.router.add_get('/', handle_log)
    app.router.add_route('*', '/login', handle_login)  # 支持GET和POST
    app.router.add_get('/logout', handle_logout)
    app.router.add_get('/api/logs', handle_log_content)
    app.router.add_get('/api/status', handle_status)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 58181)
    await site.start()

    # 打印访问地址
    local_ip = "localhost"  # 或者使用实际IP
    logging.info(f"Web服务已启动:")
    logging.info(f"- 本地访问: http://{local_ip}:58181")
    logging.info(f"- 局域网访问: http://0.0.0.0:58181")
    if WEB_PASSWORD:
        logging.info(f"- 已启用密码保护")

async def handle_log_content(request):
    """只返回日志内容的API端点"""
    try:
        content = await _read_log_content()
        if content is None:
            return web.Response(text="", status=404)
            
        return web.Response(text=content)
    except Exception as e:
        return web.Response(text="", status=500) 
