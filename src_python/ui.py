# src/ui.py
import os
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox
from datetime import datetime
from .pipeline import PipelineManager
from .config import TESSERACT_CMD

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Telenity Contract Analyzer v2.0 (Modular)")
        self.geometry("1000x750")
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("green")

        self.pipeline = PipelineManager(self.log_message)
        self.folder_path = ""
        self.is_running = False
        
        if not os.path.exists(TESSERACT_CMD):
            messagebox.showerror("Hata", "Tesseract bulunamadı! Config.py'yi kontrol et.")

        self.create_ui()

    def create_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(self.sidebar, text="MODULAR\nANALYZER", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=30)
        
        self.btn_sel = ctk.CTkButton(self.sidebar, text="Klasör Seç", command=self.select_folder)
        self.btn_sel.pack(pady=10)
        self.lbl_path = ctk.CTkLabel(self.sidebar, text="...", text_color="gray")
        self.lbl_path.pack()

        self.btn_reset = ctk.CTkButton(self.sidebar, text="🗑️ Önbelleği Sil", command=self.clear_memory, fg_color="#C62828")
        self.btn_reset.pack(pady=20, fill="x", padx=10)

        self.btn_run = ctk.CTkButton(self.sidebar, text="BAŞLAT", command=self.start, state="disabled", fg_color="green", height=50)
        self.btn_run.pack(side="bottom", pady=30, fill="x", padx=10)

        # Main Area
        self.main = ctk.CTkFrame(self, fg_color="transparent")
        self.main.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main.grid_rowconfigure(1, weight=1)
        self.main.grid_columnconfigure(0, weight=1)

        self.prog = ctk.CTkProgressBar(self.main)
        self.prog.grid(row=0, column=0, sticky="ew", pady=(0,10))
        self.prog.set(0)

        self.log = ctk.CTkTextbox(self.main, font=("Consolas", 12))
        self.log.grid(row=1, column=0, sticky="nsew")

    def log_message(self, msg):
        # UI log updates are handled by pipeline calling this callback
        # But we also want to ensure it goes to the standard logger if not already
        # Actually pipeline calls logger.info AND this callback.
        # So we just update the UI here.
        self.log.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.log.see("end")

    def select_folder(self):
        p = filedialog.askdirectory()
        if p:
            self.folder_path = p
            self.lbl_path.configure(text=f"...{p[-15:]}")
            self.btn_run.configure(state="normal")

    def clear_memory(self):
        if messagebox.askyesno("Onay", "Veritabanı silinsin mi?"):
            self.pipeline.db.clear_memory()
            self.log_message("⚠️ Önbellek temizlendi.")

    def start(self):
        if self.is_running: return
        self.is_running = True
        self.btn_run.configure(state="disabled", text="Çalışıyor...")
        self.pipeline.stop_event.clear()
        threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        try:
            self.pipeline.start_pipeline(self.folder_path, self.prog.set)
        except Exception as e:
            self.log_message(f"KRİTİK HATA: {e}")
        finally:
            self.is_running = False
            self.btn_run.configure(state="normal", text="BAŞLAT")
            messagebox.showinfo("Bitti", "İşlem Tamamlandı.")
