"""
Color utilities for console output
"""
import sys

# Reconfigure stdout/stderr encoding to UTF-8 on Windows to avoid UnicodeEncodeError crashes when printing emojis/Unicode chars
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

class Colors:
    """ANSI color codes for terminal output"""
    # Reset
    RESET = '\033[0m'
    
    # Regular colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # Bold colors
    BOLD = '\033[1m'
    BOLD_RED = '\033[1;31m'
    BOLD_GREEN = '\033[1;32m'
    BOLD_YELLOW = '\033[1;33m'
    BOLD_BLUE = '\033[1;34m'
    BOLD_MAGENTA = '\033[1;35m'
    BOLD_CYAN = '\033[1;36m'
    BOLD_WHITE = '\033[1;37m'
    
    # Background colors
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    
    @staticmethod
    def disable():
        """Disable colors if output is not a terminal"""
        if not sys.stdout.isatty():
            for attr in dir(Colors):
                if not attr.startswith('_') and attr != 'disable':
                    setattr(Colors, attr, '')

# Disable colors if not in terminal
Colors.disable()

def print_colored(text, color):
    """Print colored text"""
    print(f"{color}{text}{Colors.RESET}", flush=True)

def print_success(text):
    """Print success message in green"""
    print_colored(text, Colors.GREEN)

def print_error(text):
    """Print error message in red"""
    print_colored(text, Colors.RED)

def print_warning(text):
    """Print warning message in yellow"""
    print_colored(text, Colors.YELLOW)

def print_info(text):
    """Print info message in cyan"""
    print_colored(text, Colors.CYAN)

def print_header(text):
    """Print header in bold cyan"""
    print_colored(text, Colors.BOLD_CYAN)

