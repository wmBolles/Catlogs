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

import re

with open("website/assets/style.css", "r") as f:
    content = f.read()

# Replace .hero-icon with .header img.hero-icon
content = content.replace(".hero-icon {", ".header img.hero-icon {")

# In the mobile section, ensure we enforce 52px for the hero icon so it matches current behavior
mobile_target = ".header img.hero-icon { width: 160px; height: 160px; }"
mobile_replacement = ".header img.hero-icon { width: 52px; height: 52px; }"

# Wait, the replacement earlier changed '.hero-icon {' in the mobile section to '.header img.hero-icon {' as well!
# So it currently says '.header img.hero-icon { width: 160px; height: 160px; }' in the mobile section.
content = content.replace(mobile_target, mobile_replacement)

with open("website/assets/style.css", "w") as f:
    f.write(content)
