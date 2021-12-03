import numpy as np
import dash
import plotly.graph_objects as go
import dash_core_components as dcc
import dash_html_components as html

from collections import deque
from plotly.subplots import make_subplots
from swyftx import SwagX
from datetime import datetime, timedelta
from talib import EMA
from time import time
from dash.dependencies import Output, Input
from nearest import erase_seconds

resolution_to_seconds = {
    "1m":60,
    "5m":5*60,
    "30m":30*60,
    "1h":60*60
}

app = dash.Dash(__name__)

class Bot:

    def __init__(self, key, mode="demo"):
        self.key = key
        self.swyftx = SwagX(key, mode)
        self.ema_fast, self.ema_slow, self.macd, self.ema_hundred, self.macdsignal, self.data, self.primary, self.secondary, self.resolution, self.app = None,None,None,None,None,None, None, None, None, None
        print("-"*110)
        print("Bot created. Please call 'collect_and_process_live_data' to start trading a particular cryptocurrency.")
        print("-"*110)

    def quick_start(self, primary, secondary, resolution = "1m", fast = 12, slow = 26, signal = 9, long=100,  whole_resolution = True, start_time = None, end_time = None, graph=False):
        self.collect_and_process_live_data(primary, secondary, resolution, fast, slow, signal, long, whole_resolution, start_time, end_time)
        if graph:
            app.layout = html.Div(
                [
                    dcc.Graph(id="live-graph", animate=True, style={'height': '100vh'}),
                    dcc.Interval('graph-update',
                                 interval=1000*resolution_to_seconds[resolution])
                ]
            )
            self.run_clock()
            app.run_server(debug=False)
        # There are 2 possibilities after this point.
        # 1. The next interval has already started (very rare, only realistically happens when interval="1m")
        # 2. There are still time until we reach the next interval.
        # If 1:
        #   Call update_all()
        #   Save the time after the previous execution
        #   Call calculate_next_..., calculate the time it takes
        else:
            self.run_clock()

    def collect_and_process_live_data(self, primary, secondary, resolution = "1m", fast = 12, slow = 26, signal = 9, long=100, whole_resolution=True, start_time = None, end_time = None):
        now = end_time
        if end_time is None:
            now = time()
        if whole_resolution:
            now = erase_seconds(now) - 60

        if start_time is None:
            # If there's no specified start time, it will be set 24 hours before the time this line is executed.
            start_time = now - 24*60*60

        self.primary = primary
        self.secondary = secondary
        self.resolution = resolution
        data = self.swyftx.extract_price_data(self.swyftx.get_asset_data(primary, secondary, "ask", resolution, start_time * 1000, now * 1000, True))
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

    def step(self):
        self.update_all()


    def run_clock(self, **kwargs):
        print("Starting clock...")
        self.swyftx.livestream(delay = 2, function = self.update_all, resolution = self.resolution, **kwargs)

    def stop_clock(self):
        self.swyftx.stop_stream()
        print("Clock stopped.")

    def update_all(self, fast=12, slow=26, signal=9, long=100):
        """
        Function to be called at each step. It retrieves new data from Swyftx, adds it to the deque, calculates new
        values based on new data before adding them to their respective deques.
        """
        print(f"Last close: {self.data['close'][-1]}")
        print(f"Last time: {self.data['time'][-1]}")
        self.update_data(self.swyftx.get_last_completed_data(self.primary, self.secondary, "ask", self.resolution))
        print(f"Updated close: {self.data['close'][-1]}")
        print(f"Update time: {self.data['time'][-1]}")
        print("-"*110)
        self.update_all_ema(fast, slow, signal, long)

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
        """
        if self.data is None:
            print("self.data is not defined. Please call 'collect_and_process_live_data'")
        else:
            self.ema_fast.append(self.calculate_latest_ema(self.data["close"][-1], self.ema_fast[-1], fast))
            self.ema_slow.append(self.calculate_latest_ema(self.data["close"][-1], self.ema_slow[-1], slow))
            self.ema_hundred.append(self.calculate_latest_ema(self.data["close"][-1], self.ema_hundred[-1], long))
            self.macd.append(self.calculate_latest_macd())
            self.macdsignal.append(self.calculate_latest_macd_signal(signal))

    def update_data(self, d):
        """
        Called after calling self.swyftx.get_latest_asset_data() where it updates self.data with the data returned by
        the function.
        :param d: data dictionary returned by self.swyftx.get_latest_asset_data()
        """
        self.data["time"].append(datetime.fromtimestamp(d["time"]/1000))
        self.data["open"].append(float(d["open"]))
        self.data["close"].append(float(d["close"]))
        self.data["low"].append(float(d["low"]))
        self.data["high"].append(float(d["high"]))

    def undo_all_data(self):
        self.data["time"].pop()
        self.data["open"].pop()
        self.data["close"].pop()
        self.data["low"].pop()
        self.data["high"].pop()

    def undo_all_ema(self):
        self.ema_fast.pop()
        self.ema_slow.pop()
        self.ema_hundred.pop()
        self.macd.pop()
        self.macdsignal.pop()

    def calculate_latest_ema(self, latest_close, latest_ema, period):
        # Assumes that we have a new entry to close, while the last EMA is from an earlier period.
        return latest_close * (2/(1+period)) + latest_ema * (1 - (2/(1+period)))

    def calculate_latest_macd(self):
        # Assumes that self.ema_fast and self.ema_slow are already updated.
        return self.ema_fast[-1] - self.ema_slow[-1]

    def calculate_latest_macd_signal(self, signal=9):
        # Assumes that self.macd is already updated.
        return self.calculate_latest_ema(self.macd[-1], self.macdsignal[-1], signal)

    def plot(self):
        code = self.data["assetCode"]
        time = list(self.data["time"])
        open_ = list(self.data["open"])
        high = list(self.data["high"])
        low = list(self.data["low"])
        close = list(self.data["close"])
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True)
        candle = go.Candlestick(x=time,open=open_,high=high,low=low,close=close, name="Candle")

        ema_g = go.Scatter(x=time, y=list(self.ema_hundred), marker={'color':"orange"}, name="Long EMA")

        fig.add_trace(candle, row=1, col=1)
        fig.add_trace(ema_g, row=1, col=1)

        macdeez = go.Scatter(x=time, y=list(self.macd), marker={'color':'blue'}, name="MACD")
        macdeezsignal = go.Scatter(x=time, y=list(self.macdsignal), marker={"color":"red"}, name="Signal")

        fig.add_trace(macdeez, row=2, col=1)
        fig.add_trace(macdeezsignal, row=2, col=1)

        fig.update_layout(title={
            "text": code,
            "x": 0.5,
            "xanchor": "center",
            "yanchor": "top"
        })

        fig.show()

def calculate_next_minute(unix_time):
    return unix_time + 60 - (unix_time % 60)

"""
@app.callback(Output("live-graph", "figure"), [Input("graph-update", "interval")])
def update_graph(d):
    time = list(bot.data["time"])
    open_ = list(bot.data["open"])
    high = list(bot.data["high"])
    low = list(bot.data["low"])
    close = list(bot.data["close"])

    candle = go.Candlestick(x=time,open=open_,high=high,low=low,close=close, name="Candle")
    ema_g = go.Scatter(x=time, y=list(bot.ema_hundred), marker={'color':"orange"}, name="Long EMA")

    macdeez = go.Scatter(x=time, y=list(bot.macd), marker={'color':'blue'}, name="MACD")
    macdeezsignal = go.Scatter(x=time, y=list(bot.macdsignal), marker={"color":"red"}, name="Signal")

    return {
        "data": [candle, ema_g, macdeez, macdeezsignal]
    }
"""
@app.callback(Output("live-graph", "figure"), [Input("graph-update", "interval")])
def update_graph(d):
    # Live data resources:
    # https://dash.plotly.com/live-updates
    # https://realpython.com/python-dash/
    # https://pythonprogramming.net/live-graphs-data-visualization-application-dash-python-tutorial/

    code = bot.data["assetCode"]

    time = list(bot.data["time"])
    open_ = list(bot.data["open"])
    high = list(bot.data["high"])
    low = list(bot.data["low"])
    close = list(bot.data["close"])
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing= 0.2)
    candle = go.Candlestick(x=time,open=open_,high=high,low=low,close=close, name="Candle")

    ema_g = go.Scatter(x=time, y=list(bot.ema_hundred), marker={'color':"orange"}, name="Long EMA")

    fig.add_trace(candle, row=1, col=1)
    fig.add_trace(ema_g, row=1, col=1)

    macdeez = go.Scatter(x=time, y=list(bot.macd), marker={'color':'blue'}, name="MACD")
    macdeezsignal = go.Scatter(x=time, y=list(bot.macdsignal), marker={"color":"red"}, name="Signal")

    fig.add_trace(macdeez, row=2, col=1)
    fig.add_trace(macdeezsignal, row=2, col=1)

    fig.update_layout(title={
        "text": code,
        "x": 0.5,
        "xanchor": "center",
        "yanchor": "top"
    })

    return fig

with open("key.txt", "r") as f:
    key = f.readline()

bot = Bot(key)

if '__main__' == __name__:
    pass
    #swag = SwagX(key)
    #d_buy = swag.get_asset_data("AUD", "BTC", "ask", "1m", datetime(2021,11,24), datetime.now())
    #nd_buy = extract_price_data(d_buy)
    #d_sell = swag.get_asset_data("AUD", "BTC", "bid", "1m", datetime(2021,11,24), datetime.now())
    #nd_sell = extract_price_data(d_sell)
    #watch("AUDIO")
