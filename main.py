# main.py
from src_python.ui import App

if __name__ == "__main__":
    try:
        app = App()
        app.mainloop()
    except Exception as e:
        print(f"Başlatma Hatası: {e}")
        input("Kapanmak için Enter'a basın...")
