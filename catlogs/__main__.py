# CatLogs
# A local system logging and diagnostic tool.
# Copyright (C) 2026 Wassim Bolles
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from .gui import run
import sys

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--version":
            print("catlogs 1.0")
            print("Copyright (C) 2026 Wassim Bolles")
            print(
                "License GPLv3+: GNU GPL version 3 or later <https://gnu.org/licenses/gpl.html>.")
            print("This is free software: you are free to change and redistribute it.")
            print("There is NO WARRANTY, to the extent permitted by law.")
            sys.exit(0)
        elif sys.argv[1] == "--help":
            print("Usage: catlogs [OPTIONS]")
            print("Start the CatLogs application.\n")
            print("  --help         Display this help and exit")
            print("  --version      Output version information and exit\n")
            print("Report bugs to: <wassim@wassim.tech>.")
            sys.exit(0)

    run()
