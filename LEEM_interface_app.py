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
            ser.write(COMANDO_IGNICION)
            print("Comando 0x04 enviado por el puerto serie")
            # Activar medición automáticamente
            medicion_activa = True
            # Limpiar datos anteriores
            tiempos.clear()
            presiones.clear()
            ns.clear()
            temperaturas.clear()
            tiempo_base = None
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
        archivo.write(f"{'Presion':>12} {'Temp':>8} {'Tiempo_s':>10}\n")

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
                payload = ser.read(24)
                if len(payload) != 24:
                    continue

                valores = struct.unpack(">12H", payload)
                for i in range(10):
                    tabla_valores[i].set(f"Tp{i + 1}: {valores[i]}")

                ps_var.set(f"Ps: {valores[10]}")
                n_var.set(f"N: {valores[11]}")

                # Solo graficar cuando la medición está activa
                if medicion_activa:
                    if tiempo_base is None:
                        tiempo_base = time.time()
                    tiempo_s = time.time() - tiempo_base
                    tp_promedio = sum(valores[:10]) / 10.0
                    
                    # Mostrar valores actuales si no hay cuenta regresiva
                    if not ignition_countdown:
                        valor_label.config(
                            text=f"P: {valores[10]} | T: {tp_promedio:.1f} | t: {tiempo_s:.2f}s",
                            font=("Arial", 12),
                            fg="black"
                        )
                    
                    tiempos.append(tiempo_s)
                    presiones.append(valores[10])
                    ns.append(valores[11])
                    temperaturas.append(tp_promedio)
                continue

            if not medicion_activa:
                time.sleep(0.05)
                continue

            datos = encabezado + ser.read(BYTES_POR_PAQUETE - 1)
            if len(datos) != BYTES_POR_PAQUETE:
                continue

            presion, temperatura, tiempo_ms = struct.unpack(">ffI", datos)
            tiempo_s = tiempo_ms / 1000.0

            if not ignition_countdown:
                valor_label.config(
                    text=f"P: {presion:.2f} | T: {temperatura:.2f} | t: {tiempo_s:.2f}s",
                    font=("Arial", 12),
                    fg="black"
                )

            archivo.write(f"{presion:12.3f} {temperatura:8.3f} {tiempo_s:10.3f}\n")
            archivo.flush()

            tiempos.append(tiempo_s)
            presiones.append(presion)
            temperaturas.append(temperatura)

# ---------- GRÁFICAS ----------
def actualizar_graficas():
    if leyendo:
        if tiempos and presiones and ns and temperaturas:
            ax_presion.clear()
            ax_n.clear()
            ax_temperatura.clear()

            ax_presion.plot(tiempos, presiones, color="blue", label="Presión")
            ax_presion.set_ylabel("Presión [Pa]")
            ax_presion.grid(True)
            ax_presion.legend()

            ax_n.plot(tiempos, ns, color="green", label="N")
            ax_n.set_ylabel("N")
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

ventana.protocol("WM_DELETE_WINDOW", cerrar)
ventana.after(1000, refrescar_puertos)
ventana.mainloop()
