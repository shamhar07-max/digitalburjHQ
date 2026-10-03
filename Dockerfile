FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HQ_ENV=production HQ_SECURE_COOKIE=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.txt && useradd --create-home --uid 10001 hq
COPY --chown=hq:hq . .
RUN mkdir -p /app/private && chown hq:hq /app/private
USER hq
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os; r=urllib.request.Request('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/readyz',headers={'Host':__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(os.environ['HQ_PUBLIC_URL']).netloc}); urllib.request.urlopen(r,timeout=3)"
CMD ["gunicorn","--config","gunicorn.conf.py","production:create_app()"]
