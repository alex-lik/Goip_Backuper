import datetime
import os
from typing import Dict, List, Optional, Tuple

import requests
import yaml
from loguru import logger

LOCAL_BACKUP_DIR = "./goip_backup"
BACKUP_RETENTION_DAYS = 7
REQUEST_TIMEOUT = 30

logger.add("./logs/today.log", rotation="1 day", retention="30 days")


@logger.catch
def send_backup_to_telegram(file_path: str, tg_data: dict) -> None:
    """Отправляет файл бэкапа в Telegram-чат."""
    if not tg_data.get("CHAT_ID") or not tg_data.get("TOKEN"):
        logger.warning(f"Не заданы данные Telegram, отправка пропущена: {file_path}")
        return
    url = f"https://api.telegram.org/bot{tg_data['TOKEN']}/sendDocument"
    with open(file_path, "rb") as file:
        response = requests.post(
            url,
            data={"chat_id": tg_data["CHAT_ID"]},
            files={"document": file},
            timeout=REQUEST_TIMEOUT,
        )

    if response.status_code == 200:
        logger.info(f"Бэкап {file_path} отправлен в Telegram.")
    else:
        logger.warning(f"Ошибка отправки {file_path} в Telegram: {response.text}")


@logger.catch
def send_error_to_telegram(goip_data: dict, tg_data: dict) -> None:
    """Отправляет уведомление в Telegram при ошибке создания бэкапа."""
    if not tg_data.get("CHAT_ID") or not tg_data.get("TOKEN"):
        logger.warning("Не заданы данные Telegram, уведомление об ошибке пропущено.")
        return
    message = f"Ошибка при создании бэкапа для {goip_data.get('name')} ({goip_data.get('host')})"
    url = f"https://api.telegram.org/bot{tg_data['TOKEN']}/sendMessage"
    response = requests.post(
        url,
        data={"chat_id": tg_data["CHAT_ID"], "text": message},
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code == 200:
        logger.info(f"Уведомление об ошибке для {goip_data.get('name')} отправлено в Telegram.")
    else:
        logger.warning(f"Ошибка отправки уведомления в Telegram: {response.text}")


@logger.catch
def create_backup(goip_data: dict) -> Optional[str]:
    """Скачивает config.dat с устройства GoIP и сохраняет его локально."""
    backup_url = f"http://{goip_data['host']}/default/en_US/config.dat"
    session = requests.Session()
    session.auth = (goip_data["user"], goip_data["password"])

    try:
        response = session.get(backup_url, stream=True, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        date_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        local_backup_path = os.path.join(LOCAL_BACKUP_DIR, f"{goip_data['name']}_backup_{date_str}.dat")

        with open(local_backup_path, "wb") as backup_file:
            for chunk in response.iter_content(chunk_size=8192):
                backup_file.write(chunk)

        logger.info(f"Бэкап для {goip_data['name']} сохранён: {local_backup_path}")
        return local_backup_path

    except requests.RequestException as e:
        logger.error(f"Ошибка при создании бэкапа для {goip_data.get('name')}: {e}")
        return None


@logger.catch
def delete_old_backups() -> None:
    """Удаляет файлы бэкапов старше периода хранения."""
    now = datetime.datetime.now()
    for filename in os.listdir(LOCAL_BACKUP_DIR):
        file_path = os.path.join(LOCAL_BACKUP_DIR, filename)

        if not os.path.isfile(file_path):
            continue

        file_age_days = (now - datetime.datetime.fromtimestamp(os.path.getmtime(file_path))).days
        if file_age_days > BACKUP_RETENTION_DAYS:
            os.remove(file_path)
            logger.info(f"Удалён старый бэкап: {file_path} (возраст: {file_age_days} дней)")


@logger.catch
def read_config(path: str = "config.yml") -> Optional[dict]:
    """Читает YAML-конфиг и возвращает его содержимое."""
    try:
        with open(path, "r", encoding="utf8") as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        logger.error("Конфигурационный файл не найден.")
    except yaml.YAMLError as e:
        logger.error(f"Ошибка в формате конфигурационного файла: {e}")
    return None


@logger.catch
def parse_config(data: dict) -> Tuple[List[Dict], dict]:
    """Извлекает список устройств GoIP и настройки Telegram из конфига."""
    goips = []
    for key, val in data.items():
        if not key.startswith("Goip"):
            continue
        if not isinstance(val, dict) or not all(k in val for k in ("host", "user", "password")):
            logger.warning(f"Пропущена некорректная запись {key}: нужны host, user, password.")
            continue
        goips.append({**val, "name": key})

    if not goips:
        logger.warning(
            "В конфиге нет настроек для бэкапа GoIP. "
            "Конфиг должен содержать блоки в формате GoipXX: host, user, password."
        )

    tg_data = data.get("Telegram", {}) or {}
    return goips, tg_data


@logger.catch
def main() -> None:
    os.makedirs(LOCAL_BACKUP_DIR, exist_ok=True)

    data = read_config()
    if not data:
        logger.warning("Конфигурационный файл пуст или недоступен.")
        return

    goip_data_list, tg_data = parse_config(data)

    for goip_data in goip_data_list:
        file_path = create_backup(goip_data)
        if file_path:
            send_backup_to_telegram(file_path, tg_data)
        else:
            send_error_to_telegram(goip_data, tg_data)

    delete_old_backups()


if __name__ == "__main__":
    main()
