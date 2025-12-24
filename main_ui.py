import tkinter as tk
from tkinter import messagebox, ttk, simpledialog
from PIL import Image, ImageTk, ImageDraw, ImageGrab
import os
import shutil
import re
import threading 
import config
from trash_ui import TrashWindow
import ctypes

try:
    from upscaler import get_upscaler
    HAS_AI = True
except ImportError:
    HAS_AI = False
    print("Warning: upscaler.py not found or dependencies missing.")

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except: pass

class MaskCropper:
    def __init__(self, root):
        self.root = root
        self.root.title("数据集专家工具 (V4.5 极速版)") # 版本号升级
        self.root.configure(bg=config.BG_COLOR)
        
        ws = root.winfo_screenwidth()
        hs = root.winfo_screenheight()
        x = (ws/2) - (config.WIN_WIDTH/2)
        y = (hs/2) - (config.WIN_HEIGHT/2)
        root.geometry(f'{config.WIN_WIDTH}x{config.WIN_HEIGHT}+{int(x)}+{int(y)}')

        self.current_subfolder = tk.StringVar()         
        self.show_grid = tk.BooleanVar(value=True)
        self.target_ratio_str = tk.StringVar(value="1:1") 
        self.previous_ratio = "1:1" 
        self.fixed_target_size = None 
        self.use_ai_upscale = tk.BooleanVar(value=False)

        self.box_w = config.CROP_BOX_SIZE
        self.box_h = config.CROP_BOX_SIZE
        self.box_cx = 0; self.box_cy = 0
        self.box_x1 = 0; self.box_y1 = 0; self.box_x2 = 0; self.box_y2 = 0

        self.ensure_dirs()
        self.curr_in = config.INPUT_ROOT
        self.curr_out = config.OUTPUT_ROOT
        self.curr_trash = config.TRASH_ROOT

        self.image_list = []
        self.current_index = 0
        self.scale = 1.0
        self.min_scale = 1.0
        self.rotation = 0 
        self.img_x = 0; self.img_y = 0
        self.original_image = None 
        self.display_image = None 
        self.last_deleted_info = None 
        self.is_processing = False
        
        # === 优化核心：交互状态标记 ===
        self.is_moving_action = False # 是否正在拖拽/缩放中

        self.current_preview_pil = None
        self.preview_tk_img = None
        self.result_overlay = None
        self.bg_photo = None 

        self.setup_ui()
        self.bind_events()
        self.root.after(100, self.startup_sequence)

    def ensure_dirs(self):
        for d in [config.INPUT_ROOT, config.OUTPUT_ROOT, config.TRASH_ROOT, config.SAVE_TRASH_ROOT]:
            if not os.path.exists(d): os.makedirs(d)

    def startup_sequence(self):
        self.full_refresh()
        if self.combo_dir['values']: 
            self.combo_dir.current(0) 
        else: 
            self.current_subfolder.set("[ 根目录 ]")
        
        self.root.update()
        self.root.update_idletasks()
        
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw > 10:
            self.box_cx, self.box_cy = cw // 2, ch // 2
        else:
            self.box_cx = (config.WIN_WIDTH - 260) // 2
            self.box_cy = config.WIN_HEIGHT // 2
        
        self.update_box_shape(force_render=True) 
        self.reload_images(check_changes=False)

    def setup_ui(self):
        top_bar = tk.Frame(self.root, bg="#333333", pady=8, padx=10)
        top_bar.pack(side=tk.TOP, fill=tk.X)
        
        style = ttk.Style()
        style.configure("Dark.TCheckbutton", background="#333333", foreground="white", font=("Microsoft YaHei", 9))
        
        tk.Button(top_bar, text="?", command=self.show_help, bg="#007ACC", fg="white", bd=0, width=3).pack(side=tk.LEFT, padx=(0,10))
        tk.Label(top_bar, text="工作目录:", bg="#333333", fg="#DDDDDD").pack(side=tk.LEFT, padx=(5,2))
        
        self.combo_dir = ttk.Combobox(top_bar, textvariable=self.current_subfolder, state="readonly", width=20)
        self.combo_dir.pack(side=tk.LEFT, padx=5)
        self.combo_dir.bind("<<ComboboxSelected>>", lambda e: self.reload_images(check_changes=False))
        
        tk.Button(top_bar, text="⟳ 刷新", command=lambda: self.full_refresh(check_changes=True), bg="#555555", fg="white", bd=0, padx=8).pack(side=tk.LEFT, padx=5)

        separator = tk.Frame(top_bar, width=2, bg="#555555", height=20)
        separator.pack(side=tk.LEFT, padx=20)
        
        tk.Label(top_bar, text="固定宽高比:", bg="#333333", fg="#FF8800", font=("Microsoft YaHei", 10, "bold")).pack(side=tk.LEFT, padx=(0, 5))
        
        ratios = ["1:1", "3:4", "4:3", "9:16", "16:9", "2:3", "3:2", "自定义..."]
        self.combo_ratio = ttk.Combobox(top_bar, textvariable=self.target_ratio_str, values=ratios, state="readonly", width=10, font=("Arial", 10))
        self.combo_ratio.pack(side=tk.LEFT, padx=5)
        self.combo_ratio.bind("<<ComboboxSelected>>", self.on_ratio_change)
        
        if HAS_AI:
            cb_ai = ttk.Checkbutton(top_bar, text="✨ AI修复", variable=self.use_ai_upscale, style="Dark.TCheckbutton")
            cb_ai.pack(side=tk.LEFT, padx=(20, 5))
        
        ttk.Checkbutton(top_bar, text="井字构图线", variable=self.show_grid, command=self.create_overlay, style="Dark.TCheckbutton").pack(side=tk.RIGHT, padx=10)

        tk.Label(self.root, text="快捷键: [鼠标]移动 | [Alt+方向键]微调框 | [→]保存 | [Del]丢弃 | [Ctrl+Z]撤销", bg="#2D2D2D", fg="#AAAAAA", pady=6).pack(side=tk.TOP, fill=tk.X)

        main_area = tk.Frame(self.root, bg=config.BG_COLOR)
        main_area.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(main_area, bg=config.CANVAS_COLOR, highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.panel = tk.Frame(main_area, bg=config.PANEL_COLOR, width=260)
        self.panel.pack(side=tk.RIGHT, fill=tk.Y)
        self.panel.pack_propagate(False)
        
        self.create_right_panel()

    def create_right_panel(self):
        style_h = {"fg": config.COLOR_TEXT_SUB, "bg": config.PANEL_COLOR, "font": ("Microsoft YaHei", 9)}
        style_v = {"fg": config.COLOR_TEXT_MAIN, "bg": config.PANEL_COLOR, "font": ("Microsoft YaHei", 10, "bold"), "wraplength": 240, "justify": "left"}

        nav_frame = tk.Frame(self.panel, bg="#1E1E1E", pady=10)
        nav_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        def create_link(parent, text, cmd):
            lbl = tk.Label(parent, text=text, bg="#1E1E1E", fg="#4EC9B0", font=("Microsoft YaHei", 9), cursor="hand2", anchor="w")
            lbl.pack(fill=tk.X, padx=15, pady=2)
            lbl.bind("<Button-1>", lambda e: cmd())
            lbl.bind("<Enter>", lambda e: lbl.config(fg="#80FFD0"))
            lbl.bind("<Leave>", lambda e: lbl.config(fg="#4EC9B0"))
            return lbl

        tk.Label(nav_frame, text="快速导航:", bg="#1E1E1E", fg="#666666", font=("Arial", 8)).pack(anchor="w", padx=15)
        self.link_open_in = create_link(nav_frame, "📂 源: [ 根目录 ]", lambda: self.open_explorer(self.curr_in))
        self.link_open_out = create_link(nav_frame, "💾 存: [ save_image ]", lambda: self.open_explorer(self.curr_out))

        bf = tk.Frame(self.panel, bg=config.PANEL_COLOR)
        bf.pack(side=tk.BOTTOM, fill=tk.X, padx=15, pady=10)
        
        btn_cfg = {"fg":"white", "bd":0, "pady":5}
        tk.Button(bf, text="♻️ 回收站 (Ctrl+T)", command=self.open_trash, bg="#2B2B2B", **btn_cfg).pack(fill=tk.X, pady=2)
        tk.Button(bf, text="↶ 撤销 (Ctrl+Z)", command=self.undo, bg="#D97706", **btn_cfg).pack(fill=tk.X, pady=2)
        tk.Button(bf, text="🗑 丢弃 (Del)", command=self.trash, bg="#C53030", **btn_cfg).pack(fill=tk.X, pady=2)
        tk.Button(bf, text="⟳ 旋转 (R)", command=self.rotate, bg="#444444", **btn_cfg).pack(fill=tk.X, pady=2)

        info_frame = tk.Frame(self.panel, bg=config.PANEL_COLOR)
        info_frame.pack(side=tk.TOP, fill=tk.X)

        def add_item(t, c=None):
            tk.Label(info_frame, text=t, **style_h).pack(anchor="w", padx=15, pady=(10,0))
            l = tk.Label(info_frame, text="--", **style_v)
            if c: l.config(fg=c)
            l.pack(anchor="w", padx=15, pady=1)
            return l

        self.l_mode = add_item("当前目录")
        self.l_name = add_item("当前文件")
        self.l_prog = add_item("进度")
        self.l_size = add_item("原图尺寸")
        
        self.l_res_title = tk.Label(info_frame, text="裁剪分辨率:", **style_h)
        self.l_res_title.pack(anchor="w", padx=15, pady=(10,0))
        
        self.l_crop_res = tk.Label(info_frame, text="-- x --", bg=config.PANEL_COLOR, fg="#4CAF50", font=("Arial", 14, "bold"))
        self.l_crop_res.pack(anchor="w", padx=15, pady=2)
        
        self.l_warning = tk.Label(info_frame, text="", bg=config.PANEL_COLOR, fg="#FF5555", font=("Microsoft YaHei", 8), justify="left")
        self.l_warning.pack(anchor="w", padx=15)

        tk.Label(self.panel, text="结果预览 (点击放大):", **style_h).pack(side=tk.TOP, anchor="w", padx=15, pady=(15, 5))
        
        self.preview_frame = tk.Frame(self.panel, bg="#111111", relief="sunken", bd=1, cursor="hand2")
        self.preview_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=15, pady=(0, 10))
        
        self.l_preview_img = tk.Label(self.preview_frame, text="尚未保存", bg="#111111", fg="#555555", font=("Microsoft YaHei", 10), cursor="hand2")
        self.l_preview_img.pack(expand=True, fill=tk.BOTH)
        
        self.preview_frame.bind("<Configure>", self.on_preview_resize)
        self.preview_frame.bind("<Button-1>", self.show_large_result_preview)
        self.l_preview_img.bind("<Button-1>", self.show_large_result_preview)

    def bind_events(self):
        self.canvas.bind("<ButtonPress-1>", self.on_down)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        # === 优化：绑定鼠标松开事件 ===
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.canvas.bind("<Button-4>", self.on_wheel)
        self.canvas.bind("<Button-5>", self.on_wheel)
        self.canvas.bind("<Configure>", lambda e: self.create_overlay())
        
        r = self.root
        r.bind("<Right>", lambda e: self.save())
        r.bind("<Left>", lambda e: self.prev())
        r.bind("<space>", lambda e: self.save())
        r.bind("<r>", lambda e: self.rotate())
        r.bind("<Delete>", lambda e: self.trash())
        r.bind("<Control-z>", lambda e: self.undo())
        r.bind("<Control-t>", lambda e: self.open_trash())
        r.bind("<Escape>", lambda e: self.close_result_overlay()) 
        
        r.bind("<Alt-Up>",    lambda e: self.adjust_box_size(0, -10))
        r.bind("<Alt-Down>",  lambda e: self.adjust_box_size(0, 10))
        r.bind("<Alt-Left>",  lambda e: self.adjust_box_size(-10, 0))
        r.bind("<Alt-Right>", lambda e: self.adjust_box_size(10, 0))

    def open_explorer(self, path):
        try:
            if not os.path.exists(path): os.makedirs(path)
            os.startfile(path)
        except Exception as e: messagebox.showerror("错误", f"无法打开文件夹:\n{e}")

    def adjust_box_size(self, dw, dh):
        self.box_w = max(50, self.box_w + dw)
        self.box_h = max(50, self.box_h + dh)
        
        if self.fixed_target_size:
            self.fixed_target_size = None
            if self.target_ratio_str.get() != "自定义...":
                self.target_ratio_str.set("自定义...")
        
        self.create_overlay()
        self.fix_pos()
        self.draw()
        self.update_resolution_label()

    def on_ratio_change(self, event=None):
        val = self.target_ratio_str.get()
        if val == "自定义...":
            inp = simpledialog.askstring("自定义", "输入格式支持:\n - 512x512 (锁定输出分辨率)\n - 21:9 (仅锁定比例)\n\n支持符号: x, *, 空格, 逗号", parent=self.root)
            if not inp:
                self.target_ratio_str.set(self.previous_ratio)
                return
            clean_inp = re.sub(r'[^\d\.]+', 'x', inp).strip('x')
            try:
                parts = clean_inp.split('x')
                if len(parts) != 2: raise ValueError
                w, h = float(parts[0]), float(parts[1])
                if w > 30 or h > 30:
                    self.fixed_target_size = (int(w), int(h))
                    ratio = w / h
                    base_max = config.CROP_BOX_SIZE * 1.5
                    scale_factor = base_max / max(w, h)
                    if scale_factor < 1:
                        self.box_w = w * scale_factor
                        self.box_h = h * scale_factor
                    else:
                        base = config.CROP_BOX_SIZE
                        if ratio >= 1: self.box_w = base; self.box_h = base/ratio
                        else: self.box_h = base; self.box_w = base*ratio
                else:
                    self.fixed_target_size = None
                    ratio = w / h
                    base = config.CROP_BOX_SIZE
                    if ratio >= 1: self.box_w = base; self.box_h = base / ratio
                    else: self.box_h = base; self.box_w = base * ratio
                
                self.previous_ratio = "自定义..."
                self.update_box_shape(force_render=True)
                if self.display_image: self.fix_pos(); self.draw()
            except:
                messagebox.showwarning("格式错误", "无法解析输入。\n请尝试: 512x512 或 16:9")
                self.target_ratio_str.set(self.previous_ratio)
        else:
            self.fixed_target_size = None
            self.previous_ratio = val
            self.update_box_shape(force_render=True)
            if self.display_image: self.fix_pos(); self.draw()

    def update_box_shape(self, force_render=False):
        ratio_str = self.target_ratio_str.get()
        if ratio_str == "自定义...": pass
        else:
            try:
                w, h = map(float, ratio_str.split(":"))
                ratio = w / h
                base = config.CROP_BOX_SIZE
                if ratio >= 1: self.box_w = base; self.box_h = base / ratio
                else: self.box_h = base; self.box_w = base * ratio
            except: pass
        if force_render: self.create_overlay()

    def update_resolution_label(self):
        if self.scale <= 0: return
        current_res_w = int(self.box_w / self.scale)
        current_res_h = int(self.box_h / self.scale)
        if self.fixed_target_size:
            target_w, target_h = self.fixed_target_size
            self.l_crop_res.config(text=f"锁定: {target_w} x {target_h}", fg="#00CCFF")
            if current_res_w < target_w * 0.95:
                if self.use_ai_upscale.get() and HAS_AI: self.l_warning.config(text="✨ AI 将介入增强画质", fg="#4EC9B0")
                else:
                    ratio = target_w / current_res_w
                    self.l_warning.config(text=f"⚠️ 注意: 正在放大 {ratio:.1f}倍", fg="#FF5555")
            else: self.l_warning.config(text="", fg="#1E1E1E")
        else:
            self.l_crop_res.config(text=f"{current_res_w} x {current_res_h}", fg="#4CAF50")
            self.l_warning.config(text="", fg="#1E1E1E")

    def full_refresh(self, check_changes=False):
        try:
            items = os.listdir(config.INPUT_ROOT)
            folders = [d for d in items if os.path.isdir(os.path.join(config.INPUT_ROOT, d))]
            folders.sort()
            display_list = ["[ 根目录 ]"] + folders
            self.combo_dir['values'] = display_list
            if self.combo_dir.get() not in display_list: self.combo_dir.current(0)
        except: 
            self.combo_dir['values'] = ["[ 根目录 ]"]
            self.combo_dir.current(0)
        self.reload_images(check_changes=check_changes)

    def reload_images(self, check_changes=False):
        self.last_deleted_info = None
        selection = self.current_subfolder.get()
        current_focus = None
        if self.image_list and self.current_index < len(self.image_list): current_focus = self.image_list[self.current_index]
        
        if selection == "[ 根目录 ]" or not selection:
            self.curr_in = config.INPUT_ROOT
            self.curr_out = config.OUTPUT_ROOT
            self.curr_trash = config.TRASH_ROOT
            self.l_mode.config(text="根目录", fg="white")
            self.link_open_in.config(text="📂 源: [ 根目录 ]")
            self.link_open_out.config(text="💾 存: [ save_image ]")
        else:
            self.curr_in = os.path.join(config.INPUT_ROOT, selection)
            self.curr_out = os.path.join(config.OUTPUT_ROOT, selection)
            self.curr_trash = os.path.join(config.TRASH_ROOT, selection)
            self.l_mode.config(text=f"子文件夹: {selection}", fg="#4CAF50")
            display_name = selection if len(selection) < 15 else selection[:12]+"..."
            self.link_open_in.config(text=f"📂 源: [ {display_name} ]")
            self.link_open_out.config(text=f"💾 存: [ {display_name} ]")

        config.SAVE_TRASH_ROOT = os.path.join(config.BASE_DIR, 'trash_bin_save') 
        for d in [self.curr_out, self.curr_trash, config.SAVE_TRASH_ROOT]: 
            if not os.path.exists(d): os.makedirs(d)

        disk_files = []
        if os.path.exists(self.curr_in):
            disk_files = sorted([f for f in os.listdir(self.curr_in) if f.lower().endswith(('.jpg','.png','.webp','.bmp','.tif','.jpeg'))])
        
        jump = False
        if check_changes and self.image_list:
            old_set = set(self.image_list)
            disk_set = set(disk_files)
            added = list(disk_set - old_set)
            added.sort()
            kept = [f for f in self.image_list if f in disk_set]
            self.image_list = kept + added
            if added:
                new_idx = len(kept)
                if messagebox.askyesno("新文件", f"发现 {len(added)} 张新图，是否跳转？"):
                    self.current_index = new_idx
                    jump = True
        else:
            self.image_list = disk_files
            self.current_index = 0

        if not jump:
            if current_focus and current_focus in self.image_list: self.current_index = self.image_list.index(current_focus)
            else: self.current_index = 0

        if self.image_list: self.load_image()
        else: self.reset_canvas()

    def reset_canvas(self):
        self.original_image = None; self.display_image = None
        self.canvas.delete("img")
        self.l_name.config(text="[无图片]"); self.l_prog.config(text="-- / --")
        self.l_size.config(text="--"); self.l_crop_res.config(text="-- x --")
        self.clear_preview()

    def load_image(self):
        if not self.image_list: return
        if self.current_index >= len(self.image_list):
            if len(self.image_list) > 0:
                self.current_index = len(self.image_list) - 1
                self.refresh_preview_area()
                messagebox.showinfo("完成", "列表结束")
            else: self.reset_canvas()
            return
        
        fname = self.image_list[self.current_index]
        try:
            self.original_image = Image.open(os.path.join(self.curr_in, fname)).convert('RGB')
            self.rotation = 0
            self.update_box_shape(force_render=False) 
            self.create_overlay() 
            self.update_display()
            self.l_name.config(text=fname)
            self.l_prog.config(text=f"{self.current_index+1} / {len(self.image_list)}")
            self.l_size.config(text=f"{self.original_image.width} x {self.original_image.height}")
            self.refresh_preview_area()
        except Exception as e:
            print(f"Error: {e}"); self.current_index += 1; self.load_image()

    def update_display(self):
        if not self.original_image: return
        if self.rotation == 0: self.display_image = self.original_image.copy()
        else: self.display_image = self.original_image.rotate(self.rotation, expand=True)
        w, h = self.display_image.size
        
        if self.box_w > 0 and self.box_h > 0: self.min_scale = max(self.box_w/w, self.box_h/h)
        else: self.min_scale = 1.0
        self.scale = self.min_scale
        self.img_x = self.box_cx - (int(w*self.scale)//2)
        self.img_y = self.box_cy - (int(h*self.scale)//2)
        self.fix_pos() 
        self.draw()

    def create_overlay(self):
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10: cw = config.WIN_WIDTH - 260; ch = config.WIN_HEIGHT
        self.box_cx, self.box_cy = cw // 2, ch // 2
        mask = Image.new('RGBA', (cw, ch), (0, 0, 0, config.MASK_OPACITY))
        r_w = self.box_w // 2; r_h = self.box_h // 2
        self.box_x1 = self.box_cx - r_w; self.box_y1 = self.box_cy - r_h
        self.box_x2 = self.box_cx + r_w; self.box_y2 = self.box_cy + r_h
        draw = ImageDraw.Draw(mask)
        draw.rectangle([self.box_x1, self.box_y1, self.box_x2, self.box_y2], fill=(0,0,0,0), outline="#00FF00", width=2)
        mask.paste((0,0,0,0), (int(self.box_x1), int(self.box_y1), int(self.box_x2), int(self.box_y2)))
        if self.show_grid.get():
            gc = (255,255,255,80)
            step_w = self.box_w / 3; step_h = self.box_h / 3
            for i in range(1,3):
                draw.line([(self.box_x1+i*step_w, self.box_y1), (self.box_x1+i*step_w, self.box_y2)], fill=gc)
                draw.line([(self.box_x1, self.box_y1+i*step_h), (self.box_x2, self.box_y1+i*step_h)], fill=gc)
        self.tk_mask = ImageTk.PhotoImage(mask)
        self.canvas.delete("mask")
        self.canvas.create_image(0, 0, image=self.tk_mask, anchor=tk.NW, tags="mask")
        self.canvas.tag_raise("mask")

    def fix_pos(self):
        if not self.display_image: return
        w = self.display_image.width * self.scale
        h = self.display_image.height * self.scale
        if w < self.box_w: self.scale = self.box_w / self.display_image.width; w = self.box_w
        if h < self.box_h: self.scale = max(self.scale, self.box_h / self.display_image.height); h = self.display_image.height * self.scale
        if self.img_x > self.box_x1: self.img_x = self.box_x1
        if self.img_x + w < self.box_x2: self.img_x = self.box_x2 - w
        if self.img_y > self.box_y1: self.img_y = self.box_y1
        if self.img_y + h < self.box_y2: self.img_y = self.box_y2 - h

    # === 关键性能优化：动态画质调节 + 视口裁剪 ===
    def draw(self):
        if not self.display_image: return
        
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        w = int(self.display_image.width * self.scale)
        h = int(self.display_image.height * self.scale)
        
        # 优化策略：
        # 1. 正在拖拽中 (is_moving_action=True) -> 强制 NEAREST (极速)
        # 2. 图片极大且放大中 -> 视口裁剪 + NEAREST
        # 3. 其他情况 -> BILINEAR (平滑)
        
        use_nearest = False
        PERFORMANCE_LIMIT = 2000 * 2000 # 400万像素阈值
        
        if self.is_moving_action:
            # 拖拽中，为了跟手，一律用最近邻
            use_nearest = True
        elif (w * h > PERFORMANCE_LIMIT) and (self.scale > 1.2):
            # 虽然没拖拽，但图太大了，为了防止渲染卡顿，也用最近邻（看细节更清晰）
            use_nearest = True
            
        try:
            # === 视口裁剪逻辑 ===
            vis_x1 = max(0, self.img_x)
            vis_y1 = max(0, self.img_y)
            vis_x2 = min(cw, self.img_x + w)
            vis_y2 = min(ch, self.img_y + h)
            
            if vis_x2 <= vis_x1 or vis_y2 <= vis_y1:
                self.canvas.delete("img")
                return

            # 映射回原图坐标
            src_x1 = (vis_x1 - self.img_x) / self.scale
            src_y1 = (vis_y1 - self.img_y) / self.scale
            src_x2 = (vis_x2 - self.img_x) / self.scale
            src_y2 = (vis_y2 - self.img_y) / self.scale
            
            crop_box = (int(src_x1), int(src_y1), int(src_x2) + 1, int(src_y2) + 1)
            part = self.display_image.crop(crop_box)
            
            dest_w = int(vis_x2 - vis_x1)
            dest_h = int(vis_y2 - vis_y1)
            
            # 根据策略选择算法
            algo = Image.Resampling.NEAREST if use_nearest else Image.Resampling.BILINEAR
            resized = part.resize((dest_w, dest_h), algo)
            
            self.tk_img = ImageTk.PhotoImage(resized)
            self.canvas.delete("img")
            self.canvas.create_image(vis_x1, vis_y1, image=self.tk_img, anchor=tk.NW, tags="img")
            self.canvas.tag_lower("img", "mask")
            self.update_resolution_label()
            
        except Exception as e:
            pass

    def on_down(self, e): 
        self.lx, self.ly = e.x, e.y
        self.is_moving_action = True # 开始拖拽

    def on_release(self, e):
        # 鼠标松开，恢复高质量渲染
        self.is_moving_action = False
        self.draw() # 触发一次重绘，变清晰

    def on_drag(self, e):
        self.img_x += e.x - self.lx; self.img_y += e.y - self.ly
        self.lx, self.ly = e.x, e.y
        self.fix_pos()
        self.draw()

    def on_wheel(self, e):
        self.is_moving_action = True # 滚轮也是一种“动”
        f = 1.1 if (e.num==4 or e.delta>0) else 0.9
        if self.display_image:
             w, h = self.display_image.size
             self.min_scale = max(self.box_w/w, self.box_h/h)
        ns = max(self.scale * f, self.min_scale)
        self.img_x = e.x - (e.x - self.img_x) * (ns/self.scale)
        self.img_y = e.y - (e.y - self.img_y) * (ns/self.scale)
        self.scale = ns
        self.fix_pos()
        self.draw()
        
        # 滚轮停止检测比较麻烦，这里用定时器延时重置
        # 如果 200ms 内没有新的滚轮事件，就认为停止了
        if hasattr(self, '_wheel_timer'): self.root.after_cancel(self._wheel_timer)
        self._wheel_timer = self.root.after(200, self.on_wheel_stop)

    def on_wheel_stop(self):
        self.is_moving_action = False
        self.draw()

    def rotate(self):
        if self.original_image: 
            self.rotation = (self.rotation-90)%360
            self.update_display()
            
    def prev(self):
        if self.current_index>0: self.current_index-=1; self.load_image()
    
    def save(self):
        if not self.image_list or self.current_index >= len(self.image_list): return
        if self.is_processing: return 
        
        rx = (self.box_x1 - self.img_x) / self.scale
        ry = (self.box_y1 - self.img_y) / self.scale
        rw = self.box_w / self.scale
        rh = self.box_h / self.scale
        crop_box = (rx, ry, rx+rw, ry+rh)
        
        needs_ai = False
        if self.fixed_target_size and self.use_ai_upscale.get() and HAS_AI:
            t_w, t_h = self.fixed_target_size
            crop_w = rw
            crop_h = rh
            if t_w > crop_w or t_h > crop_h:
                needs_ai = True

        if needs_ai:
            self.is_processing = True
            self.show_loading("AI 正在努力放大中...")
            threading.Thread(target=self.run_save_task, args=(crop_box, True)).start()
        else:
            self.run_save_task(crop_box, False)

    def run_save_task(self, crop_box, use_ai):
        try:
            crop = self.display_image.crop(crop_box)
            if self.fixed_target_size:
                target_w, target_h = self.fixed_target_size
                if use_ai:
                    upscaler = get_upscaler()
                    if upscaler and upscaler.is_ready:
                        high_res = upscaler.process(crop)
                        crop = high_res.resize((target_w, target_h), Image.Resampling.LANCZOS)
                        print("[Info] AI Upscale Success")
                    else:
                        crop = crop.resize((target_w, target_h), Image.Resampling.LANCZOS)
                else:
                    crop = crop.resize((target_w, target_h), Image.Resampling.LANCZOS)
            
            name = os.path.splitext(self.image_list[self.current_index])[0] + ".jpg"
            save_path = os.path.join(self.curr_out, name)
            crop.save(save_path, quality=98, subsampling=0)
            print(f"Saved: {name}")
            self.root.after(0, self.on_save_complete)
        except Exception as e:
            print(f"Save Error: {e}")
            self.root.after(0, lambda: self.on_save_error(str(e)))

    def on_save_complete(self):
        self.hide_loading()
        self.is_processing = False
        self.refresh_preview_area()
        self.current_index += 1
        self.load_image()

    def on_save_error(self, err_msg):
        self.hide_loading()
        self.is_processing = False
        messagebox.showerror("Error", err_msg)

    def show_loading(self, msg):
        self.loading_win = tk.Toplevel(self.root)
        self.loading_win.title("")
        self.loading_win.geometry("300x100")
        x = self.root.winfo_x() + (self.root.winfo_width()//2) - 150
        y = self.root.winfo_y() + (self.root.winfo_height()//2) - 50
        self.loading_win.geometry(f"+{x}+{y}")
        self.loading_win.configure(bg="#2D2D2D")
        self.loading_win.overrideredirect(True) 
        self.loading_win.attributes("-topmost", True)
        tk.Label(self.loading_win, text=msg, fg="white", bg="#2D2D2D", font=("Microsoft YaHei", 12)).pack(expand=True)
        self.loading_win.update()

    def hide_loading(self):
        if hasattr(self, 'loading_win') and self.loading_win:
            self.loading_win.destroy()
            self.loading_win = None

    def trash(self):
        if not self.image_list or self.current_index >= len(self.image_list): return
        fname = self.image_list[self.current_index]
        src = os.path.join(self.curr_in, fname)
        dst = os.path.join(self.curr_trash, fname)
        try:
            shutil.move(src, dst)
            save_p = os.path.join(self.curr_out, os.path.splitext(fname)[0]+".jpg")
            if os.path.exists(save_p): shutil.move(save_p, os.path.join(config.SAVE_TRASH_ROOT, os.path.splitext(fname)[0]+".jpg"))
            self.last_deleted_info = {"name": fname, "src": src, "dst": dst, "idx": self.current_index}
            self.image_list.pop(self.current_index)
            if not self.image_list: self.reset_canvas()
            else: 
                if self.current_index >= len(self.image_list): self.current_index = 0
                self.load_image()
        except Exception as e: messagebox.showerror("Err", str(e))

    def undo(self):
        if not self.last_deleted_info: return
        i = self.last_deleted_info
        if os.path.exists(i['dst']):
            shutil.move(i['dst'], i['src'])
            save_name = os.path.splitext(i['name'])[0]+".jpg"
            save_trash = os.path.join(config.SAVE_TRASH_ROOT, save_name)
            save_real = os.path.join(self.curr_out, save_name)
            if os.path.exists(save_trash): shutil.move(save_trash, save_real)
            self.image_list.insert(i['idx'], i['name'])
            self.current_index = i['idx']
            self.load_image()
            self.last_deleted_info = None

    def open_trash(self):
        viewer = TrashWindow(self.root, self.curr_trash, self.curr_in, self.curr_out, config.SAVE_TRASH_ROOT, self.restore_callback)
        viewer.open()
    def restore_callback(self, filename):
        self.image_list.append(filename); self.image_list.sort(); self.reload_images()
    def show_help(self):
        
        # 创建一个独立的帮助窗口
        help_win = tk.Toplevel(self.root)
        help_win.title("新手指引 & 功能说明")
        help_win.configure(bg="#1E1E1E")
        
        # 设置窗口大小和位置
        w, h = 600, 750
        ws = self.root.winfo_screenwidth()
        hs = self.root.winfo_screenheight()
        x = (ws/2) - (w/2)
        y = (hs/2) - (h/2)
        help_win.geometry(f'{w}x{h}+{int(x)}+{int(y)}')

        # 标题栏
        tk.Label(help_win, text="📸 SmartCropper 使用指南", bg="#1E1E1E", fg="#FFFFFF", 
                 font=("Microsoft YaHei", 16, "bold"), pady=15).pack(fill=tk.X)

        # 使用 Text 组件来实现富文本（多色文字）
        text_area = tk.Text(help_win, bg="#252526", fg="#DDDDDD", font=("Microsoft YaHei", 10), 
                            bd=0, padx=20, pady=20, relief="flat", wrap="word")
        
        # 添加滚动条
        scroll = ttk.Scrollbar(help_win, orient="vertical", command=text_area.yview)
        text_area.configure(yscrollcommand=scroll.set)
        
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # === 定义样式标签 ===
        text_area.tag_config("h1", foreground="#4EC9B0", font=("Microsoft YaHei", 12, "bold"), spacing1=15, spacing3=5)
        text_area.tag_config("h2", foreground="#FFB74D", font=("Microsoft YaHei", 11, "bold"), spacing1=10, spacing3=3)
        text_area.tag_config("key", foreground="#FFFFFF", background="#444444", font=("Consolas", 9, "bold"))
        text_area.tag_config("warn", foreground="#FF5555")
        text_area.tag_config("highlight", foreground="#569CD6") # 蓝色高亮
        text_area.tag_config("normal", spacing1=2, spacing2=2)

        # === 写入内容 ===
         # === 0. 项目介绍 (新增) ===
        text_area.insert(tk.END, "🚀 关于 SmartCropper\n", "h1")
        text_area.insert(tk.END, "这是一个专为 ", "normal")
        text_area.insert(tk.END, "深度学习 (LoRA/SDXL)", "highlight")
        text_area.insert(tk.END, " 训练设计的高效数据集预处理工具。\n相比于传统的 PS 或看图软件，它解决了以下痛点：\n", "normal")
        
        # 使用 bullet point 列表
        points = [
            "拒绝黑边：自动吸附边界，手抖也不会裁出废片。",
            "锁定输出：强制统一分辨率 (如 512x512)，并支持接入放大模型，无需二次缩放。",
            "极速流：左手键盘右手鼠标，单人每小时可处理 1000+ 张图片。",
            "数据安全：独创影子回收站，误删随时可逆。"
        ]
        for p in points:
            text_area.insert(tk.END, f"  • {p}\n", "normal")
            


        # 1. 核心操作
        text_area.insert(tk.END, "\n🎮 1. 核心操作 (3秒上手)\n", "h1")
        text_area.insert(tk.END, "• 移动画布：", "h2")
        text_area.insert(tk.END, " 按住 ", "normal")
        text_area.insert(tk.END, " 鼠标左键 ", "key")
        text_area.insert(tk.END, " 拖拽图片。\n", "normal")
        
        text_area.insert(tk.END, "• 缩放大小：", "h2")
        text_area.insert(tk.END, " 滚动 ", "normal")
        text_area.insert(tk.END, " 鼠标滚轮 ", "key")
        text_area.insert(tk.END, "。\n  (程序会自动吸附边界，永远不会裁出黑边，请放心拖动)\n", "normal")
        
        text_area.insert(tk.END, "• 保存并下一张：", "h2")
        text_area.insert(tk.END, " 按 ", "normal")
        text_area.insert(tk.END, " → ", "key")
        text_area.insert(tk.END, " 或 ", "normal")
        text_area.insert(tk.END, " 空格键 ", "key")
        text_area.insert(tk.END, "。\n", "normal")

        text_area.insert(tk.END, "• 丢弃废片：", "h2")
        text_area.insert(tk.END, " 按 ", "normal")
        text_area.insert(tk.END, " Del ", "key")
        text_area.insert(tk.END, " 移入回收站。\n", "normal")

        # 2. 快捷键大全
        text_area.insert(tk.END, "\n⌨️2. 快捷键速查表\n", "h1")
        
        keys = [
            ("→ / 空格", "保存当前裁剪并跳转下一张"),
            ("←", "返回上一张图片"),
            ("Delete", "删除当前图片 (进回收站)"),
            ("Ctrl + Z", "撤销上一步删除操作"),
            ("Ctrl + T", "打开回收站 (批量管理)"),
            ("R", "旋转图片 (90度)"),
            ("Alt + 方向键", "微调裁剪框大小 (像素级调整)")
        ]
        
        for k, v in keys:
            text_area.insert(tk.END, f" {k:<12} ", "key")
            text_area.insert(tk.END, f" : {v}\n", "normal")

        # 3. 进阶功能
        text_area.insert(tk.END, "\n✨ 3. 进阶功能 (老手必看)\n", "h1")
        
        text_area.insert(tk.END, "🎯 锁定分辨率 (推荐)\n", "h2")
        text_area.insert(tk.END, "在顶部【固定宽高比】选择【自定义...】，输入 ", "normal")
        text_area.insert(tk.END, "512x512", "highlight")
        text_area.insert(tk.END, " 或 ", "normal")
        text_area.insert(tk.END, "1024x1024", "highlight")
        text_area.insert(tk.END, "。\n程序将强制输出指定尺寸，无论你框选多大区域，都会自动缩放。", "normal")
        
        text_area.insert(tk.END, "\n🤖 AI 画质增强\n", "h2")
        text_area.insert(tk.END, "当勾选顶部 ", "normal")
        text_area.insert(tk.END, " ✨ AI修复 ", "key")
        text_area.insert(tk.END, " 且处于【放大】状态时：\n", "normal")
        text_area.insert(tk.END, "保存时会自动调用 ", "normal")
        text_area.insert(tk.END, "4x-UltraSharp", "highlight")
        text_area.insert(tk.END, " 模型进行高清修复。\n适用于：截取全身图中的小脸、把小图放大做训练集。", "normal")

        text_area.insert(tk.END, "\n♻️ 回收站\n", "h2")
        text_area.insert(tk.END, "右上角点击【进入批量模式】可以像资源管理器一样多选文件，进行批量恢复或永久删除。", "normal")

        # 4. 常见问题
        text_area.insert(tk.END, "\n\n❓ 常见问题\n", "h1")
        text_area.insert(tk.END, "Q: 为什么图片拖动时会变马赛克？\n", "h2")
        text_area.insert(tk.END, "A: 这是【极速模式】。为了在大分辨率图片下保持 60帧 丝滑流畅，拖动时会降低渲染质量，松开鼠标立刻恢复高清。", "normal")
        
        text_area.insert(tk.END, "\nQ: 怎么修改保存位置？\n", "h2")
        text_area.insert(tk.END, "A: 程序会自动在当前目录下生成 save_image 文件夹。你可以点击右侧面板底部的绿色链接快速打开。", "normal")

        text_area.configure(state="disabled") # 禁止编辑

    def show_large_result_preview(self, event=None):
        if not self.image_list or self.current_index >= len(self.image_list): return
        filename = self.image_list[self.current_index]
        save_name = os.path.splitext(filename)[0] + ".jpg"
        save_path = os.path.join(self.curr_out, save_name)
        if not os.path.exists(save_path): return
        try:
            self.root.update_idletasks()
            x = self.root.winfo_rootx(); y = self.root.winfo_rooty()
            w = self.root.winfo_width(); h = self.root.winfo_height()
            screenshot = ImageGrab.grab(bbox=(x, y, x+w, y+h))
            dimmer = Image.new('RGBA', (w, h), (0, 0, 0, 210))
            screenshot.paste(dimmer, (0, 0), dimmer)
            self.bg_photo = ImageTk.PhotoImage(screenshot)
        except: self.bg_photo = None
        self.result_overlay = tk.Canvas(self.root, highlightthickness=0, bg="#111111")
        self.result_overlay.place(x=0, y=0, relwidth=1, relheight=1)
        if self.bg_photo: self.result_overlay.create_image(0, 0, image=self.bg_photo, anchor='nw')
        self.result_overlay.bind("<Button-1>", self.close_result_overlay)
        try:
            img = Image.open(save_path)
            w = self.root.winfo_width(); h = self.root.winfo_height()
            display_w = int(w * 0.8); display_h = int(h * 0.8)
            img.thumbnail((display_w, display_h), Image.Resampling.BILINEAR)
            tk_img = ImageTk.PhotoImage(img)
            lbl = tk.Label(self.result_overlay, image=tk_img, bg="black", highlightbackground="#333333", highlightthickness=1)
            lbl.image = tk_img
            self.result_overlay.create_window(w//2, h//2, window=lbl, anchor='center')
            txt_lbl = tk.Label(self.result_overlay, text="已保存结果预览 | 点击任意处或按 ESC 关闭", bg="black", fg="gray", padx=10, pady=5)
            self.result_overlay.create_window(w//2, h - 40, window=txt_lbl, anchor='center')
            lbl.bind("<Button-1>", self.close_result_overlay)
            txt_lbl.bind("<Button-1>", self.close_result_overlay)
        except Exception as e: print(f"Overlay Error: {e}"); self.close_result_overlay()

    def close_result_overlay(self, event=None):
        if self.result_overlay: self.result_overlay.destroy(); self.result_overlay = None; self.bg_photo = None
    
    def refresh_preview_area(self):
        if not self.image_list or self.current_index >= len(self.image_list): self.clear_preview(); return
        filename = self.image_list[self.current_index]
        save_name = os.path.splitext(filename)[0] + ".jpg"
        save_path = os.path.join(self.curr_out, save_name)
        if os.path.exists(save_path):
            try: self.current_preview_pil = Image.open(save_path); self.update_preview_widget()
            except: self.clear_preview()
        else: self.clear_preview()
    
    def clear_preview(self):
        self.current_preview_pil = None; self.l_preview_img.config(image="", text="尚未保存"); self.preview_tk_img = None
    
    def on_preview_resize(self, event): self.update_preview_widget()
    
    def update_preview_widget(self):
        if not self.current_preview_pil: self.l_preview_img.config(image="", text="尚未保存"); return
        w = self.preview_frame.winfo_width(); h = self.preview_frame.winfo_height()
        if w < 10 or h < 10: return 
        try:
            img = self.current_preview_pil.copy()
            img.thumbnail((w-10, h-10), Image.Resampling.BILINEAR)
            self.preview_tk_img = ImageTk.PhotoImage(img)
            self.l_preview_img.config(image=self.preview_tk_img, text="")
        except: pass