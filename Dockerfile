FROM python:3.12-slim

WORKDIR /code

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    tesseract-ocr \
    tesseract-ocr-tur \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /code/
RUN pip install --no-cache-dir -e .

COPY app /code/app
COPY alembic /code/alembic
COPY alembic.ini /code/alembic.ini
COPY scripts /code/scripts

# Where uploaded documents live (mounted volume in docker-compose)
RUN mkdir -p /code/uploaded_files

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
