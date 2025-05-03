import os
import logging
import traceback

import httpx
from okx.Finance import Savings

import config
from config import SYMBOL, DEBUG_MODE, API_TIMEOUT, RECV_WINDOW, BASE_CURRENCY
from datetime import datetime
import time
import asyncio
from okx import MarketData, Trade, Account, Funding, PublicData


class ExchangeClient:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._verify_credentials()
        
        # 初始化OKX API客户端
        self.api_key = os.getenv('OKX_API_KEY')
        self.secret_key = os.getenv('OKX_SECRET_KEY')
        self.passphrase = os.getenv('OKX_PASSPHRASE')
# export https_proxy=http://127.0.0.1:7890 http_proxy=http://127.0.0.1:7890 all_proxy=socks5://127.0.0.1:7890
        # self.proxy = httpx.Proxy(url='http://127.0.0.1:7890')
        self.proxy = None
        
        # 初始化各个API模块
        self.market_api = MarketData.MarketAPI(
            api_key=self.api_key,
            api_secret_key=self.secret_key,
            passphrase=self.passphrase,
            # flag='0'  # 实盘交易
            flag=config.FLAG,  # 模拟交易
            proxy=self.proxy
        )
        
        self.trade_api = Trade.TradeAPI(
            api_key=self.api_key,
            api_secret_key=self.secret_key,
            passphrase=self.passphrase,
            flag=config.FLAG,
            proxy=self.proxy
        )

        self.public_api = PublicData.PublicAPI(api_key=self.api_key,
                                          api_secret_key=self.secret_key,
                                          passphrase=self.passphrase,
                                          flag=config.FLAG,
                                          proxy=self.proxy)
        
        self.account_api = Account.AccountAPI(
            api_key=self.api_key,
            api_secret_key=self.secret_key,
            passphrase=self.passphrase,
            flag=config.FLAG, proxy=self.proxy
        )
        
        self.funding_api = Funding.FundingAPI(
            api_key=self.api_key,
            api_secret_key=self.secret_key,
            passphrase=self.passphrase,
            flag=config.FLAG, proxy=self.proxy
        )

        self.savings_api = Savings.SavingsAPI(
            api_key=self.api_key,
            api_secret_key=self.secret_key,
            passphrase=self.passphrase,
            flag=config.FLAG, proxy=self.proxy
        )

        self.logger.setLevel(logging.INFO)
        self.logger.info("OKX交易所客户端初始化完成")
        
        self.markets_loaded = False
        self.time_diff = 0
        self.balance_cache = {'timestamp': 0, 'data': None}
        self.funding_balance_cache = {'timestamp': 0, 'data': {}}
        self.cache_ttl = 1/5  # 缓存有效期（秒）
    
    def _verify_credentials(self):
        """验证API密钥是否存在"""
        required_env = ['OKX_API_KEY', 'OKX_SECRET_KEY', 'OKX_PASSPHRASE']
        missing = [var for var in required_env if not os.getenv(var)]
        if missing:
            error_msg = f"缺少环境变量: {', '.join(missing)}"
            self.logger.critical(error_msg)
            raise EnvironmentError(error_msg)

    async def load_markets(self):
        try:
            # 获取交易对信息
            result = self.market_api.get_tickers(instType='SPOT')
            if result['code'] == '0':
                self.markets_loaded = True
                self.logger.info(f"市场数据加载成功 | 交易对: {SYMBOL}")
                return True
            else:
                error_msg = f"加载市场数据失败: {result['msg']} | 错误码: {result['code']}"
                self.logger.error(error_msg)
                raise Exception(error_msg)
        except Exception as e:
            error_msg = f"加载市场数据失败: {str(e)} | 堆栈信息: {traceback.format_exc()}"
            self.logger.error(error_msg)
            self.markets_loaded = False
            raise Exception(error_msg)

    async def fetch_ohlcv(self, symbol, timeframe='1H', limit=None):
        """获取K线数据"""
        try:
            params = {}
            if limit:
                params['limit'] = limit
            result = self.market_api.get_candlesticks(
                instId=symbol.replace('/', '-'),
                bar=timeframe,
                limit=limit or 100
            )
            if result['code'] == '0':
                return result['data']
            else:
                error_msg = f"获取K线数据失败: {result['msg']} | 错误码: {result['code']} | 参数: symbol={symbol}, timeframe={timeframe}, limit={limit}"
                self.logger.error(error_msg)
        except Exception as e:
            error_msg = f"获取K线数据失败: {str(e)} | 堆栈信息: {traceback.format_exc()} | 参数: symbol={symbol}, timeframe={timeframe}, limit={limit}"
            raise Exception(error_msg)

    async def fetch_ticker(self, symbol):
        self.logger.debug(f"获取行情数据 {symbol}...")
        start = datetime.now()
        try:
            result = self.market_api.get_ticker(instId=symbol.replace('/', '-'))
            if result['code'] == '0':
                ticker = result['data'][0]
                latency = (datetime.now() - start).total_seconds()
                self.logger.debug(f"获取行情成功 | 延迟: {latency:.3f}s | 最新价: {ticker['last']}")
                return ticker
            else:
                error_msg = f"获取行情失败: {result['msg']} | 错误码: {result['code']} | 参数: symbol={symbol}"
                self.logger.error(error_msg)
                raise Exception(error_msg)
        except Exception as e:
            error_msg = f"获取行情失败: {str(e)} | 堆栈信息: {traceback.format_exc()} | 参数: symbol={symbol}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    async def fetch_funding_balance(self):
        """获取理财账户余额（含缓存机制）"""
        now = time.time()
        if now - self.funding_balance_cache['timestamp'] < self.cache_ttl:
            return self.funding_balance_cache['data']
        
        try:
            result = self.funding_api.get_balances()
            if result['code'] == '0':
                balances = {"USDT": 0.0, BASE_CURRENCY: 0.0}
                for item in result['data']:
                    asset = item['ccy']
                    amount = float(item['availBal'])
                    balances[asset] = amount
                
                # 更新缓存
                self.funding_balance_cache = {
                    'timestamp': now,
                    'data': balances
                }
                return balances
            else:
                error_msg = f"获取理财账户余额失败: {result['msg']} | 错误码: {result['code']}"
                self.logger.error(error_msg)
                raise Exception(error_msg)
        except Exception as e:
            error_msg = f"获取理财账户余额失败: {str(e)} | 堆栈信息: {traceback.format_exc()}"
            self.logger.error(error_msg)
            return self.funding_balance_cache['data'] if self.funding_balance_cache['data'] else {}

    async def fetch_balance(self, params=None):
        """获取账户余额（含缓存机制）"""
        now = time.time()
        if now - self.balance_cache['timestamp'] < self.cache_ttl:
            return self.balance_cache['data']
        
        try:
            # 使用 asyncio.to_thread 将同步调用转换为异步调用
            result = await asyncio.to_thread(self.account_api.get_account_balance)
            if result['code'] == '0':
                balance = {'free': {}, 'used': {}, 'total': {}}
                
                for item in result['data'][0]['details']:
                    asset = item['ccy']
                    free = float(item['availBal'])
                    total = float(item['eq'])
                    used = total - free
                    
                    balance['free'][asset] = free
                    balance['used'][asset] = used
                    balance['total'][asset] = total
                
                # 获取理财账户余额
                funding_balance = await self.fetch_funding_balance()
                # 合并现货和理财余额
                for asset, amount in funding_balance.items():
                    if asset not in balance['total']:
                        balance['total'][asset] = 0
                    if asset not in balance['free']:
                        balance['free'][asset] = 0
                    balance['total'][asset] += amount
                
                self.logger.debug(f"账户余额概要: {balance['total']}")
                # 更新缓存
                self.balance_cache = {
                    'timestamp': now,
                    'data': balance
                }
                return balance
            else:
                error_msg = f"获取余额失败: {result['msg']} | 错误码: {result['code']}"
                self.logger.error(error_msg)
                raise Exception(error_msg)
        except Exception as e:
            error_msg = f"获取余额失败: {str(e)} | 堆栈信息: {traceback.format_exc()}"
            self.logger.error(error_msg)
            return {'free': {}, 'used': {}, 'total': {}}
    
    async def create_order(self, symbol, type, side, amount, price):
        try:
            params = {
                'instId': symbol.replace('/', '-'),
                'tdMode': 'cash',
                'side': side.lower(),
                'ordType': type.lower(),
                'sz': str(amount)
            }
            
            if type.lower() != 'market':
                # 格式化价格，避免科学计数法表示
                if price < 0.0001:
                    # 对于极小价格，使用完整的十进制格式
                    price_str = f"{price:.12f}".rstrip('0').rstrip('.')
                    params['px'] = price_str
                else:
                    # 普通价格保留标准精度
                    params['px'] = f"{price:.8f}".rstrip('0').rstrip('.')
            
            self.logger.info(f"提交订单: {params}")
            result = await asyncio.to_thread(self.trade_api.place_order, **params)
            if result['code'] == '0':
                return result['data'][0]
            else:
                error_msg = f"下单失败: {result['msg']} | 错误码: {result['code']} | 参数: symbol={symbol}, type={type}, side={side}, amount={amount}, price={price}"
                self.logger.error(error_msg)
                raise Exception(error_msg)
        except Exception as e:
            error_msg = f"下单失败: {str(e)} | 堆栈信息: {traceback.format_exc()} | 参数: symbol={symbol}, type={type}, side={side}, amount={amount}, price={price}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    async def fetch_order(self, order_id, symbol, params=None):
        try:
            result = await asyncio.to_thread(self.trade_api.get_order,
                instId=symbol.replace('/', '-'),
                ordId=order_id
            )
            if result['code'] == '0':
                return result['data'][0]
            else:
                error_msg = f"获取订单失败: {result['msg']} | 错误码: {result['code']} | 参数: order_id={order_id}, symbol={symbol}"
                self.logger.error(error_msg)
                raise Exception(error_msg)
        except Exception as e:
            error_msg = f"获取订单失败: {str(e)} | 堆栈信息: {traceback.format_exc()} | 参数: order_id={order_id}, symbol={symbol}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    async def fetch_open_orders(self, symbol):
        """获取当前未成交订单"""
        try:
            result = await asyncio.to_thread(self.trade_api.get_order_list,
                instId=symbol.replace('/', '-')
            )
            if result['code'] == '0':
                return result['data']
            else:
                error_msg = f"获取未成交订单失败: {result['msg']} | 错误码: {result['code']} | 参数: symbol={symbol}"
                self.logger.error(error_msg)
                raise Exception(error_msg)
        except Exception as e:
            error_msg = f"获取未成交订单失败: {str(e)} | 堆栈信息: {traceback.format_exc()} | 参数: symbol={symbol}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    async def cancel_order(self, order_id, symbol, params=None):
        """取消指定订单"""
        try:
            result = await asyncio.to_thread(self.trade_api.cancel_order,
                instId=symbol.replace('/', '-'),
                ordId=order_id
            )
            if result['code'] == '0':
                return result['data'][0]
            else:
                error_msg = f"取消订单失败: {result['msg']} | 错误码: {result['code']} | 参数: order_id={order_id}, symbol={symbol}"
                self.logger.error(error_msg)
                raise Exception(error_msg)
        except Exception as e:
            error_msg = f"取消订单失败: {str(e)} | 堆栈信息: {traceback.format_exc()} | 参数: order_id={order_id}, symbol={symbol}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    async def close(self):
        """关闭交易所连接"""
        try:
            self.logger.info("OKX交易所连接已安全关闭")
        except Exception as e:
            error_msg = f"关闭连接时发生错误: {str(e)} | 堆栈信息: {traceback.format_exc()}"
            self.logger.error(error_msg)

    async def fetch_order_book(self, symbol, limit=5):
        """获取订单簿数据"""
        try:
            result = await asyncio.to_thread(self.market_api.get_orderbook,
                instId=symbol.replace('/', '-'),
                sz=str(limit)
            )
            if result['code'] == '0':
                return result['data'][0]
            else:
                error_msg = f"获取订单簿失败: {result['msg']} | 错误码: {result['code']} | 参数: symbol={symbol}, limit={limit}"
                self.logger.error(error_msg)
                raise Exception(error_msg)
        except Exception as e:
            error_msg = f"获取订单簿失败: {str(e)} | 堆栈信息: {traceback.format_exc()} | 参数: symbol={symbol}, limit={limit}"
            self.logger.error(error_msg)
            raise Exception(error_msg)

    async def sync_time(self):
        """同步交易所服务器时间"""
        try:
            server_time = await asyncio.to_thread(self.public_api.get_system_time)
            local_time = int(time.time() * 1000)
            self.time_diff = server_time - local_time
            self.logger.info(f"时间同步完成 | 时差: {self.time_diff}ms")
        except Exception as e:
            error_msg = f"时间同步失败: {str(e)} | 堆栈信息: {traceback.format_exc()}"
            self.logger.error(error_msg)

    async def transfer_to_spot(self, asset, amount):
        """从活期理财赎回到现货账户"""
        try:
            # 格式化金额，确保精度正确
            if asset == 'USDT':
                formatted_amount = "{:.2f}".format(float(amount))
            elif asset == config.BASE_CURRENCY:
                formatted_amount = "{:.8f}".format(float(amount))
            else:
                formatted_amount = str(amount)
            params = {
                'ccy': asset,
                'amt': formatted_amount,
                'side': 'redempt',
                'rate': '0.03'
            }
            self.logger.info(f"开始赎回: {formatted_amount} {asset} 到现货")
            result = await asyncio.to_thread(self.savings_api.savings_purchase_redemption, **params)
            self.logger.info(f"划转成功: {result}")
            
            # 赎回后清除余额缓存，确保下次获取最新余额
            self.balance_cache = {'timestamp': 0, 'data': None}
            self.funding_balance_cache = {'timestamp': 0, 'data': {}}
            
            return result
        except Exception as e:
            error_msg = f"赎回失败: {str(e)} | 堆栈信息: {traceback.format_exc()} | 参数: asset={asset}, amount={amount}"
            self.logger.error(error_msg)
            raise Exception(error_msg)

    async def transfer_to_savings(self, asset, amount):
        """从现货账户申购活期理财"""
        try:
            # 格式化金额，确保精度正确
            if asset == 'USDT':
                formatted_amount = "{:.2f}".format(float(amount))  # USDT保留2位小数
            elif asset == BASE_CURRENCY:
                formatted_amount = "{:.8f}".format(float(amount))  # 基础币种保留8位小数
            else:
                formatted_amount = str(amount)
            
            # 获取当前可用余额进行检查
            balance = await self.fetch_balance()
            available = float(balance.get('free', {}).get(asset, 0))
            
            # 检查余额是否足够
            if available < float(formatted_amount):
                self.logger.warning(f"申购余额不足: 请求申购 {formatted_amount} {asset}, 但可用余额仅有 {available} {asset}")
                return {'code': '0', 'msg': 'Skipped due to insufficient balance', 'data': []}
            
            params = {
                'ccy': asset,
                'amt': formatted_amount,
                'side': 'purchase',
                'rate': '1', # 添加rate参数，OKX API要求此参数
            }
            self.logger.info(f"开始申购: {formatted_amount} {asset} 到活期理财")
            result = await asyncio.to_thread(self.savings_api.savings_purchase_redemption, **params)
            
            # 检查API返回结果是否成功
            if isinstance(result, dict) and result.get('code') != '0':
                self.logger.error(f"申购失败 - API返回错误: {result}")
                if 'This feature is unavailable in demo trading' in str(result):
                    self.logger.warning(f"模拟交易模式不支持理财功能，忽略错误")
                    # 模拟成功，避免后续错误
                    return {'code': '0', 'msg': 'Simulated success in demo mode', 'data': []}
                elif result.get('code') == '58350':
                    self.logger.warning(f"余额不足(58350): 尝试申购 {formatted_amount} {asset}, 但交易所报告余额不足")
                    # 返回一个表示特定错误的结果，但不抛出异常中断流程
                    return {'code': '58350', 'msg': 'Insufficient balance reported by exchange', 'data': []}
                else:
                    raise Exception(f"申购API返回错误: {result}")
            else:
                self.logger.info(f"划转成功: {result}")
            
            # 申购后清除余额缓存，确保下次获取最新余额
            self.balance_cache = {'timestamp': 0, 'data': None}
            self.funding_balance_cache = {'timestamp': 0, 'data': {}}
            
            return result
        except Exception as e:
            error_msg = f"申购失败: {str(e)} | 堆栈信息: {traceback.format_exc()} | 参数: asset={asset}, amount={amount}"
            self.logger.error(error_msg)
            
            # 判断是否是模拟交易环境不支持理财功能的错误
            if 'This feature is unavailable in demo trading' in str(e):
                self.logger.warning(f"模拟交易模式不支持理财功能，忽略错误")
                # 模拟成功，避免中断交易流程
                return {'code': '0', 'msg': 'Simulated success in demo mode', 'data': []}
            
            # 判断是否是余额不足错误
            if 'Insufficient balance' in str(e) or '58350' in str(e):
                self.logger.warning(f"余额不足错误: 请求申购 {formatted_amount} {asset}, 但交易所报告余额不足")
                return {'code': '58350', 'msg': 'Insufficient balance reported by exchange', 'data': []}
                
            raise Exception(error_msg)

    async def fetch_my_trades(self, symbol, limit=10):
        """获取指定交易对的最近成交记录"""
        self.logger.debug(f"获取最近 {limit} 条成交记录 for {symbol}...")
        if not self.markets_loaded:
            self.load_markets()
        try:
            # 确保使用市场ID
            trades = await asyncio.to_thread(self.trade_api.get_orders_history,
                instType='SPOT',
                instId=symbol,
                limit=limit
            )
            self.logger.info(f"成功获取 {len(trades)} 条最近成交记录 for {symbol}")
            return trades
        except Exception as e:
            error_msg = f"获取成交记录失败: {str(e)} | 堆栈信息: {traceback.format_exc()} | 参数: symbol={symbol}, limit={limit}"
            self.logger.error(error_msg)
            return [] 
