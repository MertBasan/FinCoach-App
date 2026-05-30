from pathlib import Path
from fastapi.templating import Jinja2Templates

from app.locale import (
    format_money_tr,
    format_date_tr,
    format_date_long_tr,
    format_period_tr,
    format_percent_tr,
)


TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Turkish locale formatters available in every template
templates.env.globals.update(
    money=format_money_tr,
    date_tr=format_date_tr,
    date_long_tr=format_date_long_tr,
    period_tr=format_period_tr,
    percent_tr=format_percent_tr,
)
