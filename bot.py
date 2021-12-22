import numpy as np
import dash
import plotly.graph_objects as go
import dash_core_components as dcc
import dash_html_components as html
import webbrowser

from collections import deque
from plotly.subplots import make_subplots
from swyftx import SwagX
from datetime import datetime
from talib import EMA
from time import time, sleep
from dash.dependencies import Output, Input
from nearest import erase_seconds, next_interval, resolution_to_seconds
from threading import Timer

port = 5000
app = dash.Dash(__name__)

class Bot:

    def __init__(self, key, mode="demo"):
        """
        Initialising Bot.
        :param key: a string that is the SwyftX API key. Instructions to creating your own is here:
            https://help.swyftx.com.au/en/articles/3825168-how-to-create-an-api-key
        :param mode: a string that determines the mode in which this bot is running. There are two possibilities:
            'demo': if you want to use SwyftX' demo mode where you have $10k USD to trade.
            'base': if you want to trade for real.
        """
        self.key = key
        self.swyftx = SwagX(key, mode)
        self.ema_fast, self.ema_slow, self.macd, self.ema_hundred, self.macdsignal, self.data, self.primary, self.secondary, self.resolution, self.swing_low, self.last_macd, self.last_signal, self.cross, self.macd_gradient, self.signal_gradient, self.app = None,None,None,None,None,None, None, None, None, None, None, None, None, None, None, None
        print("-"*110)
        print("Bot created. Please call 'collect_and_process_live_data' to start trading a particular cryptocurrency.")
        print("-"*110)

    def quick_start(self, primary, secondary, resolution = "1m", fast = 12, slow = 26, signal = 9, long=100,  whole_resolution = True, start_time = None, end_time = None, graph=False):
        """
        Allows you to start trading quickly by initialising other parts of Bot for it to function properly.
        This function is usually called immediately after the initialisation of Bot.
        :param primary: a string that represents the ticker symbol of the asset that we'll use to evaluate the value of
            the secondary asset.
        :param secondary: a string that represents the ticker symbol of the asset that we're interested in trading.
        :param resolution: a string that represents the time span that the candles will cover.
            Possible values include: '1m', '5m', '1h', '4h', '1d'.
        :param fast: an integer that represents the number of periods considered when calculating the fast EMA.
        :param slow: an integer that represents the number of periods considered when calculating the slow EMA.
        :param signal: an integer that represents the number of periods considered when calculating the EMA for MACD.
        :param long: an integer that represents the number of periods considered when calculating the long EMA.
        :param whole_resolution: a boolean that will set the end time to the last completed resolution.
        :param start_time: a number or datetime object that determines the start time when we initially gather
            historical data relating to the secondary asset.
        :param end_time: a number or datetime object that determines the end time when we initially gather
            historical data relating to the secondary asset.
        :param graph: a boolean that determines whether we'll be graphing our collected data or not. It's
            recommended that we set this to False because it can slow everything down.
        """
        self.collect_and_process_live_data(primary, secondary, resolution, fast, slow, signal, long, start_time=start_time, end_time=end_time, whole_resolution=whole_resolution)

        if graph:
            #now = time()
            #execution_time = next_interval[self.resolution](now)
            #print("Execution time: ", datetime.fromtimestamp(now))
            #print("Anticipated execution time: ", datetime.fromtimestamp(execution_time))
            #sleep(execution_time-now)

            app.layout = html.Div(
                [
                    dcc.Graph(id="live-graph", animate=False, style={'height': '100vh'}),
                    dcc.Interval(id='graph-update',
                                 interval=1000*resolution_to_seconds[resolution])
                ]
            )
            now = time()
            execution_time = next_interval[self.resolution](now)
            print("Execution time: ", datetime.fromtimestamp(now))
            print("Anticipated execution time: ", datetime.fromtimestamp(execution_time))
            sleep(execution_time-now)
            Timer(0.1, open_browser).start()
            app.run_server(debug=False, port=port)
        # There are 2 possibilities after this point.
        # 1. The next interval has already started (very rare, only realistically happens when interval="1m")
        # 2. There are still time until we reach the next interval.
        # If 1:
        #   Call update_all()
        #   Save the time after the previous execution
        #   Call calculate_next_..., calculate the time it takes
        else:
            self.run_clock(self.resolution)

    def collect_and_process_live_data(self, primary, secondary, resolution = "1m", fast = 12, slow = 26, signal = 9, long=100, swing_period=60, whole_resolution=True, start_time = None, end_time = None):
        """
        Gathers and calculates initial data and financial figures. This function needs to be called for the bot to work.
        :param primary: a string that represents the ticker symbol of the asset that we'll use to evaluate the value of
            the secondary asset.
        :param secondary: a string that represents the ticker symbol of the asset that we're interested in trading.
        :param resolution: a string that represents the time span that the candles will cover.
            Possible values include: '1m', '5m', '1h', '4h', '1d'.
        :param fast: an integer that represents the number of periods considered when calculating the fast EMA.
        :param slow: an integer that represents the number of periods considered when calculating the slow EMA.
        :param signal: an integer that represents the number of periods considered when calculating the EMA for MACD.
        :param long: an integer that represents the number of periods considered when calculating the long EMA.
        :param swing_period: an integer that determines the number of periods up till now to consider when determining
            the minimum swing low.
        :param whole_resolution: a boolean that will set the end time to the last completed resolution.
        :param start_time: a number or datetime object that determines the start time when we initially gather
            historical data relating to the secondary asset.
        :param end_time: a number or datetime object that determines the end time when we initially gather
            historical data relating to the secondary asset.
        """
        now = end_time
        if end_time is None:
            now = time()
        elif type(end_time) is datetime:
            now = end_time.timestamp()

        if whole_resolution:
            print("Before: ", datetime.fromtimestamp(now))
            now = erase_seconds(now) - 60 # Gets data from start_time to the start of the current minute.
            print("After: ", datetime.fromtimestamp(now))

        if start_time is None:
            # If there's no specified start time, it will be set 24 hours before the time this line is executed.
            start_time = now - 24*60*60
        elif type(start_time) is datetime:
            start_time = start_time.timestamp()

        print("start_time: ", datetime.fromtimestamp(start_time))
        print("now: ", datetime.fromtimestamp(now))
        self.primary = primary
        self.secondary = secondary
        self.resolution = resolution
        data = self.swyftx.extract_price_data(self.swyftx.get_asset_data(primary, secondary, "ask", resolution, start_time * 1000, now * 1000, True))
        #data_bid = self.extract_price_data(self.get_asset_data(primary, secondary, "bid", "1m", start_time, now, True))
        max_length = len(data["close"])
        ema_fast = EMA(np.array(data["close"]), fast)
        ema_slow = EMA(np.array(data["close"]), slow)
        macd = ema_fast - ema_slow
        self.macdsignal = deque(EMA(macd, signal)[len(data["time"])*(-1):])
        self.ema_fast = deque(ema_fast, max_length)
        self.ema_slow = deque(ema_slow, max_length)
        self.macd = deque(macd, max_length)
        self.ema_hundred = deque(EMA(np.array(data["close"]), long), max_length)
        self.swing_low = min(list(data["low"])[swing_period*(-1):]) # Could be subjected to change. Also considering 'close'.
        self.data = data

    def step(self):
        self.update_all()


    def run_clock(self, resolution, **kwargs):
        """
        Livestreams live data directly from SwyftX, saves it locally, and calculates relevant financial figures.
        While this is running, it's possible to execute other functions.
        :param kwargs: parameter values for self.update_all()
        """
        print("Starting clock...")
        self.swyftx.livestream(function = self.update_all, resolution = resolution, delay = 0,**kwargs)

    def stop_clock(self):
        """
        Stops livestream.
        """
        self.swyftx.stop_stream()
        print("Clock stopped.")

    def update_all(self, fast=12, slow=26, signal=9, long=100):
        """
        Function to be called at each step. It retrieves new data from Swyftx, adds it to the deque, calculates new
        values based on new data before adding them to their respective deques.
        :param fast: an integer that represents the number of periods considered when calculating the fast EMA.
        :param slow: an integer that represents the number of periods considered when calculating the slow EMA.
        :param signal: an integer that represents the number of periods considered when calculating the EMA for MACD.
        :param long: an integer that represents the number of periods considered when calculating the long EMA.
        """
        print(f"Last close: {self.data['close'][-1]}")
        print(f"Last time: {self.data['time'][-1]}")
        self.update_data(self.swyftx.get_latest_asset_data(self.primary, self.secondary, "ask", self.resolution))
        #self.update_data(self.swyftx.get_last_completed_data(self.primary, self.secondary, "ask", self.resolution))
        print(f"Updated close: {self.data['close'][-1]}")
        print(f"Update time: {self.data['time'][-1]}")
        print('-'*110)
        self.update_financial_figures(fast, slow, signal, long)
        print("MACD crossed Signal: ", self.cross)
        if self.cross:
            self.stop_clock()

    def safe_update_all(self, fast=12, slow=26, signal=9, long=100):
        """
        Checks if the fetched data has the same time as the last entry in self.data['time']. If so, ignore, otherwise,
        same as self.update_all().
        :param fast: an integer that represents the number of periods considered when calculating the fast EMA.
        :param slow: an integer that represents the number of periods considered when calculating the slow EMA.
        :param signal: an integer that represents the number of periods considered when calculating the EMA for MACD.
        :param long: an integer that represents the number of periods considered when calculating the long EMA.
        """
        d = self.swyftx.get_latest_asset_data(self.primary, self.secondary, "ask", self.resolution)
        if datetime.fromtimestamp(d["time"]/1000) != self.data["time"][-1]:
            print(f"Last close: {self.data['close'][-1]}")
            print(f"Last time: {self.data['time'][-1]}")
            self.update_data(d)
            print(f"Updated close: {self.data['close'][-1]}")
            print(f"Update time: {self.data['time'][-1]}")
            self.update_financial_figures(fast, slow, signal, long)

    def update_financial_figures(self, fast=12, slow=26, signal=9, long=100):
        """
        Calculates and updates all EMA figures. This includes: self.ema_fast, self.ema_slow, and self.ema_hundred.
        *** This assumes that self.data["close"] is 1 period ahead of the aforementioned values.
        :param fast: an integer that represents the number of periods considered when calculating the fast EMA.
        :param slow: an integer that represents the number of periods considered when calculating the slow EMA.
        :param signal: an integer that represents the number of periods considered when calculating the EMA for MACD.
        :param long: an integer that represents the number of periods considered when calculating the long EMA.
        """
        if self.data is None:
            print("self.data is not defined. Please call 'collect_and_process_live_data'")
        else:
            self.ema_fast.append(self.calculate_latest_ema(self.data["close"][-1], self.ema_fast[-1], fast))
            self.ema_slow.append(self.calculate_latest_ema(self.data["close"][-1], self.ema_slow[-1], slow))
            self.ema_hundred.append(self.calculate_latest_ema(self.data["close"][-1], self.ema_hundred[-1], long))
            self.last_macd = self.calculate_latest_macd()
            self.macd.append(self.last_macd)
            self.last_signal = self.calculate_latest_macd_signal(signal)
            self.macdsignal.append(self.last_signal)
            self.macd_gradient, self.signal_gradient = self.calculate_latest_gradients()
            self.cross = self.macd_cross()

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
        self.update_swing_low(float(d["low"]))

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
        """
        Calculates the latest EMA value.
        *** Assumes that we have a new entry to close, while the last EMA is from an earlier period.
        :param latest_close: a number that represents the last registered closing price.
        :param latest_ema: a number that represents the last registered EMA value.
        :param period: an integer that represents the period in which we're interested in calculating this EMA value in.
        :return: the latest EMA value.
        """

        return latest_close * (2/(1+period)) + latest_ema * (1 - (2/(1+period)))

    def calculate_latest_macd(self):
        """
        Calculates the latest MACD value.
        *** Assumes that self.ema_fast and self.ema_slow are already updated.
        :return: the latest MACD value.
        """
        return self.ema_fast[-1] - self.ema_slow[-1]

    def calculate_latest_macd_signal(self, signal=9):
        """
        Calculates the latest MACD signal value.
        *** Assumes that self.macd is already updated.
        :param signal: an integer that represents the period in which we're interested in calculating the EMA (signal)
            of the latest MACD value.
        :return: the latest MACD signal value.
        """
        return self.calculate_latest_ema(self.macd[-1], self.macdsignal[-1], signal)

    def update_swing_low(self, value):
        """
        Checks to see if the newest value is less than the current swing low or not. If so, set self.swing_low to the
        latest value.
        """
        if self.swing_low > value:
            self.swing_low = value

    def calculate_latest_gradients(self):
        """
        Calculates the change in terms of financial figures.
        :return: gradients for MACD and MACD signal respectively.
        """
        return self.macd[-1] - self.macd[-2], self.macdsignal[-1] - self.macdsignal[-2]

    def macd_cross(self):
        """
        Checks to see if MACD has crossed the signal from below.
        An interesting note is that if this function returns True, then the next call will return False (assuming that
        the data, MACD, and MACD signal have been properly updated once)
        :return: a boolean
        """

        #print("Last MACD: ",self.macd[-2] )
        #print("Last signal: ", self.macdsignal[-2])

        #print("Current MACD: ", self.macd[-1])
        #print("Current signal: ", self.macdsignal[-1])
        return self.macd[-2] < self.macdsignal[-2] and self.macd[-1] > self.macdsignal[-1]

    def plot(self, last=None):
        """
        Plots the data that is currently stored inside Bot.
        """
        if last is None:
            last = 0
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

@app.callback(Output("live-graph", "figure"), [Input("graph-update", "n_intervals")])
def update_graph(n):
    """
    Called each step to update the graph based on data and financial figures stored inside Bot.
    :param n: an integer that represents the number of steps since the beginning.
    """
    # Live data resources:
    # https://dash.plotly.com/live-updates
    # https://realpython.com/python-dash/
    # https://pythonprogramming.net/live-graphs-data-visualization-application-dash-python-tutorial/

    #print("Callback executed")
    #print("Graph time: ", datetime.now())
    bot.safe_update_all()
    #bot.update_all()
    code = bot.data["assetCode"]
    #print("Execution time: ", datetime.now())
    #print("Last time: ", bot.data["time"][-1])
    time = list(bot.data["time"])[-60:]
    open_ = list(bot.data["open"])[-60:]
    high = list(bot.data["high"])[-60:]
    low = list(bot.data["low"])[-60:]
    close = list(bot.data["close"])[-60:]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing= 0.2)

    candle = go.Candlestick(x=time,open=open_,high=high,low=low,close=close, name="Candle")
    fig.add_trace(candle, row=1, col=1)
    ema_g = go.Scatter(x=time, y=list(bot.ema_hundred)[-60:], marker={'color':"orange"}, name="Long EMA")

    fig.add_trace(ema_g, row=1, col=1)
    #fig.add_trace(candle, row=1, col=1)
    #fig.add_trace(ema_g, row=1, col=1)

    macdeez = go.Scatter(x=time, y=list(bot.macd)[-60:], marker={'color':'blue'}, name="MACD")
    macdeezsignal = go.Scatter(x=time, y=list(bot.macdsignal)[-60:], marker={"color":"red"}, name="Signal")

    fig.add_trace(macdeez, row=2, col=1)
    fig.add_trace(macdeezsignal, row=2, col=1)

    fig.update_layout(title={
        "text": code,
        "x": 0.5,
        "xanchor": "center",
        "yanchor": "top"
    })

    #fig.update_xaxes(rangeslider_visible=False)

    return fig#{"data":[candle], "layout": go.Layout(xaxis=dict(range=[min(time), max(time)+timedelta(minutes=1)]), )}

def open_browser():
    """
    Opens the browser for data visualisation.
    """
    webbrowser.open_new("http://localhost:{}".format(port))

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
