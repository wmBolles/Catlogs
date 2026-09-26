#!/usr/bin/env python3

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

from PIL import Image
import numpy as np
import os


def remove_background(input_path, output_path):
    """Remove blue background from icon image."""
    img = Image.open(input_path).convert("RGBA")
    data = np.array(img)

    r, g, b, a = data[:, :, 0], data[:, :, 1], data[:, :, 2], data[:, :, 3]

    is_blue = (
        (b > 130) &
        (b > r * 1.3) &
        (b > g * 0.9) &
        (r < 180) &
        ~((r > 200) & (g > 200) & (b > 200))
    )

    blue_strength = np.zeros_like(b, dtype=float)
    blue_strength[is_blue] = 1.0

    is_edge = (
        (b > 100) &
        (b > r * 1.1) &
        ~is_blue &
        ~((r > 200) & (g > 200) & (b > 200))
    )
    edge_alpha = np.clip((b.astype(float) - r.astype(float)) / 150.0, 0, 1)
    blue_strength[is_edge] = edge_alpha[is_edge] * 0.7

    new_alpha = np.clip(
        a.astype(float) * (1.0 - blue_strength), 0, 255).astype(np.uint8)
    data[:, :, 3] = new_alpha

    result = Image.fromarray(data)
    result.save(output_path, "PNG")
    print(f"Saved transparent icon to {output_path}")
    print(f"Size: {result.size}")


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(script_dir, "icon.jpeg")
    output_path = os.path.join(script_dir, "icon.png")
    remove_background(input_path, output_path)
