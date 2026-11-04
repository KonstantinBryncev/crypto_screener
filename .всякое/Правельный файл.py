Шаг 1: Базовая настройка и защита Ubuntu 24.04

"Настройка убунты"
sudo apt update && sudo apt upgrade -y
sudo timedatectl set-timezone Europe/Moscow

"Конфигурация UFW: последовательное разрешение SSH, открытие порта прокси-сервера 3128 и запуск межсетевого экрана"
sudo ufw allow ssh
sudo ufw allow 3128/tc
sudo ufw enable

"Установка пакета Squid и набора утилит Apache для генерации защищенных паролей"
sudo apt install squid apache2-utils -y

"Создание дубликата исходного конфигурационного файла Squid перед внесением изменений"
sudo cp /etc/squid/squid.conf /etc/squid/squid.conf.bak

"Генерация файла скрытых паролей и создание пользователя (замените 'proxy_user' на желаемое имя)"
sudo htpasswd -c /etc/squid/passwords proxy_user

"Перезапуск системной службы Squid для загрузки новых правил и добавление процесса в автозапуск операционной системы"
sudo systemctl restart squid

"Проверка текущего статуса работы демона Squid в системе"
sudo systemctl status squid

sudo htpasswd -c /etc/squid/passwords qqqqq

  "squid_config_file": {
    "target_path": 
    "/etc/squid/squid.conf",
    "insert_at_the_top": [
      "auth_param basic program /usr/lib/squid/basic_ncsa_auth /etc/squid/passwords",
      "auth_param basic children 5",
      "auth_param basic realm My Private Proxy Server",
      "auth_param basic credentialsttl 2 hours",
      "acl authenticated_users proxy_auth REQUIRED",
      "http_access allow authenticated_users",
      "http_access deny all"
    ],
    "insert_at_the_bottom": [
      "forwarded_for off",
      "request_header_access Via deny all",
      "request_header_access X-Forwarded-For deny all"
    ]
  },
  "local_testing": {
    "description": "Команда для внешней проверки работоспособности и анонимности созданного HTTP-прокси (замените 'ваш_пароль' на установленный на шаге 7)",
    "command": "curl -x http://proxy_user:ваш_пароль@138.249.8.195:3128 https://ifconfig.me"
  }
curl -x SOCKS5://proxyspoil:92922700@138.249.8.195:1080 https://ifconfig.me

"Скройте"
 реальный IP-адрес, сделайте прокси анонимным Чтобы прокси не передавал сайтам ваш реальный IP через заголовки, добавьте в самый конец файла squid.conf следующие директивы
forwarded_for off
request_header_access Via deny all
request_header_access X-Forwarded-For deny all




ssh root@138.249.8.195:3128
/etc/squid/squid.conf