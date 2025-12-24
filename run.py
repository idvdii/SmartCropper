import tkinter as tk
from main_ui import MaskCropper

if __name__ == "__main__":
    root = tk.Tk()
    app = MaskCropper(root)
    root.mainloop()