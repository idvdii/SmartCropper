import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageTk, ImageGrab
import os
import shutil
import math

class TrashWindow:
    def __init__(self, root, trash_dir, input_dir, save_dir, save_trash_dir, on_restore_callback):
        self.root = root
        self.trash_dir = trash_dir
        self.input_dir = input_dir
        self.save_dir = save_dir
        self.save_trash_dir = save_trash_dir
        self.on_restore = on_restore_callback
        
        # 窗口状态
        self.trash_win = None
        self.overlay_active = False 
        self.lightbox_index = 0
        
        # 批量模式状态
        self.is_select_mode = False
        self.selected_files = set() 
        self.trash_files = []
        self.trash_thumbnails = [] 
        
        # 动画配置
        self.base_width = 950
        self.drawer_width = 320
        self.anim_running = False

    def open(self):
        if not os.path.exists(self.trash_dir):
            messagebox.showinfo("提示", "回收站是空的")
            return
        self.refresh_file_list()
        if not self.trash_files:
            messagebox.showinfo("提示", "回收站是空的")
            return

        self.trash_win = tk.Toplevel(self.root)
        self.trash_win.title(f"回收站 - {len(self.trash_files)} 张图片")
        self.trash_win.configure(bg="#202020")
        
        # 初始居中
        ws = self.root.winfo_screenwidth()
        hs = self.root.winfo_screenheight()
        h = 700
        x = (ws/2) - (self.base_width/2)
        y = (hs/2) - (h/2)
        self.trash_win.geometry(f'{self.base_width}x{h}+{int(x)}+{int(y)}')
        
        self.trash_win.grab_set() 
        
        self.trash_win.bind("<Escape>", self.on_key_esc)
        self.trash_win.bind("<Left>",   self.on_key_left)
        self.trash_win.bind("<Right>",  self.on_key_right)
        self.trash_win.bind("<Return>", self.on_key_enter)

        self.build_ui()
        self.trash_win.focus_force()

    def refresh_file_list(self):
        if os.path.exists(self.trash_dir):
            self.trash_files = [f for f in os.listdir(self.trash_dir) if f.lower().endswith(('.jpg', '.png', '.jpeg', '.bmp', '.webp'))]
            self.trash_files.sort()
        else:
            self.trash_files = []
        self.selected_files = {f for f in self.selected_files if f in self.trash_files}

    def build_ui(self):
        # Top Bar
        top_bar = tk.Frame(self.trash_win, bg="#2D2D2D", height=50)
        top_bar.pack(side=tk.TOP, fill=tk.X)
        top_bar.pack_propagate(False)
        
        tk.Label(top_bar, text=" 🗑️  回收站资源管理器", fg="#E0E0E0", bg="#2D2D2D", font=("Microsoft YaHei", 11, "bold")).pack(side=tk.LEFT, padx=15)
        
        self.btn_mode = tk.Button(top_bar, text="进入批量选择模式", command=self.toggle_mode_animation,
                                bg="#3E3E42", fg="white", bd=0, padx=15, pady=4, 
                                activebackground="#007ACC", activeforeground="white", cursor="hand2")
        self.btn_mode.pack(side=tk.RIGHT, padx=15, pady=10)

        # Bottom Bar
        self.bottom_bar = tk.Frame(self.trash_win, bg="#1E1E1E", height=60, relief="flat")
        self.bottom_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.bottom_bar.pack_propagate(False)

        tk.Button(self.bottom_bar, text="🗑️ 清空回收站", command=self.clear_all, 
                  bg="#C53030", fg="white", bd=0, padx=15, pady=5, font=("Microsoft YaHei", 9)).pack(side=tk.LEFT, padx=20, pady=12)

        self.batch_actions = tk.Frame(self.bottom_bar, bg="#1E1E1E")
        self.lbl_sel_count = tk.Label(self.batch_actions, text="0", fg="#007ACC", bg="#1E1E1E", font=("Arial", 12, "bold"))
        self.lbl_sel_count.pack(side=tk.LEFT, padx=(0, 10))
        tk.Label(self.batch_actions, text="已选", fg="#666666", bg="#1E1E1E").pack(side=tk.LEFT, padx=(0, 20))

        tk.Button(self.batch_actions, text="批量恢复", command=self.batch_restore, 
                  bg="#388E3C", fg="white", bd=0, padx=15, pady=5).pack(side=tk.LEFT, padx=5)
        tk.Button(self.batch_actions, text="批量删除", command=self.batch_delete, 
                  bg="#D32F2F", fg="white", bd=0, padx=15, pady=5).pack(side=tk.LEFT, padx=5)
        
        # Main Container
        self.main_container = tk.Frame(self.trash_win, bg="#202020")
        self.main_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Grid Panel
        self.grid_panel = tk.Frame(self.main_container, bg="#202020")
        self.grid_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.grid_panel, bg="#202020", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.grid_panel, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = tk.Frame(self.canvas, bg="#202020")
        
        self.scroll_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
        self.trash_win.bind("<Destroy>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

        # Drawer Panel
        self.drawer_panel = tk.Frame(self.main_container, bg="#181818", width=0)
        self.drawer_panel.pack(side=tk.RIGHT, fill=tk.Y)
        self.drawer_panel.pack_propagate(False)

        self.build_drawer_content()
        self.populate_grid()

    def build_drawer_content(self):
        container = tk.Frame(self.drawer_panel, bg="#181818")
        container.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        tk.Label(container, text="DETAILS", bg="#181818", fg="#555555", font=("Arial", 8, "bold"), anchor="w").pack(fill=tk.X)
        
        self.d_preview_frame = tk.Frame(container, bg="#111111", height=240, relief="flat")
        self.d_preview_frame.pack(fill=tk.X, pady=(10, 20))
        self.d_preview_frame.pack_propagate(False)
        
        self.d_img_label = tk.Label(self.d_preview_frame, text="Select an image", bg="#111111", fg="#333333")
        self.d_img_label.pack(expand=True, fill=tk.BOTH)
        
        def row(k):
            f = tk.Frame(container, bg="#181818"); f.pack(fill=tk.X, pady=4)
            tk.Label(f, text=k, bg="#181818", fg="#666666", width=8, anchor="w").pack(side=tk.LEFT)
            l = tk.Label(f, text="--", bg="#181818", fg="#CCCCCC", anchor="w"); l.pack(side=tk.LEFT)
            return l
        
        self.lbl_d_name = row("文件名")
        self.lbl_d_res  = row("分辨率")
        self.lbl_d_size = row("大小")
        
        tk.Label(container, text="提示: 勾选图片后，使用底部按钮进行\n批量操作。", bg="#181818", fg="#444444", justify="left").pack(side=tk.BOTTOM, anchor="w", pady=10)

    # === 动画逻辑 ===
    def toggle_mode_animation(self):
        if self.anim_running: return
        self.is_select_mode = not self.is_select_mode
        self.anim_running = True
        
        target_w = self.base_width + self.drawer_width if self.is_select_mode else self.base_width
        
        if self.is_select_mode:
            self.btn_mode.config(text="退出选择模式", bg="#007ACC")
            self.batch_actions.pack(side=tk.RIGHT, padx=15)
        else:
            self.btn_mode.config(text="进入批量选择模式", bg="#444444")
            self.batch_actions.pack_forget()
            self.selected_files.clear()
            self.refresh_drawer(None)
        
        self.populate_grid()
        self.smooth_resize(target_w)

    def smooth_resize(self, target_w):
        curr_w = self.trash_win.winfo_width()
        diff = target_w - curr_w
        
        if abs(diff) < 2:
            self.trash_win.geometry(f"{target_w}x{self.trash_win.winfo_height()}")
            final_drawer_w = self.drawer_width if self.is_select_mode else 0
            self.drawer_panel.config(width=final_drawer_w)
            self.anim_running = False
            return

        step = math.ceil(abs(diff) * 0.25) 
        if step < 2: step = 2
        
        new_w = curr_w + step if diff > 0 else curr_w - step
        self.trash_win.geometry(f"{new_w}x{self.trash_win.winfo_height()}")
        
        dw = max(0, new_w - self.base_width)
        self.drawer_panel.config(width=dw)
            
        self.trash_win.after(16, lambda: self.smooth_resize(target_w))

    # === 网格交互 ===
    def populate_grid(self):
        for w in self.scroll_frame.winfo_children(): w.destroy()
        self.trash_thumbnails = []
        
        if not self.trash_files:
            tk.Label(self.scroll_frame, text="回收站空空如也", bg="#202020", fg="#666666", font=("Microsoft YaHei", 12)).pack(pady=80)
            return

        cols = 5
        row, col = 0, 0
        
        for idx, fname in enumerate(self.trash_files):
            path = os.path.join(self.trash_dir, fname)
            try:
                img = Image.open(path)
                img.thumbnail((130, 130))
                tk_img = ImageTk.PhotoImage(img)
                self.trash_thumbnails.append(tk_img)
                
                is_sel = fname in self.selected_files
                bg = "#007ACC" if is_sel else "#202020"
                pad = 3 if is_sel else 0
                
                outer = tk.Frame(self.scroll_frame, bg=bg, padx=pad, pady=pad)
                outer.grid(row=row, column=col, padx=12, pady=12)
                
                inner = tk.Frame(outer, bg="#252526")
                inner.pack()
                
                btn = tk.Button(inner, image=tk_img, bg="#252526", bd=0, activebackground="#333333",
                                command=lambda f=fname, i=idx: self.on_item_click(f, i), takefocus=0)
                btn.pack()
                
                t_fg = "white" if is_sel else "#999999"
                trunc_name = fname if len(fname)<10 else fname[:8]+".."
                tk.Label(inner, text=trunc_name, bg="#252526", fg=t_fg, font=("Arial", 8)).pack(fill=tk.X)
                
                col+=1
                if col>=cols: col=0; row+=1
            except: pass
            
        self.update_batch_label()

    def on_item_click(self, fname, idx):
        if self.is_select_mode:
            if fname in self.selected_files:
                self.selected_files.remove(fname)
            else:
                self.selected_files.add(fname)
            self.populate_grid()
            self.refresh_drawer(fname)
        else:
            self.show_lightbox(idx)
            
    def update_batch_label(self):
        if hasattr(self, 'lbl_sel_count'):
            self.lbl_sel_count.config(text=str(len(self.selected_files)))

    def refresh_drawer(self, fname):
        if not fname or fname not in self.selected_files:
            if self.selected_files:
                fname = list(self.selected_files)[-1]
            else:
                self.d_img_label.config(image="", text="Select an image")
                self.lbl_d_name.config(text="--")
                self.lbl_d_res.config(text="--")
                self.lbl_d_size.config(text="--")
                return

        path = os.path.join(self.trash_dir, fname)
        try:
            img = Image.open(path)
            
            # === FIX 1: 先获取原图分辨率 ===
            raw_w, raw_h = img.size
            self.lbl_d_res.config(text=f"{raw_w} x {raw_h}")
            
            # 再制作缩略图
            cw, ch = 280, 220
            img.thumbnail((cw, ch), Image.Resampling.LANCZOS)
            tk_img = ImageTk.PhotoImage(img)
            self.d_img_label.config(image=tk_img, text="")
            self.d_img_label.image = tk_img
            
            self.lbl_d_name.config(text=fname if len(fname)<18 else fname[:15]+"...")
            self.lbl_d_size.config(text=f"{os.path.getsize(path)/1024:.1f} KB")
        except: pass

    # === 批量操作 (Fix: parent=self.trash_win) ===
    def batch_restore(self):
        if not self.selected_files: return
        # FIX: 指定父窗口
        if not messagebox.askyesno("确认", f"恢复选中的 {len(self.selected_files)} 张图片?", parent=self.trash_win): return
        for f in list(self.selected_files):
            self.restore_file(f)
        self.post_action_cleanup()

    def batch_delete(self):
        if not self.selected_files: return
        # FIX: 指定父窗口
        if not messagebox.askyesno("警告", f"永久删除选中的 {len(self.selected_files)} 张图片?", parent=self.trash_win): return
        for f in list(self.selected_files):
            self.delete_permanently(f)
        self.post_action_cleanup()
        
    def post_action_cleanup(self):
        self.selected_files.clear()
        self.refresh_file_list()
        self.populate_grid()
        self.refresh_drawer(None)
        self.trash_win.title(f"回收站 - {len(self.trash_files)} 张图片")

    def clear_all(self):
        # FIX: 指定父窗口
        if messagebox.askyesno("清空", "确定清空回收站吗？操作不可逆。", parent=self.trash_win):
            for f in self.trash_files: self.delete_permanently(f)
            self.post_action_cleanup()

    def restore_file(self, fname):
        try:
            shutil.move(os.path.join(self.trash_dir, fname), os.path.join(self.input_dir, fname))
            s_name = os.path.splitext(fname)[0]+".jpg"
            if os.path.exists(os.path.join(self.save_trash_dir, s_name)):
                shutil.move(os.path.join(self.save_trash_dir, s_name), os.path.join(self.save_dir, s_name))
            if self.on_restore: self.on_restore(fname)
        except: pass

    def delete_permanently(self, fname):
        try:
            os.remove(os.path.join(self.trash_dir, fname))
            s_name = os.path.splitext(fname)[0]+".jpg"
            p = os.path.join(self.save_trash_dir, s_name)
            if os.path.exists(p): os.remove(p)
        except: pass

    # === Lightbox ===
    def show_lightbox(self, idx):
        self.lightbox_index = idx
        self.overlay_active = True
        
        self.trash_win.update()
        try:
            x, y = self.trash_win.winfo_rootx(), self.trash_win.winfo_rooty()
            w, h = self.trash_win.winfo_width(), self.trash_win.winfo_height()
            ss = ImageGrab.grab((x,y,x+w,y+h))
            dim = Image.new('RGBA', (w,h), (0,0,0,210))
            ss.paste(dim, (0,0), dim)
            self.bg_photo = ImageTk.PhotoImage(ss)
        except: self.bg_photo = None
        
        self.overlay = tk.Canvas(self.trash_win, bg="black", highlightthickness=0)
        self.overlay.place(x=0, y=0, relwidth=1, relheight=1)
        if self.bg_photo: self.overlay.create_image(0,0,image=self.bg_photo, anchor="nw")
        
        self.lb_img = tk.Label(self.overlay, bg="black")
        self.overlay.create_window(w//2, h//2, window=self.lb_img)
        
        tk.Label(self.overlay, text="←/→ 切换 | Enter 恢复 | Del 删除 | Esc 关闭", 
                 bg="black", fg="#666666", font=("Arial", 9)).place(relx=0.5, rely=0.9, anchor="center")
        
        self.update_lightbox()
        self.overlay.focus_set()

    def update_lightbox(self):
        if not self.trash_files: self.close_lightbox(); return
        fname = self.trash_files[self.lightbox_index]
        self.trash_win.title(f"预览: {fname}")
        try:
            img = Image.open(os.path.join(self.trash_dir, fname))
            ww, wh = self.trash_win.winfo_width(), self.trash_win.winfo_height()
            img.thumbnail((ww-120, wh-120), Image.Resampling.BILINEAR)
            tk_img = ImageTk.PhotoImage(img)
            self.lb_img.config(image=tk_img)
            self.lb_img.image = tk_img
        except: pass

    def close_lightbox(self):
        self.overlay_active = False
        if hasattr(self, 'overlay'): self.overlay.destroy()
        self.populate_grid()
        self.trash_win.title(f"回收站 - {len(self.trash_files)} 张图片")

    def on_key_esc(self, e):
        if self.overlay_active: self.close_lightbox()
        elif self.is_select_mode: self.toggle_mode_animation()
        else: self.trash_win.destroy()

    def on_key_left(self, e):
        if self.overlay_active: 
            self.lightbox_index = (self.lightbox_index-1)%len(self.trash_files)
            self.update_lightbox()
    def on_key_right(self, e):
        if self.overlay_active: 
            self.lightbox_index = (self.lightbox_index+1)%len(self.trash_files)
            self.update_lightbox()
            
    def on_key_enter(self, e):
        if self.overlay_active:
            f = self.trash_files[self.lightbox_index]
            self.restore_file(f)
            self.trash_files.pop(self.lightbox_index)
            self.refresh_file_list()
            self.populate_grid()
            if self.lightbox_index >= len(self.trash_files): 
                self.lightbox_index = 0
            if not self.trash_files: 
                self.close_lightbox()
            else: 
                self.update_lightbox()