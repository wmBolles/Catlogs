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

import os
import re
import glob

# Remove theme toggle script, button, and init script from HTML
for html_file in glob.glob("website/*.html"):
    with open(html_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Remove <script>var t=localStorage...</script>
    content = re.sub(
        r"<script>var t=localStorage.*?<\/script>\n?", "", content)

    # Remove theme.js inclusion
    content = re.sub(
        r"<script src=\"\./assets/theme\.js\"><\/script>\n?", "", content)

    # Remove the theme-toggle buttons
    content = re.sub(
        r"<button class=\"theme-toggle\" onclick=\"toggleTheme\(\)\".*?<\/button>\n?", "", content)

    with open(html_file, "w", encoding="utf-8") as f:
        f.write(content)

# Remove dark mode and data-theme CSS from style.css
css_file = "website/assets/style.css"
with open(css_file, "r", encoding="utf-8") as f:
    css_content = f.read()

# We can find the media query block and data-theme blocks and remove them.
# The simplest is to just split by "}\n\n" or find them by regex.
# Since @media (prefers-color-scheme: dark) has nested braces, regex might be tricky.
# Let's see the structure of style.css.


# Remove dark mode and data-theme CSS from style.css
css_file = "website/assets/style.css"
with open(css_file, "r", encoding="utf-8") as f:
    css_content = f.read()

# Change `:root, [data-theme="light"]` to `:root`
css_content = css_content.replace(':root, [data-theme="light"]', ':root')

# Remove `[data-theme="dark"] { ... }`
# Find the start of `[data-theme="dark"] {` and the corresponding closing `}`
dark_start = css_content.find('[data-theme="dark"] {')
if dark_start != -1:
    dark_end = css_content.find('}\n', dark_start)
    if dark_end != -1:
        css_content = css_content[:dark_start] + css_content[dark_end+2:]

# Remove `@media (prefers-color-scheme: dark) { ... }`
media_start = css_content.find('@media (prefers-color-scheme: dark) {')
if media_start != -1:
    # We know the nested structure ends with `} \n}\n` or similar. Let's just use string slicing.
    media_end = css_content.find('}\n\n\nbody {', media_start)
    if media_end == -1:
        media_end = css_content.find('}\n\nbody {', media_start)

    if media_end != -1:
        css_content = css_content[:media_start] + css_content[media_end+2:]

with open(css_file, "w", encoding="utf-8") as f:
    f.write(css_content)
