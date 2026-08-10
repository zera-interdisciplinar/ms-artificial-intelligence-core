from datetime import datetime


class logger:
    RESET = "\033[0m"
    BLUE = "\033[94m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"

    @staticmethod
    def _timestamp():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def Info(self, message):
        print(f"{logger.BLUE}[{logger._timestamp()}] [INFO] {message}{logger.RESET}", flush=True)

    def Error(self, message, error):
        print(f"{logger.RED}[{logger._timestamp()}] [ERROR] {message}{error}{logger.RESET}", flush=True)

    def Debug(self, message):
        print(f"{logger.CYAN}[{logger._timestamp()}] [DEBUG] {message}{logger.RESET}", flush=True)

    def Warning(self, message):
        print(f"{logger.YELLOW}[{logger._timestamp()}] [WARNING] {message}{logger.RESET}", flush=True)