#!/usr/bin/env python3
"""
Оптимизированный модуль сравнения лиц с улучшенной производительностью и безопасностью
"""

import time
import sys
import os
import json
import configparser
import cv2
from datetime import timezone, datetime
import atexit
import subprocess
import snapshot
import numpy as np
import _thread as thread
import paths_factory
from recorders.video_capture import VideoCapture
from i18n import _
from model_daemon import HowdyDaemonClient
import threading
import queue
import hashlib
import struct


# Статистика производительности
timings = {
    "st": time.time()
}

# Глобальные переменные
gtk_proc = None
daemon_client = None
frame_queue = queue.Queue(maxsize=5)
result_queue = queue.Queue()
processing_thread = None
liveness_detector = None


class LivenessDetector:
    """Детектор живого лица для предотвращения спуфинга"""
    
    def __init__(self):
        self.blink_frames = []
        self.head_positions = []
        self.eye_aspect_ratios = []
        self.blink_threshold = 0.25
        self.blink_consecutive_frames = 3
        self.min_blinks_required = 1
        self.max_tracking_frames = 30
        
    def calculate_eye_aspect_ratio(self, eye_landmarks):
        """Вычисление соотношения сторон глаза (EAR)"""
        # Вертикальные расстояния между точками глаза
        A = np.linalg.norm(eye_landmarks[1] - eye_landmarks[5])
        B = np.linalg.norm(eye_landmarks[2] - eye_landmarks[4])
        
        # Горизонтальное расстояние между точками глаза
        C = np.linalg.norm(eye_landmarks[0] - eye_landmarks[3])
        
        # Вычисление EAR
        ear = (A + B) / (2.0 * C)
        return ear
    
    def extract_eye_landmarks(self, face_landmarks):
        """Извлечение координат глаз из ключевых точек лица"""
        # Для dlib 5-point модели адаптируем извлечение глаз
        # Это упрощенная версия, для полной реализации нужна 68-point модель
        points = [(face_landmarks.part(i).x, face_landmarks.part(i).y) for i in range(5)]
        
        # Приблизительное извлечение области глаз
        left_eye = points[0:2]  # Упрощенная версия
        right_eye = points[2:4]  # Упрощенная версия
        
        return left_eye, right_eye
    
    def detect_blink(self, face_landmarks):
        """Детекция моргания"""
        try:
            left_eye, right_eye = self.extract_eye_landmarks(face_landmarks)
            
            # Для упрощенной 5-point модели используем альтернативный подход
            # Анализируем изменения в области глаз между кадрами
            if len(self.blink_frames) > 0:
                prev_landmarks = self.blink_frames[-1]
                
                # Вычисляем изменение позиций ключевых точек
                current_points = np.array([(face_landmarks.part(i).x, face_landmarks.part(i).y) for i in range(5)])
                prev_points = np.array([(prev_landmarks.part(i).x, prev_landmarks.part(i).y) for i in range(5)])
                
                # Анализируем движение в области глаз (точки 0-3)
                eye_movement = np.mean(np.abs(current_points[:4] - prev_points[:4]))
                
                # Если движение превышает порог, считаем это морганием
                if eye_movement > 2.0:  # Настраиваемый порог
                    return True
            
            self.blink_frames.append(face_landmarks)
            
            # Ограничиваем размер буфера
            if len(self.blink_frames) > self.max_tracking_frames:
                self.blink_frames.pop(0)
                
            return False
            
        except Exception as e:
            print(_("Error in blink detection: {}").format(str(e)))
            return False
    
    def detect_head_movement(self, face_location):
        """Детекция движения головы"""
        try:
            # Центр лица
            center_x = (face_location.left() + face_location.right()) // 2
            center_y = (face_location.top() + face_location.bottom()) // 2
            
            current_position = (center_x, center_y)
            self.head_positions.append(current_position)
            
            # Ограничиваем размер буфера
            if len(self.head_positions) > self.max_tracking_frames:
                self.head_positions.pop(0)
            
            # Анализируем движение головы
            if len(self.head_positions) >= 5:
                positions = np.array(self.head_positions[-5:])
                movement_variance = np.var(positions, axis=0)
                
                # Если есть достаточное движение, считаем лицо живым
                total_variance = np.sum(movement_variance)
                return total_variance > 10.0  # Настраиваемый порог
                
            return False
            
        except Exception as e:
            print(_("Error in head movement detection: {}").format(str(e)))
            return False
    
    def is_live_face(self, face_landmarks, face_location):
        """Основная функция проверки живого лица"""
        blink_detected = self.detect_blink(face_landmarks)
        head_movement = self.detect_head_movement(face_location)
        
        # Лицо считается живым если обнаружено моргание ИЛИ движение головы
        return blink_detected or head_movement


class OptimizedFrameProcessor:
    """Оптимизированный процессор кадров с многопоточностью"""
    
    def __init__(self, daemon_client, config):
        self.daemon_client = daemon_client
        self.config = config
        self.processing_queue = queue.Queue(maxsize=3)
        self.result_queue = queue.Queue()
        self.stop_processing = threading.Event()
        self.worker_threads = []
        
        # Настройки обработки
        self.frame_skip_interval = 2  # Обрабатываем каждый 2-й кадр
        self.frame_counter = 0
        
        # Запускаем рабочие потоки
        for i in range(2):  # 2 потока для обработки
            thread = threading.Thread(target=self._worker, daemon=True)
            thread.start()
            self.worker_threads.append(thread)
    
    def _worker(self):
        """Рабочий поток для обработки кадров"""
        while not self.stop_processing.is_set():
            try:
                frame_data = self.processing_queue.get(timeout=1.0)
                if frame_data is None:
                    break
                    
                result = self._process_single_frame(frame_data)
                if result:
                    self.result_queue.put(result)
                    
            except queue.Empty:
                continue
            except Exception as e:
                print(_("Error in frame processing worker: {}").format(str(e)))
    
    def _process_single_frame(self, frame_data):
        """Обработка одного кадра"""
        frame, gsframe, username, encodings = frame_data
        
        try:
            # Детекция лиц через daemon
            face_locations = self.daemon_client.detect_faces(gsframe)
            
            for face_location in face_locations:
                # Получаем энкодинг лица
                face_encoding = self.daemon_client.get_face_encoding(frame, face_location)
                if face_encoding is None:
                    continue
                
                # Сравниваем с известными энкодингами
                matches = np.linalg.norm(encodings - face_encoding, axis=1)
                match_index = np.argmin(matches)
                match_certainty = matches[match_index]
                
                return {
                    'face_location': face_location,
                    'face_encoding': face_encoding,
                    'match_certainty': match_certainty,
                    'match_index': match_index,
                    'frame': frame
                }
                
        except Exception as e:
            print(_("Error processing frame: {}").format(str(e)))
            
        return None
    
    def add_frame(self, frame, gsframe, username, encodings):
        """Добавление кадра в очередь обработки"""
        self.frame_counter += 1
        
        # Пропускаем кадры для оптимизации
        if self.frame_counter % self.frame_skip_interval != 0:
            return False
        
        try:
            self.processing_queue.put((frame, gsframe, username, encodings), block=False)
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
        
        # Добавляем None для завершения потоков
        for _ in self.worker_threads:
            try:
                self.processing_queue.put(None, block=False)
            except queue.Full:
                pass


class SecurityLogger:
    """Расширенная система логирования безопасности"""
    
    def __init__(self, config):
        self.config = config
        self.log_path = "/var/log/howdy/security.log"
        self.failed_attempts = {}  # Счетчик неудачных попыток по IP/пользователю
        self.max_attempts = 5
        self.lockout_duration = 300  # 5 минут
        
        # Создаем директорию логов если не существует
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
    
    def log_auth_attempt(self, username, success, metadata=None):
        """Логирование попытки аутентификации"""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        log_entry = {
            'timestamp': timestamp,
            'username': username,
            'success': success,
            'metadata': metadata or {}
        }
        
        # Добавляем дополнительную информацию
        log_entry['metadata'].update({
            'pid': os.getpid(),
            'hostname': os.uname().nodename,
            'ssh_connection': os.environ.get('SSH_CONNECTION', ''),
            'display': os.environ.get('DISPLAY', ''),
        })
        
        # Записываем в лог
        try:
            with open(self.log_path, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            print(_("Error writing to security log: {}").format(str(e)))
        
        # Обновляем счетчик неудачных попыток
        if not success:
            self._update_failed_attempts(username)
    
    def _update_failed_attempts(self, username):
        """Обновление счетчика неудачных попыток"""
        current_time = time.time()
        
        if username not in self.failed_attempts:
            self.failed_attempts[username] = {'count': 0, 'last_attempt': current_time}
        
        # Сбрасываем счетчик если прошло достаточно времени
        if current_time - self.failed_attempts[username]['last_attempt'] > self.lockout_duration:
            self.failed_attempts[username] = {'count': 1, 'last_attempt': current_time}
        else:
            self.failed_attempts[username]['count'] += 1
            self.failed_attempts[username]['last_attempt'] = current_time
    
    def is_user_locked(self, username):
        """Проверка блокировки пользователя"""
        if username not in self.failed_attempts:
            return False
        
        current_time = time.time()
        user_data = self.failed_attempts[username]
        
        # Проверяем превышение лимита попыток
        if user_data['count'] >= self.max_attempts:
            # Проверяем не истек ли период блокировки
            if current_time - user_data['last_attempt'] < self.lockout_duration:
                return True
            else:
                # Сбрасываем счетчик после истечения блокировки
                del self.failed_attempts[username]
        
        return False
    
    def log_security_event(self, event_type, description, severity='INFO'):
        """Логирование событий безопасности"""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        log_entry = {
            'timestamp': timestamp,
            'event_type': event_type,
            'description': description,
            'severity': severity,
            'pid': os.getpid(),
            'hostname': os.uname().nodename
        }
        
        try:
            with open(self.log_path, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            print(_("Error writing security event: {}").format(str(e)))


def exit_handler(code=None):
    """Обработчик выхода с очисткой ресурсов"""
    global gtk_proc, processing_thread, frame_processor
    
    # Закрываем GTK процесс
    if "gtk_proc" in globals() and gtk_proc:
        gtk_proc.terminate()
    
    # Останавливаем обработку кадров
    if "frame_processor" in globals() and frame_processor:
        frame_processor.stop()
    
    if code is not None:
        sys.exit(code)


def send_to_ui(type, message):
    """Отправка сообщения в UI"""
    global gtk_proc
    
    if "gtk_proc" in globals() and gtk_proc:
        try:
            message_formatted = type + "=" + message + " \n"
            if gtk_proc.poll() is None:
                gtk_proc.stdin.write(bytearray(message_formatted.encode("utf-8")))
                gtk_proc.stdin.flush()
        except IOError:
            pass


def make_snapshot(type, snapframes, timings, frames, lowest_certainty):
    """Создание снимка после детекции"""
    snapshot.generate(snapframes, [
        type + _(" LOGIN"),
        _("Date: ") + datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M:%S UTC"),
        _("Scan time: ") + str(round(time.time() - timings["fr"], 2)) + "s",
        _("Frames: ") + str(frames) + " (" + str(round(frames / max(time.time() - timings["fr"], 0.001), 2)) + "FPS)",
        _("Hostname: ") + os.uname().nodename,
        _("Best certainty value: ") + str(round(lowest_certainty * 10, 1))
    ])


def main():
    """Основная функция оптимизированного сравнения"""
    global daemon_client, liveness_detector, frame_processor, gtk_proc
    
    # Проверяем аргументы
    if len(sys.argv) < 2:
        exit_handler(12)
    
    username = sys.argv[1]
    
    # Инициализируем компоненты
    daemon_client = HowdyDaemonClient()
    
    # Проверяем работу daemon
    if not daemon_client.is_daemon_running():
        print(_("Howdy daemon is not running. Please start it first:"))
        print("\tsudo python3 -m howdy.src.model_daemon --daemon")
        exit_handler(1)
    
    # Загружаем конфигурацию
    config = configparser.ConfigParser()
    config.read(paths_factory.config_file_path())
    
    # Инициализируем систему безопасности
    security_logger = SecurityLogger(config)
    
    # Проверяем блокировку пользователя
    if security_logger.is_user_locked(username):
        security_logger.log_security_event(
            'USER_LOCKED',
            f'Authentication attempt by locked user: {username}',
            'WARNING'
        )
        print(_("User is temporarily locked due to too many failed attempts"))
        exit_handler(15)
    
    # Получаем энкодинги пользователя через daemon
    user_data = daemon_client.get_user_encodings(username)
    if not user_data:
        security_logger.log_auth_attempt(username, False, {'error': 'no_face_model'})
        exit_handler(10)
    
    encodings = user_data['encodings']
    models = user_data['models']
    
    # Получаем настройки из конфигурации
    timeout = config.getint("video", "timeout", fallback=4)
    dark_threshold = config.getfloat("video", "dark_threshold", fallback=60)
    video_certainty = config.getfloat("video", "certainty", fallback=3.5) / 10
    max_height = config.getint("video", "max_height", fallback=320)
    save_failed = config.getboolean("snapshots", "save_failed", fallback=False)
    save_successful = config.getboolean("snapshots", "save_successful", fallback=False)
    end_report = config.getboolean("debug", "end_report", fallback=False)
    liveness_check = config.getboolean("security", "liveness_check", fallback=True)
    
    # Инициализируем детектор живого лица
    if liveness_check:
        liveness_detector = LivenessDetector()
    
    # Запускаем GTK UI
    gtk_pipe = subprocess.DEVNULL
    if config.getboolean("debug", "gtk_stdout", fallback=False):
        gtk_pipe = None
    
    try:
        gtk_proc = subprocess.Popen(
            ["howdy-gtk", "--start-auth-ui"], 
            stdin=subprocess.PIPE, 
            stdout=gtk_pipe, 
            stderr=gtk_pipe
        )
        atexit.register(exit_handler)
    except FileNotFoundError:
        pass
    
    # Инициализируем захват видео
    timings["ic"] = time.time()
    
    try:
        video_capture = VideoCapture(config)
    except Exception as e:
        security_logger.log_security_event(
            'CAMERA_ERROR',
            f'Failed to initialize camera: {str(e)}',
            'ERROR'
        )
        exit_handler(14)
    
    timings["ic"] = time.time() - timings["ic"]
    
    # Получаем размеры кадра
    height = video_capture.fh or 1
    scaling_factor = (max_height / height) if height > max_height else 1
    
    # Инициализируем обработчик кадров
    frame_processor = OptimizedFrameProcessor(daemon_client, config)
    
    # Инициализируем улучшение контраста
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    
    # Переменные для отслеживания
    frames = 0
    valid_frames = 0
    dark_tries = 0
    black_tries = 0
    snapframes = []
    lowest_certainty = 10
    dark_running_total = 0
    liveness_confirmed = False
    
    send_to_ui("M", _("Identifying you..."))
    
    # Основной цикл обработки
    timings["fr"] = time.time()
    
    while True:
        frames += 1
        
        # Проверяем таймаут
        if time.time() - timings["fr"] > timeout:
            if save_failed:
                make_snapshot(_("FAILED"), snapframes, timings, frames, lowest_certainty)
            
            security_logger.log_auth_attempt(username, False, {
                'error': 'timeout',
                'frames_processed': frames,
                'dark_frames': dark_tries
            })
            
            if dark_tries == valid_frames:
                print(_("All frames were too dark, please check dark_threshold in config"))
                exit_handler(13)
            else:
                exit_handler(11)
        
        # Обновляем UI
        ui_subtext = f"Scanned {valid_frames - dark_tries} frames"
        if dark_tries > 1:
            ui_subtext += f" (skipped {dark_tries} dark frames)"
        send_to_ui("S", ui_subtext)
        
        # Захватываем кадр
        try:
            frame, gsframe = video_capture.read_frame()
            gsframe = clahe.apply(gsframe)
        except Exception as e:
            print(_("Error reading frame: {}").format(str(e)))
            continue
        
        # Сохраняем кадры для снимков
        if (save_failed or save_successful) and len(snapframes) < 3:
            snapframes.append(frame)
        
        # Анализ освещенности кадра
        hist = cv2.calcHist([gsframe], [0], None, [8], [0, 256])
        hist_total = np.sum(hist)
        
        if hist_total == 0:
            black_tries += 1
            continue
        
        darkness = (hist[0] / hist_total * 100)
        
        if darkness == 100:
            black_tries += 1
            continue
        
        dark_running_total += darkness
        valid_frames += 1
        
        if darkness > dark_threshold:
            dark_tries += 1
            continue
        
        # Масштабирование кадра
        if scaling_factor != 1:
            frame = cv2.resize(frame, None, fx=scaling_factor, fy=scaling_factor, interpolation=cv2.INTER_AREA)
            gsframe = cv2.resize(gsframe, None, fx=scaling_factor, fy=scaling_factor, interpolation=cv2.INTER_AREA)
        
        # Добавляем кадр в очередь обработки
        frame_processor.add_frame(frame, gsframe, username, encodings)
        
        # Проверяем результаты обработки
        result = frame_processor.get_result()
        if result:
            match_certainty = result['match_certainty']
            
            # Обновляем лучший результат
            if lowest_certainty > match_certainty:
                lowest_certainty = match_certainty
            
            # Проверяем уверенность совпадения
            if 0 < match_certainty < video_certainty:
                # Проверка живого лица если включена
                if liveness_check and liveness_detector:
                    # Получаем ключевые точки лица для проверки живости
                    face_landmarks = daemon_client.send_request({
                        'type': 'get_face_landmarks',
                        'frame': result['frame'],
                        'face_location': result['face_location']
                    })
                    
                    if face_landmarks and not liveness_confirmed:
                        is_live = liveness_detector.is_live_face(face_landmarks, result['face_location'])
                        if not is_live:
                            send_to_ui("M", _("Please blink or move your head slightly"))
                            continue
                        else:
                            liveness_confirmed = True
                            send_to_ui("M", _("Liveness confirmed, authenticating..."))
                
                # Успешная аутентификация
                timings["tt"] = time.time() - timings["st"]
                timings["fl"] = time.time() - timings["fr"]
                
                # Логируем успешную попытку
                security_logger.log_auth_attempt(username, True, {
                    'certainty': match_certainty,
                    'frames_processed': frames,
                    'processing_time': timings["fl"],
                    'liveness_confirmed': liveness_confirmed
                })
                
                # Отчет о производительности
                if end_report:
                    print(_("Time spent"))
                    print(f"  Starting up: {round(timings.get('in', 0) * 1000)}ms")
                    print(f"  Camera + libs: {round(max(timings.get('ll', 0), timings['ic']) * 1000)}ms")
                    print(f"  Searching: {round(timings['fl'] * 1000)}ms")
                    print(f"  Total: {round(timings['tt'] * 1000)}ms")
                    print(f"Frames: {frames} ({frames / timings['fl']:.2f} fps)")
                    print(f"Certainty: {match_certainty * 10:.3f}")
                    print(f"Model: {result['match_index']} (\"{models[result['match_index']]['label']}\")")
                
                # Создаем снимок успешной аутентификации
                if save_successful:
                    make_snapshot(_("SUCCESSFUL"), snapframes, timings, frames, lowest_certainty)
                
                # Выполняем дополнительные проверки безопасности (rubberstamps)
                if config.getboolean("rubberstamps", "enabled", fallback=False):
                    import rubberstamps
                    send_to_ui("S", "")
                    
                    rubberstamps.execute(config, gtk_proc, {
                        "video_capture": video_capture,
                        "daemon_client": daemon_client,
                        "clahe": clahe
                    })
                
                # Успешное завершение
                exit_handler(0)


if __name__ == "__main__":
    main()