import serial
import serial.tools.list_ports
import time
import threading
import tkinter as tk
from tkinter import messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from collections import deque
import struct
import sys

# ---------- CONFIGURACIÓN ----------
TIMEOUT = 1
COMANDO_IGNITAR = b'IGNITAR\n'
COMANDO_DATOS = b'\x02'
COMANDO_STOP = b'\x03'
COMANDO_IGNICION = b'\x04'
BYTES_POR_PAQUETE = 12
MAX_PUNTOS = 1000
# ----------------------------------

# ---------- VARIABLES GLOBALES ----------
ser = None
leyendo = False
medicion_activa = False
ignition_countdown = False
ignitar_flag = False  # Flag que controla el envío de ignición
archivo_salida = "datos.txt"  # archivo por defecto
tiempo_base = None
contador_paquetes = 0
ultimo_calculo_hz = None
hz_actual = 0.0

# Datos para gráficas
tiempos = deque(maxlen=MAX_PUNTOS)
presiones = deque(maxlen=MAX_PUNTOS)
ns = deque(maxlen=MAX_PUNTOS)
temperaturas = deque(maxlen=MAX_PUNTOS)

# ---------------- FUNCIONES ----------------
# ---------- BOTONES ----------
def conectar():
    global ser, leyendo, archivo_salida

    puerto = puerto_var.get()
    if puerto == "No hay puertos":
        messagebox.showwarning("Aviso", "No hay puertos disponibles")
        return

    archivo_salida = archivo_var.get().strip() or "datos.txt"

    try:
        ser = serial.Serial(puerto, int(baudrate_var.get()), timeout=TIMEOUT)
        time.sleep(2)

        leyendo = True
        threading.Thread(target=leer_datos, daemon=True).start()
        actualizar_graficas()

        estado_label.config(text="Estado: Conectado", fg="green")
        btn_conectar.config(state="disabled")
        btn_desconectar.config(state="normal")

    except Exception as e:
        messagebox.showerror("Error", str(e))

def desconectar():
    global ser, leyendo, medicion_activa, ignition_countdown, ignitar_flag, contador_paquetes, ultimo_calculo_hz, hz_actual

    leyendo = False
    medicion_activa = False
    ignition_countdown = False
    ignitar_flag = False
    contador_paquetes = 0
    ultimo_calculo_hz = None
    hz_actual = 0.0

    if ser and ser.is_open:
        ser.close()
    ser = None

    estado_label.config(text="Estado: Desconectado", fg="red")
    estado_medicion.config(text="Medición: DETENIDA", fg="red")
    hz_label.config(text="Frecuencia: 0.0 Hz")
    btn_start_stop.config(text="START", bg="green")
    btn_conectar.config(state="normal")
    btn_desconectar.config(state="disabled")

# ---------- START / STOP ----------
def toggle_medicion():
    global medicion_activa, tiempo_base

    if not ser or not ser.is_open:
        messagebox.showwarning("Aviso", "Conecta el puerto primero")
        return

    medicion_activa = not medicion_activa

    if medicion_activa:
        # Limpiar datos anteriores
        tiempos.clear()
        presiones.clear()
        ns.clear()
        temperaturas.clear()
        tiempo_base = None
        
        ser.reset_input_buffer()  # descarta datos antiguos
        try:
            ser.write(COMANDO_DATOS)  # Enviar comando 0x02 al iniciar
            valor_label.config(
                text="¡COMANDO 0x02 ENVIADO!",
                font=("Arial", 16, "bold"),
                fg="green"
            )
        except Exception as e:
            messagebox.showerror("Error", f"Error al enviar comando: {e}")
            medicion_activa = False
            return
        estado_medicion.config(text="Medición: ACTIVA", fg="green")
        btn_start_stop.config(text="STOP", bg="orange")
    else:
        try:
            ser.write(COMANDO_STOP)  # Enviar comando 0x03 al detener
            valor_label.config(
                text="¡COMANDO 0x03 ENVIADO!",
                font=("Arial", 16, "bold"),
                fg="orange"
            )
        except Exception as e:
            messagebox.showerror("Error", f"Error al enviar comando STOP: {e}")
        estado_medicion.config(text="Medición: DETENIDA", fg="red")
        btn_start_stop.config(text="START", bg="green")

def mostrar_ultimo_valor():
    if not tiempos:
        messagebox.showinfo("Get Value", "Aún no hay datos")
        return

    presion = presiones[-1]
    temperatura = temperaturas[-1]
    tiempo_s = tiempos[-1]
    messagebox.showinfo(
        "Get Value",
        f"P: {presion:.2f} | T: {temperatura:.2f} | t: {tiempo_s:.2f}s"
    )

def get_value():  # obtenemos una tanda de valor de los sensores para verificar su operatividad
    if not ser or not ser.is_open:
        messagebox.showwarning("Aviso", "Puerto no conectado")
        return

    ser.reset_input_buffer()  # Limpiar buffer antes de solicitar datos
    ser.write(bytes([0x01])) # Comando para solicitar datos de sensores

def ignitar():
    global ignition_countdown

    if not ser or not ser.is_open:
        messagebox.showwarning("Aviso", "Puerto no conectado")
        return

    if ignition_countdown:
        return

    ignition_countdown = True
    cuenta_regresiva(10)

def cuenta_regresiva(segundos):
    global ignition_countdown, medicion_activa, tiempo_base

    if segundos >= 0:
        valor_label.config(
            text=f"IGNICIÓN EN {segundos} s",
            font=("Arial", 24, "bold"),
            fg="red"
        )
        ventana.after(1000, lambda: cuenta_regresiva(segundos - 1))
    else:
        ignition_countdown = False
        # Enviar comando directamente aquí
        try:
            # Limpiar datos anteriores y buffer
            tiempos.clear()
            presiones.clear()
            ns.clear()
            temperaturas.clear()
            tiempo_base = None
            ser.reset_input_buffer()
            
            ser.write(COMANDO_IGNICION)
            print("Comando 0x04 enviado por el puerto serie")
            # Activar medición automáticamente
            medicion_activa = True
            estado_medicion.config(text="Medición: ACTIVA", fg="green")
            btn_start_stop.config(text="STOP", bg="orange")
            valor_label.config(
                text="¡COMANDO 0x04 ENVIADO!",
                font=("Arial", 20, "bold"),
                fg="green"
            )
        except Exception as e:
            print(f"Error enviando ignición: {e}")
            messagebox.showerror("Error", f"Error al enviar comando: {e}")

# ---------- PUERTOS ----------
def obtener_puertos():
    return [p.device for p in serial.tools.list_ports.comports()]

def refrescar_puertos():
    global puertos_actuales

    nuevos_puertos = obtener_puertos()
    if nuevos_puertos != puertos_actuales:
        puertos_actuales = nuevos_puertos

        menu = puerto_menu["menu"]
        menu.delete(0, "end")

        if puertos_actuales:
            for puerto in puertos_actuales:
                menu.add_command(label=puerto, command=lambda v=puerto: puerto_var.set(v))
            if puerto_var.get() not in puertos_actuales:
                puerto_var.set(puertos_actuales[0])
        else:
            menu.add_command(
                label="No hay puertos",
                command=lambda: puerto_var.set("No hay puertos")
            )
            puerto_var.set("No hay puertos")

    ventana.after(1000, refrescar_puertos)

# ---------- LECTURA SERIAL ----------
def leer_datos():
    global ignitar_flag, tiempo_base, contador_paquetes, ultimo_calculo_hz, hz_actual
    with open(archivo_salida, 'w') as archivo:
        # Header con todas las columnas
        header = f"{'Timestamp_ms':>13} {'Tiempo_s':>10} {'Thrust_N':>12}"
        for i in range(1, 11):
            header += f" {'Tp'+str(i)+'_C':>10}"
        header += f" {'Transducer':>12}\n"
        archivo.write(header)

        while leyendo:
            encabezado = ser.read(1)
            if len(encabezado) != 1:
                continue

            if encabezado == b"\x01":
                # Calcular Hz cada segundo
                ahora = time.time()
                if ultimo_calculo_hz is None:
                    ultimo_calculo_hz = ahora
                    contador_paquetes = 0
                elif ahora - ultimo_calculo_hz >= 1.0:
                    hz_actual = contador_paquetes / (ahora - ultimo_calculo_hz)
                    hz_label.config(text=f"Frecuencia: {hz_actual:.1f} Hz")
                    contador_paquetes = 0
                    ultimo_calculo_hz = ahora
                
                contador_paquetes += 1
                # Nueva estructura: 4 (timestamp) + 2 (thrust) + 20 (10 temps) + 2 (transducer) = 28 bytes
                payload = ser.read(28)
                if len(payload) != 28:
                    ser.reset_input_buffer()  # Limpiar buffer si payload incompleto
                    continue

                # Desempaquetar: 1 uint32, 1 int16, 10 int16, 1 uint16
                # Formato little-endian (nativo de ARM/Arduino)
                timestamp_ms = struct.unpack("<I", payload[0:4])[0]
                thrust_raw = struct.unpack("<h", payload[4:6])[0]
                thrust = thrust_raw / 100.0  # Dividir por 100 para obtener valor real
                
                # 10 temperaturas (multiplicadas por 100)
                temps = []
                for i in range(10):
                    temp_raw = struct.unpack("<h", payload[6 + i*2:8 + i*2])[0]
                    temps.append(temp_raw / 100.0)
                
                transducer_raw = struct.unpack("<H", payload[26:28])[0]
                
                # Actualizar interfaz
                for i in range(10):
                    tabla_valores[i].set(f"Tp{i + 1}: {temps[i]:.2f}°C")

                ps_var.set(f"Thrust: {thrust:.2f} N")
                n_var.set(f"Transducer: {transducer_raw}")
                timestamp_var.set(f"Timestamp: {timestamp_ms} ms")

                # Solo graficar cuando la medición está activa
                if medicion_activa:
                    if tiempo_base is None:
                        tiempo_base = time.time()
                    tiempo_s = time.time() - tiempo_base
                    tp_promedio = sum(temps) / 10.0
                    
                    # Mostrar valores actuales si no hay cuenta regresiva
                    if not ignition_countdown:
                        valor_label.config(
                            text=f"Thrust: {thrust:.2f} N | T: {tp_promedio:.1f}°C | t: {tiempo_s:.2f}s",
                            font=("Arial", 12),
                            fg="black"
                        )
                    
                    # Guardar datos en archivo con todas las temperaturas individuales
                    linea = f"{timestamp_ms:13} {tiempo_s:10.3f} {thrust:12.3f}"
                    for temp in temps:
                        linea += f" {temp:10.3f}"
                    linea += f" {transducer_raw:12}\n"
                    archivo.write(linea)
                    archivo.flush()
                    
                    tiempos.append(tiempo_s)
                    presiones.append(thrust)  # Ahora es thrust en lugar de presión
                    ns.append(transducer_raw)
                    temperaturas.append(tp_promedio)
                
                # Limpiar buffer después de procesar exitosamente
                ser.reset_input_buffer()
                continue

            # Si no es 0x01, limpiar buffer y esperar
            ser.reset_input_buffer()
            time.sleep(0.01)

# ---------- GRÁFICAS ----------
def actualizar_graficas():
    if leyendo:
        if tiempos and presiones and ns and temperaturas:
            ax_presion.clear()
            ax_n.clear()
            ax_temperatura.clear()

            ax_presion.plot(tiempos, presiones, color="blue", label="Thrust")
            ax_presion.set_ylabel("Thrust [N]")
            ax_presion.grid(True)
            ax_presion.legend()

            ax_n.plot(tiempos, ns, color="green", label="Transducer")
            ax_n.set_ylabel("Transducer [raw]")
            ax_n.grid(True)
            ax_n.legend()

            ax_temperatura.plot(tiempos, temperaturas, color="red", label="Temperatura")
            ax_temperatura.set_ylabel("Temp [°C]")
            ax_temperatura.set_xlabel("Tiempo [s]")
            ax_temperatura.grid(True)
            ax_temperatura.legend()

            canvas.draw()

        ventana.after(200, actualizar_graficas)

def cerrar():
    desconectar()
    ventana.destroy()
    sys.exit()

# ---------------- INTERFAZ ----------------
ventana = tk.Tk()
ventana.title("Interfaz LEEM")
ventana.geometry("900x600")

frame_config = tk.Frame(ventana, width=240)
frame_config.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)
frame_config.pack_propagate(False)

frame_right = tk.Frame(ventana)
frame_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

frame_graficas = tk.Frame(frame_right)
frame_graficas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

frame_tabla = tk.Frame(frame_right)
frame_tabla.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

# Puerto COM
tk.Label(frame_config, text="Puerto COM").pack(anchor="w", pady=2)
puerto_var = tk.StringVar()
puertos_actuales = obtener_puertos()
if puertos_actuales:
    puerto_var.set(puertos_actuales[0])
else:
    puerto_var.set("No hay puertos")

puerto_menu = tk.OptionMenu(
    frame_config,
    puerto_var,
    *(puertos_actuales if puertos_actuales else ["No hay puertos"])
)
puerto_menu.pack(fill="x")

# Baudrate
tk.Label(frame_config, text="Baudrate").pack(anchor="w", pady=2)
baudrate_var = tk.StringVar(value="115200")
tk.Entry(frame_config, textvariable=baudrate_var).pack(fill="x")

# Archivo de salida
tk.Label(frame_config, text="Archivo de salida").pack(anchor="w", pady=2)
archivo_var = tk.StringVar(value="datos.txt")
tk.Entry(frame_config, textvariable=archivo_var).pack(fill="x")

estado_label = tk.Label(frame_config, text="Estado: Desconectado", fg="red")
estado_label.pack(pady=5)

estado_medicion = tk.Label(frame_config, text="Medición: DETENIDA", fg="red")
estado_medicion.pack(pady=5)

hz_label = tk.Label(frame_config, text="Frecuencia: 0.0 Hz", fg="blue")
hz_label.pack(pady=5)

valor_label = tk.Label(frame_config, text="Valor: ---")
valor_label.pack(pady=10)

btn_conectar = tk.Button(frame_config, text="Conectar", width=15, command=conectar)
btn_conectar.pack(pady=3)

btn_desconectar = tk.Button(frame_config, text="Desconectar", width=15, command=desconectar)
btn_desconectar.pack(pady=3)

btn_start_stop = tk.Button(
    frame_config, text="START", width=15,
    bg="green", fg="white",
    font=("Arial", 12, "bold"),
    command=toggle_medicion
)
btn_start_stop.pack(pady=8)

btn_get_value = tk.Button(
    frame_config, text="GET VALUE", width=15,
    bg="blue", fg="white",
    font=("Arial", 10, "bold"),
    command=get_value
)
btn_get_value.pack(pady=6)

btn_ignitar = tk.Button(
    frame_config, text="IGNITAR", width=15,
    bg="red", fg="white",
    font=("Arial", 12, "bold"),
    command=ignitar
)
btn_ignitar.pack(pady=8)

fig, (ax_presion, ax_n, ax_temperatura) = plt.subplots(3, 1, figsize=(6, 8))
canvas = FigureCanvasTkAgg(fig, master=frame_graficas)
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

# Tabla a la derecha de las gráficas (2 columnas)
tabla_valores = []
for i in range(10):
    var = tk.StringVar(value=f"Tp{i + 1}: 0.00")
    fila = i % 5
    col = i // 5
    lbl = tk.Label(frame_tabla, textvariable=var, width=16, anchor="w", font=("Arial", 12, "bold"))
    lbl.grid(row=fila, column=col, padx=4, pady=4, sticky="w")
    tabla_valores.append(var)

# Recuadros adicionales
ps_var = tk.StringVar(value="Ps: 0.00")
ps_lbl = tk.Label(frame_tabla, textvariable=ps_var, width=16, anchor="w", font=("Arial", 12, "bold"))
ps_lbl.grid(row=5, column=0, padx=4, pady=6, sticky="w")

n_var = tk.StringVar(value="N: 0.00")
n_lbl = tk.Label(frame_tabla, textvariable=n_var, width=16, anchor="w", font=("Arial", 12, "bold"))
n_lbl.grid(row=5, column=1, padx=4, pady=6, sticky="w")

# Timestamp
timestamp_var = tk.StringVar(value="Timestamp: 0 ms")
timestamp_lbl = tk.Label(frame_tabla, textvariable=timestamp_var, width=34, anchor="w", font=("Arial", 10, "bold"), fg="blue")
timestamp_lbl.grid(row=6, column=0, columnspan=2, padx=4, pady=6, sticky="w")

ventana.protocol("WM_DELETE_WINDOW", cerrar)
ventana.after(1000, refrescar_puertos)
ventana.mainloop()
