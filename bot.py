import talib
import pandas as pd
import plotly.graph_objects as go

from plotly.subplots import make_subplots
from swyftx import SwagX
from datetime import datetime


with open("key.txt", "r") as f:
    key = f.readline()

def main():
    swag = SwagX(key)


def extract_price_data(data):
    time, open, close, low, high = [], [], [], [], []
    assetCode = data["assetCode"]
    data=data["data"]
    for i in range(len(data)):
        time.append(data[i]["time"])
        open.append(data[i]["open"])
        close.append(data[i]["close"])
        low.append(data[i]["low"])
        high.append(data[i]["high"])

    df = pd.DataFrame({
        "time":time,
        "open":open,
        "close":close,
        "low":low,
        "high":high
    })

    return {
        "assetCode":assetCode,
        "data":df
    }

def plot_price_data(data):
    code = data["assetCode"]
    d = data["data"]

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True)
    candle = go.Candlestick(x=d["time"],open=d["open"],high=d["high"],low=d["low"],close=d["close"], name="Candle")

    ema = talib.EMA(d["close"], 100)
    ema_g = go.Scatter(x=d["time"], y=ema, marker={'color':"orange"}, name="100EMA")

    fig.add_trace(candle, row=1, col=1)
    fig.add_trace(ema_g, row=1, col=1)

    macd, macdsignal, macdhist = talib.MACD(d["close"])

    macdeez = go.Scatter(x=d["time"], y=macd, marker={'color':'blue'}, name="MACD")
    macdeezsignal = go.Scatter(x=d["time"], y=macdsignal, marker={"color":"red"}, name="Signal")

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
    d_buy = swag.get_asset_data("AUD", assetCode, "ask", "1m", datetime(2021,11,24), datetime.now())
    nd_buy = extract_price_data(d_buy)
    d_sell = swag.get_asset_data("AUD", assetCode, "bid", "1m", datetime(2021,11,24), datetime.now())
    nd_sell = extract_price_data(d_sell)
    plot_price_data(nd_buy)
    plot_price_data(nd_sell)

if '__main__' == __name__:
    swag = SwagX(key)
    d_buy = swag.get_asset_data("AUD", "BTC", "ask", "1m", datetime(2021,11,24), datetime.now())
    nd_buy = extract_price_data(d_buy)
    d_sell = swag.get_asset_data("AUD", "BTC", "bid", "1m", datetime(2021,11,24), datetime.now())
    nd_sell = extract_price_data(d_sell)
    #watch("AUDIO")
