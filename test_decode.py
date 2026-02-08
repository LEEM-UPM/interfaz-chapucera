import struct

# Ejemplo de paquete de prueba simulando datos del Arduino
# Timestamp: 1000 ms
# Thrust: 173.76 N → 17376 como int16
# TP1: 26.47°C → 2647 como int16
# TP2: 29.27°C → 2927 como int16
# ... más temperaturas
# Transducer: 57345

# Crear un paquete de prueba
timestamp = 1000
thrust_int = int(173.76 * 100)  # 17376
temps_int = [
    int(26.47 * 100),  # TP1: 2647
    int(29.27 * 100),  # TP2: 2927
    int(29.80 * 100),  # TP3: 2980
    int(25.29 * 100),  # TP4: 2529
    int(0 * 100),      # TP5: 0
    int(29.17 * 100),  # TP6: 2917
    int(17.27 * 100),  # TP7: 1727
    int(24.91 * 100),  # TP8: 2491
    int(21.21 * 100),  # TP9: 2121
    int(23.57 * 100),  # TP10: 2357
]
transducer = 57345

# Construir el payload (little-endian)
payload = struct.pack("<I", timestamp)  # 4 bytes
payload += struct.pack("<h", thrust_int)  # 2 bytes
for temp in temps_int:
    payload += struct.pack("<h", temp)  # 2 bytes × 10
payload += struct.pack("<H", transducer)  # 2 bytes

print(f"Payload generado: {len(payload)} bytes")
print("Bytes (hex):", payload.hex())
print()

# Ahora decodificar como lo hace Python
timestamp_ms = struct.unpack("<I", payload[0:4])[0]
thrust_raw = struct.unpack("<h", payload[4:6])[0]
thrust = thrust_raw / 100.0

temps = []
for i in range(10):
    temp_raw = struct.unpack("<h", payload[6 + i*2:8 + i*2])[0]
    temps.append(temp_raw / 100.0)

transducer_raw = struct.unpack("<H", payload[26:28])[0]

# Mostrar resultados
print(f"Timestamp: {timestamp_ms} ms")
print(f"Thrust: {thrust:.2f} N")
for i, temp in enumerate(temps):
    print(f"TP{i+1}: {temp:.2f}°C")
print(f"Transducer: {transducer_raw}")
print()
print("✓ Si ves los valores correctos, el código funciona bien")
print("✓ Si los valores están mal, hay un problema de formato")
