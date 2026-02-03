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
COMANDO_IGNITAR = b'\x01'  # Se envía 1 byte para ignitar
COMANDO_DATOS = b'\x02'
COMANDO_STOP = b'\x03'
BYTES_POR_PAQUETE = 24
MAX_PUNTOS = 1000
CUENTA_REGRESIVA = 10  # segundos
# ----------------------------------

# ---------- VARIABLES GLOBALES ----------
ser = None
leyendo = False
medicion_activa = False
ignition_countdown = False
ignitar_flag = False
archivo_salida = "datos.txt"
tiempo_base = None
contador_paquetes = 0
ultimo_calculo_hz = None
hz_actual = 0.0

# Datos para gráficas
tiempos = deque(maxlen=MAX_PUNTOS)
presiones = deque(maxlen=MAX_PUNTOS)
ns = deque(maxlen=MAX_PUNTOS)
temperaturas = [deque(maxlen=MAX_PUNTOS) for _ in range(10)]

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
    global ser, leyendo, medicion_activa, ignition_countdown, ignitar_flag
    global contador_paquetes, ultimo_calculo_hz, hz_actual

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
    btn_ignitar.config(state="normal")

# ---------- START / STOP ----------
def toggle_medicion():
    global medicion_activa, tiempo_base

    if not ser or not ser.is_open:
        messagebox.showwarning("Aviso", "Conecta el puerto primero")
        return

    medicion_activa = not medicion_activa

    if medicion_activa:
        tiempos.clear()
        presiones.clear()
        ns.clear()
        for t in temperaturas:
            t.clear()

        tiempo_base = None
        ser.reset_input_buffer()

        try:
            ser.write(COMANDO_DATOS)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            medicion_activa = False
            return

        estado_medicion.config(text="Medición: ACTIVA", fg="green")
        btn_start_stop.config(text="STOP", bg="orange")
    else:
        try:
            ser.write(COMANDO_STOP)
        except Exception:
            pass

        estado_medicion.config(text="Medición: DETENIDA", fg="red")
        btn_start_stop.config(text="START", bg="green")

def get_value():
    if not ser or not ser.is_open:
        messagebox.showwarning("Aviso", "Puerto no conectado")
        return
    ser.write(bytes([0x01]))

# ---------- BOTÓN IGNITAR ----------
def iniciar_ignitar():
    global ignition_countdown

    if not ser or not ser.is_open:
        messagebox.showwarning("Aviso", "Conecta el puerto primero")
        return

    # Doble confirmación
    if not messagebox.askyesno("Confirmación", "¿Estás seguro de que quieres iniciar la ignición?"):
        return
    if not messagebox.askyesno("Confirmación final", "Esta acción no se puede deshacer. ¿Deseas continuar?"):
        return

    # Desactivar botón para evitar presionar varias veces
    btn_ignitar.config(state="disabled")
    ignition_countdown = True
    threading.Thread(target=cuenta_regresiva_ignitar, daemon=True).start()

def cuenta_regresiva_ignitar():
    global ignition_countdown, ignitar_flag
    for i in range(CUENTA_REGRESIVA, 0, -1):
        # Mostrar cuenta atrás en ventana aparte (label temporal)
        countdown_label.config(text=f"¡Ignición en {i} s!", fg="red", font=("Arial", 20, "bold"))
        time.sleep(1)

    # Enviar comando de ignición
    try:
        ser.write(COMANDO_IGNITAR)
        ignitar_flag = True
        countdown_label.config(text="¡Ignición ACTIVADA!", fg="green", font=("Arial", 20, "bold"))
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo enviar el comando de ignición: {e}")

    ignition_countdown = False
    btn_ignitar.config(state="normal")
    time.sleep(2)
    countdown_label.config(text="")  # Limpiar label tras 2 segundos

# ---------- PUERTOS ----------
def obtener_puertos():
    return [p.device for p in serial.tools.list_ports.comports()]

def refrescar_puertos():
    global puertos_actuales

    nuevos_puertos = obtener_puertos()
    if not nuevos_puertos:
        nuevos_puertos = ["No hay puertos"]

    if nuevos_puertos != puertos_actuales:
        puertos_actuales = nuevos_puertos
        menu = puerto_menu["menu"]
        menu.delete(0, "end")
        for puerto in puertos_actuales:
            menu.add_command(label=puerto, command=lambda v=puerto: puerto_var.set(v))
        if puerto_var.get() not in puertos_actuales:
            puerto_var.set(puertos_actuales[0])

    ventana.after(1000, refrescar_puertos)

# ---------- LECTURA SERIAL ----------
def leer_datos():
    global tiempo_base, contador_paquetes, ultimo_calculo_hz, hz_actual

    with open(archivo_salida, "w") as archivo:
        archivo.write(
            "Tiempo_s "
            + " ".join([f"Tp{i+1}" for i in range(10)])
            + " Presion Newtons\n"
        )

        while leyendo:
            raw = ser.read(24)
            if len(raw) != 24:
                continue

            valores = struct.unpack("<12H", raw)

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

            tp = valores[:10]
            presion = valores[10]
            fuerza = valores[11]

            for i in range(10):
                tabla_valores[i].set(f"Tp{i+1}: {tp[i]}")

            ps_var.set(f"Ps: {presion}")
            n_var.set(f"N: {fuerza}")

            if not medicion_activa:
                continue

            if tiempo_base is None:
                tiempo_base = time.time()

            tiempo_s = time.time() - tiempo_base

            tiempos.append(tiempo_s)
            presiones.append(presion)
            ns.append(fuerza)

            for i in range(10):
                temperaturas[i].append(tp[i])

            # Solo actualizar el label de valor normal, no interferir con countdown_label
            valor_label.config(
                text=f"P: {presion} | N: {fuerza} | t: {tiempo_s:.2f}s",
                font=("Arial", 12),
                fg="black"
            )

            archivo.write(
                f"{tiempo_s:.3f} "
                + " ".join(str(v) for v in tp)
                + f" {presion} {fuerza}\n"
            )
            archivo.flush()

# ---------- GRÁFICAS ----------
def actualizar_graficas():
    if leyendo and tiempos:
        ax_presion.clear()
        ax_n.clear()
        ax_temperatura.clear()

        for i in range(10):
            ax_temperatura.plot(tiempos, temperaturas[i], label=f"Tp{i+1}")

        ax_temperatura.set_ylabel("Temperatura")
        ax_temperatura.grid(True)
        ax_temperatura.legend(fontsize=8, ncol=2)

        ax_presion.plot(tiempos, presiones, color="blue", label="Presión")
        ax_presion.set_ylabel("Presión")
        ax_presion.grid(True)
        ax_presion.legend()

        ax_n.plot(tiempos, ns, color="green", label="Newtons")
        ax_n.set_ylabel("N")
        ax_n.set_xlabel("Tiempo [s]")
        ax_n.grid(True)
        ax_n.legend()

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

frame_config = tk.Frame(ventana, width=300)
frame_config.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)
frame_config.pack_propagate(False)

frame_right = tk.Frame(ventana)
frame_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

frame_graficas = tk.Frame(frame_right)
frame_graficas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

frame_tabla = tk.Frame(frame_right)
frame_tabla.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

tk.Label(frame_config, text="Puerto COM").pack(anchor="w", pady=2)
puerto_var = tk.StringVar()
puertos_actuales = obtener_puertos()
if not puertos_actuales:
    puertos_actuales = ["No hay puertos"]

puerto_var.set(puertos_actuales[0])
puerto_menu = tk.OptionMenu(frame_config, puerto_var, puertos_actuales[0], *puertos_actuales[1:])
puerto_menu.pack(fill="x")

tk.Label(frame_config, text="Baudrate").pack(anchor="w", pady=2)
baudrate_var = tk.StringVar(value="115200")
tk.Entry(frame_config, textvariable=baudrate_var).pack(fill="x")

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

# Label para mostrar la cuenta atrás de ignición
countdown_label = tk.Label(frame_config, text="", fg="red", font=("Arial", 14, "bold"))
countdown_label.pack(pady=5)

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
    command=iniciar_ignitar
)
btn_ignitar.pack(pady=8)

fig, (ax_presion, ax_n, ax_temperatura) = plt.subplots(3, 1, figsize=(6, 8))
canvas = FigureCanvasTkAgg(fig, master=frame_graficas)
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

tabla_valores = []
for i in range(10):
    var = tk.StringVar(value=f"Tp{i+1}: 0.00")
    fila = i % 5
    col = i // 5
    lbl = tk.Label(frame_tabla, textvariable=var, width=16, anchor="w", font=("Arial", 12, "bold"))
    lbl.grid(row=fila, column=col, padx=4, pady=4, sticky="w")
    tabla_valores.append(var)

ps_var = tk.StringVar(value="Ps: 0.00")
tk.Label(frame_tabla, textvariable=ps_var, width=16, font=("Arial", 12, "bold")).grid(row=5, column=0)

n_var = tk.StringVar(value="N: 0.00")
tk.Label(frame_tabla, textvariable=n_var, width=16, font=("Arial", 12, "bold")).grid(row=5, column=1)

ventana.protocol("WM_DELETE_WINDOW", cerrar)
ventana.after(1000, refrescar_puertos)
ventana.mainloop()
