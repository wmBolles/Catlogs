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

deb_target = """
.PHONY: deb
deb: package
	@echo "Building Debian package..."
	rm -rf build_deb
	mkdir -p build_deb/DEBIAN
	mkdir -p build_deb/usr/bin
	mkdir -p build_deb/usr/share/applications
	mkdir -p build_deb/usr/share/icons/hicolor/256x256/apps
	
	echo "Package: catlogs" > build_deb/DEBIAN/control
	echo "Version: 1.1.0" >> build_deb/DEBIAN/control
	echo "Architecture: amd64" >> build_deb/DEBIAN/control
	echo "Maintainer: Wassim <admin@wassim.tech>" >> build_deb/DEBIAN/control
	echo "Description: System Logs Viewer" >> build_deb/DEBIAN/control
	echo " Securely gathers and displays historical commands and system events." >> build_deb/DEBIAN/control
	
	cp release/catlogs build_deb/usr/bin/catlogs
	chmod +x build_deb/usr/bin/catlogs
	cp release/icon.png build_deb/usr/share/icons/hicolor/256x256/apps/catlogs.png
	
	echo "[Desktop Entry]" > build_deb/usr/share/applications/catlogs.desktop
	echo "Name=CatLogs" >> build_deb/usr/share/applications/catlogs.desktop
	echo "Comment=System Logs" >> build_deb/usr/share/applications/catlogs.desktop
	echo "Exec=/usr/bin/catlogs" >> build_deb/usr/share/applications/catlogs.desktop
	echo "Icon=catlogs" >> build_deb/usr/share/applications/catlogs.desktop
	echo "Terminal=false" >> build_deb/usr/share/applications/catlogs.desktop
	echo "Type=Application" >> build_deb/usr/share/applications/catlogs.desktop
	echo "Categories=System;Utility;" >> build_deb/usr/share/applications/catlogs.desktop
	echo "StartupWMClass=catlogs" >> build_deb/usr/share/applications/catlogs.desktop
	
	dpkg-deb --build build_deb release/catlogs_1.1.0_amd64.deb
	rm -rf build_deb
	@echo "Debian package created at release/catlogs_1.1.0_amd64.deb"
"""

if "deb:" not in content:
    content += "\n" + deb_target

with open("Makefile", "w") as f:
    f.write(content)
