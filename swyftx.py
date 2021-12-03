import requests
import json
import os
import numpy as np

from collections import deque
from datetime import datetime, timedelta
from threaded_timer import NearestTimer
from talib import MACD, EMA
from time import time
from nearest import erase_seconds, resolution_to_seconds
# API documentation: https://swyftx.docs.apiary.io/

endpoints = {
    "base": "https://api.swyftx.com.au/",
    "demo": "https://api.demo.swyftx.com.au/"
}


class OldTokenError(Exception):
    pass


class EmptyTokenError(Exception):
    pass

class SwagX:
    def __init__(self, apiKey, mode="demo", blacklist = ["USDT", "USDC", "BUSD"]):
        self.endpoint = endpoints[mode]
        self.is_demo = True if mode == "demo" else False
        self.key = apiKey
        self.default_header = {
            "Content-Type": "application/json"
        }
        self.session = requests.Session()
        self.token = self._fetch_token()
        self.authenticate_header = self._authenticate_header()
        self.asset_info = self._fetch_asset_info()
        self._blacklist = blacklist
        self._to_id, self._to_code = self._create_name_id_dict(self.asset_info)
        self.collected_data = {}
        self.threaded_timer = None

    def _authenticate_header(self):
        header = dict(self.default_header)
        header["Authorization"] = "Bearer " + self.token
        return header

    def _fetch_token(self):
        try:
            if datetime.now().timestamp() >= os.path.getmtime("token.txt") + 7 * 24 * 60 * 60:
                raise OldTokenError

            with open("token.txt", "r") as f:
                # Check if the file is 7 days old:
                print("token.txt exists")
                tok = f.readline()
                if len(tok) < 1:
                    raise EmptyTokenError
                return tok

        except (FileNotFoundError, OldTokenError, EmptyTokenError):
            # Gotta generate new key
            print("Invalid token.txt \nCreating a new token...")
            with open("token.txt", "w") as f:
                self.session.headers.update(self.default_header)
                t = json.loads(self.session.post(
                    "https://api.swyftx.com.au/auth/refresh/",
                    data=json.dumps(
                        {
                            "apiKey": self.key
                        })
                ).text)['accessToken']
                print("Token created successfully!")
                f.write(t)
                return t

    def _fetch_asset_info(self):
        self.session.headers.update(self.default_header)
        return json.loads(self.session.get(endpoints["base"] + "markets/info/basic/").text)

    def _create_name_id_dict(self, assets):
        code_to_id = {}
        id_to_code = {}

        code_to_id["AUD"] = "1"
        id_to_code["36"] = "USD"

        for asset in assets:
            code_to_id[asset["code"]] = str(asset["id"])
            id_to_code[str(asset["id"])] = asset["code"]

        return code_to_id, id_to_code

    def to_code(self, iid):
        return self._to_code[iid]

    def to_id(self, name):
        return self._to_id[name]

    def fetch_balance(self, prettify=True):

        self.session.headers.update(self.authenticate_header)
        balance = json.loads(self.session.get(self.endpoint + "user/balance/").text)
        if prettify:
            for i in range(len(balance)):
                balance[i]["code"] = self.to_code(str(balance[i]["assetId"]))

        return balance

    def get_top_n_assets(self, n=20):
        """
        Description: Grabs the top n assets (by rank) and returns them in the form of:
        [code, name, altName].
        
        Assets that are in the blacklist are ignored.
        
        Eg:
        ["BTC", "Bitcoin", "Bitcoin"]
        :param n: an integer that determines the top n coins to grab from SwyftX.
        """

        def less_than_or_equal_to_n(x, n):
            if x:
                if x <= n + 1:
                    return True

            return False

        self.session.headers.update(self.default_header)
        raw_assets = json.loads(self.session.get("https://api.swyftx.com.au/markets/info/basic/").text)
        cleaned_assets = list(filter(lambda x: x["rank"] is not None, raw_assets))
        blacklist_removed = list(filter(lambda x: x["code"] not in self._blacklist, cleaned_assets))
        sorted_assets = sorted(blacklist_removed, key=lambda x: x["rank"])
        return [
            {"code": sorted_assets[i]["code"], "name": sorted_assets[i]["name"], "altName": sorted_assets[i]["altName"]}
            for i in range(n) if i < n]

    def market_buy(self, primary, secondary, quantity, assetQuantity=None):
        """
        Description: Immediately buys 'secondary' with 'quantity' worth of 'assetQuanity' (usually 'primary') using primary.

        :primary (string): The currency/asset that we're (already own) trading 'secondary' for. The string represents its symbol, eg: BTC.
        :secondary (string): The currency/asset that we're (don't own) using 'primary' to trade for. This string represents its symbol.
        :quantity (string): The amount of 'assetQuantity' that will be spent for this trade.
        :assetQuantity (string): The amount in terms of whichever currency/asset we specify for this trade to be worth.
        
        **Examples**
        -------------------------------------------------------------------------------------
        SwagX.market_buy(primary="USD", secondary="BTC", quantity="1000", assetQuantity="USD")
        -------------------------------------------------------------------------------------
        The line above is telling the SwyftX API to buy $1000 USD worth of BTC at the current market price


        """

        if assetQuantity is None:
            assetQuantity = primary

        payload = {
            "primary": primary,
            "secondary": secondary,
            "quantity": quantity,
            "assetQuantity": assetQuantity,
            "orderType": 1
        }
        self.session.headers.update(self.authenticate_header)
        response = self.session.post(self.endpoint + "orders/", data=json.dumps(payload))
        return response

    def market_sell(self, primary, secondary, quantity, assetQuantity=None):
        """
        Description: Immediately sells 'secondary' with 'quantity' worth of 'assetQuanity' (usually 'primary') using primary.

        :primary (string): The currency/asset that we're (already own) trading 'secondary' for. The string represents its symbol, eg: BTC.
        :secondary (string): The currency/asset that we're (don't own) using 'primary' to trade for. This string represents its symbol.
        :quantity (string): The amount of 'assetQuantity' that will be spent for this trade.
        :assetQuantity (string): The amount in terms of whichever currency/asset we specify for this trade to be worth.

        **Examples**
        ---------------------------------------------------------------------------------------
        SwagX.market_sell(primary="USD", secondary="BTC", quantity="1000", assetQuantity="USD")
        ---------------------------------------------------------------------------------------
        The line above is telling the SwyftX API to sell $1000 USD worth of BTC at the current market price

        ---------------------------------------------------------------------------------------------
        SwagX.market_sell(primary="USD", secondary="BTC", quantity="0.00173294", assetQuantity="BTC")
        ---------------------------------------------------------------------------------------------
        The line above is telling the SwyftX API to sell 0.00173294 BTCs at the current market price for a suitable amount of USD
        
        """

        if assetQuantity is None:
            assetQuantity = primary

        payload = {
            "primary": primary,
            "secondary": secondary,
            "quantity": quantity,
            "assetQuantity": assetQuantity,
            "orderType": 2
        }
        self.session.headers.update(self.authenticate_header)
        response = self.session.post(self.endpoint + "orders/", data=json.dumps(payload))
        return response

    def get_asset_data(self, primary, secondary, side, resolution, time_start, time_end, readable_time=True):
        """
        ----------------------------------------------------------------------------------------------------------
        Notes:
        ask refers to the buy price.
        bid refers to the sell price.
        For some reason, SwyftX Unix time has 3 extra digits to the right because they keep track of milliseconds
            for some reason. So, when converting, remember to multiply my 1000, and dividing by 1000 when
            translating it to human-readable datetime.
        ----------------------------------------------------------------------------------------------------------
        :param time_start: 2 possibilities - either a string representing unix epoch, or a datetime object.
            Determines the starting time (time of the first bar).
        :param time_end: 2 possibilities - either a string representing unix epoch, or a datetime object.
            Determines the ending time (time of the last bar).
        :return:
        """
        if type(time_start) is datetime:
            time_start = str(1000*int(time_start.timestamp()))
        if type(time_end) is datetime:
            time_end = str(1000*int(time_end.timestamp()))

        self.session.headers.update(self.default_header)
        d = json.loads(self.session.get(endpoints[
                                 "base"] + "charts/getBars/" + "/".join([primary,secondary,side,"&".join(["?resolution="+resolution, f"timeStart={int(time_start)}",f"timeEnd={int(time_end)}"])])).text)["candles"]
        if readable_time:
            for i in range(len(d)):
                d[i]["time"] = datetime.fromtimestamp(int(d[i]["time"])/1000)
        return {
            "assetCode":secondary,
            "data":d
        }

    def get_last_completed_data(self, primary, secondary, side, resolution):
        """
        Gets the last completed bar (as per resolution) and returns that data.
        :return: a dictionary in the form of:
            {
                "side",
                "bid",
                "time",
                "open",
                "close",
                "low",
                "high"
            }
        """
        end = (erase_seconds(time()) + 1) * 1000
        start = end - resolution_to_seconds[resolution]*1000
        #print("Start time: ", datetime.fromtimestamp(start/1000))
        #print("End time: ", datetime.fromtimestamp(end/1000))
        d = json.loads(self.session.get(endpoints[
                                            "base"] + "charts/getBars/" + "/".join([primary,secondary,side,"&".join(["?resolution="+resolution, f"timeStart={int(start)}",f"timeEnd={int(end)}"])])).text)["candles"]
        return d[0]


    def get_latest_asset_data(self, primary, secondary, side, resolution, stream=False):
        """
        Gets the most recent price data for secondary asset in terms of its value in the primary asset.
        :param primary: The asset that we'll use to evaluate the value of the secondary asset.
        :param secondary: The asset that we're interested in.
        :param side: Determines whether we're looking for the 'ask' or 'bid' price.
        :param resolution: The time span that the candles will cover. Possible values include: '1m', '5m', '1h', '4h', '1d'
        :return: a dictionary in the form of:
            {
                "side",
                "bid",
                "time",
                "open",
                "close",
                "low",
                "high"
            }
        """
        self.session.headers.update(self.default_header)
        if not stream:
            r = self.session.get(endpoints["base"] + "charts/getLatestBar/" + "/".join([primary,secondary,side,"?resolution="+resolution]))
            d = json.loads(r.text)
            del d["volume"]
            return d
        else:
            with self.session.get(endpoints["base"] + "charts/getLatestBar/" + "/".join([primary,secondary,side,"?resolution="+resolution]), stream=True) as resp:
                for line in resp.iter_lines():
                    if line:
                        print(line)


    def extract_price_data(self, data, max_length = None):
        if max_length is None:
            max_length = len(data["data"])
        time, open, close, low, high = deque([],max_length), deque([],max_length), deque([],max_length), deque([],max_length), deque([],max_length)
        assetCode = data["assetCode"]
        data=data["data"]
        for i in range(max_length):
            time.append(data[i]["time"])
            open.append(data[i]["open"])
            close.append(data[i]["close"])
            low.append(data[i]["low"])
            high.append(data[i]["high"])

        return {
            "assetCode":assetCode,
            "time":time,
            "open":open,
            "close":close,
            "low":low,
            "high":high
        }

    def get_live_asset_rates(self, primary, secondary, reset_header = True, print_results=False):
        primary = self.to_id(primary)
        secondary = self.to_id(secondary)
        if reset_header:
            self.session.headers.update(self.default_header)
        r = json.loads(self.session.get(endpoints["base"] + "live-rates/" + primary + "/").text)
        if print_results:
            print(r[secondary])
        else:
            return r[secondary]


    def stream_data(self, primary, secondary, resolution):
        #self.get_live_asset_rates(primary, secondary, print_results=True)
        self.threaded_timer = NearestTimer(resolution, self.get_live_asset_rates, primary, secondary, print_results=True)
        #self.threaded_timer = RepeatedTimer(interval, self.get_live_asset_rates, primary, secondary,reset_header=False, print_results=True)
        #self.session.headers.update(self.default_header)
        #print(self.session.get(endpoints["base"]+"/".join(["charts/resolveSymbol",primary,secondary])).text)

    def livestream(self, delay = 1, *args, **kwargs):
        self.threaded_timer = NearestTimer(delay = delay, *args, **kwargs)
        #self.threaded_timer = RepeatedTimer(interval, func, *args, **kwargs)

    def stop_stream(self):
        self.threaded_timer.stop()

    def collect_and_process_live_data(self, primary, secondary, duration = None, start_time = None):
        now = datetime.now()
        if start_time is None:
            # If there's no specified start time, it will be set 24 hours before the time this line is executed.
            start_time = now - timedelta(days=1)

        data = self.extract_price_data(self.get_asset_data(primary, secondary, "ask", "1m", start_time, now, True))
        #data_bid = self.extract_price_data(self.get_asset_data(primary, secondary, "bid", "1m", start_time, now, True))
        max_length = len(data["close"])
        macd, macdsignal, macdhist = MACD(np.array(data["close"]))
        macd = deque(macd, max_length)
        macdsignal = deque(macdsignal, max_length)
        ema_hundred = deque(EMA(np.array(data["close"]), 100), max_length)
        return macd, macdsignal, ema_hundred

if '__main__' == __name__:
    with open("key.txt", "r") as f:
        key = f.readline()
    swag = SwagX(key)
