#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.buttons"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026032401"


# This is blatanly stolen from https://github.com/definite-d/reskinner/issues/34?reload=1
# Thank you https://github.com/definite-d

import FreeSimpleGUI as sg
from reskinner.colorizer import Colorizer

try:
    from PIL import Image, ImageDraw
except ImportError:
    print(
        "Error: PIL/Pillow is required for this demo. "
        "Install with: `uv add --group dev Pillow`"
    )
    exit(1)

from io import BytesIO


def _is_custom_button(element):
    return (
        hasattr(element, "ButtonColor")
        and element.ButtonColor != (None, None)
        and hasattr(element, "ImageData")
        and element.ImageData
    )


def _after_element(element, colorizer: Colorizer):
    if isinstance(element, RoundedButton):
        theme_bg = colorizer.theme_color("BACKGROUND", lambda: "#000000")
        fg = colorizer.theme_color("TEXT", lambda: "#FFFFFF")
        element.widget.configure(
            foreground=fg,
            background=theme_bg,
            activebackground=theme_bg,
            activeforeground=fg,
        )
        element.update_color(colorizer.theme_color(("BUTTON", 1), lambda: "#000000"))


def round_corner(radius, fill):
    """Create a rounded corner image"""
    corner = Image.new("RGBA", (radius, radius), (0, 0, 0, 0))
    draw = ImageDraw.Draw(corner)
    draw.pieslice((0, 0, radius * 2, radius * 2), 180, 270, fill=fill)
    return corner


def round_rectangle(size, radius, fill):
    """Create a rounded rectangle image"""
    width, height = size
    rectangle = Image.new("RGBA", size, fill)
    corner = round_corner(radius, fill)
    rectangle.paste(corner, (0, 0))
    rectangle.paste(corner.rotate(90), (0, height - radius))
    rectangle.paste(corner.rotate(180), (width - radius, height - radius))
    rectangle.paste(corner.rotate(270), (width - radius, 0))
    return rectangle


def image_to_data(image):
    """Convert PIL image to bytes for PySimpleGUI"""
    with BytesIO() as output:
        image.save(output, format="PNG")
        return output.getvalue()


class RoundedButton(sg.Button):
    """A rounded button using PIL images with mask-based rendering"""

    def __init__(self, text, btn_width=100, btn_height=30, radius=30, **kwargs):
        # Remove conflicting parameters
        kwargs.pop("image_data", None)
        kwargs.pop("border_width", None)

        # Store button dimensions and create mask
        self.btn_width = btn_width
        self.btn_height = btn_height
        self.radius = radius
        self.mask = self._create_mask()

        # Store the button color for regeneration
        self.button_color = sg.theme_button_color()[1]

        # Generate the initial button image
        img = self._generate_image_from_mask()

        # Set text colors
        text_color = (sg.theme_text_color(), sg.theme_background_color())

        # Initialize the parent Button class
        super().__init__(
            text,
            button_type=sg.BUTTON_TYPE_READ_FORM,
            image_data=image_to_data(img),
            button_color=text_color,
            mouseover_colors=(None, sg.theme_background_color()),
            border_width=0,
            **kwargs,
        )

    def _create_mask(self):
        """Create a solid color mask of the button's shape"""
        # Use white as the mask color (can be any solid color)
        return round_rectangle(
            (self.btn_width, self.btn_height), self.radius, (255, 255, 255, 255)
        )

    def _generate_image_from_mask(self, fill_color=None):
        """Generate a button image from the mask with the specified fill color"""
        # Use instance button color if none provided
        if fill_color is None:
            fill_color = self.button_color

        # If fill_color doesn't include alpha, add full opacity
        if len(fill_color) == 3:
            fill_color = (*fill_color, 255)

        # Create a new image with the fill color
        img = Image.new("RGBA", (self.btn_width, self.btn_height), fill_color)

        # Use the mask as an alpha channel to apply the rounded shape
        img.putalpha(self.mask.getchannel("A"))

        return img

    def update_color(self, new_color):
        """Update the button's appearance with a new color"""
        # Update the stored button color
        self.button_color = new_color

        # Generate new image with the updated color
        new_img = self._generate_image_from_mask(new_color)

        # Update the button's image data and refresh display
        self.ImageData = image_to_data(new_img)
        self.update(image_data=self.ImageData)
