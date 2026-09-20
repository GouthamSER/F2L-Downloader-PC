import os
import sys
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image
import customtkinter as ctk

from storage import SettingsManager, DownloadStorage
from engine import DownloadEngine, resolve_url_info, format_bytes, format_duration

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

# ---- Theme Colors matching F2L Android Liquid Glass Palette ----
BG_COLOR = "#0B0D12"
SURFACE_1 = "#121722"
SURFACE_2 = "#171D2B"
BORDER_COLOR = "#222B3D"
BORDER_ACCENT = "#2979FF"
ACCENT_BLUE = "#2979FF"
ACCENT_HOVER = "#1565C0"
TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#8E99AB"
SUCCESS_GREEN = "#00E676"
ERROR_RED = "#FF5252"
WARN_AMBER = "#FFB300"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class AddDownloadDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_add_callback, default_folder, default_connections):
        super().__init__(parent)
        self.title("Start Download — F2L")
        self.geometry("580x450")
        self.resizable(False, False)
        self.configure(fg_color=BG_COLOR)
        self.transient(parent)
        self.grab_set()

        ico_path = resource_path("app_icon.ico")
        if os.path.exists(ico_path):
            try: self.iconbitmap(ico_path)
            except: pass

        self.on_add_callback = on_add_callback
        self.default_folder = default_folder
        self.default_connections = default_connections

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 580) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 450) // 2
        self.geometry(f"+{x}+{y}")

        self._probe_thread = None
        self._build_ui()

    def _build_ui(self):
        container = ctk.CTkFrame(self, fg_color=SURFACE_1, corner_radius=16, border_width=1, border_color=BORDER_COLOR)
        container.pack(fill="both", expand=True, padx=20, pady=20)

        # Header with Logo
        head_frame = ctk.CTkFrame(container, fg_color="transparent")
        head_frame.pack(fill="x", padx=20, pady=(18, 12))

        logo_path = resource_path("f2l_logo.png")
        if os.path.exists(logo_path):
            try:
                pil_logo = Image.open(logo_path)
                self.logo_img = ctk.CTkImage(light_image=pil_logo, dark_image=pil_logo, size=(28, 28))
                ctk.CTkLabel(head_frame, image=self.logo_img, text="").pack(side="left", padx=(0, 10))
            except Exception:
                pass

        title_lbl = ctk.CTkLabel(head_frame, text="Add New Download", font=ctk.CTkFont(size=18, weight="bold"), text_color=TEXT_PRIMARY)
        title_lbl.pack(side="left")

        # URL Input
        ctk.CTkLabel(container, text="Download Link (HTTP / HTTPS)", font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_SECONDARY).pack(anchor="w", padx=20)
        url_frame = ctk.CTkFrame(container, fg_color="transparent")
        url_frame.pack(fill="x", padx=20, pady=(4, 10))

        self.url_entry = ctk.CTkEntry(url_frame, placeholder_text="Paste your download link here...", height=38, fg_color=SURFACE_2, border_color=BORDER_COLOR)
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.url_entry.bind("<KeyRelease>", self._on_url_typed)

        paste_btn = ctk.CTkButton(url_frame, text="📋 Paste", width=80, height=38, fg_color=SURFACE_2, hover_color=BORDER_COLOR, command=self._paste_clipboard)
        paste_btn.pack(side="right")

        # Filename Input + Detection Status
        fn_header = ctk.CTkFrame(container, fg_color="transparent")
        fn_header.pack(fill="x", padx=20)
        ctk.CTkLabel(fn_header, text="File Name", font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_SECONDARY).pack(side="left")
        self.status_lbl = ctk.CTkLabel(fn_header, text="", font=ctk.CTkFont(size=11), text_color=ACCENT_BLUE)
        self.status_lbl.pack(side="right")

        self.fn_entry = ctk.CTkEntry(container, placeholder_text="Detected automatically or type custom name...", height=38, fg_color=SURFACE_2, border_color=BORDER_COLOR)
        self.fn_entry.pack(fill="x", padx=20, pady=(4, 12))

        # Folder picker
        ctk.CTkLabel(container, text="Save Location", font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_SECONDARY).pack(anchor="w", padx=20)
        folder_frame = ctk.CTkFrame(container, fg_color="transparent")
        folder_frame.pack(fill="x", padx=20, pady=(4, 12))

        self.folder_entry = ctk.CTkEntry(folder_frame, height=38, fg_color=SURFACE_2, border_color=BORDER_COLOR)
        self.folder_entry.insert(0, self.default_folder)
        self.folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        browse_btn = ctk.CTkButton(folder_frame, text="Browse…", width=85, height=38, fg_color=SURFACE_2, hover_color=BORDER_COLOR, command=self._browse_folder)
        browse_btn.pack(side="right")

        # Connection threads & Auto start
        conn_frame = ctk.CTkFrame(container, fg_color="transparent")
        conn_frame.pack(fill="x", padx=20, pady=(2, 14))

        ctk.CTkLabel(conn_frame, text="Threads:", font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 8))
        self.conn_combo = ctk.CTkComboBox(conn_frame, values=["2", "4", "6", "8", "16"], width=85, height=32, fg_color=SURFACE_2, border_color=BORDER_COLOR, button_color=ACCENT_BLUE)
        self.conn_combo.set(str(self.default_connections))
        self.conn_combo.pack(side="left", padx=(0, 16))

        self.auto_start_var = ctk.BooleanVar(value=True)
        auto_chk = ctk.CTkCheckBox(conn_frame, text="Start download immediately", variable=self.auto_start_var, font=ctk.CTkFont(size=12), fg_color=ACCENT_BLUE, hover_color=ACCENT_HOVER)
        auto_chk.pack(side="left")

        # Action Buttons (Clean & Clear Start Download Button)
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(10, 14))

        cancel_btn = ctk.CTkButton(btn_frame, text="Cancel", width=95, height=42, fg_color="transparent", border_width=1, border_color=BORDER_COLOR, hover_color=SURFACE_2, text_color=TEXT_SECONDARY, command=self.destroy)
        cancel_btn.pack(side="right", padx=(10, 0))

        # PROMINENT, CLEAR "START DOWNLOAD" BUTTON
        self.start_btn = ctk.CTkButton(
            btn_frame,
            text="⬇  Start Download",
            width=180,
            height=42,
            fg_color=ACCENT_BLUE,
            hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=8,
            command=self._confirm
        )
        self.start_btn.pack(side="right")

    def _on_url_typed(self, event=None):
        url = self.url_entry.get().strip()
        if url.startswith("http://") or url.startswith("https://"):
            self._trigger_probe(url)

    def _paste_clipboard(self):
        try:
            txt = self.clipboard_get().strip()
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, txt)
            if txt.startswith("http://") or txt.startswith("https://"):
                self._trigger_probe(txt)
        except Exception:
            pass

    def _trigger_probe(self, url):
        self.status_lbl.configure(text="🔍 Detecting file name…")
        def run():
            name, total, _ = resolve_url_info(url)
            def update():
                if self.winfo_exists():
                    if name:
                        self.fn_entry.delete(0, "end")
                        self.fn_entry.insert(0, name)
                        sz_str = f" ({format_bytes(total)})" if total > 0 else ""
                        self.status_lbl.configure(text=f"✓ Detected{sz_str}", text_color=SUCCESS_GREEN)
                    else:
                        self.status_lbl.configure(text="")
            self.after(0, update)
        threading.Thread(target=run, daemon=True).start()

    def _browse_folder(self):
        chosen = filedialog.askdirectory(initialdir=self.folder_entry.get())
        if chosen:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, chosen)

    def _confirm(self):
        url = self.url_entry.get().strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            messagebox.showerror("Invalid URL", "Please enter a valid HTTP or HTTPS download link.")
            return

        folder = self.folder_entry.get().strip()
        if not folder or not os.path.exists(folder):
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception as e:
                messagebox.showerror("Invalid Folder", f"Cannot create folder:\n{e}")
                return

        filename = self.fn_entry.get().strip()
        connections = int(self.conn_combo.get())
        auto_start = self.auto_start_var.get()

        self.on_add_callback(url, folder, filename if filename else None, connections, auto_start)
        self.destroy()


class F2LApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("F2L Downloader — Fast · Reliable · Simple")
        self.geometry("1020x680")
        self.minsize(840, 520)
        self.configure(fg_color=BG_COLOR)

        # Set Window and Taskbar Icon
        ico_path = resource_path("app_icon.ico")
        if os.path.exists(ico_path):
            try: self.iconbitmap(ico_path)
            except: pass

        self.settings_mgr = SettingsManager()
        self.storage = DownloadStorage()
        self.engine = DownloadEngine()

        self.items = self.storage.load()
        self.active_tab = "All"
        self.card_widgets = {}

        self._build_header()
        self._build_main_area()
        self._refresh_list()

        # Restore downloads on startup
        if self.settings_mgr.get("auto_start", True):
            for item in self.items:
                if item.get("status") == "DOWNLOADING":
                    self._start_item(item)

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=SURFACE_1, height=72, corner_radius=0, border_width=1, border_color=BORDER_COLOR)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        # Brand & Real APK Logo
        brand_frame = ctk.CTkFrame(header, fg_color="transparent")
        brand_frame.pack(side="left", padx=24, pady=14)

        logo_path = resource_path("f2l_logo.png")
        if os.path.exists(logo_path):
            try:
                pil_logo = Image.open(logo_path)
                self.head_logo_img = ctk.CTkImage(light_image=pil_logo, dark_image=pil_logo, size=(38, 38))
                logo_lbl = ctk.CTkLabel(brand_frame, image=self.head_logo_img, text="")
                logo_lbl.pack(side="left", padx=(0, 12))
            except Exception:
                pass

        tag_lbl = ctk.CTkLabel(brand_frame, text="F2L Downloader", font=ctk.CTkFont(size=20, weight="bold"), text_color=TEXT_PRIMARY)
        tag_lbl.pack(side="left", padx=(0, 10))

        ver_badge = ctk.CTkLabel(brand_frame, text="PC 3.2.0", font=ctk.CTkFont(size=11, weight="bold"), text_color=ACCENT_BLUE, fg_color=SURFACE_2, corner_radius=6, padx=8, pady=3)
        ver_badge.pack(side="left")

        # Clear, prominent "+ Start Download" button in the top bar
        self.header_add_btn = ctk.CTkButton(
            header,
            text="➕  Start Download",
            width=175,
            height=42,
            fg_color=ACCENT_BLUE,
            hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=8,
            command=self._show_add_dialog
        )
        self.header_add_btn.pack(side="right", padx=24)

    def _build_main_area(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=24, pady=16)

        # Sidebar navigation
        sidebar = ctk.CTkFrame(main, width=200, fg_color=SURFACE_1, corner_radius=14, border_width=1, border_color=BORDER_COLOR)
        sidebar.pack(side="left", fill="y", padx=(0, 16))
        sidebar.pack_propagate(False)

        ctk.CTkLabel(sidebar, text="STATUS", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_SECONDARY).pack(anchor="w", padx=16, pady=(18, 8))

        self.tab_buttons = {}
        for tab_name in ["All", "Active", "Completed", "Failed", "Settings"]:
            btn = ctk.CTkButton(
                sidebar,
                text=tab_name,
                height=38,
                anchor="w",
                fg_color="transparent",
                hover_color=SURFACE_2,
                text_color=TEXT_PRIMARY if tab_name == self.active_tab else TEXT_SECONDARY,
                font=ctk.CTkFont(size=13, weight="bold" if tab_name == self.active_tab else "normal"),
                corner_radius=8,
                command=lambda t=tab_name: self._switch_tab(t)
            )
            btn.pack(fill="x", padx=10, pady=2)
            self.tab_buttons[tab_name] = btn

        # Content area
        self.content_frame = ctk.CTkScrollableFrame(main, fg_color="transparent")
        self.content_frame.pack(side="right", fill="both", expand=True)

    def _switch_tab(self, tab_name):
        self.active_tab = tab_name
        for name, btn in self.tab_buttons.items():
            if name == tab_name:
                btn.configure(fg_color=SURFACE_2, text_color=ACCENT_BLUE, font=ctk.CTkFont(size=13, weight="bold"))
            else:
                btn.configure(fg_color="transparent", text_color=TEXT_SECONDARY, font=ctk.CTkFont(size=13, weight="normal"))

        if tab_name == "Settings":
            self._render_settings()
        else:
            self._refresh_list()

    def _show_add_dialog(self):
        AddDownloadDialog(self, self._add_download, self.settings_mgr.get("download_folder"), self.settings_mgr.get("default_connections"))

    def _add_download(self, url, folder, filename, connections, auto_start):
        task_id = int(time.time() * 1000)
        guessed_name = filename or url.split("/")[-1].split("?")[0] or f"download_{task_id}.bin"

        item = {
            "id": task_id,
            "url": url,
            "file_name": guessed_name,
            "folder": folder,
            "connections": connections,
            "total_bytes": -1,
            "downloaded_bytes": 0,
            "speed": 0,
            "eta": -1,
            "status": "QUEUED" if auto_start else "PAUSED",
            "error": None
        }
        self.items.insert(0, item)
        self.storage.save(self.items)

        if auto_start:
            self._start_item(item)
        self._refresh_list()

    def _start_item(self, item):
        item["status"] = "DOWNLOADING"
        item["error"] = None
        self.storage.save(self.items)

        self.engine.start(
            item,
            on_progress=self._on_progress_cb,
            on_complete=self._on_complete_cb,
            on_error=self._on_error_cb,
            on_name_resolved=self._on_name_resolved_cb
        )

    def _pause_item(self, item):
        self.engine.pause(item["id"])
        item["status"] = "PAUSED"
        item["speed"] = 0
        self.storage.save(self.items)
        self._refresh_list()

    def _delete_item(self, item):
        self.engine.cancel(item["id"])
        self.items = [i for i in self.items if i["id"] != item["id"]]
        self.storage.save(self.items)
        self._refresh_list()

    def _open_file(self, item):
        filepath = os.path.join(item["folder"], item["file_name"])
        if os.path.exists(filepath):
            os.startfile(filepath)
        else:
            messagebox.showwarning("File Missing", "The file could not be found at its saved location.")

    def _open_folder(self, item):
        if os.path.exists(item["folder"]):
            os.startfile(item["folder"])

    def _on_name_resolved_cb(self, task_id, real_name):
        for item in self.items:
            if item["id"] == task_id:
                item["file_name"] = real_name
                break
        self.storage.save(self.items)
        def update_ui():
            if task_id in self.card_widgets:
                self.card_widgets[task_id]["name_lbl"].configure(text=real_name)
        self.after(0, update_ui)

    def _on_progress_cb(self, task_id, downloaded, total, speed, eta):
        for item in self.items:
            if item["id"] == task_id:
                item["downloaded_bytes"] = downloaded
                item["total_bytes"] = total
                item["speed"] = speed
                item["eta"] = eta
                item["status"] = "DOWNLOADING"
                break
        self.after(0, self._update_card_ui, task_id)

    def _on_complete_cb(self, task_id):
        for item in self.items:
            if item["id"] == task_id:
                item["status"] = "COMPLETED"
                item["speed"] = 0
                item["eta"] = 0
                item["downloaded_bytes"] = item["total_bytes"] if item["total_bytes"] > 0 else item["downloaded_bytes"]
                break
        self.storage.save(self.items)
        self.after(0, self._refresh_list)

    def _on_error_cb(self, task_id, error_msg):
        for item in self.items:
            if item["id"] == task_id:
                item["status"] = "FAILED"
                item["error"] = error_msg
                item["speed"] = 0
                break
        self.storage.save(self.items)
        self.after(0, self._refresh_list)

    def _update_card_ui(self, task_id):
        item = next((i for i in self.items if i["id"] == task_id), None)
        if not item or task_id not in self.card_widgets:
            return

        w = self.card_widgets[task_id]
        total = item["total_bytes"]
        down = item["downloaded_bytes"]
        speed = item["speed"]
        eta = item["eta"]

        pct = 0
        if total > 0:
            pct = min(1.0, down / total)
            w["progress"].set(pct)
            w["percent_lbl"].configure(text=f"{int(pct * 100)}%")
            w["bytes_lbl"].configure(text=f"•  {format_bytes(down)} of {format_bytes(total)}")
        else:
            w["progress"].set(0)
            w["percent_lbl"].configure(text="--%")
            w["bytes_lbl"].configure(text=f"•  {format_bytes(down)}")

        if speed > 0:
            w["speed_lbl"].configure(text=f"{format_bytes(speed)}/s")
        else:
            w["speed_lbl"].configure(text="-- B/s")

        w["eta_lbl"].configure(text=f"ETA {format_duration(eta)}" if eta > 0 else "")

    def _refresh_list(self):
        if self.active_tab == "Settings":
            return

        for widget in self.content_frame.winfo_children():
            widget.destroy()

        filtered = []
        for it in self.items:
            st = it.get("status")
            if self.active_tab == "All":
                filtered.append(it)
            elif self.active_tab == "Active" and st in ["DOWNLOADING", "QUEUED", "PAUSED"]:
                filtered.append(it)
            elif self.active_tab == "Completed" and st == "COMPLETED":
                filtered.append(it)
            elif self.active_tab == "Failed" and st == "FAILED":
                filtered.append(it)

        if not filtered:
            empty_box = ctk.CTkFrame(self.content_frame, fg_color=SURFACE_1, corner_radius=14, height=220, border_width=1, border_color=BORDER_COLOR)
            empty_box.pack(fill="x", expand=True, pady=40)
            ctk.CTkLabel(empty_box, text="No downloads in this section", font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT_SECONDARY).pack(expand=True)
            return

        self.card_widgets = {}
        for item in filtered:
            self._render_download_card(item)

    def _render_download_card(self, item):
        card = ctk.CTkFrame(self.content_frame, fg_color=SURFACE_1, corner_radius=14, border_width=1, border_color=BORDER_COLOR)
        card.pack(fill="x", pady=6)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=16)

        # Top row: Name, status badge, action buttons
        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")

        # File Icon / Category badge
        icon_box = ctk.CTkFrame(top, width=36, height=36, fg_color=SURFACE_2, corner_radius=8)
        icon_box.pack(side="left", padx=(0, 10))
        icon_box.pack_propagate(False)
        ctk.CTkLabel(icon_box, text="📁", font=ctk.CTkFont(size=16)).pack(expand=True)

        name_lbl = ctk.CTkLabel(top, text=item["file_name"], font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT_PRIMARY, anchor="w")
        name_lbl.pack(side="left", fill="x", expand=True)

        st = item["status"]
        st_color = SUCCESS_GREEN if st == "COMPLETED" else ERROR_RED if st == "FAILED" else WARN_AMBER if st == "PAUSED" else ACCENT_BLUE
        st_badge = ctk.CTkLabel(top, text=st, font=ctk.CTkFont(size=11, weight="bold"), text_color=st_color, fg_color=SURFACE_2, corner_radius=6, padx=10, pady=3)
        st_badge.pack(side="left", padx=10)

        # Action Buttons
        if st == "DOWNLOADING":
            pause_btn = ctk.CTkButton(top, text="⏸ Pause", width=75, height=30, fg_color=SURFACE_2, hover_color=BORDER_COLOR, text_color=TEXT_PRIMARY, font=ctk.CTkFont(size=12, weight="bold"), command=lambda i=item: self._pause_item(i))
            pause_btn.pack(side="right", padx=4)
        elif st in ["PAUSED", "FAILED"]:
            resume_btn = ctk.CTkButton(top, text="▶ Resume" if st == "PAUSED" else "↺ Retry", width=85, height=30, fg_color=ACCENT_BLUE, hover_color=ACCENT_HOVER, font=ctk.CTkFont(size=12, weight="bold"), command=lambda i=item: self._start_item(i))
            resume_btn.pack(side="right", padx=4)
        elif st == "COMPLETED":
            open_btn = ctk.CTkButton(top, text="Open File", width=80, height=30, fg_color=ACCENT_BLUE, hover_color=ACCENT_HOVER, font=ctk.CTkFont(size=12, weight="bold"), command=lambda i=item: self._open_file(i))
            open_btn.pack(side="right", padx=4)

            folder_btn = ctk.CTkButton(top, text="Folder", width=65, height=30, fg_color=SURFACE_2, hover_color=BORDER_COLOR, font=ctk.CTkFont(size=12), command=lambda i=item: self._open_folder(i))
            folder_btn.pack(side="right", padx=4)

        del_btn = ctk.CTkButton(top, text="✕", width=30, height=30, fg_color="transparent", hover_color=SURFACE_2, text_color=ERROR_RED, font=ctk.CTkFont(size=14, weight="bold"), command=lambda i=item: self._delete_item(i))
        del_btn.pack(side="right", padx=(4, 0))

        # Progress bar
        total = item.get("total_bytes", -1)
        down = item.get("downloaded_bytes", 0)
        pct = (down / total) if total > 0 else (1.0 if st == "COMPLETED" else 0.0)

        prog_bar = ctk.CTkProgressBar(inner, height=9, corner_radius=4, fg_color=SURFACE_2, progress_color=st_color)
        prog_bar.set(pct)
        prog_bar.pack(fill="x", pady=(12, 8))

        # Bottom row: stats (clean spacing & clear metrics)
        bot = ctk.CTkFrame(inner, fg_color="transparent")
        bot.pack(fill="x")

        pct_str = f"{int(pct * 100)}%" if total > 0 else ("100%" if st == "COMPLETED" else "--%")
        pct_lbl = ctk.CTkLabel(bot, text=pct_str, font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_PRIMARY)
        pct_lbl.pack(side="left", padx=(0, 6))

        bytes_str = f"•  {format_bytes(down)} of {format_bytes(total)}" if total > 0 else f"•  {format_bytes(down)}"
        bytes_lbl = ctk.CTkLabel(bot, text=bytes_str, font=ctk.CTkFont(size=12), text_color=TEXT_SECONDARY)
        bytes_lbl.pack(side="left", padx=(0, 6))

        threads_lbl = ctk.CTkLabel(bot, text=f"•  {item.get('connections', 8)} threads", font=ctk.CTkFont(size=12), text_color=TEXT_SECONDARY)
        threads_lbl.pack(side="left")

        speed_val = item.get("speed", 0)
        speed_lbl = ctk.CTkLabel(bot, text=f"{format_bytes(speed_val)}/s" if speed_val > 0 else "", font=ctk.CTkFont(size=12, weight="bold"), text_color=ACCENT_BLUE)
        speed_lbl.pack(side="right", padx=(8, 0))

        eta_val = item.get("eta", -1)
        eta_lbl = ctk.CTkLabel(bot, text=f"ETA {format_duration(eta_val)}" if eta_val > 0 else "", font=ctk.CTkFont(size=12), text_color=TEXT_SECONDARY)
        eta_lbl.pack(side="right")

        if item.get("error"):
            err_lbl = ctk.CTkLabel(inner, text=f"Error: {item['error']}", font=ctk.CTkFont(size=11), text_color=ERROR_RED, anchor="w")
            err_lbl.pack(fill="x", pady=(4, 0))

        self.card_widgets[item["id"]] = {
            "name_lbl": name_lbl,
            "progress": prog_bar,
            "percent_lbl": pct_lbl,
            "bytes_lbl": bytes_lbl,
            "speed_lbl": speed_lbl,
            "eta_lbl": eta_lbl
        }

    def _render_settings(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        card = ctk.CTkFrame(self.content_frame, fg_color=SURFACE_1, corner_radius=16, border_width=1, border_color=BORDER_COLOR)
        card.pack(fill="x", expand=True, padx=4, pady=8)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=24, pady=24)

        ctk.CTkLabel(inner, text="Application Settings", font=ctk.CTkFont(size=18, weight="bold"), text_color=TEXT_PRIMARY).pack(anchor="w", pady=(0, 16))

        # Default Folder
        ctk.CTkLabel(inner, text="Default Download Folder", font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_SECONDARY).pack(anchor="w")
        folder_frame = ctk.CTkFrame(inner, fg_color="transparent")
        folder_frame.pack(fill="x", pady=(6, 16))

        folder_entry = ctk.CTkEntry(folder_frame, height=38, fg_color=SURFACE_2, border_color=BORDER_COLOR)
        folder_entry.insert(0, self.settings_mgr.get("download_folder"))
        folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def on_change_folder():
            c = filedialog.askdirectory(initialdir=folder_entry.get())
            if c:
                folder_entry.delete(0, "end")
                folder_entry.insert(0, c)
                self.settings_mgr.set("download_folder", c)

        ctk.CTkButton(folder_frame, text="Browse…", width=80, height=38, fg_color=SURFACE_2, hover_color=BORDER_COLOR, command=on_change_folder).pack(side="right")

        # Default Threads
        ctk.CTkLabel(inner, text="Default Parallel Threads", font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_SECONDARY).pack(anchor="w")
        conn_combo = ctk.CTkComboBox(inner, values=["2", "4", "6", "8", "16"], width=120, height=38, fg_color=SURFACE_2, border_color=BORDER_COLOR, button_color=ACCENT_BLUE)
        conn_combo.set(str(self.settings_mgr.get("default_connections", 8)))
        conn_combo.pack(anchor="w", pady=(6, 16))
        conn_combo.configure(command=lambda v: self.settings_mgr.set("default_connections", int(v)))

        # Auto Start
        auto_var = ctk.BooleanVar(value=self.settings_mgr.get("auto_start", True))
        def on_toggle_auto():
            self.settings_mgr.set("auto_start", auto_var.get())

        auto_chk = ctk.CTkCheckBox(inner, text="Automatically start downloads on addition", variable=auto_var, command=on_toggle_auto, font=ctk.CTkFont(size=13), fg_color=ACCENT_BLUE, hover_color=ACCENT_HOVER)
        auto_chk.pack(anchor="w", pady=(4, 24))

        # About with Logo
        about_frame = ctk.CTkFrame(inner, fg_color=SURFACE_2, corner_radius=12, border_width=1, border_color=BORDER_COLOR)
        about_frame.pack(fill="x", pady=10)

        about_inner = ctk.CTkFrame(about_frame, fg_color="transparent")
        about_inner.pack(fill="x", padx=16, pady=16)

        logo_path = resource_path("f2l_logo.png")
        if os.path.exists(logo_path):
            try:
                pil_logo = Image.open(logo_path)
                self.about_logo_img = ctk.CTkImage(light_image=pil_logo, dark_image=pil_logo, size=(48, 48))
                ctk.CTkLabel(about_inner, image=self.about_logo_img, text="").pack(side="left", padx=(0, 16))
            except Exception:
                pass

        about_text = ctk.CTkFrame(about_inner, fg_color="transparent")
        about_text.pack(side="left", fill="x")
        ctk.CTkLabel(about_text, text="F2L Downloader (PC Edition)", font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT_PRIMARY, anchor="w").pack(anchor="w")
        ctk.CTkLabel(about_text, text="Version 3.2.0 • Fast · Reliable · Simple\nMulti-threaded segmented downloads with Liquid Glass UI.\nDeveloped by Goutham Josh.", font=ctk.CTkFont(size=12), text_color=TEXT_SECONDARY, justify="left", anchor="w").pack(anchor="w", pady=(4, 0))


if __name__ == "__main__":
    app = F2LApp()
    app.mainloop()
