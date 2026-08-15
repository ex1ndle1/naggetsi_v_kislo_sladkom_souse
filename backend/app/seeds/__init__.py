"""Seeds package для демо-данных.

Без re-export из app.seeds.demo: модуль запускается как `python -m app.seeds.demo`,
и импорт здесь заставил бы интерпретатор загрузить его дважды (RuntimeWarning про
'found in sys.modules after import of package').
"""
