import debugpy

try:
    from colorama import Fore
    YELLOW, GREEN, RED, RESET = Fore.YELLOW, Fore.GREEN, Fore.RED, Fore.RESET
except ImportError:
    YELLOW, GREEN, RED, RESET = [""]*4

# https://code.visualstudio.com/docs/python/debugging#_debugging-by-attaching-over-a-network-connection

# 5678 is the default attach port in the VS Code debug configurations. Unless a host and port are specified, host defaults to 127.0.0.1
debugpy.listen(5678)
print(f"{YELLOW}Waiting for debugger attach{RESET}")
debugpy.wait_for_client()
if debugpy.is_client_connected():
    print(f"{GREEN}Debugger attached to client{RESET}")
else:
    print(f"{RED}Failed to connect to client{RESET}")

