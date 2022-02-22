class NoStartTimeError(Exception):
    def __init__(self, message="start_time was not specified."):
        self.message = message
        super().__init__(self.message)

class InvalidModeError(Exception):
    def __init__(self, message="Invalid mode was specified. Please choose one of:\nopen\nrandom\nnopen"):
        self.message = message
        super().__init__(self.message)

class InvalidTypeError(Exception):
    def __init__(self, message="Invalid type was specified. Please choose one of:\nBUY\nSELL"):
        self.message = message
        super().__init__(self.message)

class OmniError(Exception):
    def __init__(self, message="Placeholder error"):
        self.message = message
        super().__init__(self.message)


