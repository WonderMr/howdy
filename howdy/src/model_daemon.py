#!/usr/bin/env python3
"""
Howdy Model Daemon - Preloading and caching dlib models for faster authentication
"""

import os
import sys
import time
import json
import threading
import configparser
import dlib
import numpy as np
import paths_factory
from i18n import _
import socket
import pickle
import struct
import signal
import daemon
import lockfile


class HowdyModelDaemon:
    """Daemon for preloading and caching face recognition models"""
    
    def __init__(self, config_path=None):
        self.config = configparser.ConfigParser()
        if config_path:
            self.config.read(config_path)
        else:
            self.config.read(paths_factory.config_file_path())
            
        # Cache for loaded models
        self.models_cache = {}
        self.encodings_cache = {}
        
        # dlib components
        self.face_detector = None
        self.pose_predictor = None
        self.face_encoder = None
        
        # Status flags
        self.models_loaded = False
        self.use_cnn = self.config.getboolean("core", "use_cnn", fallback=False)
        
        # IPC socket
        self.socket_path = "/tmp/howdy_daemon.sock"
        self.server_socket = None
        
        # Thread safety lock
        self.lock = threading.RLock()
        
        # Statistics
        self.stats = {
            'requests_served': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'startup_time': 0,
            'average_response_time': 0
        }

    def preload_models(self):
        """Предзагрузка всех dlib моделей в память"""
        start_time = time.time()
        
        try:
            print(_("Loading face detection models..."))
            
            # Проверяем наличие файлов моделей
            if not os.path.isfile(paths_factory.shape_predictor_5_face_landmarks_path()):
                raise FileNotFoundError(_("Shape predictor model not found"))
                
            # Загрузка детектора лиц
            if self.use_cnn:
                print(_("Loading CNN face detector..."))
                self.face_detector = dlib.cnn_face_detection_model_v1(
                    paths_factory.mmod_human_face_detector_path()
                )
            else:
                print(_("Loading HOG face detector..."))
                self.face_detector = dlib.get_frontal_face_detector()
            
            # Загрузка предсказателя ключевых точек
            print(_("Loading shape predictor..."))
            self.pose_predictor = dlib.shape_predictor(
                paths_factory.shape_predictor_5_face_landmarks_path()
            )
            
            # Загрузка энкодера лиц
            print(_("Loading face encoder..."))
            self.face_encoder = dlib.face_recognition_model_v1(
                paths_factory.dlib_face_recognition_resnet_model_v1_path()
            )
            
            self.models_loaded = True
            load_time = time.time() - start_time
            self.stats['startup_time'] = load_time
            
            print(_("Models loaded successfully in {:.2f}s").format(load_time))
            
        except Exception as e:
            print(_("Error loading models: {}").format(str(e)))
            sys.exit(1)

    def load_user_encodings(self, username):
        """Загрузка и кэширование энкодингов пользователя"""
        with self.lock:
            if username in self.encodings_cache:
                self.stats['cache_hits'] += 1
                return self.encodings_cache[username]
                
            try:
                user_model_path = paths_factory.user_model_path(username)
                if not os.path.exists(user_model_path):
                    return None
                    
                with open(user_model_path, 'r') as f:
                    models = json.load(f)
                
                encodings = []
                for model in models:
                    encodings.extend(model["data"])
                
                # Преобразуем в numpy массив для быстрых вычислений
                encodings_array = np.array(encodings)
                
                # Кэшируем результат
                self.encodings_cache[username] = {
                    'encodings': encodings_array,
                    'models': models,
                    'last_modified': os.path.getmtime(user_model_path)
                }
                
                self.stats['cache_misses'] += 1
                return self.encodings_cache[username]
                
            except Exception as e:
                print(_("Error loading user encodings for {}: {}").format(username, str(e)))
                return None

    def invalidate_user_cache(self, username):
        """Инвалидация кэша для конкретного пользователя"""
        with self.lock:
            if username in self.encodings_cache:
                del self.encodings_cache[username]
                print(_("Cache invalidated for user: {}").format(username))

    def check_cache_validity(self, username):
        """Проверка актуальности кэша пользователя"""
        if username not in self.encodings_cache:
            return False
            
        try:
            user_model_path = paths_factory.user_model_path(username)
            current_mtime = os.path.getmtime(user_model_path)
            cached_mtime = self.encodings_cache[username]['last_modified']
            
            if current_mtime > cached_mtime:
                self.invalidate_user_cache(username)
                return False
                
            return True
        except:
            return False

    def get_face_encoding(self, frame, face_location):
        """Получение энкодинга лица из кадра"""
        if not self.models_loaded:
            return None
            
        try:
            # Получаем ключевые точки лица
            face_landmark = self.pose_predictor(frame, face_location)
            
            # Вычисляем энкодинг
            face_encoding = np.array(
                self.face_encoder.compute_face_descriptor(frame, face_landmark, 1)
            )
            
            return face_encoding
        except Exception as e:
            print(_("Error computing face encoding: {}").format(str(e)))
            return None

    def detect_faces(self, frame):
        """Детекция лиц в кадре"""
        if not self.models_loaded:
            return []
            
        try:
            # Детекция лиц
            face_locations = self.face_detector(frame, 1)
            
            # Преобразуем CNN результаты в обычный формат если нужно
            if self.use_cnn:
                face_locations = [fl.rect for fl in face_locations]
                
            return face_locations
        except Exception as e:
            print(_("Error detecting faces: {}").format(str(e)))
            return []

    def start_server(self):
        """Запуск IPC сервера для обработки запросов"""
        # Удаляем старый сокет если существует
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
            
        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(self.socket_path)
        self.server_socket.listen(5)
        
        print(_("Daemon server started at {}").format(self.socket_path))
        
        while True:
            try:
                client_socket, _ = self.server_socket.accept()
                # Обрабатываем каждый запрос в отдельном потоке
                threading.Thread(
                    target=self.handle_client,
                    args=(client_socket,),
                    daemon=True
                ).start()
            except Exception as e:
                print(_("Error accepting client: {}").format(str(e)))
                break

    def handle_client(self, client_socket):
        """Обработка клиентского запроса"""
        start_time = time.time()
        
        try:
            # Получаем размер данных
            raw_msglen = self.recvall(client_socket, 4)
            if not raw_msglen:
                return
            msglen = struct.unpack('>I', raw_msglen)[0]
            
            # Получаем данные запроса
            raw_data = self.recvall(client_socket, msglen)
            request = pickle.loads(raw_data)
            
            # Обрабатываем запрос
            response = self.process_request(request)
            
            # Отправляем ответ
            response_data = pickle.dumps(response)
            client_socket.sendall(struct.pack('>I', len(response_data)))
            client_socket.sendall(response_data)
            
            # Обновляем статистику
            response_time = time.time() - start_time
            self.stats['requests_served'] += 1
            self.stats['average_response_time'] = (
                (self.stats['average_response_time'] * (self.stats['requests_served'] - 1) + response_time) /
                self.stats['requests_served']
            )
            
        except Exception as e:
            print(_("Error handling client request: {}").format(str(e)))
        finally:
            client_socket.close()

    def recvall(self, sock, n):
        """Получение точно n байт данных"""
        data = bytearray()
        while len(data) < n:
            packet = sock.recv(n - len(data))
            if not packet:
                return None
            data.extend(packet)
        return data

    def process_request(self, request):
        """Обработка конкретного запроса"""
        request_type = request.get('type')
        
        if request_type == 'get_encodings':
            username = request.get('username')
            if not self.check_cache_validity(username):
                self.load_user_encodings(username)
            return self.encodings_cache.get(username)
            
        elif request_type == 'detect_faces':
            frame = request.get('frame')
            return self.detect_faces(frame)
            
        elif request_type == 'get_face_encoding':
            frame = request.get('frame')
            face_location = request.get('face_location')
            return self.get_face_encoding(frame, face_location)
            
        elif request_type == 'invalidate_cache':
            username = request.get('username')
            self.invalidate_user_cache(username)
            return {'status': 'success'}
            
        elif request_type == 'get_stats':
            return self.stats
            
        elif request_type == 'ping':
            return {'status': 'alive', 'models_loaded': self.models_loaded}
            
        else:
            return {'error': 'Unknown request type'}

    def cleanup(self):
        """Очистка ресурсов при завершении"""
        if self.server_socket:
            self.server_socket.close()
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

    def signal_handler(self, signum, frame):
        """Обработчик сигналов для корректного завершения"""
        print(_("Received signal {}, shutting down...").format(signum))
        self.cleanup()
        sys.exit(0)

    def run_daemon(self):
        """Запуск daemon в фоновом режиме"""
        # Настройка обработчиков сигналов
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        
        try:
            # Предзагружаем модели
            self.preload_models()
            
            # Запускаем сервер
            self.start_server()
            
        except KeyboardInterrupt:
            print(_("Daemon interrupted by user"))
        except Exception as e:
            print(_("Daemon error: {}").format(str(e)))
        finally:
            self.cleanup()


class HowdyDaemonClient:
    """Клиент для взаимодействия с daemon"""
    
    def __init__(self):
        self.socket_path = "/tmp/howdy_daemon.sock"
        
    def send_request(self, request):
        """Отправка запроса daemon"""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(self.socket_path)
            
            # Отправляем запрос
            request_data = pickle.dumps(request)
            sock.sendall(struct.pack('>I', len(request_data)))
            sock.sendall(request_data)
            
            # Получаем ответ
            raw_msglen = self.recvall(sock, 4)
            if not raw_msglen:
                return None
            msglen = struct.unpack('>I', raw_msglen)[0]
            
            raw_data = self.recvall(sock, msglen)
            response = pickle.loads(raw_data)
            
            sock.close()
            return response
            
        except Exception as e:
            print(_("Error communicating with daemon: {}").format(str(e)))
            return None
    
    def recvall(self, sock, n):
        """Получение точно n байт данных"""
        data = bytearray()
        while len(data) < n:
            packet = sock.recv(n - len(data))
            if not packet:
                return None
            data.extend(packet)
        return data
    
    def is_daemon_running(self):
        """Проверка работы daemon"""
        response = self.send_request({'type': 'ping'})
        return response and response.get('status') == 'alive'
    
    def get_user_encodings(self, username):
        """Получение энкодингов пользователя"""
        return self.send_request({'type': 'get_encodings', 'username': username})
    
    def detect_faces(self, frame):
        """Детекция лиц через daemon"""
        return self.send_request({'type': 'detect_faces', 'frame': frame})
    
    def get_face_encoding(self, frame, face_location):
        """Получение энкодинга лица через daemon"""
        return self.send_request({
            'type': 'get_face_encoding',
            'frame': frame,
            'face_location': face_location
        })


def main():
    """Точка входа для daemon"""
    import argparse
    
    parser = argparse.ArgumentParser(description=_("Howdy Model Daemon"))
    parser.add_argument('--daemon', action='store_true', help=_("Run as daemon"))
    parser.add_argument('--stop', action='store_true', help=_("Stop daemon"))
    parser.add_argument('--status', action='store_true', help=_("Check daemon status"))
    parser.add_argument('--config', help=_("Config file path"))
    
    args = parser.parse_args()
    
    if args.stop:
        # Останавливаем daemon
        try:
            with open('/tmp/howdy_daemon.pid', 'r') as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
            print(_("Daemon stopped"))
        except:
            print(_("Daemon not running or error stopping"))
        return
    
    if args.status:
        # Проверяем статус daemon
        client = HowdyDaemonClient()
        if client.is_daemon_running():
            stats = client.send_request({'type': 'get_stats'})
            print(_("Daemon is running"))
            if stats:
                print(_("Requests served: {}").format(stats['requests_served']))
                print(_("Cache hits: {}").format(stats['cache_hits']))
                print(_("Cache misses: {}").format(stats['cache_misses']))
                print(_("Average response time: {:.3f}s").format(stats['average_response_time']))
        else:
            print(_("Daemon is not running"))
        return
    
    # Создаем и запускаем daemon
    daemon_instance = HowdyModelDaemon(args.config)
    
    if args.daemon:
        # Запуск в фоновом режиме
        with daemon.DaemonContext(
            pidfile=lockfile.FileLock('/tmp/howdy_daemon.pid'),
            signal_map={
                signal.SIGTERM: daemon_instance.signal_handler,
                signal.SIGINT: daemon_instance.signal_handler,
            }
        ):
            daemon_instance.run_daemon()
    else:
        # Запуск в режиме отладки
        daemon_instance.run_daemon()


if __name__ == "__main__":
    main()