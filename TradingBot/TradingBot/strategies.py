import logging
from models import *
import typing

logger = logging.getLogger()


class Strategy:
    def __init__(self, contract: Contract, exchange: str, timeframe: str, balance_pct: float, take_profit: float,
                 stop_loss: float):
        
        self.contract = contract
        self.exchange = exchange
        self.tf = timeframe
        self.balance_pct = balance_pct
        self.take_profit = take_profit
        self.stop_loss = stop_loss


class TechnicalStrategy(Strategy):
    def __init__(self, contract: Contract, exchange: str, timeframe: str, balance_pct: float, take_profit: float,
                 stop_loss: float, other_params: typing.Dict):
        super().__init__(contract, exchange, timeframe, balance_pct, take_profit, stop_loss)

        self.ema_fast = other_params['ema_fast']
        self.ema_slow = other_params['ema_slow']
        self.ema_signal = other_params['ema_signal']

        print("ACTIVATED TECHNICAL")


class BreakoutStrategy(Strategy):
    def __init__(self, contract: Contract, exchange: str, timeframe: str, balance_pct: float, take_profit: float,
                 stop_loss: float, other_params: typing.Dict):
        super().__init__(contract, exchange, timeframe, balance_pct, take_profit, stop_loss)

        self.min_volume = other_params['min_volume']
