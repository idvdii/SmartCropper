import os
import sys

# ================= 路径配置 =================
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

INPUT_ROOT = os.path.join(BASE_DIR, 'set_image')    
OUTPUT_ROOT = os.path.join(BASE_DIR, 'save_image')
TRASH_ROOT  = os.path.join(BASE_DIR, 'trash_bin') 
# 新增：结果图的回收站
SAVE_TRASH_ROOT = os.path.join(BASE_DIR, 'trash_bin_save') 

# ================= 界面参数 =================
WIN_WIDTH = 1000      
WIN_HEIGHT = 850  
CROP_BOX_SIZE = 512   
MASK_OPACITY = 180 

# ================= 颜色定义 =================
BG_COLOR = "#1E1E1E"
PANEL_COLOR = "#252526"
CANVAS_COLOR = "#0F0F0F"
COLOR_TEXT_MAIN = "#FFFFFF"
COLOR_TEXT_SUB = "#888888"