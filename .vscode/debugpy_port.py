import sys
import os

# Initialize color variables safely
YELLOW, GREEN, RED, RESET = [""] * 4
try:
    from colorama import Fore
    YELLOW, GREEN, RED, RESET = Fore.YELLOW, Fore.GREEN, Fore.RED, Fore.RESET
except ImportError:
    print("colorama not found, proceeding without colors.") # Optional: inform the user

# Print the current Python path for debugging
print(f"{YELLOW}Current Python path:{RESET}")
for path in sys.path:
    print(f"{GREEN}{path}{RESET}")


# Start debugpy
try:
    import debugpy
    debugpy.listen(('localhost', 5678))
    print(f"{YELLOW}Waiting for debugger attach{RESET}")
    debugpy.wait_for_client()
    if debugpy.is_client_connected():
        print(f"{GREEN}Debugger attached to client{RESET}")
    else:
        print(f"{RED}Failed to connect to client{RESET}")
except ImportError as e:
    print(f"{RED}Failed to import debugpy: {e}{RESET}")
