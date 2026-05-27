# Обратный SOCKS5-прокси с шифрованием

Этот проект реализует обратный (reverse) SOCKS5-прокси на Python. Он позволяет машине, находящейся за NAT (Worker/Воркер), предоставлять функции прокси-сервера через машину с публичным IP-адресом (Bridge/Мост).

## Настройка

### 1. Генерация сертификатов
Для работы Bridge требуются TLS-сертификат и закрытый ключ. Выполните следующую команду для генерации самоподписанных сертификатов:

```bash
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes
```

### 2. Конфигурация
*   **Bridge (`bridge.py`)**:
    *   `PORT_CONTROL`: Порт, к которому подключается Worker (по умолчанию: 8443).
    *   `PORT_SOCKS`: Порт для пользователей SOCKS5 (по умолчанию: 1080).
    *   `SOCKS_USER` / `SOCKS_PASS`: Данные для авторизации пользователей.
*   **Worker (`worker.py`)**:
    *   `BRIDGE_HOST`: Укажите публичный IP-адрес вашего Bridge-сервера.
    *   `PORT_CONTROL`: Должен совпадать с портом управления на Bridge.

## Запуск

### Шаг 1: Запустите Bridge (на публичном IP)
```bash
python bridge.py
```

### Шаг 2: Запустите Worker (на сером IP за NAT)
```bash
python worker.py
```

## Использование
Подключитесь к IP-адресу Bridge на порт 1080, используя SOCKS5-клиент с настроенными учетными данными.

Пример с использованием `curl`:
```bash
curl --proxy-user user:pass --proxy socks5h://BRIDGE_IP:1080 https://ifconfig.me
```
(Возвращенный IP должен соответствовать IP-адресу машины, на которой запущен Worker).

## Автозагрузка в Linux (systemd)

Для того чтобы скрипты запускались автоматически при старте системы, рекомендуется использовать `systemd`.

### 1. Создайте файл сервиса
Создайте файл `/etc/systemd/system/proxy-bridge.service` (для Bridge) или `/etc/systemd/system/proxy-worker.service` (для Worker):

```ini
[Unit]
Description=Reverse SOCKS5 Proxy Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 /путь/к/скрипту/bridge.py
WorkingDirectory=/путь/к/папке/проекта
StandardOutput=inherit
StandardError=inherit
Restart=always
User=ваш_пользователь

[Install]
WantedBy=multi-user.target
```

### 2. Активируйте сервис
Выполните следующие команды в терминале:

```bash
# Перезагрузите конфигурацию systemd
sudo systemctl daemon-reload

# Включите автозапуск при старте системы
sudo systemctl enable proxy-bridge.service

# Запустите сервис прямо сейчас
sudo systemctl start proxy-bridge.service
```

### 3. Просмотр логов
Чтобы проверить работу сервиса, используйте команду:
```bash
journalctl -u proxy-bridge.service -f
```

## Примечание по безопасности
В данный момент `worker.py` настроен на пропуск проверки TLS-сертификата (`ssl.CERT_NONE`) для упрощения работы с самоподписанными сертификатами. Для использования в рабочей среде (production) следует загрузить `cert.pem` на стороне Worker и установить `ssl.CERT_REQUIRED`.
