import os
import sys

def update_main(filepath, program_name):
    if not os.path.exists(filepath):
        return
    with open(filepath, 'r') as f:
        content = f.read()

    if '--version' in content:
        return
        
    code_to_add = f"""
    if len(sys.argv) > 1:
        if sys.argv[1] == "--version":
            print("{program_name} 1.0")
            print("Copyright (C) 2026 Wassim Bolles")
            print("License GPLv3+: GNU GPL version 3 or later <https://gnu.org/licenses/gpl.html>.")
            print("This is free software: you are free to change and redistribute it.")
            print("There is NO WARRANTY, to the extent permitted by law.")
            sys.exit(0)
        elif sys.argv[1] == "--help":
            print("Usage: {program_name} [OPTIONS]")
            print("Start the CatLogs application.\\n")
            print("  --help         Display this help and exit")
            print("  --version      Output version information and exit\\n")
            print("Report bugs to: <wassim@wassim.tech>.")
            sys.exit(0)
"""

    if 'if __name__ == "__main__":' in content:
        content = content.replace('if __name__ == "__main__":', 'if __name__ == "__main__":' + code_to_add)
    
    with open(filepath, 'w') as f:
        f.write(content)

update_main('main.py', 'catlogs')
update_main('catlogs/__main__.py', 'catlogs')
