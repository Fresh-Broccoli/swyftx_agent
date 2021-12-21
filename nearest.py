def calculate_next_minute(unix_time, delay=0):
    return unix_time + 60 - (unix_time % 60) + delay

def calculate_next_3_minute(unix_time, delay=0):
    return unix_time + 60*3 - (unix_time % (60*3)) + delay

def calculate_next_5_minute(unix_time, delay=0):
    return unix_time + 60*5 - (unix_time % (60*5)) + delay

def calculate_next_10_minute(unix_time, delay=0):
    return unix_time + 60*10 - (unix_time % (60*10)) + delay

def calculate_next_15_minute(unix_time, delay=0):
    return unix_time + 60*15 - (unix_time % (60*15)) + delay

def calculate_next_half_hour(unix_time, delay=0):
    return unix_time + 60*30 - (unix_time % (60*30)) + delay

def calculate_next_hour(unix_time, delay=0):
    return unix_time + 60*60 - (unix_time % (60*60)) + delay

def calculate_next_4_hour(unix_time, delay=0):
    return unix_time + 60*60*4 - (unix_time % (60*60*4)) + delay

def calculate_next_day(unix_time, delay=0):
    return unix_time + 60*60*24 - (unix_time % (60*60*24)) + delay

def calculate_next_interval(unix_time, interval, delay=0):
    return unix_time + resolution_to_seconds[interval] - (unix_time % resolution_to_seconds[interval]) + delay

def erase_seconds(unix_time):
    return calculate_next_minute(unix_time) - 60

next_interval = {
    "1m": calculate_next_minute,
    "3m": calculate_next_3_minute, # Not supported by SwyftX as of 10/12/21
    "5m": calculate_next_5_minute,
    "10m": calculate_next_10_minute, # Not supported by SwyftX as of 10/12/21
    "15m": calculate_next_15_minute, # Not supported by SwyftX as of 10/12/21
    "30m": calculate_next_half_hour, # NNot supported by SwyftX as of 10/12/21
    "1h": calculate_next_hour,
    "4h": calculate_next_4_hour,
    "1d": calculate_next_day
}

resolution_to_seconds = {
    "1m":60,
    "3m":3*60,
    "5m":5*60,
    "10m":10*60,
    "15m":15*60,
    "30m":30*60,
    "1h":60*60,
    "4h": 60*60*4,
    "1d": 60*60*24
}
resolution_rank = ["1m", "5m", "1h", "4h", "1d"]