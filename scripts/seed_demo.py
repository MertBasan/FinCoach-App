"""
Turkish demo data seed — Phase 4 edition.

Creates:
  - Mali müşavirlik firma: Aydın Mali Müşavirlik
  - Ayşe Yıldız  — firma yöneticisi (is_firm_admin=True)
  - Mehmet Kaya  — normal muhasebeci, Boğaziçi Kahve + Ege Yoga'ya atanmış
  - 4 SME müşteri (Boğaziçi Kahve Atölyesi, Anadolu Tekstil, Ege Yoga, Pixel Tasarım)
  - 4 müşteri portal kullanıcısı
  - 1 superuser (admin@fincoach.dev / demo1234)
  - Örnek notlar, belgeler, görevler
  - Boğaziçi Kahve için 2 dönem onaylı işlem + 1 yayınlı dönem özeti
  - Anadolu Tekstil için onaylı + yayınlı dönem özeti (ar_total=85.000, ap_total=32.000)
  - Örnek denetim günlüğü kayıtları (yayın eylemleri dahil)

Idempotent: önce mevcut demo verilerini siler, sonra yeniden oluşturur.

Çalıştırmak için:
    docker compose exec app python -m scripts.seed_demo
"""
import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal, set_firm_context
from app.db.models import (
    AccountingFirm, User, Client, Note,
    TaskTemplate, ClientMonthlyTask, Document,
    Account, AccountingPeriod, Transaction,
    ClientAssignment, AdminAuditLog, PeriodSnapshot,
)
from app.auth.security import hash_password
from app.tasks.workflow import (
    current_period, previous_period, generate_tasks_for_client_period,
)


FIRM_NAME = "Aydın Mali Müşavirlik"
ADMIN_ACCOUNTANT_EMAIL = "ayse@aydinmusavirlik.com"
SECOND_ACCOUNTANT_EMAIL = "mehmet@aydinmusavirlik.com"
PLATFORM_ADMIN_EMAIL = "admin@fincoach.dev"
PASSWORD = "demo1234"

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/code/uploaded_files"))


CLIENT_SEEDS = [
    {
        "name": "Boğaziçi Kahve Atölyesi",
        "industry": "Konaklama / Yiyecek-İçecek",
        "base_currency": "TRY",
        "address_line1": "Serdar-ı Ekrem Caddesi No: 27",
        "address_line2": "Galata",
        "city": "İstanbul",
        "postcode": "34421",
        "country_code": "TR",
        "vkn": "2345678901",
        "submission_day_of_month": 7,
        "client_user_email": "bogazici@kahveatolyesi.com",
        "client_user_name": "Cemil Akın",
    },
    {
        "name": "Anadolu Tekstil Ltd. Şti.",
        "industry": "Tekstil İmalatı",
        "base_currency": "TRY",
        "address_line1": "Nilüfer Organize Sanayi Bölgesi 4. Cadde No: 12",
        "city": "Bursa",
        "postcode": "16140",
        "country_code": "TR",
        "vkn": "3456789012",
        "submission_day_of_month": 5,
        "client_user_email": "finans@anadolutekstil.com.tr",
        "client_user_name": "Elif Demir",
    },
    {
        "name": "Ege Yoga Stüdyosu",
        "industry": "Sağlık ve Spor",
        "base_currency": "TRY",
        "address_line1": "Kıbrıs Şehitleri Caddesi No: 88",
        "address_line2": "Alsancak",
        "city": "İzmir",
        "postcode": "35220",
        "country_code": "TR",
        "vkn": "4567890123",
        "submission_day_of_month": 10,
        "client_user_email": "merhaba@egeyoga.com",
        "client_user_name": "Selin Kaya",
    },
    {
        "name": "Pixel Tasarım Ajansı",
        "industry": "Yaratıcı Ajans",
        "base_currency": "TRY",
        "address_line1": "Tunalı Hilmi Caddesi No: 56/4",
        "address_line2": "Çankaya",
        "city": "Ankara",
        "postcode": "06680",
        "country_code": "TR",
        "vkn": "5678901234",
        "submission_day_of_month": 12,
        "client_user_email": "iletisim@pixeltasarim.co",
        "client_user_name": "Mert Yılmaz",
    },
]


def main():
    db: Session = SessionLocal()
    try:
        wipe_existing(db)
        firm, ayse, mehmet = create_firm_with_accountants(db)
        create_superuser(db)
        create_task_templates(db, firm)
        create_clients_and_users(db, firm)
        create_assignments(db, firm, ayse, mehmet)
        create_sample_notes(db, firm)
        create_sample_documents(db, firm)
        seed_task_progress(db, firm, ayse, mehmet)
        seed_demo_transactions(db, firm, ayse)
        seed_demo_snapshot(db, firm, ayse)
        seed_bogazici_published_snapshot(db, firm, ayse)
        seed_adhoc_tasks(db, firm, ayse, mehmet)
        seed_audit_log(db, firm, ayse, mehmet)
        db.commit()

        print("\n✅ Demo verisi başarıyla yüklendi.\n")
        print(f"  Yönetici muhasebeci: {ADMIN_ACCOUNTANT_EMAIL} / {PASSWORD}")
        print(f"  İkinci muhasebeci:  {SECOND_ACCOUNTANT_EMAIL} / {PASSWORD}")
        print(f"  Platform yöneticisi: {PLATFORM_ADMIN_EMAIL} / {PASSWORD}")
        print(f"  Müşteri girişleri:")
        for c in CLIENT_SEEDS:
            print(f"    {c['client_user_email']} / {PASSWORD}  ({c['name']})")
        print("\n  http://localhost:8000 adresinden giriş yapın.")
    finally:
        db.close()


def wipe_existing(db: Session):
    print("Mevcut demo verileri temizleniyor…")
    set_firm_context(db, None)
    firm = db.scalar(select(AccountingFirm).where(AccountingFirm.name == FIRM_NAME))
    if firm:
        set_firm_context(db, str(firm.id))
        db.execute(delete(AdminAuditLog).where(AdminAuditLog.firm_id == firm.id))
        db.execute(delete(PeriodSnapshot).where(PeriodSnapshot.firm_id == firm.id))
        db.execute(delete(Transaction).where(Transaction.firm_id == firm.id))
        db.execute(delete(AccountingPeriod).where(AccountingPeriod.firm_id == firm.id))
        db.execute(delete(Account).where(Account.firm_id == firm.id))
        db.execute(delete(ClientAssignment).where(ClientAssignment.firm_id == firm.id))
        clients = db.scalars(select(Client).where(Client.firm_id == firm.id)).all()
        client_ids = [c.id for c in clients]
        if client_ids:
            db.execute(delete(User).where(User.client_id.in_(client_ids)))
        set_firm_context(db, None)
        db.delete(firm)
    su = db.scalar(select(User).where(User.email == PLATFORM_ADMIN_EMAIL))
    if su:
        db.delete(su)
    db.flush()


def create_firm_with_accountants(db: Session):
    firm = AccountingFirm(id=uuid4(), name=FIRM_NAME)
    db.add(firm)
    db.flush()

    ayse = User(
        firm_id=firm.id,
        email=ADMIN_ACCOUNTANT_EMAIL,
        name="Ayşe Yıldız",
        password_hash=hash_password(PASSWORD),
        role="accountant",
        is_firm_admin=True,
        is_active=True,
    )
    db.add(ayse)

    mehmet = User(
        firm_id=firm.id,
        email=SECOND_ACCOUNTANT_EMAIL,
        name="Mehmet Kaya",
        password_hash=hash_password(PASSWORD),
        role="accountant",
        is_firm_admin=False,
        is_active=True,
    )
    db.add(mehmet)
    db.flush()

    set_firm_context(db, str(firm.id))
    print(f"Firma oluşturuldu: {firm.name} (Yönetici: Ayşe, Normal: Mehmet)")
    return firm, ayse, mehmet


def create_superuser(db: Session):
    set_firm_context(db, None)
    su = User(
        firm_id=None,
        email=PLATFORM_ADMIN_EMAIL,
        name="Platform Yöneticisi",
        password_hash=hash_password(PASSWORD),
        role="superuser",
        is_firm_admin=False,
        is_active=True,
    )
    db.add(su)
    db.flush()
    print("Süper kullanıcı oluşturuldu")


_DEFAULT_TEMPLATES = [
    ("Banka ekstrelerini topla", "veri-aktarımı", 5, "Önceki ay için müşteriden banka ekstrelerini iste."),
    ("Fatura ve fişleri topla", "veri-aktarımı", 7, "Tüm satış faturalarını ve gider fişlerini al ve doğrula."),
    ("İşlemleri sınıflandır", "muhasebe", 12, "Tüm işlemleri doğru gider hesaplarına kodla."),
    ("Banka mutabakatı", "muhasebe", 14, "Banka ekstrelerini defter kayıtlarıyla mutabık yap."),
    ("Vadeli alacaklar incelemesi", "alacaklar", 16, "Vadesi geçen faturaları gözden geçir."),
    ("KDV hazırlığı", "vergi", 20, "KDV yükümlülüğünü hesapla ve beyannameyi hazırla."),
    ("Aylık yönetim raporu", "raporlama", 25, "Aylık raporu hazırla ve müşteriye gönder."),
]


def create_task_templates(db: Session, firm: AccountingFirm):
    set_firm_context(db, str(firm.id))
    for name, category, day, description in _DEFAULT_TEMPLATES:
        db.add(TaskTemplate(
            firm_id=firm.id, name=name, category=category,
            day_of_month=day, description=description, active=True,
        ))
    db.flush()
    print(f"{len(_DEFAULT_TEMPLATES)} görev şablonu oluşturuldu")


def create_clients_and_users(db: Session, firm: AccountingFirm):
    from app.spine.chart_of_accounts import seed_default_coa

    set_firm_context(db, str(firm.id))
    for seed in CLIENT_SEEDS:
        client = Client(
            firm_id=firm.id,
            name=seed["name"], industry=seed["industry"],
            base_currency=seed["base_currency"],
            address_line1=seed.get("address_line1"),
            address_line2=seed.get("address_line2"),
            city=seed.get("city"),
            postcode=seed.get("postcode"),
            country_code=seed.get("country_code"),
            vkn=seed.get("vkn"),
            submission_day_of_month=seed["submission_day_of_month"],
        )
        db.add(client)
        db.flush()
        seed_default_coa(db, firm.id, client.id)
        db.add(User(
            firm_id=firm.id,
            client_id=client.id,
            email=seed["client_user_email"],
            name=seed["client_user_name"],
            password_hash=hash_password(PASSWORD),
            role="client",
            is_active=True,
        ))
        seed["_client_id"] = client.id
    db.flush()
    print(f"{len(CLIENT_SEEDS)} müşteri ve portal kullanıcısı oluşturuldu (TDHP hesap planı yüklendi)")


def create_assignments(db: Session, firm: AccountingFirm, ayse: User, mehmet: User):
    """Ayşe tüm müşterilere atanır (yönetici). Mehmet yalnızca Boğaziçi + Ege Yoga'ya."""
    set_firm_context(db, str(firm.id))
    for seed in CLIENT_SEEDS:
        cid = seed["_client_id"]
        # Ayşe (admin) → tüm müşteriler
        db.add(ClientAssignment(firm_id=firm.id, client_id=cid, user_id=ayse.id, assigned_by=ayse.id))
        # Mehmet → yalnızca Boğaziçi Kahve ve Ege Yoga
        if seed["name"] in ("Boğaziçi Kahve Atölyesi", "Ege Yoga Stüdyosu"):
            db.add(ClientAssignment(firm_id=firm.id, client_id=cid, user_id=mehmet.id, assigned_by=ayse.id))
    db.flush()
    print("Müşteri atamaları yapıldı (Mehmet: 2 müşteri, Ayşe: 4 müşteri)")


def create_sample_notes(db: Session, firm: AccountingFirm):
    set_firm_context(db, str(firm.id))
    ayse = db.scalar(select(User).where(User.email == ADMIN_ACCOUNTANT_EMAIL))

    firmwide = [
        ("3. çeyrek son tarih hatırlatması", "Tüm müşteriler için KDV beyannameleri ay sonuna kadar verilmeli. 20'sine kadar herkesle teyitleş."),
        ("Yeni yazılım aboneliği", "Pro seviyesine yükseltildi — firma genel giderlerine eklendi."),
    ]
    for title, body in firmwide:
        db.add(Note(firm_id=firm.id, author_id=ayse.id, title=title, body=body))

    client_notes = [
        (CLIENT_SEEDS[0]["_client_id"], "Espresso makinesi alımı",
         "Sahibi 4. çeyrekte yeni espresso makinesi almayı planlıyor. Fatura geldiğinde amortisman ayarlamasını teyit et."),
        (CLIENT_SEEDS[1]["_client_id"], "AB ihracat KDV iadesi",
         "Anadolu Tekstil son AB sevkiyatları için iade dosyası açacak. Geçici vergi öncesi tamamlamayı hedefle."),
        (CLIENT_SEEDS[2]["_client_id"], "Stüdyo genişlemesi",
         "Bornova'da ikinci şube düşünüyor. Banka kredisi için nakit akış projeksiyonu lazım olacak."),
        (CLIENT_SEEDS[3]["_client_id"], "Geç gider fişleri",
         "Müşteri fişleri 1-2 hafta geç gönderiyor. Aylık hatırlatma kur."),
    ]
    for cid, title, body in client_notes:
        db.add(Note(firm_id=firm.id, author_id=ayse.id, client_id=cid, title=title, body=body))
    print(f"{len(firmwide) + len(client_notes)} not oluşturuldu")


def create_sample_documents(db: Session, firm: AccountingFirm):
    set_firm_context(db, str(firm.id))
    ayse = db.scalar(select(User).where(User.email == ADMIN_ACCOUNTANT_EMAIL))
    period = current_period()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    fixtures = [
        (CLIENT_SEEDS[0]["_client_id"], "Nisan_banka_ekstresi.pdf", "bank_statement",
         "Boğaziçi Kahve için örnek banka ekstresi içeriği.\nDemo için fikstür dosyasıdır.\n", False),
        (CLIENT_SEEDS[0]["_client_id"], "Mart_yonetim_raporu.pdf", "report",
         "Boğaziçi Kahve — Mart 2026 Yönetim Raporu\nHasılat, giderler ve yorumlar.\n", True),
        (CLIENT_SEEDS[1]["_client_id"], "Q1_faturalar.zip", "invoice",
         "Anadolu Tekstil Q1 faturaları yer tutucu.", False),
        (CLIENT_SEEDS[1]["_client_id"], "KDV_ozeti_2026Q1.pdf", "report",
         "Anadolu Tekstil KDV özeti Q1 2026.", True),
        (CLIENT_SEEDS[2]["_client_id"], "Stüdyo_bordro_Nisan.csv", "payroll",
         "ad,gorev,brut\nA. Alvarez,Eğitmen,42000\nB. Çelik,Eğitmen,38000", False),
        (CLIENT_SEEDS[2]["_client_id"], "Nakit_akis_projeksiyonu.pdf", "report",
         "Ege Yoga — 12 aylık nakit akış projeksiyonu (taslak).", True),
        (CLIENT_SEEDS[3]["_client_id"], "Gider_fisleri_Nisan.zip", "receipt",
         "Pixel Tasarım Nisan gider fişleri.", False),
    ]

    for cid, name, doc_type, content, visible in fixtures:
        storage_dir = UPLOAD_DIR / str(firm.id) / str(cid)
        storage_dir.mkdir(parents=True, exist_ok=True)
        path = storage_dir / f"{uuid4().hex}_{name}"
        path.write_text(content, encoding="utf-8")
        db.add(Document(
            firm_id=firm.id, client_id=cid, uploaded_by_id=ayse.id,
            name=name, document_type=doc_type, file_path=str(path),
            size_bytes=len(content.encode("utf-8")), mime_type="text/plain",
            period=period, visible_to_client=visible,
        ))
    print(f"{len(fixtures)} belge fikstürü oluşturuldu")


def seed_task_progress(db: Session, firm: AccountingFirm, ayse: User, mehmet: User):
    set_firm_context(db, str(firm.id))
    period = current_period()
    prev = previous_period(period)

    for seed in CLIENT_SEEDS:
        generate_tasks_for_client_period(db, firm.id, seed["_client_id"], prev)
        generate_tasks_for_client_period(db, firm.id, seed["_client_id"], period)
    db.flush()

    last_month_tasks = db.scalars(
        select(ClientMonthlyTask).where(ClientMonthlyTask.period == prev)
    ).all()
    for t in last_month_tasks:
        t.status = "done"
        t.completed_at = datetime.utcnow() - timedelta(days=15)
        t.completed_by_id = ayse.id

    today = date.today()
    current_tasks = db.scalars(
        select(ClientMonthlyTask).where(ClientMonthlyTask.period == period)
        .order_by(ClientMonthlyTask.due_date)
    ).all()
    by_client: dict = {}
    for t in current_tasks:
        by_client.setdefault(t.client_id, []).append(t)
    for cid, tasks in by_client.items():
        tasks.sort(key=lambda t: t.due_date)
        n = len(tasks)
        done_n = n // 2
        in_progress_n = max(1, n // 5)
        for i, t in enumerate(tasks):
            if i < done_n:
                t.status = "done"
                t.completed_at = datetime.utcnow() - timedelta(days=3)
                t.completed_by_id = t.assigned_to_user_id or ayse.id
            elif i < done_n + in_progress_n:
                t.status = "in_progress"
    db.flush()
    total_complete = sum(1 for t in current_tasks if t.status == "done")
    print(f"Görev ilerlemesi yüklendi: bu ay {total_complete}/{len(current_tasks)}, geçen ay tümü tamamlandı")


def seed_demo_transactions(db: Session, firm: AccountingFirm, ayse: User):
    """Boğaziçi Kahve için 2 dönem onaylı işlem + 2 bekleyen işlem."""
    set_firm_context(db, str(firm.id))
    bogazici = db.scalar(
        select(Client).where(Client.firm_id == firm.id).where(Client.name == "Boğaziçi Kahve Atölyesi")
    )
    if not bogazici:
        return

    def acc(code: str):
        return db.scalar(
            select(Account).where(Account.client_id == bogazici.id).where(Account.code == code)
        )

    sales = acc("600"); cogs_goods = acc("621"); opex = acc("770")
    marketing = acc("760"); admin = acc("632"); fin_expense = acc("660"); fin_income = acc("642")

    cur_period_str = current_period()
    prev_period_str = previous_period(cur_period_str)

    def _ensure_period(period_str: str) -> AccountingPeriod:
        y, m = period_str.split("-")
        y, m = int(y), int(m)
        p = db.scalar(
            select(AccountingPeriod)
            .where(AccountingPeriod.client_id == bogazici.id)
            .where(AccountingPeriod.year == y).where(AccountingPeriod.month == m)
        )
        if p:
            return p
        p = AccountingPeriod(firm_id=firm.id, client_id=bogazici.id, year=y, month=m)
        db.add(p); db.flush()
        return p

    def _approved(d, desc, amount, account, period):
        return Transaction(
            firm_id=firm.id, client_id=bogazici.id, period_id=period.id,
            account_id=account.id if account else None,
            date=d, description=desc, amount=Decimal(str(amount)),
            source="pdf_extraction", approval_status="approved",
            created_by_id=ayse.id, approved_by_id=ayse.id, approved_at=datetime.utcnow(),
        )

    def _seed_period(period_str: str, y: int, m: int, scale: float = 1.0):
        period = _ensure_period(period_str)
        s = Decimal(str(scale))
        rows = [
            (date(y, m, 3),  "POS satışları — 1. hafta", Decimal("42500.50") * s, sales),
            (date(y, m, 10), "POS satışları — 2. hafta", Decimal("46800.75") * s, sales),
            (date(y, m, 17), "POS satışları — 3. hafta", Decimal("44200.00") * s, sales),
            (date(y, m, 24), "POS satışları — 4. hafta", Decimal("47100.25") * s, sales),
            (date(y, m, 4),  "Kahve çekirdek alımı", Decimal("-18500.00") * s, cogs_goods),
            (date(y, m, 18), "Süt ve süt ürünleri toptan", Decimal("-9200.00") * s, cogs_goods),
            (date(y, m, 11), "Şekerleme ve yan ürünler", Decimal("-3400.00") * s, cogs_goods),
            (date(y, m, 1),  "Aylık kira", Decimal("-32000.00"), opex),
            (date(y, m, 5),  "Elektrik ve doğalgaz", Decimal("-4850.50"), admin),
            (date(y, m, 25), "Personel maaşları", Decimal("-48000.00") * s, opex),
            (date(y, m, 28), "SGK ödemeleri", Decimal("-12400.00") * s, opex),
            (date(y, m, 12), "POS yazılım aboneliği", Decimal("-1290.00"), admin),
            (date(y, m, 15), "Sosyal medya reklamları", Decimal("-3500.00"), marketing),
            (date(y, m, 28), "Banka komisyonları", Decimal("-340.50"), fin_expense),
            (date(y, m, 30), "Mevduat faizi", Decimal("180.00"), fin_income),
        ]
        if period_str == cur_period_str:
            rows.append((date(y, m, 20), "Diğer tedarikçi — kodlanmamış", Decimal("-1850.30"), None))
        for d, desc, amt, account in rows:
            db.add(_approved(d, desc, amt, account, period))

    py, pm = prev_period_str.split("-")
    _seed_period(prev_period_str, int(py), int(pm), scale=1.0)
    cy, cm = cur_period_str.split("-")
    _seed_period(cur_period_str, int(cy), int(cm), scale=1.08)

    period = _ensure_period(cur_period_str)
    db.add(Transaction(
        firm_id=firm.id, client_id=bogazici.id, period_id=period.id, account_id=None,
        date=date(int(cy), int(cm), 22),
        description="POS satışları — banka teyidi bekleniyor",
        amount=Decimal("38900.00"), source="pdf_extraction", approval_status="unapproved",
        created_by_id=ayse.id,
    ))
    db.add(Transaction(
        firm_id=firm.id, client_id=bogazici.id, period_id=period.id, account_id=None,
        date=date(int(cy), int(cm), 26),
        description="Temizlik malzemesi — Migros",
        amount=Decimal("-520.30"), source="pdf_extraction", approval_status="unapproved",
        created_by_id=ayse.id,
    ))
    db.flush()
    print("Spine yüklendi: Boğaziçi Kahve — 2 dönem onaylı işlem + 2 bekleyen onay")


def seed_demo_snapshot(db: Session, firm: AccountingFirm, ayse: User):
    """Anadolu Tekstil için geçen ay onaylı + yayınlı dönem özeti (source='manual').

    Phase 4: ar_total=85.000, ap_total=32.000, published=True.
    """
    from app.locale.format import TR_MONTHS

    set_firm_context(db, str(firm.id))
    tekstil = db.scalar(
        select(Client).where(Client.firm_id == firm.id).where(Client.name == "Anadolu Tekstil Ltd. Şti.")
    )
    if not tekstil:
        return

    prev_str = previous_period(current_period())
    py, pm = prev_str.split("-")
    y, m = int(py), int(pm)

    period = db.scalar(
        select(AccountingPeriod)
        .where(AccountingPeriod.client_id == tekstil.id)
        .where(AccountingPeriod.year == y).where(AccountingPeriod.month == m)
    )
    if not period:
        period = AccountingPeriod(firm_id=firm.id, client_id=tekstil.id, year=y, month=m)
        db.add(period)
        db.flush()

    month_name = TR_MONTHS[m - 1]
    note = f"Sayın Anadolu Tekstil Ltd. Şti., burada {month_name} ayının istatistiklerini görebilirsiniz."

    snap = PeriodSnapshot(
        firm_id=firm.id,
        client_id=tekstil.id,
        period_id=period.id,
        source="manual",
        approval_status="approved",
        created_by=ayse.id,
        approved_by=ayse.id,
        approved_at=datetime.utcnow() - timedelta(days=10),
        # Phase 4: published
        published=True,
        published_at=datetime.utcnow() - timedelta(days=8),
        published_by_id=ayse.id,
        accountant_note=note,
        revenue=Decimal("480000.00"),
        cogs=Decimal("280000.00"),
        gross_profit=Decimal("200000.00"),
        operating_expenses=Decimal("95000.00"),
        net_profit=Decimal("105000.00"),
        cash_balance_opening=Decimal("120000.00"),
        cash_balance_closing=Decimal("178000.00"),
        cash_inflows=Decimal("510000.00"),
        cash_outflows=Decimal("452000.00"),
        ar_total=Decimal("85000.00"),   # Phase 4 value
        ap_total=Decimal("32000.00"),   # Phase 4 value
        vat_input=Decimal("56000.00"),
        vat_output=Decimal("96000.00"),
        expense_breakdown={
            "Personel giderleri": 42000.0,
            "Hammadde (iplik)": 30000.0,
            "Nakliye ve lojistik": 12000.0,
            "Enerji (elektrik, doğalgaz)": 6500.0,
            "Genel yönetim": 4500.0,
        },
        notes="Q1 manuel giriş — ETASQL ihracat yüklendiğinde güncellenecek.",
    )
    db.add(snap)
    db.flush()
    print(f"Dönem özeti yüklendi: Anadolu Tekstil — onaylı + yayınlı ({month_name} {y})")


def seed_bogazici_published_snapshot(db: Session, firm: AccountingFirm, ayse: User):
    """Boğaziçi Kahve için geçen ay onaylı + yayınlı dönem özeti.

    Derived from the seeded transaction totals so comparison labels work in demo.
    """
    from app.locale.format import TR_MONTHS

    set_firm_context(db, str(firm.id))
    bogazici = db.scalar(
        select(Client).where(Client.firm_id == firm.id).where(Client.name == "Boğaziçi Kahve Atölyesi")
    )
    if not bogazici:
        return

    prev_str = previous_period(current_period())
    py, pm = prev_str.split("-")
    y, m = int(py), int(pm)

    period = db.scalar(
        select(AccountingPeriod)
        .where(AccountingPeriod.client_id == bogazici.id)
        .where(AccountingPeriod.year == y).where(AccountingPeriod.month == m)
    )
    if not period:
        period = AccountingPeriod(firm_id=firm.id, client_id=bogazici.id, year=y, month=m)
        db.add(period)
        db.flush()

    month_name = TR_MONTHS[m - 1]
    note = f"Sayın Cemil Bey, burada {month_name} ayının istatistiklerini görebilirsiniz."

    snap = PeriodSnapshot(
        firm_id=firm.id,
        client_id=bogazici.id,
        period_id=period.id,
        source="manual",
        approval_status="approved",
        created_by=ayse.id,
        approved_by=ayse.id,
        approved_at=datetime.utcnow() - timedelta(days=12),
        published=True,
        published_at=datetime.utcnow() - timedelta(days=10),
        published_by_id=ayse.id,
        accountant_note=note,
        revenue=Decimal("180600.50"),
        cogs=Decimal("31100.00"),
        gross_profit=Decimal("149500.50"),
        operating_expenses=Decimal("101990.50"),
        net_profit=Decimal("47510.00"),
        cash_balance_opening=Decimal("85000.00"),
        cash_balance_closing=Decimal("118000.00"),
        cash_inflows=Decimal("182000.00"),
        cash_outflows=Decimal("149000.00"),
        ar_total=Decimal("18500.00"),
        ap_total=Decimal("9800.00"),
        expense_breakdown={
            "Aylık kira": 32000.0,
            "Personel maaşları": 48000.0,
            "SGK ödemeleri": 12400.0,
            "Elektrik ve doğalgaz": 4850.5,
            "Sosyal medya reklamları": 3500.0,
            "POS yazılım aboneliği": 1290.0,
            "Yönetim giderleri": 940.0,
        },
    )
    db.add(snap)
    db.flush()
    print(f"Dönem özeti yüklendi: Boğaziçi Kahve — onaylı + yayınlı ({month_name} {y})")


def seed_adhoc_tasks(db: Session, firm: AccountingFirm, ayse: User, mehmet: User):
    """Belirli muhasebecilere atanmış birkaç özel görev."""
    set_firm_context(db, str(firm.id))
    bogazici_id = CLIENT_SEEDS[0]["_client_id"]
    ege_id = CLIENT_SEEDS[2]["_client_id"]

    period = current_period()

    adhoc = [
        (bogazici_id, "Espresso makinesi amortisman kaydı", ayse.id),
        (bogazici_id, "Şubat POS raporunu inceleme", mehmet.id),
        (ege_id, "Nakit akış projeksiyonu hazırla", mehmet.id),
    ]
    for cid, title, assignee_id in adhoc:
        db.add(ClientMonthlyTask(
            firm_id=firm.id, client_id=cid, template_id=None,
            name=title, category="genel", period=period,
            due_date=date.today() + timedelta(days=10),
            status="pending", assigned_to_user_id=assignee_id,
        ))
    db.flush()
    print(f"{len(adhoc)} özel görev oluşturuldu")


def seed_audit_log(db: Session, firm: AccountingFirm, ayse: User, mehmet: User):
    """Demo denetim günlüğü kayıtları."""
    set_firm_context(db, str(firm.id))
    now = datetime.utcnow()
    entries = [
        AdminAuditLog(
            firm_id=firm.id, actor_user_id=ayse.id, target_user_id=mehmet.id,
            action="create_user",
            details={"email": SECOND_ACCOUNTANT_EMAIL, "role": "accountant"},
            created_at=now - timedelta(days=5),
        ),
        AdminAuditLog(
            firm_id=firm.id, actor_user_id=ayse.id, target_user_id=mehmet.id,
            action="assign_client",
            details={"client_name": "Boğaziçi Kahve Atölyesi"},
            created_at=now - timedelta(days=5),
        ),
        AdminAuditLog(
            firm_id=firm.id, actor_user_id=ayse.id, target_user_id=mehmet.id,
            action="assign_client",
            details={"client_name": "Ege Yoga Stüdyosu"},
            created_at=now - timedelta(days=5),
        ),
        AdminAuditLog(
            firm_id=firm.id, actor_user_id=ayse.id,
            action="create_task",
            details={"title": "Espresso makinesi amortisman kaydı", "client": "Boğaziçi Kahve"},
            created_at=now - timedelta(days=2),
        ),
        AdminAuditLog(
            firm_id=firm.id, actor_user_id=ayse.id,
            action="create_task",
            details={"title": "Nakit akış projeksiyonu hazırla", "client": "Ege Yoga"},
            created_at=now - timedelta(days=1),
        ),
        # Phase 4: publish audit log entries
        AdminAuditLog(
            firm_id=firm.id, actor_user_id=ayse.id,
            action="publish_snapshot",
            details={
                "client_id": str(CLIENT_SEEDS[1].get("_client_id", "")),
                "period_label": "Geçen Ay",
                "note": "Anadolu Tekstil dönem özeti yayınlandı",
            },
            created_at=now - timedelta(days=8),
        ),
        AdminAuditLog(
            firm_id=firm.id, actor_user_id=ayse.id,
            action="publish_snapshot",
            details={
                "client_id": str(CLIENT_SEEDS[0].get("_client_id", "")),
                "period_label": "Geçen Ay",
                "note": "Boğaziçi Kahve dönem özeti yayınlandı",
            },
            created_at=now - timedelta(days=10),
        ),
    ]
    for e in entries:
        db.add(e)
    db.flush()
    print(f"{len(entries)} denetim günlüğü kaydı oluşturuldu")


if __name__ == "__main__":
    main()
