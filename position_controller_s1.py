# position_controller_s1.py
import time
import asyncio
import logging
import math # 需要 math 来处理精度

class PositionControllerS1:
    """
    独立的仓位控制策略 (S1)。
    基于每日更新的52日高低点，高频检查仓位并执行调整。
    独立于主网格策略运行，不修改网格的 base_price。
    """
    def __init__(self, trader_instance):
        """
        初始化S1仓位控制器。

        Args:
            trader_instance: 主 GridTrader 类的实例，用于访问交易所客户端、
                             获取账户信息、执行订单和日志记录。
        """
        self.trader = trader_instance  # 保存对主 trader 实例的引用
        self.config = trader_instance.config # 访问配置
        self.logger = logging.getLogger(self.__class__.__name__) # 创建独立的 logger

        # S1 策略参数 (从配置或直接赋值)
        # 确保这些参数在你的 config.py 或 trader_instance 中可访问
        self.s1_lookback = getattr(self.config, 'S1_LOOKBACK', 52)
        self.s1_sell_target_pct = getattr(self.config, 'S1_SELL_TARGET_PCT', 0.50)
        self.s1_buy_target_pct = getattr(self.config, 'S1_BUY_TARGET_PCT', 0.70)

        # S1 状态变量
        self.s1_daily_high = None
        self.s1_daily_low = None
        self.s1_last_data_update_ts = 0
        # 每日更新时间间隔（秒），略小于24小时确保不会错过
        self.daily_update_interval = 23.9 * 60 * 60 

        self.logger.info(f"S1 Position Controller initialized. Lookback={self.s1_lookback} days, Sell Target={self.s1_sell_target_pct*100}%, Buy Target={self.s1_buy_target_pct*100}%.")

    def _format_crypto_price(self, price):
        """格式化加密货币价格，保留足够精度并避免科学计数法"""
        if price is None:
            return "N/A"
        
        # 计算适合的小数位数
        if price == 0:
            return "0.00000000"
            
        # 对于非常小的价格，自动计算所需精度
        if abs(price) < 0.0001:
            # 找到第一个非零数字的位置
            temp = abs(price)
            count = 0
            while temp < 1:
                temp *= 10
                count += 1
                
            # 至少保留该精度后3位
            precision = max(count + 3, 10)
            return f"{price:.{precision}f}"
        
        # 常规价格处理
        elif abs(price) < 0.01:
            return f"{price:.8f}"
        elif abs(price) < 1:
            return f"{price:.6f}"
        elif abs(price) < 1000:
            return f"{price:.4f}"
        else:
            return f"{price:.2f}"

    async def _fetch_and_calculate_s1_levels(self):
        """获取日线数据并计算52日高低点"""
        try:
            # 获取比回看期稍多的日线数据 (+2 buffer)
            limit = self.s1_lookback + 2
            self.logger.info(f"S1: 获取{limit}条日线数据计算高低点")
            
            # 从交易所获取K线数据
            try:
                klines = await self.trader.exchange.fetch_ohlcv(
                    self.trader.symbol, 
                    timeframe='1D',
                    limit=limit
                )
                
                # 检查API返回结果
                if klines is None:
                    self.logger.error("S1: API返回了None，请检查交易对是否正确")
                    return False
                    
            except Exception as api_error:
                self.logger.error(f"S1: 获取K线数据失败: {api_error}")
                import traceback
                self.logger.error(f"S1: API调用堆栈跟踪: {traceback.format_exc()}")
                return False
            
            # 处理API响应格式 (简化日志输出)
            self.logger.debug(f"S1: API返回的K线数据类型: {type(klines)}")
            
            # 检查返回数据格式
            if isinstance(klines, dict):
                self.logger.debug(f"S1: API返回了字典格式数据")
                
                # 尝试处理OKX的API响应格式
                if 'data' in klines:
                    klines_data = klines['data']
                    self.logger.debug(f"S1: 从data字段中提取K线数据")
                    
                    if isinstance(klines_data, list) and len(klines_data) > 0:
                        klines = klines_data
                        self.logger.debug(f"S1: 成功提取了{len(klines)}条K线数据")
                    else:
                        self.logger.error(f"S1: data字段中的数据格式无效")
                        return False
                else:
                    self.logger.error("S1: 无法从API响应中找到data字段")
                    return False
            
            # 仅记录K线数量 (避免详细打印)
            self.logger.debug(f"S1: 获取到K线数量: {len(klines) if isinstance(klines, list) else '非列表格式'}")
            
            # 检查数据是否为空或不足
            if not isinstance(klines, list) or len(klines) < 3:
                self.logger.error(f"S1: K线数据不足或格式错误")
                return False
            
            # 确认每个K线元素的格式 (仅在调试级别记录)
            is_valid_format = True
            for i, kline in enumerate(klines[:3]):  # 只检查前3个元素
                if not isinstance(kline, (list, tuple)) or len(kline) < 6:
                    self.logger.error(f"S1: K线 #{i} 格式错误")
                    is_valid_format = False
                    break
                    
            if not is_valid_format:
                self.logger.error("S1: K线数据格式不符合预期")
                return False
                
            # 检查是否有足够的K线
            if len(klines) < self.s1_lookback:
                self.logger.warning(f"S1: K线数量不足 (有{len(klines)}，需要{self.s1_lookback})")
                return False
                
            try:
                # 获取高低点索引
                high_index = 2  # OKX格式：高点在索引2
                low_index = 3   # OKX格式：低点在索引3
                
                # 不再记录详细的K线样本数据，仅在调试级别记录一条
                if self.logger.isEnabledFor(logging.DEBUG):
                    sample = klines[0]
                    self.logger.debug(f"S1: K线样本 - 高:{self._format_crypto_price(float(sample[high_index]))}, 低:{self._format_crypto_price(float(sample[low_index]))}")
                
                # 使用前n个K线计算高低点
                relevant_klines = klines[:self.s1_lookback]
                
                # 计算高低点
                highs = [float(k[high_index]) for k in relevant_klines]
                lows = [float(k[low_index]) for k in relevant_klines]
                
                self.s1_daily_high = max(highs)
                self.s1_daily_low = min(lows)
                self.s1_last_data_update_ts = time.time()
                
                high_formatted = self._format_crypto_price(self.s1_daily_high)
                low_formatted = self._format_crypto_price(self.s1_daily_low)
                ratio = self.s1_daily_high/self.s1_daily_low if self.s1_daily_low != 0 else 0
                
                self.logger.info(f"S1: 52日高低点更新 - 高:{high_formatted}, 低:{low_formatted}, 比率:{ratio:.2f}")
                return True
                
            except Exception as calc_error:
                self.logger.error(f"S1: 计算高低点时出错: {calc_error}")
                import traceback
                self.logger.error(f"S1: 计算错误堆栈跟踪: {traceback.format_exc()}")
                return False
                
        except Exception as e:
            self.logger.error(f"S1: 获取或计算高低点失败: {e}")
            import traceback
            self.logger.error(f"S1: 错误堆栈跟踪: {traceback.format_exc()}")
            return False

    def _process_non_standard_klines(self, klines_data):
        """尝试处理非标准格式的K线数据"""
        try:
            self.logger.debug("S1: 尝试处理非标准K线格式")
            
            # 检查是否是字典格式（某些API返回格式）
            if isinstance(klines_data, dict):
                # 例如 {'data': [...klines...]}
                if 'data' in klines_data and isinstance(klines_data['data'], list):
                    klines = klines_data['data']
                    self.logger.debug(f"S1: 在data字段中找到{len(klines)}条K线")
                else:
                    # 尝试其他可能的字段
                    possible_fields = ['candles', 'klines', 'bars', 'ohlcv']
                    for field in possible_fields:
                        if field in klines_data and isinstance(klines_data[field], list):
                            klines = klines_data[field]
                            self.logger.debug(f"S1: 在{field}字段中找到{len(klines)}条K线")
                            break
                    else:
                        self.logger.error(f"S1: 无法在字典格式中找到K线数据")
                        return False
                        
                # 检查数据格式
                if len(klines) == 0:
                    self.logger.error("S1: 提取的K线列表为空")
                    return False
                    
                self.logger.debug("S1: 提取了K线数据")
                
                # 根据不同的K线格式处理
                # 1. 字典格式 - 例如 [{'timestamp':..., 'open':..., 'high':..., 'low':...}, ...]
                if isinstance(klines[0], dict):
                    self.logger.debug("S1: 检测到字典格式的K线")
                    
                    # 确定字段名
                    high_field = None
                    low_field = None
                    
                    # 常见的高低价字段名
                    high_candidates = ['high', 'h', 'High', 'HIGH']
                    low_candidates = ['low', 'l', 'Low', 'LOW']
                    
                    # 查找高价字段
                    for field in high_candidates:
                        if field in klines[0]:
                            high_field = field
                            break
                            
                    # 查找低价字段
                    for field in low_candidates:
                        if field in klines[0]:
                            low_field = field
                            break
                            
                    if high_field is None or low_field is None:
                        self.logger.error(f"S1: 无法确定字典格式中的高低价字段")
                        return False
                        
                    # 确保足够的K线数据
                    if len(klines) < self.s1_lookback:
                        self.logger.warning(f"S1: 字典格式中的K线不足: {len(klines)}")
                        return False
                        
                    # 计算高低点
                    relevant_klines = klines[:self.s1_lookback]
                    self.s1_daily_high = max(float(k[high_field]) for k in relevant_klines)
                    self.s1_daily_low = min(float(k[low_field]) for k in relevant_klines)
                    self.s1_last_data_update_ts = time.time()
                    self.logger.info(f"S1: 从字典格式更新高低点 - 高:{self._format_crypto_price(self.s1_daily_high)}, 低:{self._format_crypto_price(self.s1_daily_low)}")
                    return True
            
            # 如果无法处理数据
            self.logger.error("S1: 无法处理非标准K线格式")
            return False
            
        except Exception as e:
            self.logger.error(f"S1: 处理非标准K线时出错: {e}")
            import traceback
            self.logger.error(f"S1: 非标准处理错误: {traceback.format_exc()}")
            return False

    async def update_daily_s1_levels(self):
        """每日检查并更新一次S1所需的52日高低价"""
        try:
            now = time.time()
            if now - self.s1_last_data_update_ts >= self.daily_update_interval:
                self.logger.info("S1: 更新每日高低点...")
                try:
                    result = await self._fetch_and_calculate_s1_levels()
                    if not result:
                        self.logger.warning("S1: 更新每日高低点失败")
                except Exception as e:
                    self.logger.error(f"S1: 处理K线数据时出错: {str(e)}")
                    import traceback
                    self.logger.error(f"S1: K线处理错误详情: {traceback.format_exc()}")
            # else: 不需要更新
        except Exception as e:
            self.logger.error(f"S1: update_daily_s1_levels意外错误: {str(e)}")
            import traceback
            self.logger.error(f"S1: 更新错误堆栈跟踪: {traceback.format_exc()}")

    async def _execute_s1_adjustment(self, side, amount_okb):
        """
        专门执行 S1 仓位调整的下单函数。
        使用 trader 实例的 exchange 客户端直接下单。
        不更新网格的 base_price。
        """
        try:
            base_currency = self.trader.symbol_info['base']
            
            # 1. 精度调整 (复用 trader 中的方法，如果存在且安全)
            # 假设 trader 中有 _adjust_amount_precision 方法
            if hasattr(self.trader, '_adjust_amount_precision') and callable(self.trader._adjust_amount_precision):
                adjusted_amount = self.trader._adjust_amount_precision(amount_okb)
            else:
                # 如果没有，提供一个基础实现 (根据需要调整精度)
                precision = 3 
                factor = 10 ** precision
                adjusted_amount = math.floor(amount_okb * factor) / factor
                self.logger.warning("S1: Using basic amount precision adjustment.")

            if adjusted_amount <= 0:
                self.logger.warning(f"S1: Adjusted amount is zero or negative ({adjusted_amount}), skipping order.")
                return False

            # 2. 获取当前价格（用于后续日志和最小名义价值判断）
            current_price = self.trader.current_price # 假设主循环已更新
            if not current_price or current_price <= 0:
                 self.logger.error("S1: Invalid current price, cannot execute adjustment.")
                 return False
                 
            # 3. 检查最小订单限制 (复用 trader 中的 symbol_info, 如果存在)
            min_notional = 10 # 默认最小名义价值 (USDT)
            min_amount_limit = 0.0001 # 默认最小数量
            if hasattr(self.trader, 'symbol_info') and self.trader.symbol_info:
                 limits = self.trader.symbol_info.get('limits', {})
                 min_notional = limits.get('cost', {}).get('min', min_notional)
                 min_amount_limit = limits.get('amount', {}).get('min', min_amount_limit)
                 
            if adjusted_amount < min_amount_limit:
                self.logger.warning(f"S1: Adjusted amount {adjusted_amount:.8f} {base_currency} is below minimum amount limit {min_amount_limit:.8f}.")
                return False
            if adjusted_amount * current_price < min_notional:
                 self.logger.warning(f"S1: Order value {adjusted_amount * current_price:.2f} USDT is below minimum notional value {min_notional:.2f}.")
                 return False

            # 4. 检查余额，必要时从理财账户赎回资金
            if side == 'BUY':
                # 检查USDT余额是否足够
                usdt_needed = adjusted_amount * current_price
                usdt_available = await self.trader.get_available_balance('USDT')
                
                if usdt_available < usdt_needed:
                    self.logger.info(f"S1: USDT余额不足，需要{usdt_needed:.2f}，可用{usdt_available:.2f}，尝试从理财赎回")
                    
                    # 使用网格策略的资金转移方法
                    if hasattr(self.trader, '_pre_transfer_funds'):
                        try:
                            await self.trader._pre_transfer_funds(current_price)
                            # 重新检查余额
                            usdt_available = await self.trader.get_available_balance('USDT')
                            if usdt_available < usdt_needed:
                                self.logger.warning(f"S1: 即使赎回后，USDT余额仍不足，可用{usdt_available:.2f}")
                                return False
                        except Exception as e:
                            self.logger.error(f"S1: 从理财赎回资金失败: {e}")
                            return False
                    else:
                        self.logger.warning("S1: 无法从理财赎回资金，trader没有_pre_transfer_funds方法")
                        return False
                    
            elif side == 'SELL':
                # 检查币种余额是否足够
                if adjusted_amount > await self.trader.get_available_balance(base_currency):
                    self.logger.warning(f"S1: {base_currency}余额不足，无法执行卖出操作")
                    return False

            self.logger.info(f"S1: Placing {side} order for {adjusted_amount:.8f} {base_currency} at market price (approx {current_price})...")

            # 5. 使用 trader 的 exchange 客户端直接下单 (使用市价单确保执行调整)
            # 注意：市价单可能有滑点风险，对于大额调整需谨慎
            order = await self.trader.exchange.create_market_order(
                symbol=self.trader.symbol,
                side=side.lower(), # ccxt 通常需要小写
                amount=adjusted_amount
            )

            self.logger.info(f"S1: Adjustment order placed successfully. Order ID: {order.get('id', 'N/A')}")
            
            # 6. （可选）更新交易记录器 (如果希望S1交易也记录在案)
            if hasattr(self.trader, 'order_tracker'):
                 trade_info = {
                     'timestamp': time.time(),
                     'strategy': 'S1', # 标记来源
                     'side': side,
                     'price': float(order.get('average', current_price)), # 使用成交均价或市价
                     'amount': float(order.get('filled', adjusted_amount)), # 使用实际成交量
                     'order_id': order.get('id')
                     # 可以添加更多信息，如 cost, fee (如果API返回)
                 }
                 self.trader.order_tracker.add_trade(trade_info)
                 self.logger.info("S1: Trade logged in OrderTracker.")
                 
            # 7. 买入后如有多余资金，转入理财
            if side == 'BUY' and hasattr(self.trader, '_transfer_excess_funds'):
                try:
                    await self.trader._transfer_excess_funds()
                    self.logger.info("S1: 交易完成后尝试将多余资金转入理财")
                except Exception as e:
                    self.logger.warning(f"S1: 转移多余资金到理财失败: {e}")

            return True # 表示成功执行

        except Exception as e:
            self.logger.error(f"S1: Failed to execute adjustment order ({side} {amount_okb:.8f}): {e}", exc_info=True)
            return False


    async def check_and_execute(self):
        """
        高频检查 S1 仓位控制条件并执行调仓。
        应在主交易循环中频繁调用。
        """
        # 0. 确保我们有当天的 S1 边界值
        if self.s1_daily_high is None or self.s1_daily_low is None:
            self.logger.debug("S1: 尚未获取到每日高低点")
            return # 等待下次数据更新

        # 1. 获取当前状态 (通过 trader 实例)
        try:
            current_price = self.trader.current_price
            if not current_price or current_price <= 0:
                self.logger.warning("S1: 从trader获取的当前价格无效")
                return

            # 使用风控管理器的仓位计算方法
            self.logger.debug("S1: 获取当前仓位比例...")
            position_pct = await self.trader.risk_manager._get_position_ratio()
            self.logger.debug(f"S1: 当前仓位比例: {position_pct:.2%}")
            
            self.logger.debug("S1: 获取持仓价值...")
            position_value = await self.trader.risk_manager._get_position_value()
            
            self.logger.debug("S1: 获取总资产...")
            total_assets = await self.trader._get_total_assets()
            
            base_currency = self.trader.symbol_info['base']
            self.logger.debug(f"S1: 获取{base_currency}可用余额...")
            coin_balance = await self.trader.get_available_balance(base_currency) # 获取可用币种余额

            if total_assets <= 0:
                self.logger.warning("S1: 总资产值无效")
                return

        except Exception as e:
            self.logger.error(f"S1: 获取当前状态失败: {e}")
            import traceback
            self.logger.error(f"S1: 获取状态错误: {traceback.format_exc()}")
            return

        # 2. 判断 S1 条件
        s1_action = 'NONE'
        s1_trade_amount_okb = 0

        # 记录当前价格和高低点进行比较 - 精简为一行
        current_price_fmt = self._format_crypto_price(current_price)
        high_fmt = self._format_crypto_price(self.s1_daily_high)
        low_fmt = self._format_crypto_price(self.s1_daily_low)
        self.logger.debug(f"S1: 价格检查 - 当前: {current_price_fmt}, 高: {high_fmt}, 低: {low_fmt}, 仓位: {position_pct:.2%}")

        try:
            # 高点检查
            if current_price > self.s1_daily_high and position_pct > self.s1_sell_target_pct:
                s1_action = 'SELL'
                target_position_value = total_assets * self.s1_sell_target_pct
                sell_value_needed = position_value - target_position_value
                # 确保不会卖出负数或零 (以防万一)
                if sell_value_needed > 0:
                    s1_trade_amount_okb = min(sell_value_needed / current_price, coin_balance)
                    amount_fmt = self._format_crypto_price(s1_trade_amount_okb)
                    self.logger.info(f"S1: 价格突破52日高点，准备卖出 {amount_fmt} {base_currency} 降至目标仓位 {self.s1_sell_target_pct*100:.0f}%")
                else:
                    s1_action = 'NONE' # 重置，因为计算结果无效
                    self.logger.debug(f"S1: 价格突破52日高点但无需卖出，目标价值: {target_position_value:.2f}，当前价值: {position_value:.2f}")

            # 低点检查 (用 elif 避免同时触发)
            elif current_price < self.s1_daily_low and position_pct < self.s1_buy_target_pct:
                s1_action = 'BUY'
                target_position_value = total_assets * self.s1_buy_target_pct
                buy_value_needed = target_position_value - position_value
                # 确保不会买入负数或零
                if buy_value_needed > 0:
                    s1_trade_amount_okb = buy_value_needed / current_price
                    amount_fmt = self._format_crypto_price(s1_trade_amount_okb)
                    self.logger.info(f"S1: 价格跌破52日低点，准备买入 {amount_fmt} {base_currency} 提升至目标仓位 {self.s1_buy_target_pct*100:.0f}%")
                else:
                    s1_action = 'NONE' # 重置
                    self.logger.debug(f"S1: 价格跌破52日低点但无需买入，目标价值: {target_position_value:.2f}，当前价值: {position_value:.2f}")
            else:
                self.logger.debug(f"S1: 无调仓信号")
                
        except Exception as e:
            self.logger.error(f"S1: 信号计算错误: {e}")
            import traceback
            self.logger.error(f"S1: 信号计算堆栈跟踪: {traceback.format_exc()}")
            s1_action = 'NONE'

        # 3. 如果触发，执行 S1 调仓
        if s1_action != 'NONE' and s1_trade_amount_okb > 1e-9: # 加个极小值判断
            self.logger.info(f"S1: 执行{s1_action}调仓操作")
            try:
                await self._execute_s1_adjustment(s1_action, s1_trade_amount_okb)
            except Exception as e:
                self.logger.error(f"S1: 执行调仓失败: {e}")
                import traceback
                self.logger.error(f"S1: 调仓执行堆栈跟踪: {traceback.format_exc()}")
        else:
            self.logger.debug(f"S1: 无需调仓或调仓数量过小") 