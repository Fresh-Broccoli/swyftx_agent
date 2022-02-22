class Id_Generator:
    # Just a tool used during backtesting for keeping track of dummy order numbers.
    def __init__(self, start = 0, length=12):
        self.current_id = start
        self.length = length

    def increment(self, by=1, ret=True):
        self.current_id += 1
        if ret:
            return self.output()

    def output(self):
        return str(self.current_id).zfill(self.length)
