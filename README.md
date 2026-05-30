# FinCoach — Türkçe Sürüm

Türkiye pazarına yönelik mali müşavirlik iş akışı otomasyonu. Bu sürüm:

- Çok kiracılı altyapı (Postgres + Row Level Security)
- Üç kullanıcı rolü: Yönetici, Muhasebeci, Müşteri
- Müşteri başına aylık görev takibi
- Müşteri yönetimi, notlar, belgeler
- **Banka ekstresi PDF aktarıcısı** — Halkbank, Akbank, Ziraat (vektör + OCR), Yapı Kredi, Kuveyt Türk, Türkiye Finans Katılım için özel ayrıştırıcılar + genel ayrıştırıcı. Bakiye zinciri doğrulamalı.
- **Veri omurgası** — TDHP (Tek Düzen Hesap Planı) tabanlı hesap planı, aylık dönemler, onay akışlı işlem yönetimi
- **İşlem inceleme ve onay** ekranı müşteri/dönem bazlı
- **Mali Raporlama** — Gelir Tablosu (önceki dönem ve önceki yıl karşılaştırması), nakit akışı
- **KPI Panosu** — hasılat, net kâr, brüt kâr marjı, en yüksek gider kategorileri; muhasebeci ve müşteri portalı arasında paylaşılan

## Hızlı başlangıç

```bash
cp .env.example .env
docker compose up --build
```

`Application startup complete` mesajını bekleyin, sonra başka bir terminalde:

```bash
docker compose exec app python -m scripts.seed_demo
```

<http://localhost:8000> adresini açın.

## Demo girişleri

Tüm parolalar: **`demo1234`**

| Rol | E-posta | Açılan sayfa |
| --- | --- | --- |
| Muhasebeci | `ayse@aydinmusavirlik.com` | Pano |
| Müşteri (Boğaziçi, TRY) | `bogazici@kahveatolyesi.com` | Portal — örnek işlem ve raporlar yüklü |
| Müşteri (Anadolu, TRY) | `finans@anadolutekstil.com.tr` | Portal — boş durum |
| Müşteri (Ege, TRY) | `merhaba@egeyoga.com` | Portal — boş durum |
| Müşteri (Pixel, TRY) | `iletisim@pixeltasarim.co` | Portal — boş durum |
| Yönetici | `admin@fincoach.dev` | Platform yönetimi |

## Demo akışı

1. **Ayşe olarak giriş yap** (muhasebeci).
2. **Boğaziçi Kahve Atölyesi'ne** tıkla. Adres, VKN, aylık görev ilerlemesi, son belgeler ve notlar.
3. **Raporlar** sekmesine tıkla. Hasılat, SMM, Brüt Kâr, Faaliyet Giderleri, Net Kâr; önceki dönem ve önceki yıl karşılaştırmalı. En yüksek gider kategorileri. Tüm sayılar onaylanmış işlemlerden hesaplanır.
4. **İşlem İnceleme** sekmesine tıkla. 2 bekleyen, ~30 onaylanmış işlem. Satır içi düzenle (açıklama, tutar, hesap dropdown). Toplu onayla.
5. **Hizmetler** sekmesine tıkla. 3 Hazır (Banka Ekstresi → Excel, Mali Raporlama, KPI Panosu), 9 Çok Yakında.
6. **Banka Ekstresi → Excel** sayfasını aç. Müşteri seç, banka ekstresi PDF'i yükle. Excel dosyası inecek; hem kaynak PDF hem çıktı Excel müşterinin belgelerine kaydedilir; güvenilir banka ayrıştırıcıları için satırlar inceleme kuyruğuna onaylanmamış olarak yüklenir.
7. **Çıkış yap, müşteri olarak giriş yap** (`bogazici@kahveatolyesi.com`). Mali Görünüm sayfası — sadece Ayşe'nin onayladığı işlemlerden KPI'lar.

## Mimari

```
app/
├── main.py              FastAPI giriş noktası
├── config.py            ayarlar
├── db/                  SQLAlchemy oturum + RLS yardımcı + modeller
├── auth/                bcrypt + imzalı çerez oturumları, rol kontrolleri
├── locale/              Türkçe biçimlendirme, KDV oranları, VKN/TCKN doğrulama
├── reference/           para birimleri + ülkeler
├── dashboard/           muhasebeci ana ekranı
├── clients/             liste, oluşturma, detay
├── notes/               firma + müşteri bazlı notlar
├── tasks/               aylık görev şablonları ve panosu
├── documents/           yükleme, listeleme, indirme, görünürlük
├── services/            hizmet kataloğu + banka ekstresi aktarıcısı (~1.950 satır)
├── transactions/        işlem inceleme ve onay UI'sı
├── spine/               hesaplar (TDHP), dönemler, staging, onaylı-yalnızca sorgular
├── reporting/           Gelir Tablosu, nakit, KPI (deterministik Python — AI yok)
├── portal/              müşteri ekranları
├── admin/               yönetici görünümü
└── ui/                  şablonlar + CSS
```

## Türkiye yerelleştirmesi

**Tek Düzen Hesap Planı (TDHP)** — devlet tarafından zorunlu kılınan resmi
hesap planı. Her yeni müşteri için 30+ TDHP hesabı otomatik kurulur:

- 100s — Dönen Varlıklar (Kasa, Bankalar, Alıcılar, Ticari Mallar, İndirilecek KDV)
- 200s — Duran Varlıklar (Binalar, Tesis/Makine, Taşıtlar, Birikmiş Amortismanlar)
- 300s/400s — Kısa ve Uzun Vadeli Yabancı Kaynaklar (Satıcılar, Borç Senetleri, Hesaplanan KDV, Banka Kredileri)
- 500s — Özkaynaklar (Sermaye, Yedekler, Geçmiş Yıllar Kârları)
- 600/601 — Yurtiçi/Yurtdışı Satışlar
- **621/622** — SMM hesapları (Mali Raporlama'da SMM satırına otomatik akar)
- 632/642/646/656/660 — Faaliyet ve mali gelir/giderler
- 689 — Olağandışı giderler
- 760/770 — Detaylı gider takibi

**Para birimi:** TRY varsayılan. Biçim: `1.234,56 ₺` (nokta binlik ayracı, virgül ondalık, sembolden önce boşluk).

**Tarih:** `30.05.2026` (kısa), `30 Mayıs 2026` (uzun). Ay adları Türkçe.

**Vergi kimlikleri:** VKN (10 hane, kurumlar) ve TCKN (11 hane, şahıs şirketleri) Müşteri modelinde opsiyonel alanlar olarak. Doğrulama uzunluk + tüm haneler sayı.

**KDV oranları** referans sabit olarak `app/locale/tax.py` içinde (%1, %10, %20). KDV beyannamesi otomasyonu bu sürümün kapsamı dışında.

## Test çalıştırma

```bash
docker compose up -d db
docker compose exec db createdb -U fincoach fincoach_test
docker compose run --rm -e POSTGRES_DB=fincoach_test app pytest -v
```

54 test yeşil olmalı:

- 22 kiracı izolasyonu + bağlam dayanıklılığı testi
- 3 kimlik doğrulama testi
- 29 yerelleştirme testi (para/tarih biçimi, TDHP planı, COGS bayrağı, VKN/TCKN doğrulama)

## Çok kiracılı izolasyon

Her kiracı kapsamındaki tabloda Row-Level Security: `clients`, `notes`,
`task_templates`, `client_monthly_tasks`, `documents`, `accounts`,
`accounting_periods`, `transactions`.

Postgres ayarı `app.current_firm_id` her istek başına `get_current_user`
tarafından oturum kapsamında (`is_local=false`) belirlenir; commit
boundary'lerinde kaybolmaz. `get_db` bağlantı havuzuna iade etmeden önce
ayarı temizler.

## Onay kapısı

Tüm raporlama / KPI / analitik sorgular `app/spine/queries.py` üzerinden
geçer. Bu yardımcılar `approval_status='approved'` filtresini sabit
şekilde içerir. Yeni analitik kod eklerken: oradaki yardımcıyı kullanın,
ham `select(Transaction)` yazmayın. AI ile dokunulmuş kayıtlar (Faz 3'te
gelecek olan) `approval_status='ai_suggested'` ile inilir ve muhasebeci
imzalamadan raporlara çıkmaz.

## Demo verisini sıfırlama

Idempotent:

```bash
docker compose exec app python -m scripts.seed_demo
```

## Hizmet durumu

**Hazır:**
- Banka Ekstresi → Excel (güvenilir banka ayrıştırıcıları için işlem staging dahil)
- Mali Raporlama (müşteri başına Raporlar sekmesi)
- KPI Panosu (Raporlar sekmesi + müşteri portalı Mali Görünüm)

**Çok Yakında** (Hizmetler sayfasında yer tutucu):

- İşlem Sınıflandırma
- Banka Mutabakatı
- Alacaklar
- Borçlar
- KDV ve Vergi Desteği
- Bordro Desteği
- AI Yorumu
- Anomali Tespiti
- İş Akışı Otomasyonu

## UK sürümüyle ilişki

Bu Türkçe sürüm, İngilizce/UK sürümünün aynı ana repo'nun ayrı bir
branch'inde yaşar. Şema kasıtlı olarak aynıdır — sadece iki yerel ayar
deltası vardır:

1. `accounts.is_cogs` boolean — UK 5000 serisinde, TR'de 621/622 üzerinde
   `True` olarak kurulur. Brittle "5 ile başlıyor" tahminini değiştirir.
2. `clients.vkn` ve `clients.tckn` — Türkiye'de opsiyonel kullanılır, UK
   sürümünde boş kalır.

Şema düzeltmeleri kardeş branch'e cherry-pick edilebilir.
