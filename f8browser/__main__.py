import tkinter as tk
from f8browser import F8BrowserGUI
import os
import click

@click.command()
@click.option('--debug',default=False)
def f8browserCli(debug):
    root = tk.Tk()
    f8b = F8BrowserGUI(root,debug=debug)
    root.mainloop()
    os._exit(0)

if __name__ == "__main__":
    f8browserCli()