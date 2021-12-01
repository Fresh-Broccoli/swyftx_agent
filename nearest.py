def calculate_next_minute(unix_time):
    return unix_time + 60 - (unix_time % 60)


def calculate_next_5_minute(unix_time):
    return unix_time + 60*5 - (unix_time % (60*5))


def calculate_next_half_hour(unix_time):
    return unix_time + 60*30 - (unix_time % (60*30))


def calculate_next_hour(unix_time):
    return unix_time + 60*60 - (unix_time % (60*60))

next_interval = {
    "1m": calculate_next_minute,
    "5m": calculate_next_5_minute,
    "30m": calculate_next_half_hour,
    "1h": calculate_next_hour
}

resolution_to_seconds = {
    "1m":60,
    "5m":5*60,
    "30m":30*60,
    "1h":60*60
}