import requests
from requests.auth import HTTPBasicAuth
import datetime
import os
import yaml
from loguru import logger

# Настройки логирования
logger.add('./logs/today.log', rotation='1 day', retention='30 days')
LOCAL_BACKUP_DIR = "./goip_backup"  # Локальная директория для хранения бэкапов
BACKUP_RETENTION_DAYS = 7  # Период хранения бэкапов в днях


@logger.catch
def send_backup_to_telegram(file_path, tg_data):
    """Отправляет файл бэкапа в Telegram чат"""
    if not tg_data.get('CHAT_ID') or not tg_data.get('TOKEN'):
        logger.warning(f'Невозможно отправить {file_path}. Не указаны данные для Telegram: {tg_data}')
        return
    url = f"https://api.telegram.org/bot{tg_data['TOKEN']}/sendDocument"
    with open(file_path, "rb") as file:
        response = requests.post(url, data={"chat_id": tg_data['CHAT_ID']}, files={"document": file})
    
    if response.status_code == 200:
        logger.info(f"Бэкап {file_path} успешно отправлен в Telegram.")
    else:
        logger.warning(f"Ошибка при отправке {file_path} в Telegram: {response.text}")


@logger.catch
def create_backup(goip_data):
    """Создаёт резервную копию конфигурации GoIP и сохраняет её локально"""
    backup_url = f"http://{goip_data['host']}/default/en_US/config.dat"
    session = requests.Session()
    session.auth = HTTPBasicAuth(goip_data['user'], goip_data['password'])
    
    try:
        response = session.get(backup_url, stream=True)
        response.raise_for_status()

        # Создание имени файла с датой
        date_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        local_backup_path = os.path.join(LOCAL_BACKUP_DIR, f"{goip_data['name']}_backup_{date_str}.dat")

        # Сохранение бэкапа
        with open(local_backup_path, "wb") as backup_file:
            for chunk in response.iter_content(chunk_size=8192):
                backup_file.write(chunk)

        logger.info(f"Бэкап для {goip_data['name']} сохранён: {local_backup_path}")
        return local_backup_path

    except requests.RequestException as e:
        logger.error(f"Ошибка при создании или загрузке бэкапа для {goip_data['name']}: {e}")
        return None


@logger.catch
def delete_old_backups():
    """Удаляет файлы бэкапов старше заданного периода хранения"""
    now = datetime.datetime.now()
    for filename in os.listdir(LOCAL_BACKUP_DIR):
        file_path = os.path.join(LOCAL_BACKUP_DIR, filename)
        
        if os.path.isfile(file_path):
            file_creation_time = datetime.datetime.fromtimestamp(os.path.getctime(file_path))
            file_age_days = (now - file_creation_time).days
            
            if file_age_days > BACKUP_RETENTION_DAYS:
                os.remove(file_path)
                logger.info(f"Удалён старый бэкап: {file_path} (возраст: {file_age_days} дней)")


@logger.catch
def read_config():
    """Читает конфигурационный файл и возвращает данные"""
    try:
        with open('config.yml', 'r', encoding='utf8') as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        logger.error("Конфигурационный файл не найден.")
    except yaml.YAMLError as e:
        logger.error(f"Ошибка в формате конфигурационного файла: {e}")
    return None


@logger.catch
def parse_config(data):
    """Извлекает данные GoIP и Telegram из конфигурации"""
    goips = [
        {**val, 'name': key} for key, val in data.items() if key.startswith("Goip")
    ]
    if not goips:
        logger.warning("В конфиге нет настроек для бэкапа GoIP. "
                       "Конфиг должен содержать блоки в формате GoipXX:\n"
                       "host: ...\nuser: ...\npassword: ...")
    
    tg_data = data.get("Telegram", {})
    return goips, tg_data


@logger.catch
def main():
    # Подготовка локальной директории для бэкапов
    os.makedirs(LOCAL_BACKUP_DIR, exist_ok=True)
    
    # Чтение конфигурации
    data = read_config()
    if not data:
        logger.warning("Конфигурационный файл пуст или недоступен.")
        return

    goip_data_list, tg_data = parse_config(data)

    # Создание и отправка бэкапа для каждого GoIP
    for goip_data in goip_data_list:
        file_path = create_backup(goip_data)
        if file_path:
            send_backup_to_telegram(file_path, tg_data)
    
    # Удаление старых бэкапов
    delete_old_backups()

if __name__ == "__main__":
    main()
