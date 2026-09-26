import re

with open('keylogger/keylogger.c', 'r') as f:
    code = f.read()

# Add help and version to main
main_match = re.search(r'int main\(int argc, char \*argv\[\]\) {.*?(?=unsigned char ok)', code, re.DOTALL)
if main_match:
    help_version = """
  if (argc >= 2)
    {
      if (strcmp (argv[1], "--version") == 0)
        {
          printf ("keylogger 1.0\\n");
          printf ("Copyright (C) 2026 Wassim Bolles\\n");
          printf ("License GPLv3+: GNU GPL version 3 or later <https://gnu.org/licenses/gpl.html>.\\n");
          printf ("This is free software: you are free to change and redistribute it.\\n");
          printf ("There is NO WARRANTY, to the extent permitted by law.\\n");
          return 0;
        }
      if (strcmp (argv[1], "--help") == 0)
        {
          printf ("Usage: %s [LOGFILE_PATH] [--daemon]\\n", argv[0]);
          printf ("Start the CatLogs keylogger.\\n\\n");
          printf ("  --daemon       Run in the background as a daemon\\n");
          printf ("  --help         Display this help and exit\\n");
          printf ("  --version      Output version information and exit\\n\\n");
          printf ("Report bugs to: <wassim@wassim.tech>.\\n");
          return 0;
        }
    }
"""
    new_main = main_match.group(0) + help_version
    code = code.replace(main_match.group(0), new_main)

# Quick format for GNU style (some basics)
code = re.sub(r'^(\w+[\w\s\*]*)\s+(\w+)\s*\((.*?)\)\s*\{', r'\1\n\2 (\3)\n{', code, flags=re.MULTILINE)
code = re.sub(r'if\s*\((.*?)\)\s*\{', r'if (\1)\n  {', code)
code = re.sub(r'while\s*\((.*?)\)\s*\{', r'while (\1)\n  {', code)
code = re.sub(r'for\s*\((.*?)\)\s*\{', r'for (\1)\n  {', code)
code = re.sub(r'\}\s*else\s*\{', r'}\nelse\n  {', code)
code = re.sub(r'([a-zA-Z0-9_]+)\(', r'\1 (', code) # Space before parens
code = code.replace('main (', 'main (') # Just in case

# Fix the usage of stderr without program name
code = re.sub(r'fprintf\s*\(\s*stderr,\s*"([^"]+)"', r'fprintf (stderr, "%s: \1", argv[0]', code)
code = code.replace('perror ("', 'perror ("keylogger: ')

with open('keylogger/keylogger.c', 'w') as f:
    f.write(code)

