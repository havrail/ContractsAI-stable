# 🖥️ Desktop App Build Kılavuzu

Tauri ile Windows desktop application oluşturma.

## ✅ Avantajlar

- **Native görünüm** (Windows 11 style)
- **Hızlı başlatma** (web browser'dan 3x hızlı)
- **Küçük boyut** (~5-10 MB vs Electron 200MB)
- **Sistem tepsisi** (minimize to tray)
- **Auto-update** desteği

---

## 🚀 Hızlı Başlangıç

### 1. Tauri CLI Yükle

```powershell
# Rust toolchain (gerekli)
winget install --id Rustlang.Rustup

# Tauri CLI
cargo install tauri-cli
```

### 2. Development Build

```powershell
cd contracts-ai-ui
npm run tauri dev
```

Desktop window açılacak (browser yerine native app).

### 3. Production Build

```powershell
cd contracts-ai-ui
npm run tauri build
```

**Çıktı:**
```
src-tauri/target/release/contracts-ai-ui.exe  (5-10 MB)
```

---

## 📦 Installer Oluşturma

Build sonrası otomatik oluşur:

```
src-tauri/target/release/bundle/
  ├── msi/            → Windows Installer
  └── nsis/           → Portable .exe
```

**Kullanım:**
- MSI: `contracts-ai-ui_0.1.0_x64.msi` (kurulum gerekli)
- NSIS: Portable .exe (kurulum gereksiz)

---

## ⚙️ Konfigürasyon

### Auto-start Backend

`src-tauri/src/main.rs` düzenle:

```rust
use std::process::Command;

fn main() {
    // Backend'i otomatik başlat
    Command::new("python")
        .arg("run_dev.py")
        .spawn()
        .expect("Failed to start backend");
    
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

### System Tray (Minimize to Tray)

`src-tauri/tauri.conf.json`:

```json
{
  "tauri": {
    "systemTray": {
      "iconPath": "icons/icon.png",
      "menuOnLeftClick": false
    }
  }
}
```

---

## 🎨 UI İyileştirmeleri

### Native Titlebar

`src-tauri/tauri.conf.json`:

```json
{
  "tauri": {
    "windows": [
      {
        "decorations": true,  // Windows 11 native titlebar
        "transparent": false,
        "resizable": true,
        "fullscreen": false
      }
    ]
  }
}
```

### Dark Mode Support

`src/index.css`:

```css
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1e1e1e;
    --text: #ffffff;
  }
}
```

---

## 🔧 Troubleshooting

### Build Hatası: WebView2 Missing

```powershell
# WebView2 Runtime yükle (Windows 10/11)
winget install Microsoft.EdgeWebView2Runtime
```

### Port Çakışması

Backend zaten çalışıyorsa:

```javascript
// src/App.jsx
const API_URL = "http://localhost:8000"  // Sabit port
```

---

## 📊 Performans Karşılaştırma

| Özellik | Web Browser | Tauri Desktop |
|---------|-------------|---------------|
| **Başlatma Süresi** | 3-5 sn | 1 sn |
| **Bellek Kullanımı** | 200-300 MB | 50-80 MB |
| **Dosya Boyutu** | - | 5-10 MB |
| **Native Görünüm** | ❌ | ✅ |
| **Auto-update** | ❌ | ✅ |
| **System Tray** | ❌ | ✅ |

---

## 🎯 Önerilen Workflow

### Development:
```powershell
# Terminal 1: Backend
python run_dev.py

# Terminal 2: Desktop app
cd contracts-ai-ui
npm run tauri dev
```

### Production:
```powershell
# Build
npm run tauri build

# Distribute
# MSI installer'ı kullanıcılara dağıt
```

---

## 💡 Ek Özellikler

### 1. File Dialogs (Native)

```javascript
import { open } from '@tauri-apps/api/dialog';

const selectFolder = async () => {
  const folder = await open({
    directory: true,
    multiple: false
  });
  return folder;
}
```

### 2. Notifications

```javascript
import { sendNotification } from '@tauri-apps/api/notification';

sendNotification({
  title: 'Analiz Tamamlandı',
  body: '100 sözleşme işlendi'
});
```

### 3. Auto-update

`src-tauri/tauri.conf.json`:

```json
{
  "updater": {
    "active": true,
    "endpoints": [
      "https://releases.myapp.com/{{target}}/{{current_version}}"
    ]
  }
}
```

---

## 🚀 HIZLI BAŞLATMA

```powershell
# 1. Rust yükle
winget install Rustlang.Rustup

# 2. Desktop app çalıştır
cd contracts-ai-ui
npm install
npm run tauri dev
```

✅ **Native Windows app açılacak!**

---

## 📝 Notlar

- **Geliştirme:** `tauri dev` (hot reload)
- **Production:** `tauri build` (optimized)
- **Boyut:** ~5-10 MB (Electron'dan 20x küçük)
- **Performans:** Chromium tabanlı ama native
