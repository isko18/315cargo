# Деплой 315CARGO Backend

Инструкция по развёртыванию на **VPS (Ubuntu 22.04/24.04)** с **PostgreSQL + Redis + Gunicorn + Nginx + Celery**.

---

## 0. Что понадобится

| Компонент | Минимум |
|---|---|
| VPS | 2 GB RAM, 1 vCPU, 20 GB SSD |
| ОС | Ubuntu 22.04 или 24.04 |
| Домен | например `api.315cargo.kg` |
| SSH-доступ | `root` или пользователь с sudo |
| Репозиторий | `https://github.com/isko18/315cargo.git` |

Сервисы на сервере: **Python 3.12**, **PostgreSQL 16**, **Redis 7**, **Nginx**, **Certbot** (SSL).

---

## 1. Подготовка проекта (локально, перед деплоем)

Сейчас в репозитории нет production-настроек. Добавьте перед первым деплоем.

### 1.1. Зависимости

В `requirements.txt` добавьте:

```txt
gunicorn
whitenoise
```

### 1.2. Настройки Django (`config/settings.py`)

Добавьте после блока `STATIC_URL`:

```python
STATIC_ROOT = BASE_DIR / "staticfiles"

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
```

В `MIDDLEWARE` — **сразу после** `SecurityMiddleware`:

```python
"whitenoise.middleware.WhiteNoiseMiddleware",
```

Для production (когда `DEBUG=False`) — в конец файла:

```python
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
```

### 1.3. Закоммитьте и запушьте

```bash
git add requirements.txt config/settings.py
git commit -m "Add production settings for deployment"
git push origin master
```

---

## 2. Первичная настройка сервера

Подключитесь по SSH:

```bash
ssh root@ВАШ_IP
```

### 2.1. Обновление системы и базовые пакеты

```bash
apt update && apt upgrade -y
apt install -y git curl ufw nginx certbot python3-certbot-nginx \
  postgresql postgresql-contrib redis-server \
  python3.12 python3.12-venv python3-pip build-essential libpq-dev
```

### 2.2. Firewall

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw enable
```

### 2.3. PostgreSQL

```bash
sudo -u postgres psql
```

В psql:

```sql
CREATE USER cargo_user WITH PASSWORD 'СЛОЖНЫЙ_ПАРОЛЬ';
CREATE DATABASE cargo_db OWNER cargo_user;
GRANT ALL PRIVILEGES ON DATABASE cargo_db TO cargo_user;
\q
```

### 2.4. Redis

Redis обычно уже запущен:

```bash
systemctl enable redis-server
systemctl status redis-server
```

---

## 3. Размещение приложения

### 3.1. Пользователь и директория

```bash
adduser --disabled-password --gecos "" cargo
mkdir -p /var/www/315cargo
chown cargo:cargo /var/www/315cargo
```

### 3.2. Клонирование репозитория

```bash
sudo -u cargo git clone https://github.com/isko18/315cargo.git /var/www/315cargo/app
cd /var/www/315cargo/app
```

### 3.3. Виртуальное окружение

```bash
sudo -u cargo python3.12 -m venv /var/www/315cargo/venv
sudo -u cargo /var/www/315cargo/venv/bin/pip install --upgrade pip
sudo -u cargo /var/www/315cargo/venv/bin/pip install -r requirements.txt
```

---

## 4. Файл `.env` на сервере

```bash
sudo -u cargo nano /var/www/315cargo/app/.env
```

Пример production-конфига:

```env
SECRET_KEY=сгенерируйте-длинную-случайную-строку-минимум-50-символов
DEBUG=False

DATABASE_URL=postgres://cargo_user:СЛОЖНЫЙ_ПАРОЛЬ@127.0.0.1:5432/cargo_db

ALLOWED_HOSTS=api.315cargo.kg,ВАШ_IP
CSRF_TRUSTED_ORIGINS=https://api.315cargo.kg

SMS_BACKEND=nikita
NIKITA_SMS_LOGIN=ваш_логин
NIKITA_SMS_PASSWORD=ваш_пароль
NIKITA_SMS_SENDER=315CARGO
NIKITA_SMS_TEST=0
NIKITA_SMS_BRAND=315CARGO

REDIS_URL=redis://127.0.0.1:6379/0

JWT_ACCESS_LIFETIME_MINUTES=60
JWT_REFRESH_LIFETIME_DAYS=30

ENABLE_API_DOCS=True

FCM_CREDENTIALS_PATH=/var/www/315cargo/secrets/firebase.json
PINDUODUO_CLIENT_PATH=
```

Сгенерировать `SECRET_KEY`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

Права на `.env`:

```bash
chmod 600 /var/www/315cargo/app/.env
```

Если используете Firebase — положите JSON:

```bash
mkdir -p /var/www/315cargo/secrets
nano /var/www/315cargo/secrets/firebase.json
chown -R cargo:cargo /var/www/315cargo/secrets
chmod 600 /var/www/315cargo/secrets/firebase.json
```

---

## 5. Первый запуск Django

```bash
cd /var/www/315cargo/app
sudo -u cargo /var/www/315cargo/venv/bin/python manage.py migrate
sudo -u cargo /var/www/315cargo/venv/bin/python manage.py collectstatic --noinput
sudo -u cargo /var/www/315cargo/venv/bin/python manage.py createsuperuser
```

Опционально — демо-данные:

```bash
sudo -u cargo /var/www/315cargo/venv/bin/python manage.py seed_demo
```

Проверка Nikita SMS:

```bash
sudo -u cargo /var/www/315cargo/venv/bin/python manage.py check_nikita_sms
```

---

## 6. Systemd-сервисы

### 6.1. Gunicorn (веб)

```bash
nano /etc/systemd/system/cargo-web.service
```

```ini
[Unit]
Description=315CARGO Gunicorn
After=network.target postgresql.service redis-server.service

[Service]
User=cargo
Group=cargo
WorkingDirectory=/var/www/315cargo/app
EnvironmentFile=/var/www/315cargo/app/.env
ExecStart=/var/www/315cargo/venv/bin/gunicorn config.wsgi:application \
  --bind 127.0.0.1:8000 \
  --workers 3 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 6.2. Celery worker

```bash
nano /etc/systemd/system/cargo-celery.service
```

```ini
[Unit]
Description=315CARGO Celery Worker
After=network.target redis-server.service

[Service]
User=cargo
Group=cargo
WorkingDirectory=/var/www/315cargo/app
EnvironmentFile=/var/www/315cargo/app/.env
ExecStart=/var/www/315cargo/venv/bin/celery -A config worker -l info
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 6.3. Celery beat (планировщик Pinduoduo)

```bash
nano /etc/systemd/system/cargo-celery-beat.service
```

```ini
[Unit]
Description=315CARGO Celery Beat
After=network.target redis-server.service

[Service]
User=cargo
Group=cargo
WorkingDirectory=/var/www/315cargo/app
EnvironmentFile=/var/www/315cargo/app/.env
ExecStart=/var/www/315cargo/venv/bin/celery -A config beat -l info
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Запуск:

```bash
systemctl daemon-reload
systemctl enable cargo-web cargo-celery cargo-celery-beat
systemctl start cargo-web cargo-celery cargo-celery-beat
systemctl status cargo-web cargo-celery cargo-celery-beat
```

---

## 7. Nginx

### 7.1. DNS

В панели домена создайте **A-запись**:

```
api.315cargo.kg  →  ВАШ_IP
```

### 7.2. Конфиг Nginx

```bash
nano /etc/nginx/sites-available/315cargo
```

```nginx
server {
    listen 80;
    server_name api.315cargo.kg;

    client_max_body_size 20M;

    location /static/ {
        alias /var/www/315cargo/app/staticfiles/;
    }

    location /media/ {
        alias /var/www/315cargo/app/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

Активация:

```bash
ln -s /etc/nginx/sites-available/315cargo /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

### 7.3. SSL (Let's Encrypt)

```bash
certbot --nginx -d api.315cargo.kg
```

Certbot сам настроит HTTPS и редирект с HTTP.

---

## 8. Nikita SMS — обязательно для production

В кабинете [smspro.nikita.kg](https://smspro.nikita.kg):

1. **Параметры API** — проверьте логин/пароль (те же, что в `.env`).
2. **Разрешённые IP** — добавьте **публичный IP вашего VPS** (иначе status `3`).
3. **Отправитель** `315CARGO` — должен быть одобрен.
4. **Баланс** — пополните (иначе status `4`).
5. На production: `NIKITA_SMS_TEST=0`, `NIKITA_SMS_ALLOWED_PHONE` можно убрать (это только для тестового аккаунта).

---

## 9. Проверка после деплоя

```bash
# Статус сервисов
systemctl status cargo-web cargo-celery cargo-celery-beat nginx

# Логи
journalctl -u cargo-web -f
journalctl -u cargo-celery -f
```

В браузере или curl:

| URL | Ожидание |
|---|---|
| `https://api.315cargo.kg/api/docs/` | Swagger UI |
| `https://api.315cargo.kg/admin/` | Django Admin |
| `POST https://api.315cargo.kg/api/auth/send-code/` | Отправка SMS |

Пример:

```bash
curl -X POST https://api.315cargo.kg/api/auth/send-code/ \
  -H "Content-Type: application/json" \
  -d '{"phone": "+996505180600"}'
```

---

## 10. Обновление после изменений в коде

На сервере:

```bash
cd /var/www/315cargo/app
sudo -u cargo git pull origin master
sudo -u cargo /var/www/315cargo/venv/bin/pip install -r requirements.txt
sudo -u cargo /var/www/315cargo/venv/bin/python manage.py migrate
sudo -u cargo /var/www/315cargo/venv/bin/python manage.py collectstatic --noinput
systemctl restart cargo-web cargo-celery cargo-celery-beat
```

---

## 11. Резервное копирование

### База данных (ежедневно через cron)

```bash
mkdir -p /var/backups
crontab -e
```

```cron
0 3 * * * pg_dump -U cargo_user cargo_db | gzip > /var/backups/cargo_db_$(date +\%F).sql.gz
```

### Медиа-файлы (QR-коды клиентов)

```bash
tar -czf /var/backups/cargo_media_$(date +%F).tar.gz /var/www/315cargo/app/media/
```

---

## 12. Чеклист перед go-live

- [ ] `DEBUG=False`
- [ ] Уникальный `SECRET_KEY`
- [ ] PostgreSQL (не SQLite)
- [ ] `ALLOWED_HOSTS` и `CSRF_TRUSTED_ORIGINS` с вашим доменом
- [ ] SSL работает (HTTPS)
- [ ] IP сервера добавлен в Nikita
- [ ] SMS отправляется на реальный номер
- [ ] Celery worker и beat запущены
- [ ] Создан superuser для админки
- [ ] Swagger доступен (или `ENABLE_API_DOCS=False` на prod, если не нужен публично)

---

## 13. Частые проблемы

| Симптом | Причина | Решение |
|---|---|---|
| `502 Bad Gateway` | Gunicorn не запущен | `systemctl status cargo-web`, смотреть логи |
| `DisallowedHost` | Нет домена в `ALLOWED_HOSTS` | Добавить домен/IP в `.env`, перезапустить |
| CSRF ошибка в admin | Нет `CSRF_TRUSTED_ORIGINS` | Добавить `https://ваш-домен` |
| SMS status `2` | Неверный логин/пароль Nikita | Проверить `.env` |
| SMS status `3` | IP не разрешён | Добавить IP VPS в кабинете Nikita |
| SMS status `4` | Нет баланса | Пополнить счёт |
| Статика admin не грузится | Не запускали collectstatic | `python manage.py collectstatic --noinput` |
| Celery не работает | Redis не запущен | `systemctl status redis-server` |

---

## 14. Альтернатива: Docker

Если нужен деплой через Docker — добавьте в репозиторий `Dockerfile` и `docker-compose.yml` (web, db, redis, celery, nginx). Сейчас их нет; инструкция выше — **без Docker**, напрямую на VPS.
