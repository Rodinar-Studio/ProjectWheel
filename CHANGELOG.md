# Değişiklik Günlüğü

Bu projenin sürüm geçmişi. En yeni sürüm en üstte.

## [v1.0.0] — 2026-08-15

### Eklenen
- İki telefonun jiroskop verisiyle sanal Xbox 360 gamepad (gaz/fren pedalı + direksiyon) emülasyonu.
- WiFi bağlantı desteği (WebSocket).
- USB (ADB reverse) bağlantı desteği.
- Bluetooth Classic (Serial SPP) bağlantı desteği (`flutter_blue_classic` + `pyserial`).
- Fiziksel güç tuşu (ekran kapatma) desteği: Foreground Service + Partial Wake Lock.
- WebUI kontrol paneli (Tailwind) — canlı pedal/direksiyon durumu.
- Uzaktan kalibrasyon (Sıfır Noktası Ayarla) butonu.
- Pedal ayarları: ölü bölge, hassasiyet, aktivasyon noktası, eğim yönü.
- Direksiyon ölü bölgesi ve yumuşak ölçekleme.
- Fiziksel direksiyon okuma (Win32 `winmm.dll`).

### Değişen
- Dosya yolları taşınabilir hale getirildi (`BASE_DIR` / `%~dp0`).
