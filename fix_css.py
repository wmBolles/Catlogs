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
content = content.replace(
    ".header img {\n    width: 72px;\n    height: 72px;\n    border-radius: 4px;\n}", "")

# Wait, if I remove .header img completely, then I should specify .header img.hero-icon with 270px or something.
# The user wants it bigger. If it was 72px, maybe 270px is what was originally intended but failed due to specificity.
# Let's just give .header img.hero-icon the 270px width/height.            fclose (f);

