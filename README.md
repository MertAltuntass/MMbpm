<img src="mmbpm/assets/icon.png" width="96" align="left" hspace="12"/>

# MMBpm — Harmonic AutoMix

Bir müzik klasörünü tarayıp her parçanın **BPM** ve **tonunu (Camelot)** tespit
eden, ardından harmonik olarak en uyumlu sıralamayı kurup **gerçek, beat-matched
bir DJ miksi** üreten masaüstü uygulaması. [dj.studio](https://dj.studio) tarzı
otomatik mikslemenin sade, bağımsız bir sürümü.

![tür](https://img.shields.io/badge/python-3.10+-blue) ![lisans](https://img.shields.io/badge/deps-ffmpeg%20%2B%20numpy-green)

## Ne yapar?

- **📁 Kütüphane analizi** — mp3/wav/flac/m4a/aac/ogg dosyalarını tarar.
- **⚡ BPM tespiti** — spectral-flux onset + autocorrelation (tempo önceliğiyle).
- **🎹 Ton tespiti** — kromagram + Krumhansl-Schmuckler profilleri (major/minor),
  sonuç **Camelot** koduyla (örn. `8A`).
- **⚡ Enerji analizi** — her parçanın gürlük/enerji seviyesini 1–10 ölçeğinde
  ölçer; miksi zayıf→güçlü enerji eğrisine göre sıralayabilir.
- **🎡 Camelot çarkı** — kütüphanedeki tonları ve seçili parçanın uyumlu
  komşularını görselleştirir.
- **🧩 Uyum Haritası** — bir şarkı seç, onunla **uyumlu tüm şarkıları** renk
  kodlu (✓ Mükemmel · ○ İyi · △ Dikkatli) gör. Her eşleşmede hem **ton ilişkisi**
  (harmonik) hem de **enerji ilişkisi** (▲ yükselir / ▼ düşer) düz Türkçe yazar.
  Eşleşmeye çift tıklayıp zincir kurabilirsin.
- **▶ Oynatıcı** — üretilen mikste **ileri/geri sarma** çubuğu ve ⏪/⏩ (±10 sn)
  ile istediğin yere atla, duraklat, kaydet.
- **🎚 Geçiş ayarı** — sonuç ekranından **geçiş süresini** ve **tarzını**
  (Yumuşak crossfade / DJ EQ bass-swap) değiştirip **🔁 yeniden oluştur**; dinle,
  beğenmezsen tekrar dene. Geçişler equal-power'dır (ortada ses çökmesi yok).
- **🎚 Tek-tuş miks** — **sadece birbiriyle uyumlu** parçaları otomatik seçip
  sıralar (uyumsuzları dışarıda bırakır, sana da söyler), ortak hedef BPM'e
  **pitch bozulmadan** time-stretch eder, **beat-grid** ile vuruşları hizalar ve
  equal-power crossfade'lerle tek bir mp3'e birleştirir. Sonunda basit bir
  **“Miksin hazır!”** ekranı: ▶ Dinle / 💾 Kaydet. Editör yok, jargon yok.
- **🎯 Beat-grid** — geçiş süresini tam vuruşa yuvarlar ve parçaların beat'lerini
  crossfade boyunca çakıştırır (kicklar üst üste biner).
- **🧭 Kolay kullanım** — 3 adımlı rehber şerit, ilk açılış karşılaması,
  ipucu balonları ve tek tuşluk **🪄 Otomatik Miks**: hiç bilmeyen de miks yapar.
- **⚙️ Konfor** — analiz sonuçları **önbelleğe** alınır (aynı klasörü tekrar
  açınca anında hazır), **son klasör** hatırlanır, tablo başlıklarına tıklayıp
  **sütuna göre sıralama** yapılır.
- **▶ Oynatma** — seçili parçayı veya üretilen miksi çalar.
- **💾 Dışa aktarma** — analiz sonuçlarını JSON olarak kaydeder.

## Neden librosa/pydub yok?

Eski sürümler `librosa` + `pydub`'a dayanıyordu; ikisi de modern Python'da (3.13+)
kırılgan (`pydub`, kaldırılan `audioop` modülüne muhtaç; `librosa`, `numba`
gerektiriyor). Bu sürüm tüm DSP'yi **numpy + scipy** ile, tüm ses I/O'sunu ise
doğrudan **ffmpeg** ile yapar — kurulumu basit ve dayanıklı.

## İndir (hazır .exe)

Kurulumla uğraşmak istemiyorsan **[Releases](https://github.com/MertAltuntass/MMbpm/releases)**
bölümünden `MMBpm.exe`'yi indir ve çift tıkla — ffmpeg içine gömülü gelir, ekstra
bir şey kurmana gerek yok (Windows).

## Kaynaktan kurulum

```bash
pip install -r requirements.txt
```

Ayrıca **ffmpeg** kurulu ve PATH'te olmalı:

| OS      | Komut                                   |
|---------|-----------------------------------------|
| Windows | `winget install ffmpeg` (veya gyan.dev) |
| macOS   | `brew install ffmpeg`                   |
| Linux   | `sudo apt install ffmpeg`               |

## Çalıştırma

```bash
python MMBpm.py
```

### En kolay yol (yeni başlayanlar)

İlk açılışta **3 adımlık rehber** ve bir karşılama penceresi çıkar. Tek yapman
gereken üstteki **🪄 Otomatik Miks Yap** düğmesine basmak: klasörü seçersin,
MMBpm hepsini analiz eder, uyumlu miksi otomatik oluşturur ve **“Miksin hazır!”**
ekranını gösterir — oradan **▶ Dinle** ya da **💾 Kaydet**. Editörle uğraşmana
gerek yok; ince ayar istersen "🎚 Gelişmiş düzenle" bir tık uzakta. Üstteki
**1 → 2 → 3** şeridi nerede olduğunu, **ipucu balonları** her düğmenin ne işe
yaradığını anlatır.

### Adım adım (tam kontrol)

1. **Klasör Aç** ile müzik klasörünü seç.
2. **Tümünü Analiz Et** — BPM / ton / enerji çıkar.
3. (İsteğe bağlı) Tabloda birkaç parça seç; seçim yoksa tüm kütüphane kullanılır.
4. **Mix Studio Aç** — timeline açılır:
   - Sıralama modunu ve hedef BPM'i seç, gerekirse **↻ Yeniden Sırala**.
   - Bir parçaya tıklayıp **▲ ▼ ✕** ile sırayı düzenle.
   - İki blok arasındaki **geçiş rozetine** tıklayıp tipini ve süresini ayarla.
   - **💾 Render & Kaydet** — miks dosyasını üret; **▶ Oynat** ile dinle.

## Proje yapısı

```
MMBpm.py            # başlatıcı
mmbpm/
├── app.py          # ana tkinter arayüz (koyu tema, kütüphane, Camelot çarkı)
├── compat.py       # Uyum Haritası penceresi (hangi şarkı hangisiyle uyumlu)
├── result.py       # “Miksin hazır!” sonuç ekranı (Dinle / Kaydet)
├── wheel.py        # paylaşılan Camelot çarkı çizimi
├── widgets.py      # tooltip + 3-adım rehber şeridi (StepBar)
├── logo.py         # MMBpm markası (başlıkta canvas çizimi + pencere ikonu)
├── assets/         # icon.png · icon.ico · logo_512.png
├── config.py       # küçük kalıcı ayarlar (ilk açılış, son klasör)
├── cache.py        # analiz önbelleği (~/.mmbpm_cache.json)
├── analysis.py     # BPM + ton (Camelot) + enerji tespiti
├── automix.py      # uyumlu-zincir sıralama, MixPlan, geçişler, beat-matched render
├── audio.py        # ffmpeg tabanlı decode/encode/time-stretch/dalga formu
└── models.py       # Track, Transition, MixPlan veri modelleri
```

## Kendi .exe'ni derlemek

```bash
pip install pyinstaller
pyinstaller MMBpm.spec        # dist/MMBpm.exe
```

ffmpeg'i içine gömmek için, `ffmpeg.exe` ve `ffprobe.exe`'yi `ffmpeg_bin/`
klasörüne koyup tekrar derle. (GitHub Actions bunu her `v*` etiketinde otomatik
yapar — bkz. `.github/workflows/release.yml`.)

## Notlar / sınırlar

- Time-stretch ffmpeg `atempo` iledir; çok büyük tempo farklarında (>2x) ses
  kalitesi düşebilir. Yakın BPM'li parçalarla en iyi sonuç alınır.
- Ton tespiti istatistikseldir; belirsiz/atonal parçalarda hata payı olabilir.
