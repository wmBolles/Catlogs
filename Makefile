SHELL      := /bin/bash
PYTHON     := python3
APP_NAME   := catlogs
VERSION    := 1.1.0
DIST_DIR   := dist
BUILD_DIR  := build

VENV       := .venv
VENV_BIN   := $(VENV)/bin
VENV_PYTHON:= $(VENV_BIN)/python3
VENV_PIP   := $(VENV_BIN)/pip

INSTALLED  := .installed

.PHONY: all install run build clean distclean help package test

all: build

test:
	@echo "──▶ Running test suite..."
	$(PYTHON) -m unittest discover -s tests -p "test_*.py" -v

$(INSTALLED):
	@echo "──▶ Setting up environment..."
	@if $(PYTHON) -m venv $(VENV) 2>/dev/null; then \
		echo "    Using virtual environment."; \
		$(VENV_PIP) install --upgrade pip setuptools wheel -q; \
		$(VENV_PIP) install pyinstaller -q; \
		echo "venv" > $(INSTALLED); \
	else \
		echo "    python3-venv not available, using system pip with --user."; \
		$(PYTHON) -m pip install --user pyinstaller -q; \
		echo "user" > $(INSTALLED); \
	fi
	@echo "Dependencies installed."

install: $(INSTALLED)

define get_python
$(shell if [ -f $(INSTALLED) ] && [ "$$(cat $(INSTALLED))" = "venv" ]; then echo "$(VENV_PYTHON)"; else echo "$(PYTHON)"; fi)
endef

define get_pyinstaller
$(shell if [ -f $(INSTALLED) ] && [ "$$(cat $(INSTALLED))" = "venv" ]; then echo "$(VENV_BIN)/pyinstaller"; else echo "$(PYTHON) -m PyInstaller"; fi)
endef

run: $(INSTALLED)
	@echo "──▶ Launching CatLogs..."
	$(call get_python) -m catlogs

build: $(INSTALLED)
	@echo "──▶ Building standalone executable..."
	$(call get_pyinstaller) \
		--onefile \
		--name $(APP_NAME) \
		--clean \
		--noconfirm \
		--hidden-import=catlogs \
		--hidden-import=catlogs.gui \
		--hidden-import=catlogs.models \
		--hidden-import=catlogs.collectors \
		--hidden-import=catlogs.exporter \
		--hidden-import=catlogs.export_log \
		--hidden-import=catlogs.read_errors \
		--hidden-import=catlogs.config \
		--hidden-import=catlogs.log_parsers \
		--hidden-import=catlogs.keylogger \
		--add-data "$$(pwd)/icon:icon" \
		--add-data "$$(pwd)/keylogger:keylogger" \
		--distpath $(DIST_DIR) \
		--workpath $(BUILD_DIR) \
		--specpath $(BUILD_DIR) \
		main.py
	@echo ""
	@echo "    Build complete!"
	@echo "    Executable: $(DIST_DIR)/$(APP_NAME)"
	@echo "    Run it:     ./$(DIST_DIR)/$(APP_NAME)"

package: build
	@echo "──▶ Packaging release..."
	mkdir -p release
	cp $(DIST_DIR)/$(APP_NAME) release/$(APP_NAME)
	cp icon/icon.png release/icon.png
	@echo '#!/bin/bash' > release/install.sh
	@echo 'set -e' >> release/install.sh
	@echo '' >> release/install.sh
	@echo 'BASE_URL="$${BASE_URL:-https://catlogs.wassim.tech}"' >> release/install.sh
	@echo '' >> release/install.sh
	@echo 'if [ "$$(id -u)" -ne 0 ]; then' >> release/install.sh
	@echo '    echo "This installer needs root privileges. Re-running with sudo..."' >> release/install.sh
	@echo '    exec sudo bash "$$0" "$$@"' >> release/install.sh
	@echo 'fi' >> release/install.sh
	@echo '' >> release/install.sh
	@echo 'echo "Installing CatLogs..."' >> release/install.sh
	@echo '' >> release/install.sh
	@echo 'mkdir -p /usr/local/bin' >> release/install.sh
	@echo 'mkdir -p /usr/share/icons/hicolor/256x256/apps' >> release/install.sh
	@echo 'mkdir -p /usr/share/applications' >> release/install.sh
	@echo '' >> release/install.sh
	@echo 'SCRIPT_DIR="$$(cd "$$(dirname "$$0")" && pwd)"' >> release/install.sh
	@echo '' >> release/install.sh
	@echo 'if [ -f "$$SCRIPT_DIR/catlogs" ]; then' >> release/install.sh
	@echo '    cp "$$SCRIPT_DIR/catlogs" /usr/local/bin/catlogs' >> release/install.sh
	@echo 'else' >> release/install.sh
	@echo '    echo "Downloading binary..."' >> release/install.sh
	@echo '    curl -sSL "$$BASE_URL/catlogs" -o /usr/local/bin/catlogs' >> release/install.sh
	@echo 'fi' >> release/install.sh
	@echo 'chmod +x /usr/local/bin/catlogs' >> release/install.sh
	@echo '' >> release/install.sh
	@echo 'if [ -f "$$SCRIPT_DIR/icon.png" ]; then' >> release/install.sh
	@echo '    cp "$$SCRIPT_DIR/icon.png" /usr/share/icons/hicolor/256x256/apps/catlogs.png' >> release/install.sh
	@echo 'else' >> release/install.sh
	@echo '    echo "Downloading icon..."' >> release/install.sh
	@echo '    curl -sSL "$$BASE_URL/icon.png" -o /usr/share/icons/hicolor/256x256/apps/catlogs.png' >> release/install.sh
	@echo 'fi' >> release/install.sh
	@echo '' >> release/install.sh
	@echo 'echo "Creating desktop entry..."' >> release/install.sh
	@echo 'cat > /usr/share/applications/catlogs.desktop << DESKTOP_EOF' >> release/install.sh
	@echo '[Desktop Entry]' >> release/install.sh
	@echo 'Name=CatLogs' >> release/install.sh
	@echo 'Comment=System Logs' >> release/install.sh
	@echo 'Exec=/usr/local/bin/catlogs' >> release/install.sh
	@echo 'Icon=catlogs' >> release/install.sh
	@echo 'Terminal=false' >> release/install.sh
	@echo 'Type=Application' >> release/install.sh
	@echo 'Categories=System;Monitor;Utility;' >> release/install.sh
	@echo 'StartupWMClass=catlogs' >> release/install.sh
	@echo 'DESKTOP_EOF' >> release/install.sh
	@echo '' >> release/install.sh
	@echo 'echo " CatLogs installed successfully!"' >> release/install.sh
	@echo 'echo "You can find CatLogs in your application menu."' >> release/install.sh
	chmod +x release/install.sh
	@echo "  Release packaged in release/"

clean:
	@echo "──▶ Cleaning build artefacts..."
	rm -rf $(BUILD_DIR) $(DIST_DIR) __pycache__ catlogs/__pycache__ release
	rm -rf *.spec .pytest_cache
	@echo "  Cleaned."

distclean: clean
	@echo "──▶ Removing environment..."
	rm -rf $(VENV) $(INSTALLED)
	@echo "  Fully cleaned."

help:
	@echo ""
	@echo "  CatLogs — System Logs"
	@echo "  ─────────────────────────────────"
	@echo ""
	@echo "  make install     Install dependencies"
	@echo "  make run         Run the application"
	@echo "  make build       Build standalone executable (./dist/catlogs)"
	@echo "  make package     Package for release (creates release/ with install.sh)"
	@echo "  make clean       Remove build artefacts"
	@echo "  make distclean   Remove everything including venv"
	@echo "  make help        Show this help"
	@echo "  make release     Build and release to website/"
	@echo ""


.PHONY: deb release
deb: package
	@echo "Building Debian package..."
	rm -rf build_deb
	mkdir -p build_deb/DEBIAN
	mkdir -p build_deb/usr/bin
	mkdir -p build_deb/usr/share/applications
	mkdir -p build_deb/usr/share/pixmaps
	
	echo "Package: catlogs" > build_deb/DEBIAN/control
	echo "Version: $(VERSION)" >> build_deb/DEBIAN/control
	echo "Architecture: $$(dpkg --print-architecture 2>/dev/null || echo amd64)" >> build_deb/DEBIAN/control
	echo "Maintainer: Wassim <admin@wassim.tech>" >> build_deb/DEBIAN/control
	echo "Description: System Logs Viewer" >> build_deb/DEBIAN/control
	echo " Securely gathers and displays historical commands and system events." >> build_deb/DEBIAN/control
	
	cp release/catlogs build_deb/usr/bin/catlogs
	chmod +x build_deb/usr/bin/catlogs
	mkdir -p build_deb/usr/share/icons/hicolor/256x256/apps
	cp icon/icon_256.png build_deb/usr/share/pixmaps/catlogs.png
	cp icon/icon_256.png build_deb/usr/share/icons/hicolor/256x256/apps/catlogs.png
	
	echo "[Desktop Entry]" > build_deb/usr/share/applications/catlogs.desktop
	echo "Name=CatLogs" >> build_deb/usr/share/applications/catlogs.desktop
	echo "Comment=System Logs" >> build_deb/usr/share/applications/catlogs.desktop
	echo "Exec=/usr/bin/catlogs" >> build_deb/usr/share/applications/catlogs.desktop
	echo "Icon=catlogs" >> build_deb/usr/share/applications/catlogs.desktop
	echo "Terminal=false" >> build_deb/usr/share/applications/catlogs.desktop
	echo "Type=Application" >> build_deb/usr/share/applications/catlogs.desktop
	echo "Categories=System;Utility;" >> build_deb/usr/share/applications/catlogs.desktop
	echo "StartupWMClass=catlogs" >> build_deb/usr/share/applications/catlogs.desktop
	
	dpkg-deb --build build_deb release/catlogs_$(VERSION)_$$(dpkg --print-architecture 2>/dev/null || echo amd64).deb
	rm -rf build_deb
	@echo "Debian package created at release/catlogs_$(VERSION)_$$(dpkg --print-architecture 2>/dev/null || echo amd64).deb"

release: deb
	@echo "──▶ Releasing to website..."
	mkdir -p website
	cp $(DIST_DIR)/$(APP_NAME) website/$(APP_NAME)
	cp release/$(APP_NAME)_$(VERSION)_$$(dpkg --print-architecture 2>/dev/null || echo amd64).deb website/$(APP_NAME)_$(VERSION)_$$(dpkg --print-architecture 2>/dev/null || echo amd64).deb
	echo "$(VERSION)" > website/version.txt
	@echo "  Released to website/"
