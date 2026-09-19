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

with open("Makefile", "r") as f:
    content = f.read()

content = content.replace("cp release/icon.png build_deb/usr/share/pixmaps/catlogs.png",
                          "mkdir -p build_deb/usr/share/icons/hicolor/256x256/apps\n\tcp icon/icon_256.png build_deb/usr/share/pixmaps/catlogs.png\n\tcp icon/icon_256.png build_deb/usr/share/icons/hicolor/256x256/apps/catlogs.png")

with open("Makefile", "w") as f:
    f.write(content)
