#!/usr/bin/env python3
"""
Система детекции живого лица (Liveness Detection) для предотвращения спуфинга
"""

import cv2
import numpy as np
import time
import dlib
from collections import deque
import math
from i18n import _


class AdvancedLivenessDetector:
    """Продвинутая система детекции живого лица с множественными методами"""
    
    def __init__(self, config=None):
        self.config = config
        
        # Параметры детекции моргания
        self.eye_ar_threshold = 0.25
        self.eye_ar_consecutive_frames = 3
        self.blink_counter = 0
        self.total_blinks = 0
        self.eye_ar_history = deque(maxlen=30)
        
        # Параметры детекции движения головы
        self.head_movement_threshold = 15.0
        self.head_positions = deque(maxlen=20)
        self.head_movement_confirmed = False
        
        # Параметры анализа текстуры
        self.texture_threshold = 0.02
        self.texture_history = deque(maxlen=10)
        
        # Параметры детекции глубины
        self.depth_analysis_enabled = True
        self.depth_threshold = 0.1
        
        # Временные ограничения
        self.max_detection_time = 10.0  # максимальное время на детекцию
        self.min_confirmation_time = 2.0  # минимальное время для подтверждения
        self.start_time = None
        
        # Статистика
        self.detection_stats = {
            'blinks_detected': 0,
            'head_movements': 0,
            'texture_variations': 0,
            'depth_confirmations': 0,
            'total_frames_processed': 0
        }
        
        # Флаги подтверждения различных методов
        self.blink_confirmed = False
        self.movement_confirmed = False
        self.texture_confirmed = False
        self.depth_confirmed = False
    
    def reset(self):
        """Сброс детектора для нового сеанса"""
        self.blink_counter = 0
        self.total_blinks = 0
        self.eye_ar_history.clear()
        self.head_positions.clear()
        self.texture_history.clear()
        
        self.blink_confirmed = False
        self.movement_confirmed = False
        self.texture_confirmed = False
        self.depth_confirmed = False
        self.head_movement_confirmed = False
        
        self.start_time = time.time()
        
        # Сброс статистики
        for key in self.detection_stats:
            self.detection_stats[key] = 0
    
    def calculate_eye_aspect_ratio(self, eye_points):
        """Вычисление соотношения сторон глаза (EAR)"""
        # Вертикальные расстояния
        A = np.linalg.norm(np.array(eye_points[1]) - np.array(eye_points[5]))
        B = np.linalg.norm(np.array(eye_points[2]) - np.array(eye_points[4]))
        
        # Горизонтальное расстояние
        C = np.linalg.norm(np.array(eye_points[0]) - np.array(eye_points[3]))
        
        # EAR
        if C == 0:
            return 0
        ear = (A + B) / (2.0 * C)
        return ear
    
    def extract_eye_regions(self, landmarks):
        """Извлечение областей глаз из ключевых точек"""
        # Для 68-точечной модели dlib
        left_eye_points = []
        right_eye_points = []
        
        # Левый глаз (точки 36-41)
        for i in range(36, 42):
            point = landmarks.part(i)
            left_eye_points.append((point.x, point.y))
        
        # Правый глаз (точки 42-47)
        for i in range(42, 48):
            point = landmarks.part(i)
            right_eye_points.append((point.x, point.y))
        
        return left_eye_points, right_eye_points
    
    def detect_blink_advanced(self, landmarks):
        """Продвинутая детекция моргания"""
        try:
            left_eye, right_eye = self.extract_eye_regions(landmarks)
            
            # Вычисляем EAR для обоих глаз
            left_ear = self.calculate_eye_aspect_ratio(left_eye)
            right_ear = self.calculate_eye_aspect_ratio(right_eye)
            
            # Средний EAR
            ear = (left_ear + right_ear) / 2.0
            self.eye_ar_history.append(ear)
            
            # Проверяем моргание
            if ear < self.eye_ar_threshold:
                self.blink_counter += 1
            else:
                if self.blink_counter >= self.eye_ar_consecutive_frames:
                    self.total_blinks += 1
                    self.detection_stats['blinks_detected'] += 1
                    
                    # Подтверждаем моргание если достаточно морганий
                    if self.total_blinks >= 1:
                        self.blink_confirmed = True
                        return True
                
                self.blink_counter = 0
            
            return False
            
        except Exception as e:
            print(_("Error in advanced blink detection: {}").format(str(e)))
            return False
    
    def detect_head_movement_advanced(self, landmarks):
        """Продвинутая детекция движения головы"""
        try:
            # Используем несколько ключевых точек для более точного отслеживания
            # Нос (точка 30), подбородок (точка 8), центр лба (точка между 19 и 24)
            nose_tip = landmarks.part(30)
            chin = landmarks.part(8)
            
            # Центр лица
            center_x = (nose_tip.x + chin.x) / 2
            center_y = (nose_tip.y + chin.y) / 2
            
            # Угол наклона головы (используя нос и подбородок)
            angle = math.atan2(chin.y - nose_tip.y, chin.x - nose_tip.x)
            
            position = {
                'center': (center_x, center_y),
                'angle': angle,
                'timestamp': time.time()
            }
            
            self.head_positions.append(position)
            
            # Анализируем движение если накопилось достаточно точек
            if len(self.head_positions) >= 5:
                positions = list(self.head_positions)
                
                # Вычисляем дисперсию позиций
                centers = [pos['center'] for pos in positions]
                angles = [pos['angle'] for pos in positions]
                
                center_variance = np.var(centers, axis=0)
                angle_variance = np.var(angles)
                
                # Проверяем движение
                total_movement = np.sum(center_variance) + angle_variance * 1000
                
                if total_movement > self.head_movement_threshold:
                    self.movement_confirmed = True
                    self.detection_stats['head_movements'] += 1
                    return True
            
            return False
            
        except Exception as e:
            print(_("Error in head movement detection: {}").format(str(e)))
            return False
    
    def analyze_texture_variation(self, frame, face_region):
        """Анализ вариации текстуры для детекции живого лица"""
        try:
            # Извлекаем область лица
            x, y, w, h = face_region
            face_roi = frame[y:y+h, x:x+w]
            
            if face_roi.size == 0:
                return False
            
            # Преобразуем в градации серого если нужно
            if len(face_roi.shape) == 3:
                face_gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
            else:
                face_gray = face_roi
            
            # Вычисляем локальную дисперсию (LBP-подобный анализ)
            # Используем фильтр Лапласа для детекции краев
            laplacian_var = cv2.Laplacian(face_gray, cv2.CV_64F).var()
            
            # Нормализуем значение
            normalized_var = laplacian_var / (face_gray.shape[0] * face_gray.shape[1])
            
            self.texture_history.append(normalized_var)
            
            # Анализируем изменения текстуры во времени
            if len(self.texture_history) >= 5:
                texture_variance = np.var(list(self.texture_history))
                
                # Живое лицо должно иметь естественные вариации текстуры
                if texture_variance > self.texture_threshold:
                    self.texture_confirmed = True
                    self.detection_stats['texture_variations'] += 1
                    return True
            
            return False
            
        except Exception as e:
            print(_("Error in texture analysis: {}").format(str(e)))
            return False
    
    def detect_depth_cues(self, frame, landmarks):
        """Детекция признаков глубины и трехмерности"""
        try:
            # Анализ теней и освещения
            # Получаем области вокруг глаз и носа
            
            # Левый глаз
            left_eye_center = landmarks.part(36)  # Примерный центр левого глаза
            # Правый глаз  
            right_eye_center = landmarks.part(45)  # Примерный центр правого глаза
            # Нос
            nose_tip = landmarks.part(30)
            
            # Анализируем освещение в этих областях
            regions = []
            for point in [left_eye_center, right_eye_center, nose_tip]:
                x, y = point.x, point.y
                # Небольшая область вокруг точки
                region = frame[max(0, y-10):y+10, max(0, x-10):x+10]
                if region.size > 0:
                    if len(region.shape) == 3:
                        region_gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
                    else:
                        region_gray = region
                    regions.append(np.mean(region_gray))
            
            if len(regions) >= 3:
                # Анализируем различия в освещении между регионами
                lighting_variance = np.var(regions)
                
                # Живое лицо должно иметь естественные различия в освещении
                if lighting_variance > 100:  # Настраиваемый порог
                    self.depth_confirmed = True
                    self.detection_stats['depth_confirmations'] += 1
                    return True
            
            return False
            
        except Exception as e:
            print(_("Error in depth analysis: {}").format(str(e)))
            return False
    
    def process_frame(self, frame, landmarks, face_region):
        """Обработка кадра для всех методов детекции"""
        if self.start_time is None:
            self.start_time = time.time()
        
        self.detection_stats['total_frames_processed'] += 1
        
        # Проверяем таймаут
        elapsed_time = time.time() - self.start_time
        if elapsed_time > self.max_detection_time:
            return self.get_final_decision()
        
        # Применяем все методы детекции
        blink_result = self.detect_blink_advanced(landmarks)
        movement_result = self.detect_head_movement_advanced(landmarks)
        texture_result = self.analyze_texture_variation(frame, face_region)
        depth_result = self.detect_depth_cues(frame, landmarks)
        
        # Проверяем достижение минимального времени подтверждения
        if elapsed_time >= self.min_confirmation_time:
            return self.get_final_decision()
        
        return False  # Продолжаем обработку
    
    def get_final_decision(self):
        """Получение финального решения о живости лица"""
        # Подсчитываем количество подтвержденных методов
        confirmed_methods = sum([
            self.blink_confirmed,
            self.movement_confirmed,
            self.texture_confirmed,
            self.depth_confirmed
        ])
        
        # Требуем подтверждения минимум 2 методов для высокой уверенности
        # или 1 метод + достаточное время наблюдения
        elapsed_time = time.time() - self.start_time if self.start_time else 0
        
        if confirmed_methods >= 2:
            return True
        elif confirmed_methods >= 1 and elapsed_time >= self.min_confirmation_time * 1.5:
            return True
        elif elapsed_time >= self.max_detection_time:
            # Если время истекло, принимаем решение на основе имеющихся данных
            return confirmed_methods >= 1
        
        return False
    
    def get_detection_status(self):
        """Получение текущего статуса детекции"""
        return {
            'blink_confirmed': self.blink_confirmed,
            'movement_confirmed': self.movement_confirmed,
            'texture_confirmed': self.texture_confirmed,
            'depth_confirmed': self.depth_confirmed,
            'total_blinks': self.total_blinks,
            'stats': self.detection_stats.copy(),
            'elapsed_time': time.time() - self.start_time if self.start_time else 0
        }
    
    def get_user_feedback(self):
        """Получение сообщения для пользователя о текущем состоянии"""
        if not self.start_time:
            return _("Starting liveness detection...")
        
        elapsed_time = time.time() - self.start_time
        
        if not self.blink_confirmed and elapsed_time < 3:
            return _("Please blink naturally")
        elif not self.movement_confirmed and elapsed_time < 5:
            return _("Please move your head slightly")
        elif elapsed_time < self.min_confirmation_time:
            return _("Analyzing facial features...")
        else:
            confirmed_methods = sum([
                self.blink_confirmed,
                self.movement_confirmed,
                self.texture_confirmed,
                self.depth_confirmed
            ])
            
            if confirmed_methods >= 2:
                return _("Liveness confirmed!")
            elif confirmed_methods >= 1:
                return _("Almost there, keep looking at the camera")
            else:
                return _("Please ensure good lighting and look directly at camera")


class SimpleLivenessDetector:
    """Упрощенная версия детектора для систем с ограниченными ресурсами"""
    
    def __init__(self, config=None):
        self.config = config
        self.blink_frames = deque(maxlen=15)
        self.movement_positions = deque(maxlen=10)
        self.detection_start = None
        self.min_detection_time = 1.5
        self.max_detection_time = 8.0
        
        self.blink_detected = False
        self.movement_detected = False
    
    def reset(self):
        """Сброс детектора"""
        self.blink_frames.clear()
        self.movement_positions.clear()
        self.detection_start = time.time()
        self.blink_detected = False
        self.movement_detected = False
    
    def process_frame_simple(self, landmarks):
        """Упрощенная обработка кадра"""
        if self.detection_start is None:
            self.detection_start = time.time()
        
        # Простая детекция моргания по изменению позиций точек глаз
        if landmarks.num_parts >= 5:  # Для 5-точечной модели
            # Используем точки вокруг глаз
            eye_points = [(landmarks.part(i).x, landmarks.part(i).y) for i in range(2)]
            self.blink_frames.append(eye_points)
            
            if len(self.blink_frames) >= 3:
                # Анализируем изменения
                recent_frames = list(self.blink_frames)[-3:]
                variations = []
                
                for i in range(len(recent_frames) - 1):
                    frame_diff = 0
                    for j in range(len(recent_frames[i])):
                        diff = abs(recent_frames[i][j][1] - recent_frames[i+1][j][1])  # Y координата
                        frame_diff += diff
                    variations.append(frame_diff)
                
                # Если есть значительные изменения, считаем это морганием
                if max(variations) > 3.0:
                    self.blink_detected = True
        
        # Простая детекция движения головы
        if landmarks.num_parts >= 5:
            # Центр лица (приблизительно)
            center_x = sum(landmarks.part(i).x for i in range(min(5, landmarks.num_parts))) / min(5, landmarks.num_parts)
            center_y = sum(landmarks.part(i).y for i in range(min(5, landmarks.num_parts))) / min(5, landmarks.num_parts)
            
            self.movement_positions.append((center_x, center_y))
            
            if len(self.movement_positions) >= 5:
                positions = list(self.movement_positions)
                movement_variance = np.var(positions, axis=0)
                
                if np.sum(movement_variance) > 25:
                    self.movement_detected = True
        
        # Проверяем готовность к принятию решения
        elapsed_time = time.time() - self.detection_start
        
        if elapsed_time >= self.min_detection_time:
            if self.blink_detected or self.movement_detected:
                return True
        
        if elapsed_time >= self.max_detection_time:
            # Время истекло, принимаем решение на основе имеющихся данных
            return self.blink_detected or self.movement_detected
        
        return False
    
    def get_user_feedback_simple(self):
        """Простое сообщение пользователю"""
        if not self.detection_start:
            return _("Starting verification...")
        
        elapsed_time = time.time() - self.detection_start
        
        if elapsed_time < 2:
            return _("Please blink or nod slightly")
        elif elapsed_time < 4:
            return _("Keep looking at the camera...")
        else:
            return _("Final verification...")


def create_liveness_detector(config=None):
    """Фабричная функция для создания подходящего детектора"""
    # Выбираем детектор на основе конфигурации или возможностей системы
    if config and config.getboolean("security", "advanced_liveness", fallback=False):
        return AdvancedLivenessDetector(config)
    else:
        return SimpleLivenessDetector(config)