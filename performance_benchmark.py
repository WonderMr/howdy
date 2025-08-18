#!/usr/bin/env python3
"""
Скрипт для тестирования производительности оптимизированной версии Howdy
"""

import time
import sys
import os
import subprocess
import json
import statistics
import argparse
from datetime import datetime, timedelta
import psutil


class HowdyPerformanceBenchmark:
    """Бенчмарк производительности Howdy"""
    
    def __init__(self):
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'system_info': self.get_system_info(),
            'tests': {}
        }
    
    def get_system_info(self):
        """Получение информации о системе"""
        return {
            'cpu_count': psutil.cpu_count(),
            'memory_total': psutil.virtual_memory().total,
            'python_version': sys.version,
            'platform': sys.platform
        }
    
    def run_daemon_startup_test(self, iterations=3):
        """Тест времени запуска daemon"""
        print("🚀 Тестирование времени запуска daemon...")
        
        startup_times = []
        
        for i in range(iterations):
            print(f"  Итерация {i+1}/{iterations}")
            
            # Останавливаем daemon если запущен
            subprocess.run(['systemctl', 'stop', 'howdy-daemon.service'], 
                         capture_output=True)
            time.sleep(2)
            
            # Засекаем время запуска
            start_time = time.time()
            
            result = subprocess.run(['systemctl', 'start', 'howdy-daemon.service'], 
                                  capture_output=True)
            
            if result.returncode != 0:
                print(f"    ❌ Ошибка запуска daemon")
                continue
            
            # Ждем готовности daemon
            max_wait = 10
            wait_start = time.time()
            
            while time.time() - wait_start < max_wait:
                try:
                    result = subprocess.run([
                        'python3', '-c', 
                        'from howdy.src.model_daemon import HowdyDaemonClient; '
                        'c = HowdyDaemonClient(); '
                        'exit(0 if c.is_daemon_running() else 1)'
                    ], capture_output=True, timeout=2)
                    
                    if result.returncode == 0:
                        break
                except:
                    pass
                
                time.sleep(0.1)
            
            startup_time = time.time() - start_time
            startup_times.append(startup_time)
            print(f"    ⏱️  Время запуска: {startup_time:.2f}s")
        
        if startup_times:
            avg_time = statistics.mean(startup_times)
            min_time = min(startup_times)
            max_time = max(startup_times)
            
            self.results['tests']['daemon_startup'] = {
                'average': avg_time,
                'min': min_time,
                'max': max_time,
                'samples': startup_times
            }
            
            print(f"  📊 Среднее время запуска: {avg_time:.2f}s")
            print(f"  📊 Минимальное время: {min_time:.2f}s")
            print(f"  📊 Максимальное время: {max_time:.2f}s")
        else:
            print("  ❌ Не удалось получить данные о времени запуска")
    
    def run_authentication_test(self, username, iterations=5):
        """Тест времени аутентификации"""
        print(f"🔐 Тестирование времени аутентификации для {username}...")
        
        auth_times = []
        success_count = 0
        
        for i in range(iterations):
            print(f"  Итерация {i+1}/{iterations}")
            
            start_time = time.time()
            
            # Запускаем тест аутентификации
            result = subprocess.run([
                'timeout', '10',
                'python3', '/lib/security/howdy/compare.py', username
            ], capture_output=True, text=True)
            
            auth_time = time.time() - start_time
            
            if result.returncode == 0:
                success_count += 1
                auth_times.append(auth_time)
                print(f"    ✅ Успешно за {auth_time:.2f}s")
            else:
                print(f"    ❌ Неудачно за {auth_time:.2f}s (код: {result.returncode})")
        
        if auth_times:
            avg_time = statistics.mean(auth_times)
            min_time = min(auth_times)
            max_time = max(auth_times)
            success_rate = success_count / iterations * 100
            
            self.results['tests']['authentication'] = {
                'average': avg_time,
                'min': min_time,
                'max': max_time,
                'success_rate': success_rate,
                'samples': auth_times
            }
            
            print(f"  📊 Среднее время аутентификации: {avg_time:.2f}s")
            print(f"  📊 Минимальное время: {min_time:.2f}s")
            print(f"  📊 Максимальное время: {max_time:.2f}s")
            print(f"  📊 Процент успеха: {success_rate:.1f}%")
        else:
            print("  ❌ Не удалось получить данные об аутентификации")
    
    def run_memory_usage_test(self, duration=30):
        """Тест использования памяти"""
        print(f"🧠 Тестирование использования памяти ({duration}s)...")
        
        memory_samples = []
        start_time = time.time()
        
        # Находим процесс daemon
        daemon_pid = None
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if 'model_daemon.py' in ' '.join(proc.info['cmdline'] or []):
                    daemon_pid = proc.info['pid']
                    break
            except:
                continue
        
        if not daemon_pid:
            print("  ❌ Daemon процесс не найден")
            return
        
        daemon_process = psutil.Process(daemon_pid)
        
        while time.time() - start_time < duration:
            try:
                memory_info = daemon_process.memory_info()
                memory_mb = memory_info.rss / 1024 / 1024
                memory_samples.append(memory_mb)
                time.sleep(1)
            except:
                break
        
        if memory_samples:
            avg_memory = statistics.mean(memory_samples)
            min_memory = min(memory_samples)
            max_memory = max(memory_samples)
            
            self.results['tests']['memory_usage'] = {
                'average_mb': avg_memory,
                'min_mb': min_memory,
                'max_mb': max_memory,
                'samples': memory_samples
            }
            
            print(f"  📊 Среднее использование памяти: {avg_memory:.1f} MB")
            print(f"  📊 Минимальное: {min_memory:.1f} MB")
            print(f"  📊 Максимальное: {max_memory:.1f} MB")
        else:
            print("  ❌ Не удалось получить данные о памяти")
    
    def run_daemon_stats_test(self):
        """Тест статистики daemon"""
        print("📈 Получение статистики daemon...")
        
        try:
            result = subprocess.run([
                'python3', '-c',
                'from howdy.src.model_daemon import HowdyDaemonClient; '
                'import json; '
                'c = HowdyDaemonClient(); '
                'stats = c.send_request({"type": "get_stats"}); '
                'print(json.dumps(stats) if stats else "{}")'
            ], capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0 and result.stdout.strip():
                stats = json.loads(result.stdout.strip())
                self.results['tests']['daemon_stats'] = stats
                
                print("  📊 Статистика daemon:")
                for key, value in stats.items():
                    if isinstance(value, float):
                        print(f"    {key}: {value:.3f}")
                    else:
                        print(f"    {key}: {value}")
            else:
                print("  ❌ Не удалось получить статистику daemon")
                
        except Exception as e:
            print(f"  ❌ Ошибка получения статистики: {e}")
    
    def run_comparison_test(self, username):
        """Сравнение оригинальной и оптимизированной версий"""
        print("⚖️  Сравнение производительности...")
        
        # Тест оригинальной версии
        print("  Тестирование оригинальной версии...")
        
        # Временно переключаемся на оригинальную версию
        subprocess.run(['systemctl', 'stop', 'howdy-daemon.service'], capture_output=True)
        
        if os.path.exists('/lib/security/howdy/compare_original.py'):
            # Создаем временную ссылку
            subprocess.run(['rm', '-f', '/lib/security/howdy/compare.py'], capture_output=True)
            subprocess.run(['ln', '-s', '/lib/security/howdy/compare_original.py', 
                          '/lib/security/howdy/compare.py'], capture_output=True)
            
            original_times = []
            for i in range(3):
                start_time = time.time()
                result = subprocess.run([
                    'timeout', '15',
                    'python3', '/lib/security/howdy/compare.py', username
                ], capture_output=True)
                
                if result.returncode == 0:
                    original_times.append(time.time() - start_time)
            
            # Возвращаем оптимизированную версию
            subprocess.run(['rm', '-f', '/lib/security/howdy/compare.py'], capture_output=True)
            subprocess.run(['ln', '-s', '/lib/security/howdy/compare_optimized.py', 
                          '/lib/security/howdy/compare.py'], capture_output=True)
            subprocess.run(['systemctl', 'start', 'howdy-daemon.service'], capture_output=True)
            time.sleep(3)
            
            # Тест оптимизированной версии
            print("  Тестирование оптимизированной версии...")
            optimized_times = []
            for i in range(3):
                start_time = time.time()
                result = subprocess.run([
                    'timeout', '10',
                    'python3', '/lib/security/howdy/compare.py', username
                ], capture_output=True)
                
                if result.returncode == 0:
                    optimized_times.append(time.time() - start_time)
            
            # Сравнение результатов
            if original_times and optimized_times:
                orig_avg = statistics.mean(original_times)
                opt_avg = statistics.mean(optimized_times)
                improvement = ((orig_avg - opt_avg) / orig_avg) * 100
                
                self.results['tests']['comparison'] = {
                    'original_average': orig_avg,
                    'optimized_average': opt_avg,
                    'improvement_percent': improvement,
                    'original_samples': original_times,
                    'optimized_samples': optimized_times
                }
                
                print(f"  📊 Оригинальная версия: {orig_avg:.2f}s")
                print(f"  📊 Оптимизированная версия: {opt_avg:.2f}s")
                print(f"  📊 Улучшение: {improvement:.1f}%")
            else:
                print("  ❌ Недостаточно данных для сравнения")
        else:
            print("  ❌ Оригинальная версия не найдена")
    
    def generate_report(self, output_file=None):
        """Генерация отчета о производительности"""
        if output_file is None:
            output_file = f"howdy_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\n📄 Отчет сохранен в: {output_file}")
        
        # Краткий отчет в консоль
        print("\n" + "="*50)
        print("📊 КРАТКИЙ ОТЧЕТ О ПРОИЗВОДИТЕЛЬНОСТИ")
        print("="*50)
        
        if 'daemon_startup' in self.results['tests']:
            startup = self.results['tests']['daemon_startup']
            print(f"🚀 Запуск daemon: {startup['average']:.2f}s (среднее)")
        
        if 'authentication' in self.results['tests']:
            auth = self.results['tests']['authentication']
            print(f"🔐 Аутентификация: {auth['average']:.2f}s (среднее)")
            print(f"   Успешность: {auth['success_rate']:.1f}%")
        
        if 'memory_usage' in self.results['tests']:
            memory = self.results['tests']['memory_usage']
            print(f"🧠 Память: {memory['average_mb']:.1f} MB (среднее)")
        
        if 'comparison' in self.results['tests']:
            comp = self.results['tests']['comparison']
            print(f"⚖️  Улучшение: {comp['improvement_percent']:.1f}%")
        
        print("="*50)


def main():
    parser = argparse.ArgumentParser(description="Бенчмарк производительности Howdy")
    parser.add_argument('--user', '-u', required=True, help='Имя пользователя для тестирования')
    parser.add_argument('--output', '-o', help='Файл для сохранения результатов')
    parser.add_argument('--iterations', '-i', type=int, default=3, 
                       help='Количество итераций для тестов')
    parser.add_argument('--memory-duration', type=int, default=30,
                       help='Длительность теста памяти в секундах')
    parser.add_argument('--skip-comparison', action='store_true',
                       help='Пропустить сравнение с оригинальной версией')
    
    args = parser.parse_args()
    
    print("🧪 Howdy Performance Benchmark")
    print("="*40)
    print(f"Пользователь: {args.user}")
    print(f"Итерации: {args.iterations}")
    print(f"Длительность теста памяти: {args.memory_duration}s")
    print("="*40)
    
    benchmark = HowdyPerformanceBenchmark()
    
    try:
        # Запуск тестов
        benchmark.run_daemon_startup_test(args.iterations)
        print()
        
        benchmark.run_authentication_test(args.user, args.iterations)
        print()
        
        benchmark.run_memory_usage_test(args.memory_duration)
        print()
        
        benchmark.run_daemon_stats_test()
        print()
        
        if not args.skip_comparison:
            benchmark.run_comparison_test(args.user)
            print()
        
        # Генерация отчета
        benchmark.generate_report(args.output)
        
    except KeyboardInterrupt:
        print("\n❌ Тестирование прервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка во время тестирования: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()