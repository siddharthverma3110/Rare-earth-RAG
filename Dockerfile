FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Pre-build the search index at image build time (fast cold starts)
# Never let the index build break the image: if it fails, the app rebuilds the index at startup
RUN python -m scripts.ingest || echo "WARNING: index build failed during image build; it will be built at startup"
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
