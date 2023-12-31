import logging
import requests
import pprint
import time
import hmac
import hashlib
import typing
from urllib.parse import urlencode
import websocket
import threading
import json
from models import *

#######################################################################################################

#######################################################################################################

#"https://fapi.binance.com"
#"https://testnet.binancefuture.com"
#"wss://fstream.binance.com"

logger = logging.getLogger()

class BinanceFuturesClient:
    def __init__(self, public_key: str, secret_key: str, testnet: bool):
        if testnet:
            self.base_url = "https://testnet.binancefuture.com"
            self.wss_url = "wss://stream.binancefuture.com/ws"
        else:
            self.base_url = "https://fapi.binance.com"
            self.wss_url = "wss://fstream.binance.com/ws"
        
        self.prices = dict()
        self.public_key = public_key
        self.secret_key = secret_key
        self.headers = {'X-MBX-APIKEY': self.public_key}
        self.ws_id = 1
        self.ws = None
        self.contracts = self.get_contracts()
        self.balances = self.get_balances()
        self.logs = []

        threading.Thread(target=self._start_ws).start()

        logger.info("Binance Futures Client successfully initialized")

    def _add_log(self, msg: str):
        logger.info("%s", msg)
        self.logs.append({"log": msg, "displayed": False})

    def _generate_signature(self, data: typing.Dict):
        return hmac.new(self.secret_key.encode(), urlencode(data).encode(), hashlib.sha256).hexdigest()

    def _make_request(self, method: str, endpoint: str, data: typing.Dict):
        if method == "GET":
            try:
                response = requests.get(self.base_url + endpoint, params=data, headers=self.headers)
            except Exception as e:
                logger.error("Connection error while making %s request to %s: %s", method, endpoint, e)
                return None
        elif method == "POST":
            try:
                response = requests.post(self.base_url + endpoint, params=data, headers=self.headers)
            except Exception as e:
                logger.error("Connection error while making %s request to %s: %s", method, endpoint, e)
                return None
        elif method == "DELETE":
            try:
                response = requests.delete(self.base_url + endpoint, params=data, headers=self.headers) 
            except Exception as e:
                logger.error("Connection error while making %s request to %s: %s", method, endpoint, e)  
                return None
        else:
            raise ValueError()
        if response.status_code == 200:
            return response.json()
        else:
            logger.error("ERROR while making %s request to %s: %s (error code %s)", method, endpoint, response.json(), response.status_code)
            return None
    
    def get_contracts(self) -> typing.Dict[str, Contract]:
        exchange_info = self._make_request("GET", "/fapi/v1/exchangeInfo", dict())
        contracts = dict()

        if exchange_info is not None:
            for contract_data in exchange_info['symbols']:
                contracts[contract_data['symbol']] = Contract(contract_data)

        return contracts

    def get_historical_candles(self, contract: Contract, interval: str) -> typing.List[Candle]:
        #"https://testnet.binancefuture.com//fapi/v1/ticker/bookTicker?symbol=BTCUSDT"
        data = dict()
        data['symbol'] = contract.symbol
        data['interval'] = interval
        data['limit'] = 1000

        raw_candles = self._make_request("GET", "/fapi/v1/klines", data)
        candles = []

        if raw_candles is not None:
            for c in raw_candles:
                candles.append(Candle(c))

        return candles
    
    def get_bid_ask(self, contract: Contract) -> typing.Dict[str, float]:
        data = dict()
        data['symbol'] = contract.symbol
        ob_data = self._make_request("GET", "/fapi/v1/ticker/bookTicker", data)

        if ob_data is not None:
            if contract.symbol not in self.prices:
                self.prices[contract.symbol] = {'bid': float(ob_data['bidPrice']), 'ask': float(ob_data['askPrice'])}
            else: 
                self.prices[contract.symbol]['bid'] = float(ob_data['bidPrice'])
                self.prices[contract.symbol]['ask'] = float(ob_data['askPrice'])

            return self.prices[contract.symbol]
    
    def get_balances(self) -> typing.Dict[str, Balance]:
        data = dict()
        data['timestamp'] = int(time.time()*1000)
        data['signature'] = self._generate_signature(data)
        balances = dict()

        account_data = self._make_request("GET", "/fapi/v2/account", data)

        if account_data is not None:
            for a in account_data['assets']:
                balances[a['asset']] = Balance(a)

        return balances
    
    def place_order(self, contract: Contract, side: str, quantity: float, order_type: str, price=None, tif=None) -> OrderStatus:
        data = dict()
        data['symbol'] = contract.symbol
        data['side'] = side
        data['quantity'] = quantity
        data['type'] = order_type

        if  price is not None:
            data['price'] = price
        if tif is not None:
            data['timeInForce'] = tif
        
        data['timestamp'] = int(time.time()*1000)
        data['signature'] = self._generate_signature(data)

        order_status = self._make_request("POST", "/fapi/v1/order", data)

        if order_status is not None:
            order_status = OrderStatus(order_status)

        return order_status
    
    def cancel_order(self, contract: Contract, order_id: int) -> OrderStatus:
        data = dict()
        data['orderId'] = order_id
        data['symbol'] = contract.symbol
        data['timestamp'] = int(time.time()*1000)
        data['signature'] = self._generate_signature(data)

        order_status = self._make_request("DELETE", "/fapi/v1/order", data)

        if order_status is not None:
            order_status = OrderStatus(order_status)

        return order_status
    
    def get_order_status(self, contract: Contract, order_id: int) -> OrderStatus:
        data = dict()
        data['timestamp'] = int(time.time()*1000)
        data['symbol'] = contract.symbol
        data['orderId'] = order_id
        data['signature'] = self._generate_signature(data)

        order_status = self._make_request("GET", "/fapi/v1/order", data)

        if order_status is not None:
            order_status = OrderStatus(order_status)

        return order_status
    
    def _start_ws(self):
        self.ws = websocket.WebSocketApp(self.wss_url, on_open=self._on_open, on_close=self._on_close, 
                                    on_error=self._on_error, on_message=self._on_message)
        while True:
            try:
                self.ws.run_forever()
            except Exception as e:
                logger.error("Binance error in run_forever(): %s", e)
            time.sleep(2)  
    
    def _on_open(self, ws):
        logger.info("Binance connection openend")
        self.subscribe_channel(list(self.contracts.values()), "bookTicker")
        


    def _on_close(self, ws):
        logger.warning("Binance connection closed")

    def _on_error(self, ws, msg: str):
        logger.error("Binance connection error: %s", msg)

    def _on_message(self, ws, msg: str):
        data = json.loads(msg)

        if "e" in data:
            if data['e'] == "bookTicker":
                symbol = data['s']
                if symbol not in self.prices:
                    self.prices[symbol] = {'bid': float(data['b']), 'ask': float(data['a'])}
                else: 
                    self.prices[symbol]['bid'] = float(data['b'])
                    self.prices[symbol]['ask'] = float(data['a'])

                    #self._add_log(symbol + " " + str(self.prices[symbol]['bid']) + " / " + str(self.prices[symbol]['ask']))                


    def subscribe_channel(self, contracts: typing.List[Contract], channel: str):
        data = dict()
        data ['method'] = "SUBSCRIBE"
        data['params'] = []

        for contract in contracts:
            data['params'].append(contract.symbol.lower() + "@" + channel)
        data['id'] = self.ws_id

        try:
            self.ws.send(json.dumps(data))
        except Exception as e:
            logger.error("Websocket error while subscribing to %s %s updates: %s", len(contracts), channel, e)  
        self.ws_id += 1
