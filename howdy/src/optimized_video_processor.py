#!/usr/bin/env python3
"""
Оптимизированная система обработки видео с улучшенной производительностью
"""

import cv2
import numpy as np
import threading
import queue
import time
from collections import deque
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor, as_completed
from i18n import _
import os


class FrameBuffer:
    """Кольцевой буфер для эффективного хранения кадров"""
    
    def __init__(self, max_size=10):
        self.buffer = deque(maxlen=max_size)
        self.lock = threading.RLock()
        self.frame_metadata = deque(maxlen=max_size)
    
    def add_frame(self, frame, metadata=None):
        """Добавление кадра в буфер"""
        with self.lock:
            self.buffer.append(frame.copy())
            self.frame_metadata.append(metadata or {})
    
    def get_latest_frames(self, count=1):
        """Получение последних кадров"""
        with self.lock:
            if len(self.buffer) < count:
                return list(self.buffer), list(self.frame_metadata)
            return list(self.buffer)[-count:], list(self.frame_metadata)[-count:]
    
    def get_frame_history(self):
        """Получение всей истории кадров"""
        with self.lock:
            return list(self.buffer), list(self.frame_metadata)
    
    def clear(self):
        """Очистка буфера"""
        with self.lock:
            self.buffer.clear()
            self.frame_metadata.clear()


class AdaptiveFrameProcessor:
    """Адаптивный процессор кадров с динамической оптимизацией"""
    
    def __init__(self, config):
        self.config = config
        
        # Параметры адаптации
        self.target_fps = 15  # Целевой FPS
        self.min_fps = 5      # Минимальный FPS
        self.max_fps = 30     # Максимальный FPS
        
        # Динамические параметры
        self.current_skip_rate = 1  # Пропуск каждого N-го кадра
        self.current_resolution_scale = 1.0  # Масштаб разрешения
        self.processing_times = deque(maxlen=30)  # История времени обработки
        
        # Статистика
        self.stats = {
            'frames_processed': 0,
            'frames_skipped': 0,
            'average_processing_time': 0,
            'current_fps': 0,
            'resolution_adaptations': 0
        }
        
        # Пороги для адаптации
        self.slow_processing_threshold = 0.1  # 100ms
        self.fast_processing_threshold = 0.03  # 30ms
        
    def adapt_parameters(self, processing_time):
        """Адаптация параметров на основе времени обработки"""
        self.processing_times.append(processing_time)
        
        if len(self.processing_times) < 5:
            return
        
        avg_time = np.mean(list(self.processing_times)[-10:])
        
        # Если обработка медленная, увеличиваем пропуск кадров
        if avg_time > self.slow_processing_threshold:
            if self.current_skip_rate < 4:
                self.current_skip_rate += 1
                print(_("Adapting: increasing frame skip to {}").format(self.current_skip_rate))
            elif self.current_resolution_scale > 0.5:
                self.current_resolution_scale *= 0.8
                self.stats['resolution_adaptations'] += 1
                print(_("Adapting: reducing resolution scale to {:.2f}").format(self.current_resolution_scale))
        
        # Если обработка быстрая, можем уменьшить пропуск
        elif avg_time < self.fast_processing_threshold:
            if self.current_skip_rate > 1:
                self.current_skip_rate = max(1, self.current_skip_rate - 1)
                print(_("Adapting: reducing frame skip to {}").format(self.current_skip_rate))
            elif self.current_resolution_scale < 1.0:
                self.current_resolution_scale = min(1.0, self.current_resolution_scale * 1.1)
                print(_("Adapting: increasing resolution scale to {:.2f}").format(self.current_resolution_scale))
        
        # Обновляем статистику
        self.stats['average_processing_time'] = avg_time
        if avg_time > 0:
            self.stats['current_fps'] = 1.0 / avg_time
    
    def should_process_frame(self, frame_number):
        """Определение, нужно ли обрабатывать кадр"""
        if frame_number % self.current_skip_rate == 0:
            return True
        else:
            self.stats['frames_skipped'] += 1
            return False
    
    def prepare_frame(self, frame):
        """Подготовка кадра с учетом текущих параметров"""
        if self.current_resolution_scale != 1.0:
            height, width = frame.shape[:2]
            new_height = int(height * self.current_resolution_scale)
            new_width = int(width * self.current_resolution_scale)
            
            if new_height > 0 and new_width > 0:
                frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
        
        return frame


class ParallelVideoProcessor:
    """Параллельный процессор видео с многопоточностью"""
    
    def __init__(self, config, daemon_client):
        self.config = config
        self.daemon_client = daemon_client
        
        # Количество рабочих потоков
        self.num_workers = min(4, mp.cpu_count())
        
        # Очереди для работы
        self.input_queue = queue.Queue(maxsize=10)
        self.result_queue = queue.Queue()
        
        # Пул потоков
        self.executor = ThreadPoolExecutor(max_workers=self.num_workers)
        self.futures = []
        
        # Статистика
        self.processing_stats = {
            'total_frames': 0,
            'successful_detections': 0,
            'failed_detections': 0,
            'average_faces_per_frame': 0
        }
        
        # Флаг остановки
        self.stop_processing = threading.Event()
    
    def start_processing(self):
        """Запуск параллельной обработки"""
        for i in range(self.num_workers):
            future = self.executor.submit(self._worker_thread, i)
            self.futures.append(future)
    
    def _worker_thread(self, worker_id):
        """Рабочий поток для обработки кадров"""
        while not self.stop_processing.is_set():
            try:
                frame_data = self.input_queue.get(timeout=1.0)
                if frame_data is None:
                    break
                
                result = self._process_frame_data(frame_data, worker_id)
                if result:
                    self.result_queue.put(result)
                
                self.input_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(_("Error in worker thread {}: {}").format(worker_id, str(e)))
    
    def _process_frame_data(self, frame_data, worker_id):
        """Обработка данных кадра в рабочем потоке"""
        frame, gsframe, timestamp, frame_id = frame_data
        
        start_time = time.time()
        
        try:
            # Детекция лиц
            face_locations = self.daemon_client.detect_faces(gsframe)
            
            results = []
            for i, face_location in enumerate(face_locations):
                # Получение энкодинга лица
                face_encoding = self.daemon_client.get_face_encoding(frame, face_location)
                
                if face_encoding is not None:
                    results.append({
                        'face_location': face_location,
                        'face_encoding': face_encoding,
                        'face_id': f"{frame_id}_{i}",
                        'worker_id': worker_id
                    })
            
            processing_time = time.time() - start_time
            
            # Обновляем статистику
            self.processing_stats['total_frames'] += 1
            if results:
                self.processing_stats['successful_detections'] += 1
                self.processing_stats['average_faces_per_frame'] = (
                    (self.processing_stats['average_faces_per_frame'] * (self.processing_stats['total_frames'] - 1) + len(results)) /
                    self.processing_stats['total_frames']
                )
            else:
                self.processing_stats['failed_detections'] += 1
            
            return {
                'frame_id': frame_id,
                'timestamp': timestamp,
                'faces': results,
                'processing_time': processing_time,
                'worker_id': worker_id
            }
            
        except Exception as e:
            print(_("Error processing frame in worker {}: {}").format(worker_id, str(e)))
            return None
    
    def add_frame(self, frame, gsframe, timestamp=None, frame_id=None):
        """Добавление кадра для обработки"""
        if timestamp is None:
            timestamp = time.time()
        if frame_id is None:
            frame_id = f"frame_{int(timestamp * 1000)}"
        
        try:
            self.input_queue.put((frame, gsframe, timestamp, frame_id), block=False)
            return True
        except queue.Full:
            return False
    
    def get_result(self, timeout=0.1):
        """Получение результата обработки"""
        try:
            return self.result_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def stop(self):
        """Остановка обработки"""
        self.stop_processing.set()
        
        # Добавляем сигналы остановки для всех потоков
        for _ in range(self.num_workers):
            try:
                self.input_queue.put(None, block=False)
            except queue.Full:
                pass
        
        # Ждем завершения всех потоков
        for future in self.futures:
            try:
                future.result(timeout=2.0)
            except:
                pass
        
        self.executor.shutdown(wait=True)


class SmartFrameAnalyzer:
    """Умный анализатор кадров с предсказанием и кэшированием"""
    
    def __init__(self, config):
        self.config = config
        
        # Кэш для результатов анализа
        self.analysis_cache = {}
        self.cache_max_size = 100
        
        # История анализа для предсказаний
        self.frame_history = deque(maxlen=20)
        self.quality_history = deque(maxlen=10)
        
        # Параметры анализа качества
        self.blur_threshold = 100
        self.brightness_range = (50, 200)
        self.contrast_threshold = 30
        
    def analyze_frame_quality(self, frame):
        """Анализ качества кадра"""
        # Генерируем хэш кадра для кэширования
        frame_hash = self._generate_frame_hash(frame)
        
        if frame_hash in self.analysis_cache:
            return self.analysis_cache[frame_hash]
        
        # Преобразуем в градации серого если нужно
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame
        
        # Анализ резкости (размытия)
        blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
        is_sharp = blur_score > self.blur_threshold
        
        # Анализ яркости
        brightness = np.mean(gray)
        is_bright_enough = self.brightness_range[0] <= brightness <= self.brightness_range[1]
        
        # Анализ контрастности
        contrast = gray.std()
        has_good_contrast = contrast > self.contrast_threshold
        
        # Анализ равномерности освещения
        # Разделяем кадр на регионы и анализируем различия в освещении
        h, w = gray.shape
        regions = [
            gray[:h//2, :w//2],    # Верх-лево
            gray[:h//2, w//2:],    # Верх-право
            gray[h//2:, :w//2],    # Низ-лево
            gray[h//2:, w//2:]     # Низ-право
        ]
        
        region_means = [np.mean(region) for region in regions]
        lighting_variance = np.var(region_means)
        has_even_lighting = lighting_variance < 500  # Настраиваемый порог
        
        # Общая оценка качества
        quality_score = sum([
            is_sharp * 0.3,
            is_bright_enough * 0.25,
            has_good_contrast * 0.25,
            has_even_lighting * 0.2
        ])
        
        result = {
            'blur_score': blur_score,
            'is_sharp': is_sharp,
            'brightness': brightness,
            'is_bright_enough': is_bright_enough,
            'contrast': contrast,
            'has_good_contrast': has_good_contrast,
            'lighting_variance': lighting_variance,
            'has_even_lighting': has_even_lighting,
            'quality_score': quality_score,
            'is_good_quality': quality_score > 0.7
        }
        
        # Кэшируем результат
        self._cache_result(frame_hash, result)
        
        # Добавляем в историю
        self.quality_history.append(quality_score)
        
        return result
    
    def _generate_frame_hash(self, frame):
        """Генерация хэша кадра для кэширования"""
        # Простой хэш на основе среднего значения пикселей и размера
        if len(frame.shape) == 3:
            mean_val = np.mean(frame)
        else:
            mean_val = np.mean(frame)
        
        h, w = frame.shape[:2]
        return f"{h}x{w}_{mean_val:.2f}_{np.std(frame):.2f}"
    
    def _cache_result(self, frame_hash, result):
        """Кэширование результата анализа"""
        if len(self.analysis_cache) >= self.cache_max_size:
            # Удаляем старые записи
            oldest_key = next(iter(self.analysis_cache))
            del self.analysis_cache[oldest_key]
        
        self.analysis_cache[frame_hash] = result
    
    def predict_next_frame_quality(self):
        """Предсказание качества следующего кадра на основе истории"""
        if len(self.quality_history) < 3:
            return 0.5  # Нейтральное предсказание
        
        recent_scores = list(self.quality_history)[-5:]
        
        # Простое предсказание на основе тренда
        if len(recent_scores) >= 3:
            trend = np.polyfit(range(len(recent_scores)), recent_scores, 1)[0]
            last_score = recent_scores[-1]
            predicted_score = last_score + trend
            
            return max(0, min(1, predicted_score))
        
        return np.mean(recent_scores)
    
    def should_process_frame_based_on_prediction(self):
        """Определение необходимости обработки на основе предсказания"""
        predicted_quality = self.predict_next_frame_quality()
        return predicted_quality > 0.6  # Обрабатываем только если ожидается хорошее качество


class OptimizedVideoCapture:
    """Оптимизированный захват видео с умным буферизованием"""
    
    def __init__(self, config):
        self.config = config
        
        # Базовый захват видео
        from recorders.video_capture import VideoCapture
        self.base_capture = VideoCapture(config)
        
        # Компоненты оптимизации
        self.frame_buffer = FrameBuffer(max_size=15)
        self.adaptive_processor = AdaptiveFrameProcessor(config)
        self.frame_analyzer = SmartFrameAnalyzer(config)
        
        # Статистика
        self.capture_stats = {
            'total_frames_captured': 0,
            'frames_processed': 0,
            'frames_skipped_quality': 0,
            'frames_skipped_adaptive': 0,
            'average_capture_time': 0
        }
        
        # Настройки
        self.enable_quality_filtering = config.getboolean("video", "enable_quality_filtering", fallback=True)
        self.enable_adaptive_processing = config.getboolean("video", "enable_adaptive_processing", fallback=True)
        
        self.frame_counter = 0
    
    def read_optimized_frame(self):
        """Оптимизированное чтение кадра"""
        start_time = time.time()
        
        # Захватываем кадр
        try:
            frame, gsframe = self.base_capture.read_frame()
        except Exception as e:
            print(_("Error capturing frame: {}").format(str(e)))
            return None, None
        
        self.frame_counter += 1
        self.capture_stats['total_frames_captured'] += 1
        
        # Проверяем, нужно ли обрабатывать кадр (адаптивная обработка)
        if self.enable_adaptive_processing:
            if not self.adaptive_processor.should_process_frame(self.frame_counter):
                self.capture_stats['frames_skipped_adaptive'] += 1
                return None, None
        
        # Анализируем качество кадра
        if self.enable_quality_filtering:
            quality_analysis = self.frame_analyzer.analyze_frame_quality(frame)
            
            if not quality_analysis['is_good_quality']:
                self.capture_stats['frames_skipped_quality'] += 1
                return None, None
        
        # Подготавливаем кадр с учетом адаптивных параметров
        if self.enable_adaptive_processing:
            frame = self.adaptive_processor.prepare_frame(frame)
            gsframe = self.adaptive_processor.prepare_frame(gsframe)
        
        # Добавляем кадр в буфер
        frame_metadata = {
            'timestamp': time.time(),
            'frame_number': self.frame_counter,
            'quality_analysis': quality_analysis if self.enable_quality_filtering else None
        }
        
        self.frame_buffer.add_frame(frame, frame_metadata)
        
        # Обновляем статистику
        capture_time = time.time() - start_time
        self.capture_stats['frames_processed'] += 1
        self.capture_stats['average_capture_time'] = (
            (self.capture_stats['average_capture_time'] * (self.capture_stats['frames_processed'] - 1) + capture_time) /
            self.capture_stats['frames_processed']
        )
        
        # Адаптируем параметры
        if self.enable_adaptive_processing:
            self.adaptive_processor.adapt_parameters(capture_time)
        
        return frame, gsframe
    
    def get_frame_buffer_stats(self):
        """Получение статистики буфера кадров"""
        frames, metadata = self.frame_buffer.get_frame_history()
        
        if not metadata:
            return {}
        
        quality_scores = []
        for meta in metadata:
            if meta and 'quality_analysis' in meta and meta['quality_analysis']:
                quality_scores.append(meta['quality_analysis']['quality_score'])
        
        return {
            'buffer_size': len(frames),
            'average_quality': np.mean(quality_scores) if quality_scores else 0,
            'quality_variance': np.var(quality_scores) if quality_scores else 0,
            'capture_stats': self.capture_stats.copy(),
            'adaptive_stats': self.adaptive_processor.stats.copy()
        }
    
    def release(self):
        """Освобождение ресурсов"""
        if hasattr(self, 'base_capture'):
            self.base_capture.release()
        
        self.frame_buffer.clear()


def create_optimized_video_system(config, daemon_client):
    """Фабричная функция для создания оптимизированной видео системы"""
    
    # Создаем оптимизированный захват видео
    video_capture = OptimizedVideoCapture(config)
    
    # Создаем параллельный процессор
    parallel_processor = ParallelVideoProcessor(config, daemon_client)
    parallel_processor.start_processing()
    
    return {
        'video_capture': video_capture,
        'parallel_processor': parallel_processor,
        'frame_buffer': video_capture.frame_buffer,
        'adaptive_processor': video_capture.adaptive_processor,
        'frame_analyzer': video_capture.frame_analyzer
    }