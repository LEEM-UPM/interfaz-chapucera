import serial
import serial.tools.list_ports
import struct
import time

# Listar puertos disponibles
ports = serial.tools.list_ports.comports()
print("Puertos disponibles:")
for i, port in enumerate(ports):
    print(f"{i}: {port.device}")

# Seleccionar puerto
port_idx = int(input("\nSelecciona el puerto (número): "))
puerto = ports[port_idx].device

# Conectar
ser = serial.Serial(puerto, 115200, timeout=1)
print(f"\nConectado a {puerto}")
print("Enviando comando 0x01 para solicitar datos...\n")

try:
    while True:
        # Limpiar buffer antes de enviar comando
        ser.reset_input_buffer()
        
        # Enviar comando para solicitar datos
        ser.write(bytes([0x01]))
        print("→ Comando 0x01 enviado")
        
        # Esperar más tiempo para que lleguen todos los datos por radio
        time.sleep(0.5)
        
        # Ver cuántos bytes hay disponibles
        bytes_disponibles = ser.in_waiting
        print(f"  Bytes en buffer: {bytes_disponibles}")
        
        # Leer header
        header = ser.read(1)
        if len(header) != 1:
            print("  ⚠ No se recibió header")
            time.sleep(1)
            continue
        
        print(f"  Header recibido: 0x{header.hex()}")
        
        if header == b"\x01":
            # Leer 28 bytes de payload
            payload = ser.read(28)
            print(f"  Payload recibido: {len(payload)} bytes")
            
            if len(payload) != 28:
                print(f"  ⚠ Payload incompleto: {len(payload)} bytes")
                print(f"  Hex: {payload.hex()}")
                # Limpiar buffer
                ser.reset_input_buffer()
                time.sleep(1)
                continue
            
            print(f"✓ Paquete recibido: {len(payload)} bytes")
            print(f"  Hex: {payload.hex()}")
            
            # Decodificar
            timestamp_ms = struct.unpack("<I", payload[0:4])[0]
            thrust_raw = struct.unpack("<h", payload[4:6])[0]
            thrust = thrust_raw / 100.0
            
            temps = []
            for i in range(10):
                temp_raw = struct.unpack("<h", payload[6 + i*2:8 + i*2])[0]
                temps.append(temp_raw / 100.0)
            
            transducer_raw = struct.unpack("<H", payload[26:28])[0]
            
            print(f"  Timestamp: {timestamp_ms} ms")
            print(f"  Thrust: {thrust:.2f} N")
            print(f"  Temperaturas: {[f'{t:.2f}' for t in temps]}")
            print(f"  Transducer: {transducer_raw}")
            print()
            
            # Limpiar buffer después de procesar exitosamente
            ser.reset_input_buffer()
        else:
            print(f"  ⚠ Header desconocido: 0x{header.hex()}")
            ser.reset_input_buffer()
        
        # Esperar antes de siguiente comando
        time.sleep(1)

except KeyboardInterrupt:
    print("\nDetenido por usuario")
finally:
    ser.close()
