# 🚀 ContractsAI Çalıştırma Rehberi

Uygulamayı çalıştırmak için aşağıdaki adımları takip edin.

## 1. Gereksinimler
- **Docker Desktop** (Redis için gerekli)
- **Python 3.10+**
- **Node.js 18+**

## 2. Redis Başlatma (Zorunlu)
Celery'nin çalışması için Redis gereklidir. En kolayı Docker ile başlatmaktır:

```powershell
# Terminal 1
docker run -d -p 6379:6379 --name contractsai-redis redis:alpine
```

## 3. Celery Worker Başlatma (Arka Plan İşlemleri)
PDF analizlerini yapacak olan worker.

```powershell
# Terminal 2
cd src_python
celery -A celery_app worker --loglevel=info --pool=solo
```
*Not: Windows'ta `--pool=solo` parametresi zorunludur.*

## 4. Uygulamayı Başlatma (Backend + Frontend)
Bu script hem API'yi hem de React arayüzünü başlatır.

```powershell
# Terminal 3
python run_dev.py
```

## 5. Monitoring (Opsiyonel)
Celery işlemlerini görsel olarak takip etmek için Flower'ı başlatabilirsiniz.

```powershell
# Terminal 4
cd src_python
celery -A celery_app flower --port=5555
```
- Dashboard: http://localhost:5555

---

## 🌐 Erişim Adresleri
- **Uygulama:** http://localhost:5173
- **API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Monitoring:** http://localhost:5555

## 🛠️ Sorun Giderme

**Redis Hatası Alırsanız:**
- Docker Desktop'ın çalıştığından emin olun.
- `docker ps` ile redis container'ını kontrol edin.

**Worker Çalışmıyorsa:**
- `.env` dosyasında `CELERY_BROKER_URL` ayarını kontrol edin.
- `pip install celery[redis]` yaptığınızdan emin olun.

**PDF Analizi Başlamıyorsa:**
- Worker terminalini kontrol edin, hata logu var mı?
- Redis bağlantısını kontrol edin.
