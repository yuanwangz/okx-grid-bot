import logging
import traceback
from config import MAX_POSITION_RATIO

class AdvancedRiskManager:
    def __init__(self, trader):
        self.trader = trader
        self.logger = logging.getLogger(self.__class__.__name__)
        
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
    
    async def multi_layer_check(self):
        try:
            position_ratio = await self._get_position_ratio()
            
            # 保存上次的仓位比例
            if not hasattr(self, 'last_position_ratio'):
                self.last_position_ratio = position_ratio
            
            # 只在仓位比例变化超过0.1%时打印日志
            if abs(position_ratio - self.last_position_ratio) > 0.001:
                self.logger.info(
                    f"风控检查 | "
                    f"当前仓位比例: {position_ratio:.2%} | "
                    f"最大允许比例: {self.trader.config.MAX_POSITION_RATIO:.2%} | "
                    f"最小底仓比例: {self.trader.config.MIN_POSITION_RATIO:.2%}"
                )
                self.last_position_ratio = position_ratio
            
            if position_ratio < self.trader.config.MIN_POSITION_RATIO:
                self.logger.warning(f"底仓保护触发 | 当前: {position_ratio:.2%}")
                return True
            
            if position_ratio > self.trader.config.MAX_POSITION_RATIO:
                self.logger.warning(f"仓位超限 | 当前: {position_ratio:.2%}")
                return True
        except Exception as e:
            self.logger.error(f"风控检查失败: {str(e)} | 堆栈信息: {traceback.format_exc()}")
            return False

    async def _get_position_value(self):
        balance = await self.trader.exchange.fetch_balance()
        funding_balance = await self.trader.exchange.fetch_funding_balance()
        if not self.trader.symbol_info:
            self.trader.trade_log.error("交易对信息未初始化")
            return 0
        base_amount = (
            float(balance.get('free', {}).get(self.trader.symbol_info['base'], 0)) +
            float(funding_balance.get(self.trader.symbol_info['base'], 0))
        )
        current_price = await self.trader._get_latest_price()
        return base_amount * current_price

    async def _get_position_ratio(self):
        """获取当前仓位占总资产比例"""
        try:
            position_value = await self._get_position_value()
            balance = await self.trader.exchange.fetch_balance()
            funding_balance = await self.trader.exchange.fetch_funding_balance()
            
            usdt_balance = (
                float(balance.get('free', {}).get('USDT', 0)) +
                float(funding_balance.get('USDT', 0))
            )
            
            total_assets = position_value + usdt_balance
            if total_assets == 0:
                return 0
                
            ratio = position_value / total_assets
            
            # 获取当前币价和币种余额，用于日志
            current_price = self.trader.current_price
            price_formatted = self._format_crypto_price(current_price)
            
            # 获取币种余额
            base_symbol = self.trader.symbol_info['base']
            base_amount = (
                float(balance.get('free', {}).get(base_symbol, 0)) +
                float(funding_balance.get(base_symbol, 0))
            )
            base_formatted = f"{base_amount:.8f}".rstrip('0').rstrip('.') if '.' in f"{base_amount:.8f}" else f"{base_amount:.8f}"
            
            self.logger.debug(
                f"仓位计算 | "
                f"{base_symbol}:{base_formatted}个, "
                f"{base_symbol}价值: {position_value:.2f} USDT | "
                f"USDT余额: {usdt_balance:.2f} | "
                f"总资产: {total_assets:.2f} | "
                f"仓位比例: {ratio:.2%} | "
                f"当前价格: {price_formatted}"
            )
            return ratio
        except Exception as e:
            self.logger.error(f"计算仓位比例失败: {str(e)} | 堆栈信息: {traceback.format_exc()}")
            return 0

    async def check_market_sentiment(self):
        """检查市场情绪指标"""
        try:
            fear_greed = await self._get_fear_greed_index()
            if fear_greed < 20:  # 极度恐惧
                self.trader.config.RISK_FACTOR *= 0.5  # 降低风险系数
            elif fear_greed > 80:  # 极度贪婪
                self.trader.config.RISK_FACTOR *= 1.2  # 提高风险系数
        except Exception as e:
            self.logger.error(f"获取市场情绪失败: {str(e)} | 堆栈信息: {traceback.format_exc()}") 