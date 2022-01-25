import numpy as np
import dash
import plotly.graph_objects as go
import dash_core_components as dcc
import dash_html_components as html
import webbrowser
import pandas as pd
import os

from collections import deque
from plotly.subplots import make_subplots
from swyftx import SwyftX
from datetime import datetime
from talib import EMA
from time import time, sleep
from dash.dependencies import Output, Input
from nearest import erase_seconds, next_interval, resolution_to_seconds, check_rank, rank_up, rank_down, \
    no_of_resolutions
from threading import Timer
from errors import *

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
        self.swyftx = SwyftX(key, mode)
        self.ema_fast, self.ema_slow, self.macd, self.ema_hundred, self.macdsignal, self.data = [None for _ in range(
            no_of_resolutions)], [None for _ in range(no_of_resolutions)], [None for _ in range(no_of_resolutions)], [
                                                                                                    None for _ in range(
                no_of_resolutions)], [None for _ in range(no_of_resolutions)], [None for _ in range(no_of_resolutions)]
        self.primary, self.secondary, self.balance, self.resolution, self.swing_low, self.last_macd, self.last_signal, self.cross, self.macd_gradient, self.signal_gradient, self.buy_signal, self.bull, self.app, self.buy_rate, self.buy_price, self.stop_loss_id = None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None
        self.fast, self.slow, self.signal, self.long = None, None, None, None
        self.start_time, self.backtest = None, None
        self.history = []
        self.zoomed, self.bought = False, False
        self.tolerance, self.temp_tolerance = 0, 0
        print("-" * 110)
        print("Bot created. Please call 'collect_and_process_live_data' to start trading a particular cryptocurrency.")
        print("-" * 110)

    def quick_start(self, primary, secondary, resolution="1m", fast=12, slow=26, signal=9, long=100,
                    whole_resolution=True, start_time=None, end_time=None, buy_rate=0.2, graph=False, backtest=False):
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
        :param backtest: a boolean that determines whether to backtest the current strategy. If so, start_time
            will have to be manually specified. end_time can be left as None because it will be assumed to be the most
            recent timeslot at the time of execution.

        """

        # Create directories for buying/selling history/log:
        os.makedirs(os.path.join("history", secondary), exist_ok=True)

        self.collect_and_process_live_data(primary, secondary, resolution, fast, slow, signal, long,
                                           start_time=start_time, end_time=end_time, whole_resolution=whole_resolution)
        self.fast, self.slow, self.signal, self.long = fast, slow, signal, long
        self.buy_rate = buy_rate
        self.backtest = backtest

        if graph:
            # now = time()
            # execution_time = next_interval[self.resolution](now)
            # print("Execution time: ", datetime.fromtimestamp(now))
            # print("Anticipated execution time: ", datetime.fromtimestamp(execution_time))
            # sleep(execution_time-now)

            app.layout = html.Div(
                [
                    dcc.Graph(id="live-graph", animate=False, style={'height': '100vh'}),
                    dcc.Interval(id='graph-update',
                                 interval=1000 * resolution_to_seconds[resolution])
                ]
            )
            now = time()
            execution_time = next_interval[self.resolution](now)
            print("Execution time: ", datetime.fromtimestamp(now))
            print("Anticipated execution time: ", datetime.fromtimestamp(execution_time))
            sleep(execution_time - now)
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
            if not backtest:
                self.run_clock(resolution=self.resolution)
            else:
                pass

    def collect_and_process_live_data(self, primary, secondary, resolution="1m", fast=12, slow=26, signal=9, long=100,
                                      swing_period=60, tolerance=2, whole_resolution=True, start_time=None, end_time=None,
                                      ):
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
        :param tolerance: an integer that is used to determine how many times the MACD gradient can go negative before
            the bot executes a sell order.
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
            # print("Before: ", datetime.fromtimestamp(now))
            now = erase_seconds(now) - 60  # Gets data from start_time to the start of the current minute.
            # print("After: ", datetime.fromtimestamp(now))

        if start_time is None:
            # Check if we're backtesting:
            if self.backtest:
                raise NoStartTimeError()
            # If there's no specified start time, it will be set 24 hours before the time this line is executed.
            start_time = now - 24 * 60 * 60
        elif type(start_time) is datetime:
            start_time = start_time.timestamp()

        # print("start_time: ", datetime.fromtimestamp(start_time))
        # print("now: ", datetime.fromtimestamp(now))
        self.primary = primary
        self.secondary = secondary
        self.resolution = resolution
        self.tolerance, self.temp_tolerance = tolerance, tolerance
        self.balance = self.swyftx.fetch_balance()
        data = self.swyftx.extract_price_data(
            self.swyftx.get_asset_data(primary, secondary, "ask", resolution, start_time * 1000, now * 1000, True))
        # data_bid = self.extract_price_data(self.get_asset_data(primary, secondary, "bid", "1m", start_time, now, True))
        max_length = len(data["close"])
        ema_fast = EMA(np.array(data["close"]), fast)
        ema_slow = EMA(np.array(data["close"]), slow)
        macd = ema_fast - ema_slow
        self.macdsignal[check_rank(self.resolution)] = deque(EMA(macd, signal)[len(data["time"]) * (-1):])
        self.ema_fast[check_rank(self.resolution)] = deque(ema_fast, max_length)
        self.ema_slow[check_rank(self.resolution)] = deque(ema_slow, max_length)
        self.macd[check_rank(self.resolution)] = deque(macd, max_length)
        self.ema_hundred[check_rank(self.resolution)] = deque(EMA(np.array(data["close"]), long), max_length)
        self.swing_low = min(
            list(data["low"])[swing_period * (-1):])  # Could be subjected to change. Also considering 'close'.
        self.data[check_rank(self.resolution)] = data

    def step(self):
        self.update_all()

    def run_clock(self, **kwargs):
        """
        Livestreams live data directly from SwyftX, saves it locally, and calculates relevant financial figures.
        While this is running, it's possible to execute other functions.
        :param kwargs: parameter values for self.update_all()
        """
        print("Starting clock...")
        self.swyftx.livestream(function=self.update_all, **kwargs)

    def stop_clock(self):
        """
        Stops livestream.
        """
        self.swyftx.stop_stream()
        self.history_to_csv()
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
        print(f"Last close: {self.data[check_rank(self.resolution)]['close'][-1]}")
        print(f"Last time: {self.data[check_rank(self.resolution)]['time'][-1]}")
        # self.update_data(self.swyftx.get_latest_asset_data(self.primary, self.secondary, "ask", self.resolution))
        self.update_data(self.swyftx.get_last_completed_data(self.primary, self.secondary, "ask", self.resolution))
        print(f"Updated close: {self.data[check_rank(self.resolution)]['close'][-1]}")
        print(f"Update time: {self.data[check_rank(self.resolution)]['time'][-1]}")
        print('-' * 110)
        self.update_financial_figures(fast, slow, signal, long)
        #print("MACD crossed Signal: ", self.cross)


        # Strategy:
        self.macd_gradient_strategy()

    def macd_gradient_strategy(self):
        if not self.bought:
            if self.check_macro_buy_signal():
                if self.zoomed:
                    # if zoomed, it's time to buy
                    amount = self.primary_balance() * self.buy_rate
                    r = self.market_buy(amount, stop_loss=True)
                    """
                    r = self.swyftx.market_buy(self.primary, self.secondary, amount,
                                               self.primary)
                    if r.ok:  # Check to see if response is successful
                        r = r.json()["order"]
                        if r["status"] == 4:  # If purchase is successful, set self.bought to true, and create
                            # stop loss
                            self.bought = True
                            self.buy_price = r["rate"]

                            self.balance = self.swyftx.fetch_balance()
                            #self.balance[self.primary] -= r["userCountryValue"]
                            #self.balance[self.secondary] += r["amount"]
                            self.stop_loss_id = self.swyftx.stop_loss(self.primary, self.secondary, amount, self.swing_low).json()["orderUuid"]
                    """

                else:
                    # otherwise, we zoom in.
                    self.stop_clock()
                    # self.resolution = rank_down(self.resolution)
                    self.zoomed = True
                    self.collect_and_process_live_data(primary=self.primary, secondary=self.secondary,
                                                       resolution=rank_down(self.resolution))
                    self.run_clock(resolution=self.resolution)
        else: # If bought, observe momentum
            if self.macd_gradient <= 0: # MACD is decreasing/stagnant
                self.temp_tolerance -= 1
                if self.temp_tolerance < 0:
                    r = self.market_sell(self.balance[self.secondary], self.secondary)
                    """
                    r = self.swyftx.market_sell(self.primary, self.secondary, self.balance[self.secondary], self.secondary)
                    if r.ok: # If sell request is successful:
                        r = r.json()["order"]
                        if r["status"] == 4: # If market sell is successful.
                            self.balance = self.swyftx.fetch_balance()
                            # Figure out a way to find out how much was actually made during a sell transaction.
                            # Apparently, we don't get charged any fees in the demo mode.
                            #self.balance[self.primary] += (r["userCountryValue"] - r["amount"]*r["rate"])
                            #self.balance[self.secondary] -= r["amount"]
                            self.swyftx.delete_order(self.stop_loss_id)
                            self.bought = False
                            self.zoomed = False
                            self.stop_clock()
                            self.collect_and_process_live_data(primary=self.primary, secondary=self.secondary,
                                                               resolution=rank_up(self.resolution))
                            self.run_clock(resolution=self.resolution)
                    """


        """
        if self.check_macro_buy_signal(): # Buy condition/signal
            # Stop clock
            # Create
            if self.zoomed:
                # Buy

            else:
                self.stop_clock()
                #self.resolution = rank_down(self.resolution)
                self.zoomed = True
                self.collect_and_process_live_data(primary=self.primary, secondary=self.secondary, resolution=rank_down(self.resolution))
                #self.quick_start(self.primary, self.secondary, resolution=rank_down(self.resolution), fast=self.fast, slow=self.slow, signal=self.signal, long=self.long)
                self.run_clock(resolution=self.resolution)
        """

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
        if datetime.fromtimestamp(d["time"] / 1000) != self.data[check_rank(self.resolution)]["time"][-1]:
            print(f"Last close: {self.data[check_rank(self.resolution)]['close'][-1]}")
            print(f"Last time: {self.data[check_rank(self.resolution)]['time'][-1]}")
            self.update_data(d)
            print(f"Updated close: {self.data[check_rank(self.resolution)]['close'][-1]}")
            print(f"Update time: {self.data[check_rank(self.resolution)]['time'][-1]}")
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
        if self.data[check_rank(self.resolution)] is None:
            print("self.data is not defined. Please call 'collect_and_process_live_data'")
        else:
            self.ema_fast[check_rank(self.resolution)].append(
                self.calculate_latest_ema(self.data[check_rank(self.resolution)]["close"][-1],
                                          self.ema_fast[check_rank(self.resolution)][-1], fast))
            self.ema_slow[check_rank(self.resolution)].append(
                self.calculate_latest_ema(self.data[check_rank(self.resolution)]["close"][-1],
                                          self.ema_slow[check_rank(self.resolution)][-1], slow))
            self.ema_hundred.append(self.calculate_latest_ema(self.data[check_rank(self.resolution)]["close"][-1],
                                                              self.ema_hundred[check_rank(self.resolution)][-1], long))
            self.last_macd = self.calculate_latest_macd()
            self.macd[check_rank(self.resolution)].append(self.last_macd)
            self.last_signal = self.calculate_latest_macd_signal(signal)
            self.macdsignal[check_rank(self.resolution)].append(self.last_signal)
            self.macd_gradient, self.signal_gradient = self.calculate_latest_gradients()
            self.cross = self.macd_cross()

    def update_data(self, d):
        """
        Called after calling self.swyftx.get_latest_asset_data() where it updates self.data with the data returned by
        the function.
        :param d: data dictionary returned by self.swyftx.get_latest_asset_data()
        """
        self.data[check_rank(self.resolution)]["time"].append(datetime.fromtimestamp(d["time"] / 1000))
        self.data[check_rank(self.resolution)]["open"].append(float(d["open"]))
        self.data[check_rank(self.resolution)]["close"].append(float(d["close"]))
        self.data[check_rank(self.resolution)]["low"].append(float(d["low"]))
        self.data[check_rank(self.resolution)]["high"].append(float(d["high"]))
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
        return latest_close * (2 / (1 + period)) + latest_ema * (1 - (2 / (1 + period)))

    def calculate_latest_macd(self):
        """
        Calculates the latest MACD value.
        *** Assumes that self.ema_fast and self.ema_slow are already updated.
        :return: the latest MACD value.
        """
        return self.ema_fast[check_rank(self.resolution)][-1] - self.ema_slow[check_rank(self.resolution)][-1]

    def calculate_latest_macd_signal(self, signal=9):
        """
        Calculates the latest MACD signal value.
        *** Assumes that self.macd is already updated.
        :param signal: an integer that represents the period in which we're interested in calculating the EMA (signal)
            of the latest MACD value.
        :return: the latest MACD signal value.
        """
        return self.calculate_latest_ema(self.macd[check_rank(self.resolution)][-1],
                                         self.macdsignal[check_rank(self.resolution)][-1], signal)

    def update_swing_low(self, value):
        """
        Checks to see if the newest value is less than the current swing low or not. If so, set self.swing_low to the
        latest value.
        """
        if self.swing_low >= value:
            # If we see a value equal to or lower than the old swing-low, then we'll have to zoom out 1 level
            # because it implies that the previous stop loss order has been filled, and therefore we'll have to zoom out
            # to look at the overall trend once again.
            # Since the stop loss order has been filled, self.bought will become False because we're now looking for a
            # new opportunity to re-enter the market.
            self.zoomed = False
            self.bought = False
            self.swing_low = value

            self.stop_clock()
            self.collect_and_process_live_data(primary=self.primary, secondary=self.secondary,
                                               resolution=rank_up(self.resolution))
            self.run_clock(resolution=self.resolution)

    def calculate_latest_gradients(self):
        """
        Calculates the change in terms of financial figures.
        :return: gradients for MACD and MACD signal respectively.
        """
        return self.macd[check_rank(self.resolution)][-1] - self.macd[check_rank(self.resolution)][-2], \
               self.macdsignal[check_rank(self.resolution)][-1] - self.macdsignal[check_rank(self.resolution)][-2]

    def macd_cross(self):
        """
        Checks to see if MACD has crossed the signal from below.
        An interesting note is that if this function returns True, then the next call will return False (assuming that
        the data, MACD, and MACD signal have been properly updated once)
        :return: a boolean
        """

        # print("Last MACD: ",self.macd[-2] )
        # print("Last signal: ", self.macdsignal[-2])

        # print("Current MACD: ", self.macd[-1])
        # print("Current signal: ", self.macdsignal[-1])
        return self.macd[check_rank(self.resolution)][-2] < self.macdsignal[check_rank(self.resolution)][-2] and \
               self.macd[check_rank(self.resolution)][-1] > self.macdsignal[check_rank(self.resolution)][-1]

    def check_macro_buy_signal(self):
        """
        Checks to see if the market's bullish by making sure that the long EMA is at least equal to the low (or below)
        and that MACD has crossed signal.
        :return: a boolean
        """
        return self.ema_hundred[check_rank(self.resolution)][-1] <= self.data[check_rank(self.resolution)]["low"][
            -1] and self.cross

    def order_to_list(self, d):
        """
        Takes the json of a buy/sell order and converts it to a list.
        :param d: a dictionary containing information about an order.
        :return: a list
        """
        return [d["orderUuid"]] + list(d["order"].values()) + [d["processed"]]


    def market_buy(self, amount, assetQuantity=None, stop_loss = False):
        if assetQuantity is None:
            assetQuantity = self.primary
        r = self.swyftx.market_buy(self.primary, self.secondary, amount,
                                   assetQuantity).json()
        if r["order"]["status"] == 4:  # If purchase is successful, set self.bought to true, and create
            # stop loss
            self.bought = True
            self.buy_price = r["order"]["rate"]
            self.balance = self.swyftx.fetch_balance()

            if stop_loss:
                self.stop_loss_id = self.swyftx.stop_loss(self.primary, self.secondary, amount,
                                                          self.swing_low).json()["orderUuid"]

            self.history.append(self.order_to_list(r))
        return r

    def backtest_buy(self, mode="open", open, close, low, high):
        """
        Buy function used in backtesting. It's the same as market_buy, except it doesn't actually make a real purchase.
        :param mode: a string that determines the value at which to buy. There are currently n modes:
            'open': buy price is always the open value.
            'random': buy price is a random value between low and high.
            'nopen': buy price is near open
        :param open: a float that represents the price at open.
        :param close: a float that represents the price at close.
        :param low: a float that represents the lowest price within a timeframe.
        :param high: a float that represents the highest price within a timeframe.
        :return:
        """
        if mode == "open":

        elif mode == "random":

        elif mode == "nopen":

    def market_sell(self, amount, assetQuantity=None):
        if assetQuantity is None:
            assetQuantity = self.primary
        r = self.swyftx.market_sell(self.primary, self.secondary, amount,
                                    assetQuantity).json()
        if r["order"]["status"] == 4: # If market sell is successful.
            self.balance = self.swyftx.fetch_balance()
            # Figure out a way to find out how much was actually made during a sell transaction.
            # Apparently, we don't get charged any fees in the demo mode.
            #self.balance[self.primary] += (r["userCountryValue"] - r["amount"]*r["rate"])
            #self.balance[self.secondary] -= r["amount"]
            self.swyftx.delete_order(self.stop_loss_id)
            self.bought = False
            self.zoomed = False
            self.history.append(self.order_to_list(r))

            # Used for timer related stuff:

            self.stop_clock()
            self.collect_and_process_live_data(primary=self.primary, secondary=self.secondary,
                                               resolution=rank_up(self.resolution))
            self.run_clock(resolution=self.resolution)


    def primary_balance(self):
        return float(self.balance[self.primary])

    def history_to_csv(self):
        d = pd.DataFrame(self.history, columns=["orderUuid", "order_type", "primary_asset", "secondary_asset", "quantity_asset", "quantity", "trigger", "status", "created_time", "updated_time", "amount", "total", "rate", "aud_value", "swyftxValue", "userCountryValue", "processed"])
        path = os.path.join("history", self.secondary)
        d.to_csv(os.path.join(path, str(1+len(os.listdir(path)))))

    def plot(self, resolution=None, last=None):
        """
        Plots the data that is currently stored inside Bot.
        """
        if last is None:
            last = 0
        if resolution is None:
            idx = check_rank(self.resolution)
        else:
            idx = check_rank(resolution)
        code = self.data[idx]["assetCode"]
        time = list(self.data[idx]["time"])[last * -1:]
        open_ = list(self.data[idx]["open"])[last * -1:]
        high = list(self.data[idx]["high"])[last * -1:]
        low = list(self.data[idx]["low"])[last * -1:]
        close = list(self.data[idx]["close"])[last * -1:]
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True)
        candle = go.Candlestick(x=time, open=open_, high=high, low=low, close=close, name="Candle")

        ema_g = go.Scatter(x=time, y=list(self.ema_hundred[idx])[last * -1:], marker={'color': "orange"},
                           name="Long EMA")

        fig.add_trace(candle, row=1, col=1)
        fig.add_trace(ema_g, row=1, col=1)

        macdeez = go.Scatter(x=time, y=list(self.macd[idx])[last * -1:], marker={'color': 'blue'}, name="MACD")
        macdeezsignal = go.Scatter(x=time, y=list(self.macdsignal[idx])[last * -1:], marker={"color": "red"},
                                   name="Signal")

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

    # print("Callback executed")
    # print("Graph time: ", datetime.now())
    bot.safe_update_all()
    # bot.update_all()
    code = bot.data[check_rank(bot.resolution)]["assetCode"]
    # print("Execution time: ", datetime.now())
    # print("Last time: ", bot.data["time"][-1])
    time = list(bot.data[check_rank(bot.resolution)]["time"])[-60:]
    open_ = list(bot.data[check_rank(bot.resolution)]["open"])[-60:]
    high = list(bot.data[check_rank(bot.resolution)]["high"])[-60:]
    low = list(bot.data[check_rank(bot.resolution)]["low"])[-60:]
    close = list(bot.data[check_rank(bot.resolution)]["close"])[-60:]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.2)

    candle = go.Candlestick(x=time, open=open_, high=high, low=low, close=close, name="Candle")
    fig.add_trace(candle, row=1, col=1)
    ema_g = go.Scatter(x=time, y=list(bot.ema_hundred[check_rank(bot.resolution)])[-60:], marker={'color': "orange"},
                       name="Long EMA")

    fig.add_trace(ema_g, row=1, col=1)
    # fig.add_trace(candle, row=1, col=1)
    # fig.add_trace(ema_g, row=1, col=1)

    macdeez = go.Scatter(x=time, y=list(bot.macd[check_rank(bot.resolution)])[-60:], marker={'color': 'blue'},
                         name="MACD")
    macdeezsignal = go.Scatter(x=time, y=list(bot.macdsignal[check_rank(bot.resolution)])[-60:],
                               marker={"color": "red"}, name="Signal")

    fig.add_trace(macdeez, row=2, col=1)
    fig.add_trace(macdeezsignal, row=2, col=1)

    fig.update_layout(title={
        "text": code,
        "x": 0.5,
        "xanchor": "center",
        "yanchor": "top"
    })

    # fig.update_xaxes(rangeslider_visible=False)

    return fig  # {"data":[candle], "layout": go.Layout(xaxis=dict(range=[min(time), max(time)+timedelta(minutes=1)]), )}


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
    # swag = SwagX(key)
    # d_buy = swag.get_asset_data("AUD", "BTC", "ask", "1m", datetime(2021,11,24), datetime.now())
    # nd_buy = extract_price_data(d_buy)
    # d_sell = swag.get_asset_data("AUD", "BTC", "bid", "1m", datetime(2021,11,24), datetime.now())
    # nd_sell = extract_price_data(d_sell)
    # watch("AUDIO")
