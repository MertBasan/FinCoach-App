# FinCoach Türkçe — Hızlı Başlangıç / Quick Start

Bu klasörde uygulamanın tam kaynak kodu var. Aşağıdaki adımları sırasıyla
takip edin.

## 1. Klasörü VS Code'da aç

Bu dosyanın bulunduğu klasörü açın — `fincoach-tr/`. (Eğer **boş** görüyorsanız,
muhtemelen yanlış klasörü açmışsınız. Zip bir alt klasöre açılıyor.)

VS Code'da Terminal → New Terminal ile terminal açın.

## 2. Önkoşullar

Tek gereken **Docker Desktop**. (https://www.docker.com/products/docker-desktop)

Docker Desktop'ın çalıştığından emin olun. Ayrıca PostgreSQL kurmanıza
**gerek yok** — `docker compose` zaten kendi Postgres'ini ayağa kaldırıyor.

## 3. Çalıştır

```bash
# .env dosyasını oluştur
cp .env.example .env

# Docker imajını derle ve servisleri başlat
docker compose up --build
```

İlk çalıştırmada Docker imajı derlemesi 2-5 dakika sürebilir. Hazır olduğunda
`Application startup complete` satırını göreceksiniz.

Tarayıcıda <http://localhost:8000> adresini açın.

## 4. Demo verisini yükle

Yeni bir terminal aç (ilk terminal `docker compose up` ile meşgul olacak):

```bash
docker compose exec app python -m scripts.seed_demo
```

Bu komut firma, müşteriler ve işlem verilerini ekler.

## 5. Giriş bilgileri

Tüm parolalar: **`demo1234`**

### Muhasebeci (asıl gösterim)
- **E-posta:** `ayse@aydinmusavirlik.com`
- **Açılış:** Pano

### Müşteri girişleri
| Müşteri | E-posta | Para Birimi |
|---|---|---|
| Boğaziçi Kahve Atölyesi | `bogazici@kahveatolyesi.com` | TRY (dolu veri) |
| Anadolu Tekstil Ltd. Şti. | `finans@anadolutekstil.com.tr` | TRY (boş) |
| Ege Yoga Stüdyosu | `merhaba@egeyoga.com` | TRY (boş) |
| Pixel Tasarım Ajansı | `iletisim@pixeltasarim.co` | TRY (boş) |

### Süper kullanıcı (platform yönetimi)
- **E-posta:** `admin@fincoach.dev`
- **Açılış:** Yönetim — tüm firmaları gösterir

## 6. Demo akışı (Türkçe demo için sırayla)

1. **Ayşe olarak giriş yap** (`ayse@aydinmusavirlik.com`)
2. Panoda gör: müşteri sayısı, görev tamamlama grafikleri, vadeleri yaklaşan görevler
3. **Müşteriler → Boğaziçi Kahve Atölyesi**'ne tıkla
4. Detay sayfasında: VKN (2345678901), Galata adresi, aylık görev ilerlemesi
5. **Raporlar** sekmesine tıkla:
   - Hasılat: ~195.229,62 ₺
   - Brüt Kâr Marjı: %82,8
   - Net Kâr: ~54.428,62 ₺
   - SMM hesabı **621 Satılan Ticari Mallar Maliyeti** üzerinden hesaplanmış
   - Önceki Döneme ve Önceki Yıla göre karşılaştırma
6. **İşlem İnceleme** sekmesine git:
   - 2 bekleyen onay (POS satışları, temizlik malzemesi)
   - Bir tanesini onayla, rapora dön — sayılar güncellendi
7. **Hizmetler** → 3 Hazır + 9 Çok Yakında
8. Çıkış yap, müşteri olarak gir (`bogazici@kahveatolyesi.com`)
9. **Mali Görünüm** — Boğaziçi sahibi kendi KPI'larını görüyor (TRY cinsinden)

## 7. Durdurmak / sıfırlamak için

```bash
# Servisleri durdur (verileri tutar)
docker compose down

# Servisleri durdur VE veritabanını sıfırla
docker compose down -v

# Demo verisini yeniden yükle (idempotent)
docker compose exec app python -m scripts.seed_demo
```

## 8. Testleri çalıştır (opsiyonel)

```bash
docker compose exec db createdb -U fincoach fincoach_test
docker compose run --rm -e POSTGRES_DB=fincoach_test app pytest -v
```

54 test yeşil olmalı.

## Sorun çözme

**"docker: command not found"** → Docker Desktop kurulu değil veya
çalışmıyor. https://www.docker.com/products/docker-desktop

**"port 5432 already in use"** → Bilgisayarınızda zaten bir Postgres
çalışıyor. Kapatın ya da `docker-compose.yml`'de `db.ports`'u `"5433:5432"`
yapın.

**"port 8000 already in use"** → 8000 portu kullanımda. `docker-compose.yml`'de
`app.ports`'u `"8001:8000"` yapın ve <http://localhost:8001>'i kullanın.

**Tarayıcıda "Bad Request" / "CSRF"** → `.env` dosyasındaki `SECRET_KEY`
değerini değiştirin (geliştirme için herhangi bir uzun rastgele dize).

**Sayfalar yükleniyor ama veri yok** → `seed_demo` komutunu çalıştırmayı
unutmuşsunuz olabilir (adım 4).

---

## What's inside this folder

```
fincoach-tr/
├── README.md             # Detaylı dokümantasyon
├── QUICKSTART.md         # Bu dosya
├── Dockerfile            # Uygulama Docker imajı
├── docker-compose.yml    # Postgres + uygulama servisi
├── .env.example          # Ortam değişkenleri şablonu
├── pyproject.toml        # Python bağımlılıkları
├── alembic.ini           # DB migration ayarı
├── alembic/              # Veritabanı migrationları (4 adet)
├── app/                  # Tüm uygulama kodu (~6.800 satır Python)
│   ├── main.py
│   ├── config.py
│   ├── auth/             # Giriş, kayıt, oturum yönetimi
│   ├── clients/          # Müşteri CRUD
│   ├── dashboard/        # Muhasebeci panosu
│   ├── documents/        # Belge yükleme
│   ├── locale/           # Türkçe biçimlendirme, KDV, VKN/TCKN
│   ├── notes/            # Notlar
│   ├── portal/           # Müşteri portalı
│   ├── reporting/        # Gelir Tablosu, KPI'lar
│   ├── services/         # Banka ekstresi ayrıştırıcısı (~1.950 satır)
│   ├── spine/            # TDHP, dönemler, işlemler
│   ├── tasks/            # Aylık görev takibi
│   ├── transactions/     # İşlem inceleme ve onay
│   └── ui/               # 18 HTML şablon + CSS
├── scripts/
│   └── seed_demo.py      # Demo verisi yükleyici
└── tests/                # 54 test
```
