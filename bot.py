import talib
import numpy as np
import plotly.graph_objects as go

from collections import deque
from plotly.subplots import make_subplots
from swyftx import SwagX
from datetime import datetime, timedelta
from talib import MACD, EMA



class Bot:

    def __init__(self, key, mode="demo"):
        self.key = key
        self.swyftx = SwagX(key, mode)
        self.ema_fast, self.ema_slow, self.macd, self.ema_hundred, self.macdsignal, self.data = None,None,None,None,None,None
        print("-"*100)
        print("Bot created. Please call 'collect_and_process_live_data' to start trading a particular cryptocurrency.")
        print("-"*100)

    def collect_and_process_live_data(self, primary, secondary, fast = 12, slow = 26, signal = 9, long=100, duration = None, start_time = None):
        now = datetime.now()
        if start_time is None:
            # If there's no specified start time, it will be set 24 hours before the time this line is executed.
            start_time = now - timedelta(days=1)

        data = self.swyftx.extract_price_data(self.swyftx.get_asset_data(primary, secondary, "ask", "1m", start_time, now, True))
        #data_bid = self.extract_price_data(self.get_asset_data(primary, secondary, "bid", "1m", start_time, now, True))
        max_length = len(data["close"])
        ema_fast = EMA(np.array(data["close"]), fast)
        ema_slow = EMA(np.array(data["close"]), slow)
        macd = ema_fast - ema_slow
        self.macdsignal = deque(EMA(macd, signal))
        self.ema_fast = deque(ema_fast, max_length)
        self.ema_slow = deque(ema_slow, max_length)
        self.macd = deque(macd, max_length)
        self.ema_hundred = deque(EMA(np.array(data["close"]), long), max_length)
        self.data = data


    def update_calculations(self, fast=12, slow=26, signal=9):
        """
        Assuming that there's an update to self.data, specifically, an updated entry in its 'close' deque, calculate and
        update respective values for self.macd, self.macdsignal, and self.ema_hundred.
        """
        pass

    def update_all_ema(self, fast=12, slow=26, signal=9, long=100):
        """
        Calculates and updates all EMA figures. This includes: self.ema_fast, self.ema_slow, and self.ema_hundred.
        *** This assumes that self.data["close"] is 1 period ahead of the aforementioned values.
        :param period: an integer specifying the period in which we calculate our EMA.
        """
        if self.data is None:
            print("self.data is not defined. Please call 'collect_and_process_live_data'")
        else:
            self.ema_fast.append(self.calculate_latest_ema(self.data["close"][-1], self.ema_fast[-1], fast))
            self.ema_slow.append(self.calculate_latest_ema(self.data["close"][-1], self.ema_slow[-1], slow))
            self.ema_hundred.append(self.calculate_latest_ema(self.data["close"][-1], self.ema_hundred[-1], long))
            self.macd.append(self.calculate_latest_macd())
            self.macdsignal.append(self.calculate_lastest_macd_signal(signal))

    def calculate_latest_ema(self, latest_close, latest_ema, period):
        # Assumes that we have a new entry to close, while the last EMA is from an earlier period.
        return latest_close * (2/(1+period)) + latest_ema * (1 - (2/(1+period)))

    def calculate_latest_macd(self):
        # Assumes that self.ema_fast and self.ema_slow are already updated.
        return self.ema_fast[-1] - self.ema_slow[-1]

    def calculate_lastest_macd_signal(self, signal=9):
        # Assumes that self.macd is already updated.
        return self.calculate_latest_ema(self.macd[-1], self.macdsignal[-1], signal)

with open("key.txt", "r") as f:
    key = f.readline()

def main():
    bot = Bot(key)


def extract_price_data(data, max_length = None):
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

def plot_price_data(data):
    code = data["assetCode"]
    time, open_, close, low, high = np.array(data["time"]), np.array(data["open"]), np.array(data["close"]), np.array(data["low"]), np.array(data["high"])

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True)
    candle = go.Candlestick(x=time,open=open_,high=close,low=low,close=close, name="Candle")

    ema = talib.EMA(close, 100)
    ema_g = go.Scatter(x=time, y=ema, marker={'color':"orange"}, name="100EMA")

    fig.add_trace(candle, row=1, col=1)
    fig.add_trace(ema_g, row=1, col=1)

    macd, macdsignal, macdhist = talib.MACD(close)

    macdeez = go.Scatter(x=time, y=macd, marker={'color':'blue'}, name="MACD")
    macdeezsignal = go.Scatter(x=time, y=macdsignal, marker={"color":"red"}, name="Signal")

    fig.add_trace(macdeez, row=2, col=1)
    fig.add_trace(macdeezsignal, row=2, col=1)

    fig.update_layout(title={
        "text": code,
        "x": 0.5,
        "xanchor": "center",
        "yanchor": "top"
    })

    fig.show()

def watch(assetCode):
    swag = SwagX(key)
    d_buy = swag.get_asset_data("AUD", assetCode, "ask", "1m", datetime(2021,11,25), datetime.now())
    nd_buy = extract_price_data(d_buy)
    #d_sell = swag.get_asset_data("AUD", assetCode, "bid", "1m", datetime(2021,11,24), datetime.now())
    #nd_sell = extract_price_data(d_sell)
    plot_price_data(nd_buy)
    #plot_price_data(nd_sell)

if '__main__' == __name__:
    bot = Bot(key)
    #swag = SwagX(key)
    #d_buy = swag.get_asset_data("AUD", "BTC", "ask", "1m", datetime(2021,11,24), datetime.now())
    #nd_buy = extract_price_data(d_buy)
    #d_sell = swag.get_asset_data("AUD", "BTC", "bid", "1m", datetime(2021,11,24), datetime.now())
    #nd_sell = extract_price_data(d_sell)
    #watch("AUDIO")
