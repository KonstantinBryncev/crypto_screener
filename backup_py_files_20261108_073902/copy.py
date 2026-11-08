# Файл: copy_py_files.py
import os
import shutil
from datetime import datetime

def copy_all_py_files():
	# Определяем корень проекта (где лежит этот скрипт)
	project_root = os.path.dirname(os.path.abspath(__file__))
	
	# Создаем имя для отдельной папки с отметкой даты и времени
	timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
	output_dir_name = f"backup_py_files_{timestamp}"
	output_dir = os.path.join(project_root, output_dir_name)
	
	print(f"🚀 Начинаем копирование .py файлов из: {project_root}")
	print(f"📁 Папка назначения: {output_dir}")
	
	# Создаем целевую директорию, если её нет
	os.makedirs(output_dir, exist_ok=True)
	
	copied_count = 0
	
	# Обходим все папки и файлы в проекте
	for root, dirs, files in os.walk(project_root):
		# Исключаем виртуальное окружение и саму целевую папку, чтобы не гонять файлы по кругу
		if '.venv' in root or output_dir_name in root or '__pycache__' in root:
			continue
			
		for file in files:
			if file.endswith('.py') and file != 'copy_py_files.py':
				# Полный путь к исходному файлу
				src_file = os.path.join(root, file)
				
				# Формируем красивое уникальное имя для копии, сохраняя структуру папок в названии
				# Например: core_analyzer.py или exchanges_bybit.py
				relative_path = os.path.relpath(root, project_root)
				if relative_path == '.':
					new_file_name = file
				else:
					clean_rel_path = relative_path.replace(os.sep, '_')
					new_file_name = f"{clean_rel_path}_{file}"
					
				dst_file = os.path.join(output_dir, new_file_name)
				
				try:
					shutil.copy2(src_file, dst_file)
					print(f"✅ Скопирован: {os.path.relpath(src_file, project_root)} ➔ {new_file_name}")
					copied_count += 1
				except Exception as e:
					print(f"❌ Ошибка копирования {file}: {e}")
					
	print(f"\n🎉 Готово! Всего скопировано файлов: {copied_count}")
	print(f"📍 Все файлы сохранены в папке: {output_dir}")

if __name__ == "__main__":
	copy_all_py_files()
