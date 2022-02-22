import requests
import json
import os
import numpy as np

from collections import deque
from datetime import datetime, timedelta
from threaded_timer import NearestTimer
from talib import MACD, EMA
from time import time, sleep
from nearest import erase_seconds, resolution_to_seconds, next_interval
# API documentation: https://swyftx.docs.apiary.io/

endpoints = {
    "base": "https://api.swyftx.com.au/",
    "demo": "https://api.demo.swyftx.com.au/"
}


class OldTokenError(Exception):
    pass


class EmptyTokenError(Exception):
    pass

class SwyftX:
    def __init__(self, apiKey, mode="demo", blacklist = ["USDT", "USDC", "BUSD"]):
        """
        Initialisation for SwyftX agent. Its main purpose is to interact with the SwyftX server such as fetching data
        and executing bull/sell orders.
        :param apiKey: a string that is the SwyftX API key. Instructions to creating your own is here:
            https://help.swyftx.com.au/en/articles/3825168-how-to-create-an-api-key
        :param mode: a string that determines the mode in which this bot is running. There are two possibilities:
            'demo': if you want to use SwyftX' demo mode where you have $10k USD to trade.
            'base': if you want to trade for real.
        :param blacklist: a list of ticker symbols that represents all secondary assets that we're not interested in
            trading.
        """
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
        self.asset_info = self._reshape_asset_info()
        self.collected_data = {}
        self.threaded_timer = None

    def _authenticate_header(self):
        """
        Creates the header that is needed for actions that require a higher level of authentication such as placing
        buy/sell orders.
        :return: a dictionary that is the header required to obtain permission to execute certain actions.
        """
        header = dict(self.default_header)
        header["Authorization"] = "Bearer " + self.token
        return header

    def _reshape_asset_info(self):
        """
        Converts the output of self._fetch_asset_info() into a dictionary with asset code as key.
        :return: a dictionary of dictionaries with the following structure:
            {
                *asset code*: {
                                    name,
                                    altName,
                                    code,
                                    id,
                                    rank,
                                    buy,
                                    sell,
                                    spread,
                                    volume24H,
                                    marketCap
                              }
            }
        """
        out = {}
        for asset in self.asset_info:
            out[asset["code"]] = asset

        return out

    def _fetch_token(self):
        """
        Attempts to retrieve a token from 'token.txt'. If the 'token.txt' doesn't exist, or the token inside is already
        expired, generate a new token and store it inside 'token.txt'.

        Tokens are required to perform actions that require a higher level of authentication. A notable example is
        placing buy/sell orders.
        :return: a string that represents the token.
        """
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

    def _fetch_asset_info(self, assetCode = ''):
        """
        Fetches all assets available on SwyftX.
        :return: a list of dictionaries in the following structure:
            {
                name,
                altName,
                code,
                id,
                rank,
                buy,
                sell,
                spread,
                volume24H,
                marketCap
            }
        """
        self.session.headers.update(self.default_header)
        return json.loads(self.session.get(endpoints["base"] + "markets/info/basic/" + assetCode).text)

    def _create_name_id_dict(self, assets):
        """
        Creates two dictionaries that can convert the id attributed to an asset by SwyftX to its ticker symbol and vice
        versa.
        :param assets: a dictionary with the same structure of the output of self._fetch_asset_info()
        :return: 2 dictionaries that can convert ID to ticker symbol and vice versa.
        """
        code_to_id = {}
        id_to_code = {}

        code_to_id["AUD"] = "1"
        code_to_id["USD"] = "36"
        id_to_code["36"] = "USD"
        id_to_code["1"] = "AUD"

        for asset in assets:
            code_to_id[asset["code"]] = str(asset["id"])
            id_to_code[str(asset["id"])] = asset["code"]

        return code_to_id, id_to_code

    def to_code(self, iid):
        """
        Takes in an id and converts it to the correct asset symbol that the id was referring to.
        :param iid: a string that represents the id of the asset we're interested in converting.
        :return: a string that represents the ticker symbol of the asset we're interested in converting.
        """
        return self._to_code[iid]

    def to_id(self, name):
        """
        Takes in a ticker symbol and converts it to the correct id that was referring to.
        :param name: a string that represents the ticker symbol of the asset we're interested in converting.
        :return: a string that represents the id of the asset we're interested in converting.
        """
        return self._to_id[name]

    def fetch_balance(self):
        """
        Fetches data about our wallet.
        :param prettify: a booylean that determines whether to convert id to ticker symbols such that it's more readable.
        :return: a list of dictionaries in the structure of:

            if prettify = True:
                {
                    assetId,
                    availableBalance,
                    code
                }

            else:
                {
                    assetId,
                    availableBalance
                }
        """
        self.session.headers.update(self.authenticate_header)
        balance = json.loads(self.session.get(self.endpoint + "user/balance/").text)
        out = {}
        for c in balance:
            out[self.to_code(str(c["assetId"]))] = float(c["availableBalance"])

        return out

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
        SwyftX.market_buy(primary="USD", secondary="BTC", quantity="1000", assetQuantity="USD")
        -------------------------------------------------------------------------------------
        The line above is telling the SwyftX API to buy $1000 USD worth of BTC at the current market price


        """

        if assetQuantity is None:
            assetQuantity = primary

        payload = {
            "primary": primary,
            "secondary": secondary,
            "quantity": str(quantity),
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
        SwyftX.market_sell(primary="USD", secondary="BTC", quantity="1000", assetQuantity="USD")
        ---------------------------------------------------------------------------------------
        The line above is telling the SwyftX API to sell $1000 USD worth of BTC at the current market price

        ---------------------------------------------------------------------------------------------
        SwyftX.market_sell(primary="USD", secondary="BTC", quantity="0.00173294", assetQuantity="BTC")
        ---------------------------------------------------------------------------------------------
        The line above is telling the SwyftX API to sell 0.00173294 BTCs at the current market price for a suitable amount of USD
        
        """

        if assetQuantity is None:
            assetQuantity = primary

        payload = {
            "primary": primary,
            "secondary": secondary,
            "quantity": str(quantity),
            "assetQuantity": assetQuantity,
            "orderType": 2
        }
        self.session.headers.update(self.authenticate_header)
        response = self.session.post(self.endpoint + "orders/", data=json.dumps(payload))
        return response

    def stop_loss(self, primary, secondary, quantity, trigger, assetQuantity=None):
        """
        Creates a sell order when (buy/sell) price drops to trigger.
        :primary (string): The currency/asset that we're (already own) trading 'secondary' for. The string represents its symbol, eg: BTC.
        :secondary (string): The currency/asset that we're (don't own) using 'primary' to trade for. This string represents its symbol.
        :quantity (string): The amount of 'assetQuantity' that will be spent for this trade.
        :trigger (string): The price that secondary asset needs to reach in order to execute a sell order.
        :assetQuantity (string): The amount in terms of whichever currency/asset we specify for this trade to be worth.

        **Examples**
        ---------------------------------------------------------------------------------------
        SwyftX.stop_loss(primary="AUD", secondary="BTC", quantity="1000", trigger="60000" assetQuantity="AUD")
        ---------------------------------------------------------------------------------------
        The line above is telling the SwyftX API to place a stop loss sell order that will sell $1000 AUD worth of BTC
        when the price falls to $60000 AUD.
        """
        if assetQuantity is None:
            assetQuantity = primary

        payload = {
            "primary": primary,
            "secondary": secondary,
            "quantity": str(quantity),
            "assetQuantity": assetQuantity,
            "orderType": 6,
            "trigger": 1/float(trigger)
        }
        self.session.headers.update(self.authenticate_header)
        response = self.session.post(self.endpoint + "orders/", data=json.dumps(payload))
        return response

    def get_order(self, orderUuid):
        """
        Grabs a specific order by its ID.
        :param orderUuid: a string that indicates the order ID of a particular order that we're interested in deleting.
        :return: a dictionary with the following structure if successful:
            {
              "orderUuid": "ord_123abc...",
              "order_type": "3",
              "primary_asset": "1",
              "secondary_asset": "3",
              "quantity_asset": "1",
              "quantity": 100,
              "trigger": 8500,
              "status": "1",
              "created_time": 1596684928098,
              "updated_time": 1596684928098,
              "amount": 100,
              "total": 0.01,
              "rate": 0.01,
              "audValue": 8501.025,
              "userCountryValue": 8501.025,
              "feeAmount": 12.25,
              "feeAsset": "36",
              "feeAudValue": 40.25,
              "feeUserCountryValue": 40.25
            }
        """
        self.session.headers.update(self.authenticate_header)
        response = self.session.get(self.endpoint + "orders/byId/" + orderUuid)
        return response

    def delete_order(self, orderUuid):
        """
        Deletes a specific order by its order ID.
        :param orderUuid: a string that indicates the order ID of a particular order that we're interested in deleting.
        :return: a dictionary with the following structure if successful:
            {
                'orderUuid',
                'updated_time',
                'status',
                'message'
            }

            Otherwise, it'll look like this:
            {
                'error',
                'message'
            }

        """
        self.session.headers.update(self.authenticate_header)
        response = self.session.delete(self.endpoint + "orders/" + orderUuid + "/")
        return response

    def delete_last_order(self, assetCode=""):
        """
        ###################### Not Reliable #########################
        Cancels the latest order. If we want to delete the last order for a specific asset, change orderUuid, otherwise
        it'll just delete the last asset.
        :param assetCode: a string that denotes the order for a specific asset.
        :return:
        """
        return self.delete_order(self.recent_order(assetCode)[-1]["orderUuid"])

    def recent_order(self, assetCode, limit="", page=""):
        """
        ###################### Not Reliable #########################
        Returns a list of dictionaries about recent orders.
        :param assetCode: a string that indicates the
        :param limit: a string that represents the number of entries (orders) we're interested in getting.
        :param page: **Honestly, I have no idea. Best to leave it blank.
        :return: a list of dictionaries in the form:
            {
                "orderUuid": order ID,
                "order_type": order type,
                "primary_asset",
                "secondary_asset",
                "quantity_asset": value in which quantity is evaluated in,
                "quantity": the number of asset indicated by "quantity_asset",
                "trigger",
                "status": a numerical digit that indicates the status of the order. ,
                "created_time",
                "updated_time",
                "amount": amount of secondary asset bought,
                "total": amount of primary asset sold,
                "rate": primary/secondary ratio for this particular trade,
                "audValue",
                "userCountryValue",
                "feeAmount": fees charged in terms of the primary asset,
                "feeAsset",
                "feeAudValue",
                "feeUserCountryValue"
              }
        """
        self.session.headers.update(self.authenticate_header)
        response = self.session.get(self.endpoint + "orders/" + "?".join([assetCode, limit, page]))
        return json.loads(response.text)["orders"]

    def get_asset_data(self, primary, secondary, side, resolution, time_start, time_end, readable_time=True):
        """

        ----------------------------------------------------------------------------------------------------------
        Notes:
        ask refers to the buy price.
        bid refers to the sell price.
        For some reason, SwyftX Unix time has 3 extra digits to the right because they keep track of milliseconds
            So, when converting, remember to multiply my 1000, and dividing by 1000 when translating it to
            human-readable datetime.
        ----------------------------------------------------------------------------------------------------------
        :param side: a string that can either be 'ask' or 'bid'.
        :param resolution: a string that can be one of the following:
            1m - 1 minute interval
            5m - 5 minute interval
            1h - 1 hour interval
            4h - 4 hour interval
            1d - 1 day interval
        :param time_start: 2 possibilities - either a string representing unix epoch, or a datetime object.
            Determines the starting time (time of the first bar).
        :param time_end: 2 possibilities - either a string representing unix epoch, or a datetime object.
            Determines the ending time (time of the last bar).
        :param readable_time: a boolean that will convert time to human-readable time instead of unix time.
        :return: a dictionary with the following structure:
            {
                assetCode,
                data
            }

            data is a list of dictionaries with the following structure:
                {
                    time,
                    close,
                    high,
                    low,
                    open,
                    volume,
                    name
                }
        """
        #print("time_start: ", datetime.fromtimestamp(time_start/1000))
        #print("time_end: ", datetime.fromtimestamp(time_end/1000))
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

    def get_asset_timeslot(self, primary, secondary, side, resolution, t):
        """
        Gets a specific timeslot for a specific cryptocurrency.
        :param primary:
        :param secondary:
        :param side:
        :param resolution:
        :param t: datetime object that indicates the timeslot we're interested.
        :return: a dictionary in the form of:
            {
                "time",
                "close",
                "high",
                "low",
                "open",
                "volume"
            }
        """
        out= self.get_asset_data(primary, secondary, side, resolution, t, t, readable_time=False)["data"]#[-1]
        #print("out =", out)
        print(t)
        return out[-1]


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

        #print(f"primary: {primary}, secondary: {secondary}, side: {side}, resolution: {resolution}")
        #print("get_last_completed_data execution time: ", datetime.now())
        end = (erase_seconds(time()) + 0) * 1000
        start = end - resolution_to_seconds[resolution]*1000
        #print("Start time: ", datetime.fromtimestamp(start/1000))
        #print("End time: ", datetime.fromtimestamp(end/1000))
        #print("Execution Time: ", datetime.now())

        #print(self.session.get(endpoints[
        #                           "base"] + "charts/getBars/" + "/".join([primary,secondary,side,"&".join(["?resolution="+resolution, f"timeStart={int(start)}",f"timeEnd={int(end)}"])])).text)
        #print("Fetch Time: ", datetime.now())

        d = []

        while len(d) < 1: # Band-aid fix for now.
            d = json.loads(self.session.get(endpoints[
                                                "base"] + "charts/getBars/" + "/".join([primary,secondary,side,"&".join(["?resolution="+resolution, f"timeStart={int(start)}",f"timeEnd={int(end)}"])])).text)["candles"]
            #print(d)

        return d[0]


    def get_latest_asset_data(self, primary, secondary, side, resolution, delay=0.3, stream=False):
        """
        Gets the most recent price data for secondary asset in terms of its value in the primary asset.
        To get the most recent bar, it has to be called EXACTLY at the point at which the price closes.
        :param primary: The asset that we'll use to evaluate the value of the secondary asset.
        :param secondary: The asset that we're interested in.
        :param side: Determines whether we're looking for the 'ask' or 'bid' price.
        :param resolution: The time span that the candles will cover. Possible values include: '1m', '5m', '1h', '4h', '1d'
        :param delay: A number that determines the time in seconds to delay the execution time by.
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
        ----------------------------------------------------------------------------------------------------------------
        So far, it only works well when resolution is set to '1m' or '5m'.

        Upon further testing:

        delay = 0.1 works well for '1m'
        delay = 0.3 works well for '1m' and '5m'
        delay = 0.5 doesn't work well for '1m'

        """
        #now = time()
        #execution_time = next_interval[resolution](now)
        #print("Execution time: ", datetime.fromtimestamp(now))
        #print("Anticipated execution time: ", datetime.fromtimestamp(execution_time))
        #sleep(execution_time-now + delay)
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
        """
        Takes in the raw data fetched by self.fetch_asset_data() and converts them into a neater structure.
        Deques will be used to store data for space efficiency's sake.
        :param data: output of self.fetch_asset_data()
        :param max_length: an integer that represents the maximum number of elements that our deques can simultaneously
            hold. If None, it will be as long as data.
        :return: a dictionary with the following structure:
            {
                assetCode,
                time,
                open,
                close,
                low,
                high
            }
        """
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
        """

        :param primary:
        :param secondary:
        :param reset_header:
        :param print_results:
        :return:
        """
        primary = self.to_id(primary)
        secondary = self.to_id(secondary)
        if reset_header:
            self.session.headers.update(self.default_header)
        r = json.loads(self.session.get(endpoints["base"] + "live-rates/" + primary + "/").text)
        if print_results:
            print(r[secondary])
        else:
            return r[secondary]

    def livestream(self, delay = 1, *args, **kwargs):
        """
        Livestreams live data directly from SwyftX.
        While this is running, it's possible to execute other functions.
        :param args: parameter values for NearestTimer
        :param kwargs: parameter values for NearestTimer
        """
        self.threaded_timer = NearestTimer(delay = delay, *args, **kwargs)
        #self.threaded_timer = RepeatedTimer(interval, func, *args, **kwargs)

    def stop_stream(self):
        """
        Stops livestream.
        """
        self.threaded_timer.stop()



if '__main__' == __name__:
    with open("key.txt", "r") as f:
        key = f.readline()
    swyftx = SwyftX(key)
