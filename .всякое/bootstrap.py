import os

# Описываем структуру: Ключ - это папка, значение - список файлов в ней
PROJECT_STRUCTURE = {
	"": ["main.py", "requirements.txt"], # Файлы в корне проекта
	"config": ["__init__.py", "settings.py", "proxies.txt"],
	"core": ["__init__.py", "manager.py", "analyzer.py"],
	"exchanges": ["__init__.py", "base.py", "bybit.py"],
	"network": ["__init__.py", "client.py"],
	"database": ["__init__.py", "storage.py"],
	"notifications": ["__init__.py", "console.py", "telegram.py"]
}

def create_project():
	# Определяем корневую директорию как текущую папку, где запущен скрипт
	root_dir = os.getcwd()
	print(f"🚀 Начинаем развертывание проекта в: {root_dir}\n")

	for folder, files in PROJECT_STRUCTURE.items():
		# Формируем полный путь к папке
		folder_path = os.path.join(root_dir, folder) if folder else root_dir
		
		# Создаем папку, если её еще нет (кроме корня)
		if folder:
			if not os.path.exists(folder_path):
				os.makedirs(folder_path)
				print(f"📁 Создана папка: {folder}/")
			else:
				print(f"📂 Папка уже существует: {folder}/")
		
		# Создаем файлы внутри папки
		for file in files:
			file_path = os.path.join(folder_path, file)
			if not os.path.exists(file_path):
				with open(file_path, "w", encoding="utf-8") as f:
					# Добавляем базовый комментарий для файлов Python, чтобы они не были совсем пустыми
					if file.endswith(".py") and file != "__init__.py":
						f.write(f'# Модуль: {folder}/{file if folder else file}\n')
				print(f"   📄 Создан файл: {file}")
			else:
				print(f"   ⚠️ Файл уже существует: {file}")

	print("\n✅ Готово! Все папки и файлы структуры успешно созданы.")

if __name__ == "__main__":
	create_project()
