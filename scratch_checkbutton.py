import tkinter as tk
from tkinter import ttk

root = tk.Tk()
style = ttk.Style()
style.theme_use("clam")
print("Layout:", style.layout("TCheckbutton"))
print("Options Checkbutton.indicator:", style.element_options("Checkbutton.indicator"))
print("Options TCheckbutton:", style.configure("TCheckbutton"))
