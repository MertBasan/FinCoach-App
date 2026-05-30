"""
FinCoach hizmet kataloğu. Her hizmet için durum (available / coming_soon)
ve metadata. Çok Yakında etiketli kartlar üzerine henüz iş mantığı bağlı
değil; ana iskelet hazır ama hizmetler aşamalı olarak açılacak.
"""

SERVICES = [
    {
        "slug": "pdf_extraction",
        "name": "Banka Ekstresi → Excel",
        "category": "Veri Aktarımı",
        "status": "available",
        "url": "/services/pdf-extraction",
        "short": "Banka ekstresi PDF'lerini doğrulanmış işlem satırlarına dönüştürür.",
        "long": "Muhasebeci kalitesinde banka ekstresi aktarımı. Halkbank, Akbank, "
                "Ziraat (vektör + taranmış/OCR), Yapı Kredi, Kuveyt Türk ve "
                "Türkiye Finans Katılım için özel ayrıştırıcılar; diğer bankalar "
                "için genel ayrıştırıcı. Her satır bakiye zinciri doğrulamasından "
                "geçer. Kaynak PDF ve oluşturulan Excel, müşterinin belgelerine "
                "otomatik olarak kaydedilir.",
        "icon": "📄",
    },
    {
        "slug": "transaction_categorization",
        "name": "İşlem Sınıflandırma",
        "category": "Muhasebe",
        "status": "coming_soon",
        "url": None,
        "short": "Banka satırları ve faturalar için kategori önerileri.",
        "long": "Kurallar motoru + AI desteği ile doğru hesap kodu önerilir. "
                "Muhasebeci toplu onaylar. Düzeltmelerinizden öğrenir.",
        "icon": "🏷️",
    },
    {
        "slug": "bank_reconciliation",
        "name": "Banka Mutabakatı",
        "category": "Muhasebe",
        "status": "coming_soon",
        "url": None,
        "short": "Banka satırlarını faturalarla ve defter kayıtlarıyla eşleştirir.",
        "long": "Mükerrer kayıt, eksik kayıt ve eşleşmeyen işlemleri tespit eder.",
        "icon": "🔁",
    },
    {
        "slug": "financial_reporting",
        "name": "Mali Raporlama",
        "category": "Raporlama",
        "status": "available",
        "url": None,
        "short": "Gelir Tablosu, SMM, faaliyet giderleri; önceki dönem ve önceki yılla karşılaştırma.",
        "long": "Yalnızca onaylanmış işlemlerden deterministik Python ile hesaplanır. "
                "Müşteriye gidin ve Raporlar'a tıklayın.",
        "icon": "📊",
    },
    {
        "slug": "kpi_dashboard",
        "name": "KPI Panosu",
        "category": "Raporlama",
        "status": "available",
        "url": None,
        "short": "Müşteri başına hasılat, net kâr, brüt kâr marjı, en yüksek 3 gider kategorisi.",
        "long": "Her müşterinin Raporlar sekmesinde canlı KPI'lar. Müşteriye de "
                "kendi portalında aynı rakamlar gösterilir.",
        "icon": "📈",
    },
    {
        "slug": "ar",
        "name": "Alacaklar",
        "category": "Nakit Akışı",
        "status": "coming_soon",
        "url": None,
        "short": "Ödenmemiş faturaların ve tahsilat aksiyonlarının takibi.",
        "long": "Vadeli alacak raporu, ödeme hatırlatmaları, müşteri ekstreleri.",
        "icon": "💷",
    },
    {
        "slug": "ap",
        "name": "Borçlar",
        "category": "Nakit Akışı",
        "status": "coming_soon",
        "url": None,
        "short": "Tedarikçi faturaları, vade tarihleri, mükerrer fatura tespiti.",
        "long": "Tedarikçilere olan borcunuzu takip edin ve ödemeleri planlayın.",
        "icon": "📤",
    },
    {
        "slug": "vat",
        "name": "KDV ve Vergi Desteği",
        "category": "Vergi & Mevzuat",
        "status": "coming_soon",
        "url": None,
        "short": "KDV hesaplaması, beyanname hazırlığı, vergi özetleri.",
        "long": "KDV beyannamesi desteği, geçici vergi hazırlığı, yıl sonu paketleri.",
        "icon": "🏛️",
    },
    {
        "slug": "payroll",
        "name": "Bordro Desteği",
        "category": "Vergi & Mevzuat",
        "status": "coming_soon",
        "url": None,
        "short": "Bordro PDF'lerinden aktarım, bordro yevmiyeleri, personel maliyeti analizi.",
        "long": "Bordro çıktılarını içeri alın, deftere işleyin, ekibe göre maliyet analizi yapın.",
        "icon": "👥",
    },
    {
        "slug": "ai_commentary",
        "name": "AI Yorumu",
        "category": "Yapay Zekâ",
        "status": "coming_soon",
        "url": None,
        "short": "Aylık rakamlar üzerine sade Türkçe anlatım.",
        "long": "Yalnızca hesaplanmış rakamlara dayanır — asla uydurmaz. "
                "Müşteri görmeden önce muhasebeci inceler ve onaylar.",
        "icon": "💬",
    },
    {
        "slug": "anomaly_detection",
        "name": "Anomali Tespiti",
        "category": "Yapay Zekâ",
        "status": "coming_soon",
        "url": None,
        "short": "Olağandışı işlemleri inceleme için işaretler.",
        "long": "Müşteri yoğunlaşması, gider sıçramaları, mükerrer tedarikçiler ve "
                "diğer operasyonel anomaliler otomatik olarak yüzeye çıkarılır.",
        "icon": "🚩",
    },
    {
        "slug": "workflow_automation",
        "name": "İş Akışı Otomasyonu",
        "category": "Operasyon",
        "status": "coming_soon",
        "url": None,
        "short": "Aylık kapanış kontrol listeleri, hatırlatmalar, onay akışları.",
        "long": "Aylık görev panosu zaten bunun için kullanılıyor. Onay akışları, "
                "tekrarlanan içe aktarmalar ve e-posta hatırlatmaları sıradaki adımlar.",
        "icon": "⚙️",
    },
]


def by_slug(slug: str):
    for s in SERVICES:
        if s["slug"] == slug:
            return s
    return None
