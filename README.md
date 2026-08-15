<p align="center">
  <a href="README.md"><img src="https://img.shields.io/badge/T%C3%BCrk%C3%A7e-e11d48?style=for-the-badge" alt="Türkçe" height="28"></a>
  <a href="README.en.md"><img src="https://img.shields.io/badge/English-3b82f6?style=for-the-badge" alt="English" height="28"></a>
</p>

# ProjectWheel — Gyro Pedal & Steering Wheel Gamepad

İki Android telefonun jiroskop (ivmeölçer) verilerini kullanarak, bilgisayarda **sanal Xbox 360 gamepad** (gaz/fren pedalı + direksiyon) oluşturan entegre bir sürücü sistemidir.

Telefonları yere/sürüş standına sabitleyip eğerek **gaz** ve **fren** pedallarını kontrol eder, fiziksel bir direksiyon simidini ise **X** ekseni olarak oyuna yansıtır. Bağlantı **WiFi**, **USB (ADB)** veya **Bluetooth Classic (Serial SPP)** üzerinden kurulabilir.

## Özellikler

- **Çift telefon desteği** — bir telefon gaz, diğeri fren pedalı olarak atanır.
- **Üç bağlantı yöntemi**
  - **WiFi** — telefon ve bilgisayar aynı ağda.
  - **USB (ADB)** — `adb reverse` ile düşük gecikme.
  - **Bluetooth Classic (Serial SPP)** — Windows "Gelen COM Portu" üzerinden kablosuz.
- **Fiziksel güç tuşu (ekran kapatma) desteği** — Android Foreground Service + Partial Wake Lock sayesinde ekran kapalıyken bile sensör okuma ve veri iletimi kesintisiz sürer.
- **Uzaktan kalibrasyon (Sıfır Noktası Ayarla)** — WebUI üzerinden pedalları tek tıkla sıfırla.
- **Ölü bölge (deadzone), hassasiyet (sensitivity), aktivasyon noktası, eğim yönü** ayarları — gaz ve fren için ayrı ayrı.
- **Direksiyon ölü bölgesi** ve yumuşak (smooth) ölçekleme.
- **Canlı WebUI kontrol paneli** — pedal/direksiyon durumu, eksen değerleri, kalibrasyon.

## Ekran Görüntüleri

| Bölüm | Önizleme |
|-------|----------|
| WebUI Kontrol Paneli | ![WebUI Dashboard](screenshots/01-dashboard.png) |
| Mobil Bağlantı Ekranı | ![Mobil Bağlantı](screenshots/05-connection.png) |
| Mobil Pedal Seçim Ekranı | ![Mobil Pedal Seçim](screenshots/02-pedal-select.png) |
| Mobil Gaz Aktif Ekranı | ![Mobil Gaz](screenshots/03-pedal-gas.png) |
| Mobil Fren Aktif Ekranı | ![Mobil Fren](screenshots/04-pedal-brake.png) |

## Teknoloji Yığını

| Katman | Teknoloji |
|--------|-----------|
| Mobil uygulama | Flutter (Dart) |
| Sensör okuma | `sensors_plus` (ivmeölçer) |
| Arka plan servisi | `flutter_background` + `wakelock_plus` |
| Bluetooth | `flutter_blue_classic` (RFCOMM/SPP) |
| Ağ | `web_socket_channel` (WebSocket) |
| Sunucu | Python + FastAPI + Uvicorn |
| Sanal gamepad | `vgamepad` (ViGEm) |
| Seri port (Bluetooth) | `pyserial` |
| Fiziksel direksiyon okuma | `ctypes` + Win32 `winmm.dll` |

## Dosya Yapısı

```
.
├── backend_app.py           # FastAPI sunucusu (gamepad + WebSocket + serial)
├── run_backend.bat          # Windows başlatma betiği
├── build_apk.bat            # Flutter APK derleme betiği
├── settings.json            # Çalışma zamanı ayarları
├── requirements.txt         # Python bağımlılıkları
├── templates/
│   ├── dashboard.html       # WebUI kontrol paneli
│   └── pedal.html           # Telefon web istemcisi (opsiyonel)
└── gyro_pedal_app/          # Flutter mobil uygulaması
    ├── lib/main.dart        # Ana uygulama kodu
    ├── pubspec.yaml
    └── android/             # Android platform dosyaları
```

## Kurulum

### 1. Bilgisayar (Backend)

Gereksinimler:
- **Windows 10/11**
- **Python 3.9+**
- **ViGEmBus** sürücüsü (sanal gamepad için): https://github.com/nefarius/ViGEmBus/releases

```bash
pip install -r requirements.txt
```

Sunucuyu başlat:

```bat
run_backend.bat
```

Ardından tarayıcıdan kontrol paneline erişin: **http://localhost:8000**

### 2. Telefon (Flutter Uygulaması)

```bash
cd gyro_pedal_app
flutter pub get
flutter build apk --release
```

Üretilen APK: `gyro_pedal_app/build/app/outputs/flutter-apk/app-release.apk`

> Hazır APK'yı backend çalışırken doğrudan indirebilirsiniz:
> **http://localhost:8000/download/gyro-pedal.apk**

## Bağlantı Kılavuzu

### WiFi
1. Telefon ve bilgisayarı aynı ağa bağlayın.
2. Uygulamada **WiFi** seçip bilgisayarın yerel IP'sini girin (örn. `192.168.1.100`).
3. **Bağlan** deyin ve pedalları atayın.

### USB (ADB)
1. Telefonda USB Hata Ayıklama'yı açın.
2. `run_backend.bat` çalışırken `adb reverse tcp:8000 tcp:8000` otomatik kurulur.
3. Uygulamada **USB** modunu seçin.

### Bluetooth Classic (Serial SPP)
1. Telefonu bilgisayarla Bluetooth üzerinden eşleştirin.
2. Windows'ta: *Bluetooth Ayarları → Diğer Bluetooth Seçenekleri → COM Bağlantı Noktaları → Ekle → "Gelen"* ile bir COM portu oluşturun (örn. `COM3`).
3. WebUI'deki **Bluetooth COM Portu** alanına bu portu yazın.
4. Uygulamada **Bluetooth** seçip bilgisayarınızı listeden seçin.

## Veri Kaynakları & Sorumluluk Reddi

Bu proje tamamen **yerel** çalışır; üçüncü taraf bir API'ye bağımlı değildir. Tüm sensör verileri kullanıcının kendi telefonlarından gelir ve yerel ağ içinde kalır. Sanal gamepad emülasyonu ViGEmBus sürücüsü üzerinden yapılır; kullanım yalnızca yasal simülasyon/oyun amaçlıdır.

## Lisans

Bu proje [MIT Lisansı](LICENSE) ile lisanslanmıştır.

## Değişiklik Günlüğü

Ayrıntılı sürüm geçmişi için [CHANGELOG.md](CHANGELOG.md) dosyasına bakın.
