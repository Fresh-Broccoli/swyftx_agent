class NoStartTimeError(Exception):
    def __init__(self, message="start_time was not specified."):
        self.message = message
        super().__init__(self.message)
