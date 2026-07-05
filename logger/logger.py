class logger:
    RESET = "\033[0m"
    BLUE = "\033[94m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"

    def Info(self, message):
        print(f"{logger.BLUE}[INFO] {message}{logger.RESET}")
        
    def Error(self, message, error):
        print(f"{logger.RED}[ERROR] {message}{error}{logger.RESET}")
        
    def Debug(self, message):
        print(f"{logger.CYAN}[DEBUG] {message}{logger.RESET}")
        
    def Warning(self, message):
        print(f"{logger.YELLOW}[WARNING] {message}{logger.RESET}")