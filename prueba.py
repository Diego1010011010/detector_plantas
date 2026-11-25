from ultralytics import YOLO 
import cv2 
import serial
import time
import re
import datetime

print("="*60)
print("SISTEMA DETECCIÓN DE PLANTAS + ANÁLISIS DE HUMEDAD DEL SUELO")
print("="*60)

# 1. Cargar modelo
model = YOLO("best.pt")
print("✓ Modelo cargado")

# 2. Conectar Arduino
try:
    print("Conectando Arduino COM5...")
    arduino = serial.Serial('COM5', 9600, timeout=2)
    time.sleep(3)
    
    # Leer mensaje de bienvenida
    arduino.reset_input_buffer()
    time.sleep(1)
    
    print("Esperando mensaje de Arduino...")
    for _ in range(10):
        if arduino.in_waiting:
            mensaje = arduino.readline().decode().strip()
            if mensaje:
                print(f"Arduino: {mensaje}")
                if "LISTO" in mensaje:
                    print("✓ Arduino listo")
                    break
        time.sleep(0.1)
    
    arduino_connected = True
    print("✓ Arduino CONECTADO en COM5")
    
except Exception as e:
    print(f"✗ Error conectando Arduino: {e}")
    print("⚠️  Continuando solo con detección")
    arduino = None
    arduino_connected = False

# 3. Configurar cámara
cap = cv2.VideoCapture(0)
cap.set(3, 640)
cap.set(4, 480)

if not cap.isOpened():
    print("✗ No se pudo abrir cámara")
    exit()

# Variables para almacenar datos del sensor
ultima_humedad = None
ultima_lectura = None
recomendacion_hum = ""

# Umbrales para recomendaciones de humedad (AJUSTA SEGÚN TUS PLANTAS)
HUM_BAJA = 30.0     # % - humedad baja crítica
HUM_OPTIMA_MIN = 40.0  # % - mínimo óptimo
HUM_OPTIMA_MAX = 70.0  # % - máximo óptimo
HUM_ALTA = 80.0     # % - humedad alta crítica

print(f"\n⚙️  CONFIGURACIÓN DE UMBRALES DE HUMEDAD:")
print(f"   ⚠️  CRÍTICAMENTE BAJA: < {HUM_BAJA}%")
print(f"   ✅ ÓPTIMA: {HUM_OPTIMA_MIN}% - {HUM_OPTIMA_MAX}%")
print(f"   ⚠️  CRÍTICAMENTE ALTA: > {HUM_ALTA}%")
print("="*60)

print("\nCONTROLES:")
print("  M - Mover brazo y medir humedad del suelo")
print("  T - Solo medir humedad (sin mover)")
print("  D - Activar/desactivar detección automática")
print("  R - Mostrar últimas recomendaciones")
print("  Q - Salir")
print("="*60 + "\n")

detection_active = True
last_detection = 0
cooldown = 10
targets = ["plant", "planta", "maceta", "pot", "flower", "leaf", "vase"]

def parsear_datos_sensor(texto):
    """Extrae humedad del suelo del texto"""
    try:
        # Buscar patrones como "HUM_SUELO:60.2%"
        hum_match = re.search(r'HUM_SUELO:([\d\.]+)%', texto)
        
        if hum_match:
            hum = float(hum_match.group(1))
            return hum
    except Exception as e:
        print(f"Error parseando datos: {e}")
    
    return None

def generar_recomendaciones_humedad(humedad):
    """Genera recomendaciones basadas solo en la humedad del suelo"""
    global recomendacion_hum
    
    # Recomendaciones de humedad
    if humedad < HUM_BAJA:
        recomendacion_hum = "🏜️ HUMEDAD CRÍTICAMENTE BAJA - Regar URGENTE"
        hum_color = (50, 50, 255)  # Rojo intenso
        nivel = "CRÍTICO"
    elif humedad < HUM_OPTIMA_MIN:
        recomendacion_hum = "🌵 HUMEDAD BAJA - Recomendado regar pronto"
        hum_color = (100, 100, 255)  # Rojo claro
        nivel = "BAJO"
    elif humedad <= HUM_OPTIMA_MAX:
        recomendacion_hum = "✅ HUMEDAD ÓPTIMA - Condiciones perfectas"
        hum_color = (100, 255, 100)  # Verde
        nivel = "ÓPTIMO"
    elif humedad <= HUM_ALTA:
        recomendacion_hum = "💧 HUMEDAD ALTA - Reducir frecuencia de riego"
        hum_color = (255, 255, 100)  # Amarillo
        nivel = "ALTO"
    else:
        recomendacion_hum = "🌊 HUMEDAD CRÍTICAMENTE ALTA - Riesgo de hongos"
        hum_color = (255, 100, 255)  # Magenta
        nivel = "CRÍTICO"
    
    return hum_color, nivel

def mostrar_recomendaciones_consola(humedad):
    """Muestra recomendaciones en consola con colores"""
    print("\n" + "="*60)
    print("📊 ANÁLISIS DE HUMEDAD DEL SUELO:")
    print(f"   Humedad: {humedad}%")
    print("-"*60)
    
    # Mostrar recomendaciones con emojis
    print("💡 RECOMENDACIÓN:")
    
    if humedad < HUM_BAJA:
        print("   🚨 ¡ALERTA! HUMEDAD CRÍTICAMENTE BAJA")
        print("   ⚡ ACCIÓN: Regar URGENTEMENTE")
        print("   💦 Cantidad: Riego abundante")
    elif humedad < HUM_OPTIMA_MIN:
        print("   ⚠️  HUMEDAD BAJA")
        print("   📅 ACCIÓN: Regar en las próximas 24 horas")
        print("   💧 Cantidad: Riego moderado")
    elif humedad <= HUM_OPTIMA_MAX:
        print("   ✅ HUMEDAD ÓPTIMA")
        print("   👍 Mantener frecuencia de riego actual")
        print("   📏 Monitorear cada 2-3 días")
    elif humedad <= HUM_ALTA:
        print("   ⚠️  HUMEDAD ALTA")
        print("   ⏳ ACCIÓN: Esperar 2-3 días antes de regar")
        print("   🚫 Evitar riego adicional")
    else:
        print("   🚨 ¡ALERTA! HUMEDAD CRÍTICAMENTE ALTA")
        print("   🌧️  ACCIÓN: Suspender riego inmediatamente")
        print("   ☀️  Dejar secar al sol si es posible")
    
    print("="*60 + "\n")

def leer_respuesta_arduino(timeout=5):
    """Lee la respuesta del Arduino y procesa datos del sensor de humedad"""
    global ultima_humedad, ultima_lectura, recomendacion_hum
    
    start_time = time.time()
    respuesta_completa = []
    
    print("⏳ Esperando datos del sensor de humedad...")
    
    while time.time() - start_time < timeout:
        if arduino_connected and arduino.in_waiting:
            linea = arduino.readline().decode().strip()
            if linea:
                print(f"← Arduino: {linea}")
                respuesta_completa.append(linea)
                
                # Intentar extraer datos del sensor
                humedad = parsear_datos_sensor(linea)
                if humedad is not None:
                    ultima_humedad = humedad
                    ultima_lectura = time.time()
                    
                    # Generar recomendaciones
                    hum_color, nivel = generar_recomendaciones_humedad(humedad)
                    
                    # Mostrar en consola
                    mostrar_recomendaciones_consola(humedad)
                    
                    # Guardar en archivo
                    guardar_datos_humedad(humedad, nivel)
                
                # Si recibimos FIN, terminar
                if "FIN" in linea or "COMPLETADO" in linea:
                    break
        
        time.sleep(0.1)
    
    return respuesta_completa

def guardar_datos_humedad(humedad, nivel):
    """Guarda datos de humedad en archivo CSV"""
    try:
        # Crear archivo si no existe
        try:
            with open("humedad_suelo.csv", "r") as f:
                pass
        except:
            # Crear encabezado
            with open("humedad_suelo.csv", "w") as f:
                f.write("fecha,hora,humedad_%,nivel,recomendacion\n")
        
        # Agregar datos
        now = datetime.datetime.now()
        fecha = now.strftime("%Y-%m-%d")
        hora = now.strftime("%H:%M:%S")
        
        with open("humedad_suelo.csv", "a") as f:
            f.write(f"{fecha},{hora},{humedad},{nivel},{recomendacion_hum}\n")
        
        print(f"✓ Datos de humedad guardados en humedad_suelo.csv")
        
    except Exception as e:
        print(f"✗ Error guardando datos: {e}")

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # Detectar objetos
        results = model(frame, verbose=False)
        
        detected = False
        for result in results:
            boxes = result.boxes
            if boxes is not None:
                for box in boxes:
                    conf = box.conf[0].item()
                    cls_id = int(box.cls[0].item())
                    cls_name = model.names[cls_id]
                    
                    # Verificar si es objetivo
                    if any(target in cls_name.lower() for target in targets):
                        if conf > 0.5:
                            detected = True
                            
                            # Dibujar
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                            cv2.putText(frame, f"{cls_name} {conf:.2f}", 
                                      (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 2)
                            
                            # Enviar a Arduino si está activo y conectado
                            current_time = time.time()
                            if (detection_active and 
                                arduino_connected and
                                (current_time - last_detection) > cooldown):
                                
                                print(f"\n{'='*50}")
                                print(f"🌱 DETECTADO: {cls_name} ({conf:.2f})")
                                print(f"📤 Enviando 'M' a Arduino...")
                                
                                try:
                                    arduino.write(b'M\n')
                                    arduino.flush()
                                    print("✓ Comando enviado")
                                    last_detection = current_time
                                    
                                    # Leer respuesta con datos del sensor
                                    leer_respuesta_arduino(10)
                                    
                                except Exception as e:
                                    print(f"✗ Error enviando: {e}")
                                
                                print(f"{'='*50}\n")
        
        # Mostrar información en pantalla
        # 1. Estado del sistema
        status = "ACTIVA" if detection_active else "INACTIVA"
        color = (0, 255, 0) if detection_active else (0, 0, 255)
        cv2.putText(frame, f"Deteccion: {status}", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        
        # 2. Estado Arduino
        arduino_text = "CONECTADO" if arduino_connected else "NO CONECTADO"
        arduino_color = (0, 255, 0) if arduino_connected else (0, 0, 255)
        cv2.putText(frame, f"Arduino: {arduino_text}", (10, 60), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, arduino_color, 2)
        
        # 3. Mostrar datos de humedad si están disponibles
        y_pos = 90
        if ultima_humedad is not None:
            # Título
            cv2.putText(frame, "HUMEDAD DEL SUELO:", (10, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            y_pos += 25
            
            # Valor de humedad con color según nivel
            hum_color, nivel = generar_recomendaciones_humedad(ultima_humedad)
            
            # Mostrar valor numérico
            cv2.putText(frame, f"Valor: {ultima_humedad}%", (10, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, hum_color, 2)
            y_pos += 30
            
            # Mostrar nivel
            nivel_text = f"Nivel: {nivel}"
            cv2.putText(frame, nivel_text, (10, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, hum_color, 1)
            y_pos += 25
            
            # Mostrar recomendación resumida
            if recomendacion_hum:
                # Dividir texto largo en líneas
                lines = []
                current_line = ""
                for word in recomendacion_hum.split():
                    if len(current_line + word) <= 30:
                        current_line += word + " "
                    else:
                        lines.append(current_line)
                        current_line = word + " "
                if current_line:
                    lines.append(current_line)
                
                for i, line in enumerate(lines):
                    cv2.putText(frame, line, (10, y_pos), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, hum_color, 1)
                    y_pos += 20
                    if y_pos > 400:  # Evitar salirse de la pantalla
                        break
            
            # Tiempo desde última lectura
            if ultima_lectura:
                tiempo_transcurrido = int(time.time() - ultima_lectura)
                if tiempo_transcurrido < 60:
                    tiempo_text = f"Medido hace: {tiempo_transcurrido}s"
                else:
                    minutos = tiempo_transcurrido // 60
                    tiempo_text = f"Medido hace: {minutos}min"
                
                cv2.putText(frame, tiempo_text, (10, y_pos), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                y_pos += 20
        
        # 4. Barra de progreso de humedad
        if ultima_humedad is not None:
            # Posición y dimensiones de la barra
            bar_x, bar_y = 400, 80
            bar_width, bar_height = 200, 20
            
            # Dibujar barra de fondo
            cv2.rectangle(frame, (bar_x, bar_y), 
                         (bar_x + bar_width, bar_y + bar_height), 
                         (100, 100, 100), -1)
            
            # Calcular progreso (0-100% en 200px)
            progress = min(max(ultima_humedad, 0), 100)
            progress_width = int((progress / 100) * bar_width)
            
            # Dibujar barra de progreso con color según nivel
            hum_color, _ = generar_recomendaciones_humedad(ultima_humedad)
            cv2.rectangle(frame, (bar_x, bar_y), 
                         (bar_x + progress_width, bar_y + bar_height), 
                         hum_color, -1)
            
            # Bordes de la barra
            cv2.rectangle(frame, (bar_x, bar_y), 
                         (bar_x + bar_width, bar_y + bar_height), 
                         (255, 255, 255), 1)
            
            # Texto de la barra
            cv2.putText(frame, "Humedad:", (bar_x, bar_y - 10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # 5. Tiempo de espera para siguiente detección
        if last_detection > 0:
            tiempo_restante = cooldown - (time.time() - last_detection)
            if tiempo_restante > 0:
                wait_text = f"Espera: {tiempo_restante:.1f}s"
                cv2.putText(frame, wait_text, (10, 450), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)
        
        # Mostrar frame
        cv2.imshow("Sistema Deteccion + Analisis Humedad", frame)
        
        # Controles de teclado
        key = cv2.waitKey(1) & 0xFF
        
        if key in [27, ord('q')]:
            print("\nSaliendo del programa...")
            break
        
        elif key == ord('m') and arduino_connected:
            print(f"\n{'='*50}")
            print("[MANUAL] Moviendo brazo y midiendo humedad...")
            print(f"{'='*50}")
            arduino.write(b'M\n')
            arduino.flush()
            leer_respuesta_arduino(10)
        
        elif key == ord('t') and arduino_connected:
            print(f"\n{'='*50}")
            print("[TEST] Midiendo solo sensor de humedad...")
            print(f"{'='*50}")
            arduino.write(b'T\n')
            arduino.flush()
            leer_respuesta_arduino(5)
        
        elif key == ord('d'):
            detection_active = not detection_active
            estado = "activada" if detection_active else "desactivada"
            print(f"\n[CONTROL] Detección automática {estado}")
        
        elif key == ord('r'):
            # Mostrar últimas recomendaciones
            if ultima_humedad is not None:
                print(f"\n{'='*60}")
                print("📋 RESUMEN DE HUMEDAD:")
                print(f"   Última humedad: {ultima_humedad}%")
                print(f"   Recomendación: {recomendacion_hum}")
                print("="*60 + "\n")
            else:
                print("\n⚠️  No hay datos de humedad aún")
        
        # Leer cualquier dato adicional del Arduino
        if arduino_connected and arduino.in_waiting:
            extra = arduino.readline().decode().strip()
            if extra and not ("HUM" in extra):
                print(f"[INFO] Arduino: {extra}")

except KeyboardInterrupt:
    print("\nPrograma interrumpido por usuario")
    
except Exception as e:
    print(f"\n✗ Error inesperado: {e}")
    
finally:
    # Limpiar todo
    print("\n" + "="*60)
    print("FINALIZANDO SISTEMA...")
    print("="*60)
    
    # Cerrar cámara
    cap.release()
    cv2.destroyAllWindows()
    
    # Cerrar Arduino
    if arduino_connected and arduino:
        print("Desconectando Arduino...")
        try:
            arduino.write(b'\n')
            arduino.close()
            print("✓ Arduino desconectado")
        except:
            pass
    
    # Resumen final
    print(f"\n📊 RESUMEN FINAL:")
    print(f"   Arduino: {'CONECTADO' if arduino_connected else 'NO CONECTADO'}")
    if ultima_humedad is not None:
        print(f"   Última humedad del suelo: {ultima_humedad}%")
        print(f"   Recomendación final: {recomendacion_hum}")
        print(f"   Número de mediciones guardadas: Consultar humedad_suelo.csv")
    print(f"   Detecciones realizadas: {int(last_detection > 0)}")
    print(f"   Datos guardados en: humedad_suelo.csv")
    
    print("\n✅ Programa finalizado correctamente")
    print("="*60)