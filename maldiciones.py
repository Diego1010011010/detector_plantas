from ultralytics import YOLO 
import cv2 
import serial
import time
import threading
import sys

class MacetaDetector:
    def __init__(self, model_path="best.pt", arduino_port="COM5", baudrate=9600):
        """
        Inicializa el detector de macetas con comunicación Arduino
        """
        print("="*60)
        print("INICIANDO SISTEMA DE DETECCIÓN")
        print("="*60)
        
        # Cargar modelo YOLO
        try:
            self.model = YOLO(model_path)
            print(f"✓ Modelo YOLO cargado: {model_path}")
        except Exception as e:
            print(f"✗ Error cargando modelo: {e}")
            return
        
        # Configurar Arduino
        self.arduino = None
        self.arduino_connected = False
        
        if arduino_port:
            print(f"\nConectando con Arduino en {arduino_port}...")
            
            # Intentar conectar varias veces
            for intento in range(3):
                try:
                    print(f"Intento {intento + 1}/3...")
                    self.arduino = serial.Serial(
                        port=arduino_port,
                        baudrate=baudrate,
                        timeout=2,
                        write_timeout=2,
                        bytesize=serial.EIGHTBITS,
                        parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_ONE
                    )
                    
                    time.sleep(3)  # Dar tiempo para inicializar
                    
                    if self.arduino.is_open:
                        print(f"✓ Conexión establecida con Arduino")
                        self.arduino_connected = True
                        
                        # Limpiar buffers
                        self.arduino.reset_input_buffer()
                        self.arduino.reset_output_buffer()
                        
                        # Esperar mensaje de Arduino
                        print("Esperando mensaje de Arduino...")
                        time.sleep(2)
                        
                        # Leer mensaje inicial
                        for _ in range(10):
                            if self.arduino.in_waiting:
                                mensaje = self.arduino.readline().decode('utf-8', errors='ignore').strip()
                                if mensaje:
                                    print(f"Arduino: {mensaje}")
                                    if "LISTO" in mensaje or "ARDUINO" in mensaje:
                                        print("✓ Arduino listo para recibir comandos")
                                        break
                            time.sleep(0.1)
                        
                        break  # Salir del bucle si conectó
                        
                except Exception as e:
                    print(f"✗ Intento {intento + 1} fallado: {type(e).__name__}")
                    if intento < 2:
                        print("Reintentando en 2 segundos...")
                        time.sleep(2)
                    else:
                        print("\n⚠️  No se pudo conectar con Arduino")
                        print("   El sistema funcionará en modo solo detección")
                        self.arduino = None
                        self.arduino_connected = False
        else:
            print("\nℹ️  Modo sin Arduino activado")
        
        # Configuración de detección
        self.CONFIDENCE_THRESHOLD = 0.50
        self.detection_active = True
        self.last_detection_time = 0
        self.detection_cooldown = 10  # segundos entre detecciones
        
        # Clases objetivo (IMPORTANTE: verifica los nombres en tu modelo)
        self.target_classes = ["plant", "planta", "maceta", "pot", "flower", "leaf", "vase", "potted plant"]
        
        # Estadísticas
        self.detection_count = 0
        self.frame_count = 0
        self.commands_sent = 0
        
        print(f"\n✓ Configuración completada")
        print(f"  Umbral de confianza: {self.CONFIDENCE_THRESHOLD}")
        print(f"  Clases objetivo: {self.target_classes}")
        print(f"  Arduino: {'CONECTADO' if self.arduino_connected else 'NO CONECTADO'}")
        print("="*60)
    
    def send_to_arduino(self, command):
        """Envía comando al Arduino con verificación robusta"""
        if not self.arduino_connected or not self.arduino:
            print(f"  [ARDUINO] ✗ No conectado - Comando '{command}' no enviado")
            return False
        
        try:
            # Agregar salto de línea (CR+LF para compatibilidad)
            full_command = command + "\n"
            bytes_written = self.arduino.write(full_command.encode('utf-8'))
            self.arduino.flush()  # Forzar envío
            
            if bytes_written == len(full_command):
                print(f"  [ARDUINO] ✓ Comando '{command}' enviado ({bytes_written} bytes)")
                self.commands_sent += 1
                
                # Registrar en archivo
                try:
                    with open("comandos.log", "a", encoding='utf-8') as f:
                        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                        f.write(f"{timestamp} - ENVIADO: {command}\n")
                except:
                    pass
                
                return True
            else:
                print(f"  [ARDUINO] ✗ Error: Solo se escribieron {bytes_written}/{len(full_command)} bytes")
                return False
                
        except Exception as e:
            print(f"  [ARDUINO] ✗ Error enviando '{command}': {type(e).__name__}: {e}")
            return False
    
    def read_from_arduino(self, timeout=0.1):
        """Lee datos del Arduino con timeout corto"""
        if not self.arduino_connected or not self.arduino:
            return None
        
        try:
            start_time = time.time()
            while time.time() - start_time < timeout:
                if self.arduino.in_waiting > 0:
                    # Leer línea completa
                    data = self.arduino.readline().decode('utf-8', errors='ignore').strip()
                    if data:
                        print(f"  [ARDUINO] ← {data}")
                        
                        # Registrar en archivo
                        try:
                            with open("comandos.log", "a", encoding='utf-8') as f:
                                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                                f.write(f"{timestamp} - RECIBIDO: {data}\n")
                        except:
                            pass
                        
                        return data
                time.sleep(0.01)
        except Exception as e:
            print(f"  [ARDUINO] ✗ Error leyendo: {type(e).__name__}")
        
        return None
    
    def test_arduino_connection(self):
        """Prueba la conexión con Arduino"""
        print("\n[TEST] Probando conexión Arduino...")
        
        if not self.arduino_connected:
            print("  ✗ Arduino no conectado")
            return False
        
        # Enviar comando de prueba
        print("  Enviando comando 'T'...")
        if self.send_to_arduino("T"):
            print("  Esperando respuesta...")
            
            # Esperar respuesta por 5 segundos
            start_time = time.time()
            while time.time() - start_time < 5:
                response = self.read_from_arduino(0.5)
                if response:
                    print(f"  ✓ Respuesta recibida: {response}")
                    return True
                time.sleep(0.1)
            
            print("  ✗ No hubo respuesta del Arduino")
            return False
        else:
            print("  ✗ No se pudo enviar comando de prueba")
            return False
    
    def check_target_class(self, class_name):
        """Verifica si la clase detectada es de interés"""
        class_lower = class_name.lower()
        for target in self.target_classes:
            if target in class_lower:
                return True
        return False
    
    def process_frame(self, frame):
        """Procesa un frame para detectar plantas/macetas"""
        self.frame_count += 1
        
        # Realizar detección (cada frame para mejor respuesta)
        try:
            results = self.model(frame, verbose=False, conf=0.3)  # conf mínimo 0.3
        except Exception as e:
            return frame, False
        
        target_detected = False
        best_confidence = 0
        best_box = None
        best_class = ""
        
        for result in results:
            boxes = result.boxes
            if boxes is not None:
                for box in boxes:
                    confidence = box.conf[0].item()
                    class_id = int(box.cls[0].item())
                    class_name = self.model.names[class_id]
                    
                    # Verificar si es clase objetivo y tiene buena confianza
                    if self.check_target_class(class_name):
                        # Debug: mostrar todas las detecciones relevantes
                        if confidence > 0.3:
                            print(f"  [DETECCION] {class_name}: {confidence:.2f}")
                        
                        if confidence > best_confidence:
                            best_confidence = confidence
                            best_class = class_name
                            best_box = box.xyxy[0].tolist()
                            target_detected = True
        
        # Dibujar y actuar si hay detección válida
        if target_detected and best_box and best_confidence >= self.CONFIDENCE_THRESHOLD:
            x1, y1, x2, y2 = map(int, best_box)
            
            # Dibujar en frame
            color = (0, 255, 0)  # Verde
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # Etiqueta
            label = f"{best_class} {best_confidence:.2f}"
            cv2.putText(frame, label, (x1, y1-10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            
            # Centro
            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2
            cv2.circle(frame, (center_x, center_y), 5, color, -1)
            
            # Intentar enviar comando a Arduino
            current_time = time.time()
            time_since_last = current_time - self.last_detection_time
            
            if (self.detection_active and 
                time_since_last > self.detection_cooldown and
                self.arduino_connected):
                
                self.detection_count += 1
                print(f"\n" + "🔥"*50)
                print(f"🔥 DETECCIÓN #{self.detection_count}")
                print(f"🔥 Clase: {best_class}")
                print(f"🔥 Confianza: {best_confidence:.2f}")
                print(f"🔥 Posición: ({center_x}, {center_y})")
                print(f"🔥 Enviando comando 'M' a Arduino...")
                
                # Enviar comando
                if self.send_to_arduino("M"):
                    self.last_detection_time = current_time
                    
                    # Monitorear respuesta en segundo plano
                    threading.Thread(
                        target=self.wait_for_arduino_response,
                        daemon=True
                    ).start()
                else:
                    print(f"🔥 ✗ Falló el envío del comando")
                
                print(f"🔥"*50 + "\n")
        
        return frame, target_detected
    
    def wait_for_arduino_response(self):
        """Espera respuesta del Arduino después de enviar comando"""
        print("  [ARDUINO] Monitoreando respuesta...")
        
        start_time = time.time()
        timeout = 30  # 30 segundos máximo
        received_fin = False
        
        while time.time() - start_time < timeout:
            response = self.read_from_arduino(0.5)
            
            if response:
                # Buscar "FIN" en cualquier parte de la respuesta
                if "FIN" in response.upper():
                    print("  [ARDUINO] ✓ Proceso completado (FIN recibido)")
                    received_fin = True
                    break
                
                # También aceptar otros mensajes de finalización
                if any(word in response.upper() for word in ["COMPLETADO", "TERMINADO", "LISTO", "FINISH"]):
                    print(f"  [ARDUINO] ✓ Proceso completado ({response})")
                    received_fin = True
                    break
            
            # Pequeña pausa para no saturar CPU
            time.sleep(0.1)
        
        if not received_fin:
            print("  [ARDUINO] ⚠️  Timeout esperando respuesta FIN")
        
        # Asegurar posición de reposo
        print("  [ARDUINO] Asegurando posición de reposo...")
        self.send_to_arduino("R")
    
    def run(self, camera_id=0):
        """Ejecuta el sistema principal"""
        print("\n" + "="*60)
        print("INICIANDO CÁMARA Y SISTEMA DE VISIÓN")
        print("="*60)
        
        # Configurar cámara
        cap = cv2.VideoCapture(camera_id)
        if not cap.isOpened():
            print("✗ No se pudo abrir la cámara")
            
            # Listar cámaras disponibles
            print("\nProbando cámaras disponibles...")
            for i in range(5):
                test_cap = cv2.VideoCapture(i)
                if test_cap.isOpened():
                    print(f"✓ Cámara {i} disponible")
                    test_cap.release()
                    cap = cv2.VideoCapture(i)
                    break
                test_cap.release()
            
            if not cap.isOpened():
                print("✗ No se encontraron cámaras disponibles")
                return
        
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        
        print(f"✓ Cámara {camera_id} configurada: 640x480 @ 30FPS")
        
        # Test de conexión Arduino si está conectado
        if self.arduino_connected:
            self.test_arduino_connection()
        
        print("\n" + "="*60)
        print("SISTEMA LISTO - CONTROLES DISPONIBLES")
        print("="*60)
        print("  M, m  - Mover brazo manualmente")
        print("  T, t  - Testear sensor DHT")
        print("  S, s  - Activar/desactivar detección automática")
        print("  R, r  - Resetear posición del brazo")
        print("  C, c  - Probar conexión Arduino")
        print("  Q, q  - Salir")
        print("="*60 + "\n")
        
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("✗ Error leyendo frame de cámara")
                    break
                
                # Procesar frame
                processed_frame, detected = self.process_frame(frame)
                
                # Mostrar información en pantalla
                status = "ACTIVA" if self.detection_active else "INACTIVA"
                status_color = (0, 255, 0) if self.detection_active else (0, 0, 255)
                
                # Información general
                cv2.putText(processed_frame, f"Deteccion: {status}", 
                           (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
                
                cv2.putText(processed_frame, f"Detectadas: {self.detection_count}", 
                           (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                
                # Estado Arduino
                arduino_status = "CONECTADO" if self.arduino_connected else "SIN ARDUINO"
                arduino_color = (0, 255, 0) if self.arduino_connected else (0, 0, 255)
                cv2.putText(processed_frame, f"Arduino: {arduino_status}", 
                           (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, arduino_color, 2)
                
                # Tiempo de espera
                if self.last_detection_time > 0:
                    time_left = self.detection_cooldown - (time.time() - self.last_detection_time)
                    if time_left > 0:
                        cv2.putText(processed_frame, f"Espera: {time_left:.1f}s", 
                                   (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)
                
                # FPS aproximado
                if hasattr(self, 'last_fps_time'):
                    fps = 1.0 / (time.time() - self.last_fps_time)
                    cv2.putText(processed_frame, f"FPS: {fps:.1f}", 
                               (10, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                self.last_fps_time = time.time()
                
                # Mostrar frame
                cv2.imshow("Sistema de Deteccion - Control de Brazo Robotico", processed_frame)
                
                # Controles de teclado
                key = cv2.waitKey(1) & 0xFF
                
                if key in [27, ord('q'), ord('Q')]:
                    print("\nSolicitando salida...")
                    break
                
                elif key in [ord('m'), ord('M')]:
                    print("\n" + "-"*40)
                    print("[MANUAL] Enviando comando 'M' a Arduino...")
                    print("-"*40)
                    self.send_to_arduino("M")
                    threading.Thread(target=self.wait_for_arduino_response, daemon=True).start()
                
                elif key in [ord('t'), ord('T')]:
                    print("\n[TEST] Enviando comando 'T' a Arduino...")
                    self.send_to_arduino("T")
                
                elif key in [ord('s'), ord('S')]:
                    self.detection_active = not self.detection_active
                    estado = "ACTIVADA" if self.detection_active else "DESACTIVADA"
                    print(f"\n[CONTROL] Detección automática {estado}")
                
                elif key in [ord('r'), ord('R')]:
                    print("\n[RESET] Enviando comando 'R' a Arduino...")
                    self.send_to_arduino("R")
                
                elif key in [ord('c'), ord('C')]:
                    print("\n[TEST CONEXION] Probando Arduino...")
                    self.test_arduino_connection()
                
                # Leer datos del Arduino continuamente (pero sin bloquear)
                self.read_from_arduino(0.05)
        
        except KeyboardInterrupt:
            print("\n⚠️  Programa interrumpido por usuario")
        except Exception as e:
            print(f"\n✗ Error inesperado: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Limpieza ordenada
            print("\n" + "="*60)
            print("FINALIZANDO SISTEMA...")
            print("="*60)
            
            # Enviar comando de reset final
            if self.arduino_connected:
                print("Enviando comando de reset final a Arduino...")
                self.send_to_arduino("R")
                time.sleep(1)
            
            # Liberar cámara
            cap.release()
            cv2.destroyAllWindows()
            
            # Cerrar conexión Arduino
            if self.arduino and self.arduino.is_open:
                self.arduino.close()
                print("✓ Conexión Arduino cerrada")
            
            # Resumen
            print(f"\n📊 RESUMEN DE EJECUCIÓN:")
            print(f"   Frames procesados: {self.frame_count}")
            print(f"   Detecciones válidas: {self.detection_count}")
            print(f"   Comandos enviados: {self.commands_sent}")
            print(f"   Arduino: {'CONECTADO' if self.arduino_connected else 'NO CONECTADO'}")
            print("\n✅ Sistema finalizado correctamente")

def main():
    """Función principal"""
    print("="*60)
    print("SISTEMA DE DETECCIÓN Y CONTROL DE BRAZO ROBÓTICO")
    print("="*60)
    
    # CONFIGURACIÓN (¡AJUSTA ESTOS VALORES!)
    MODEL_PATH = "best.pt"
    
    # Para Windows - VERIFICA EL PUERTO CORRECTO:
    # 1. Abre Administrador de Dispositivos
    # 2. Busca "Puertos (COM y LPT)"
    # 3. Mira qué COM tiene tu Arduino (ej: COM3, COM4, etc.)
    ARDUINO_PORT = "COM3"  # <-- CAMBIA ESTO SI ES NECESARIO
    
    # Para Linux/Mac:
    # ARDUINO_PORT = "/dev/ttyUSB0"  # o "/dev/ttyACM0"
    
    # Si no tienes Arduino o quieres probar solo detección:
    # ARDUINO_PORT = None
    
    print(f"\nConfiguración:")
    print(f"  Modelo: {MODEL_PATH}")
    print(f"  Puerto Arduino: {ARDUINO_PORT if ARDUINO_PORT else 'NO CONFIGURADO'}")
    
    # Verificar que el modelo existe
    import os
    if not os.path.exists(MODEL_PATH):
        print(f"\n⚠️  ADVERTENCIA: No se encuentra el modelo {MODEL_PATH}")
        print("   Asegúrate de que el archivo best.pt esté en la misma carpeta")
        respuesta = input("   ¿Continuar sin modelo? (s/n): ")
        if respuesta.lower() != 's':
            return
    
    # Crear y ejecutar detector
    try:
        detector = MacetaDetector(
            model_path=MODEL_PATH,
            arduino_port=ARDUINO_PORT
        )
        detector.run()
    except Exception as e:
        print(f"\n❌ ERROR CRÍTICO: {type(e).__name__}: {e}")
        print("\nPosibles soluciones:")
        print("1. Verifica que tengas instalado: pip install ultralytics opencv-python pyserial")
        print("2. Asegúrate de que la cámara esté conectada")
        print("3. Verifica el puerto COM del Arduino")
        print("4. Cierra Arduino IDE completamente")

if __name__ == "__main__":
    main()