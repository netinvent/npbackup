#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.buttons"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2025 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025102101"


from PIL import Image, ImageDraw
import FreeSimpleGUI as sg


# balanty stolen from https://github.com/PySimpleGUI/PySimpleGUI/issues/5091

def backgroundPNG(MAX_W, MAX_H, backgroundColor=None):
    background = Image.new("RGBA", (MAX_W, MAX_H), color=backgroundColor)
    draw = ImageDraw.Draw(background)

    return [background, draw]

def roundCorners(im, rad):
    """
    Rounds the corners of an image to given radius
    """
    mask = Image.new("L", im.size)
    if rad > min(*im.size) // 2:
        rad = min(*im.size) // 2
    draw = ImageDraw.Draw(mask)

    draw.ellipse((0, 0, rad * 2, rad * 2), fill=255)
    draw.ellipse((0, im.height - rad * 2 -2, rad * 2, im.height-1) , fill=255)
    draw.ellipse((im.width - rad * 2, 1, im.width, rad * 2), fill=255)
    draw.ellipse(
        (im.width - rad * 2, im.height - rad * 2, im.width-1, im.height-1), fill=255
    )
    draw.rectangle([rad, 0, im.width - rad, im.height], fill=255)
    draw.rectangle([0, rad, im.width, im.height - rad], fill=255)
    
    mask = superSample(mask, 8)
    im.putalpha(mask)
    
    return im

def superSample(image, sample):
    """
    Supersample an image for better edges
    image: image object
    sample: sampling multiplicator int(suggested: 2, 4, 8)
    """
    w, h = image.size

    image = image.resize((int(w * sample), int(h * sample)), resample=Image.LANCZOS)
    image = image.resize((image.width // sample, image.height // sample), resample=Image.LANCZOS)

    return image

def image_to_data(im):
    """
    This is for Pysimplegui library
    Converts image into data to be used inside GUIs
    """
    from io import BytesIO

    with BytesIO() as output:
        im.save(output, format="PNG")
        data = output.getvalue()
    return data

def RoundedButton(button_text=' ', corner_radius=0, button_type=sg.BUTTON_TYPE_READ_FORM, target=(None, None),
                  tooltip=None, file_types=sg.FILE_TYPES_ALL_FILES, initial_folder=None, default_extension='',
                  disabled=False, change_submits=False, enable_events=False,
                  image_size=(None, None), image_subsample=None, border_width=None, size=(None, None),
                  auto_size_button=None, button_color=None, disabled_button_color=None, highlight_colors=None, 
                  mouseover_colors=(None, None), use_ttk_buttons=None, font=None, bind_return_key=False, focus=False, 
                  pad=None, key=None, right_click_menu=None, expand_x=False, expand_y=False, visible=True, 
                  metadata=None, btn_size=(None, None)):

    if btn_size != (None, None):
        btn_width: int = btn_size[0]
        btn_height: int = btn_size[1]
    else:
        btn_width: int = 100
        btn_height: int = 30
    button_img = backgroundPNG(btn_width*5, btn_height*5, button_color[1])
    button_img[0] = roundCorners(button_img[0], 30*5)
    button_img[0] = button_img[0].resize((btn_width, btn_height), resample=Image.LANCZOS)
    btn_img = image_to_data(button_img[0])
    if button_color is None:
        button_color = sg.theme_button_color()
    return sg.Button(button_text=button_text, button_type=button_type, target=target, tooltip=tooltip,
                  file_types=file_types, initial_folder=initial_folder, default_extension=default_extension,
                  disabled=disabled, change_submits=change_submits, enable_events=enable_events,
                  image_data=btn_img, image_size=image_size,
                  image_subsample=image_subsample, border_width=border_width, size=size,
                  auto_size_button=auto_size_button, button_color=(button_color[0], sg.theme_background_color()),
                  disabled_button_color=disabled_button_color, highlight_colors=highlight_colors,
                  mouseover_colors=mouseover_colors, use_ttk_buttons=use_ttk_buttons, font=font,
                  bind_return_key=bind_return_key, focus=focus, pad=pad, key=key, right_click_menu=right_click_menu,
                  expand_x=expand_x, expand_y=expand_y, visible=visible, metadata=metadata)