import requests
import json
import os
from datetime import datetime

# API documentation: https://swyftx.docs.apiary.io/

key = "g_ZzZKJaMHt9ufjYtZ16iHZWn-lKyjy0i8KzwFY3G-QLE"

endpoints = {
    "base": "https://api.swyftx.com.au/",
    "demo": "https://api.demo.swyftx.com.au/"
}


class OldTokenError(Exception):
    pass


class EmptyTokenError(Exception):
    pass


class SwagX:
    def __init__(self, apiKey, mode="demo"):
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
        self._blacklist = ["USDT", "USDC", "BUSD"]
        self._to_id, self._to_code = self._create_name_id_dict(self.asset_info)

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

    def fetch_balance(self, prettify=False):

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

    def stream_asset_data(self, assetCode):
        swag.session.headers.update(swag.default_header)
        r = swag.session.get(endpoints[
                                 "base"] + "charts/getBars/" + "USD/BTC/ask/?resolution=1m&timeStart=1637530212000&timeEnd=1637579983000")

        return r.text
        pass

    def dummy_buy(self):
        values = '''{
        "primary": "USD",
        "secondary": "BTC",
        "quantity": "1",
        "assetQuantity": "USD",
        "orderType": 1
        }'''
        self.session.headers.update(self.authenticate_header)
        response = self.session.post("https://api.demo.swyftx.com.au/orders/", data=values)
        return response


if '__main__' == __name__:
    swag = SwagX(key)
