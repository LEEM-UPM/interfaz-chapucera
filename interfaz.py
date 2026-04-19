import serial
import serial.tools.list_ports
import time
import threading
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from collections import deque
from queue import Queue, Empty
import struct
import sys


# ---------- CONFIGURACIÓN ----------
TIMEOUT = 1
COMANDO_DATOS     = b'\x02'
COMANDO_STOP      = b'\x03'
COMANDO_IGNICION  = b'\x04'
MAX_PUNTOS        = 1000
# ----------------------------------

# ---------- PRESIÓN: constantes precalculadas ----------
# Original pipeline:
#   v   = (raw / 4095) * 3.3
#   i   = v / 150
#   psi = (i - 0.004) * 312500
#   bar = psi * 0.0689476 + 1.01325
#
# Desarrollado:
#   bar = raw * (3.3 / 4095 / 150 * 312500 * 0.0689476)
#              + (-0.004 * 312500 * 0.0689476 + 1.01325)
#
_BAR_K      = (3.3 / 4095) / 150 * 312500 * 0.0689476   # ≈ 1.1065e-4  bar/LSB
_BAR_OFFSET = -0.004 * 312500 * 0.0689476 + 1.01325      # ≈ -85.1735   bar
# bar = raw * _BAR_K + _BAR_OFFSET
# -------------------------------------------------------

# ---------- VARIABLES GLOBALES ----------
ser               = None
leyendo           = False
medicion_activa   = False
ignition_countdown = False
archivo_salida    = "datos.txt"
tiempo_base       = None

contador_paquetes  = 0
ultimo_calculo_hz  = None
hz_actual          = 0.0

data_queue = Queue(maxsize=500)

tiempos      = deque(maxlen=MAX_PUNTOS)
presiones    = deque(maxlen=MAX_PUNTOS)
ns           = deque(maxlen=MAX_PUNTOS)
temperaturas = deque(maxlen=MAX_PUNTOS)
# ----------------------------------------


# ---------- CONEXIÓN ----------
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

        while not data_queue.empty():
            try:
                data_queue.get_nowait()
            except Empty:
                break

        threading.Thread(target=leer_datos, daemon=True).start()
        ventana.after(20,   procesar_queue)
        ventana.after(1000, actualizar_graficas)

        estado_label.config(text="Estado: Conectado", fg="green")
        btn_conectar.config(state="disabled")
        btn_desconectar.config(state="normal")

    except Exception as e:
        messagebox.showerror("Error", str(e))


def desconectar():
    global ser, leyendo, medicion_activa, ignition_countdown
    global contador_paquetes, ultimo_calculo_hz, hz_actual

    leyendo            = False
    medicion_activa    = False
    ignition_countdown = False
    contador_paquetes  = 0
    ultimo_calculo_hz  = None
    hz_actual          = 0.0

    if ser and ser.is_open:
        try:
            ser.close()
        except:
            pass
    ser = None

    estado_label.config(text="Estado: Desconectado", fg="red")
    estado_medicion.config(text="Medición: DETENIDA",  fg="red")
    hz_label.config(text="Frecuencia: 0.0 Hz")
    btn_start_stop.config(text="START")
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
        tiempos.clear()
        presiones.clear()
        ns.clear()
        temperaturas.clear()
        tiempo_base = None

        try:
            ser.write(COMANDO_DATOS)
            valor_label.config(text="¡COMANDO 0x02 ENVIADO!",
                               font=("Arial", 16, "bold"), fg="green")
        except Exception as e:
            messagebox.showerror("Error", f"Error al enviar comando: {e}")
            medicion_activa = False
            return

        estado_medicion.config(text="Medición: ACTIVA", fg="green")
        btn_start_stop.config(text="STOP")
    else:
        try:
            ser.write(COMANDO_STOP)
            valor_label.config(text="¡COMANDO 0x03 ENVIADO!",
                               font=("Arial", 16, "bold"), fg="orange")
        except Exception as e:
            messagebox.showerror("Error", f"Error al enviar comando STOP: {e}")
        estado_medicion.config(text="Medición: DETENIDA", fg="red")
        btn_start_stop.config(text="START")


# ---------- GET VALUE ----------
def get_value():
    if not ser or not ser.is_open:
        messagebox.showwarning("Aviso", "Puerto no conectado")
        return
    try:
        ser.write(bytes([0x01]))
    except Exception as e:
        messagebox.showerror("Error", str(e))


# ---------- IGNICIÓN ----------
def ignitar():
    global ignition_countdown

    if not ser or not ser.is_open:
        messagebox.showwarning("Aviso", "Puerto no conectado")
        return
    if ignition_countdown:
        return

    ignition_countdown = True
    cuenta_regresiva(10)


def cancelar_ignicion():
    global ignition_countdown
    if ignition_countdown:
        ignition_countdown = False


def cuenta_regresiva(segundos):
    global ignition_countdown, medicion_activa, tiempo_base

    if not ignition_countdown:
        valor_label.config(text="Ignición cancelada",
                           font=("Arial", 16, "bold"), fg="orange")
        return

    if segundos >= 0:
        valor_label.config(text=f"IGNICIÓN EN {segundos} s",
                           font=("Arial", 24, "bold"), fg="red")
        ventana.after(1000, lambda: cuenta_regresiva(segundos - 1))
    else:
        ignition_countdown = False
        try:
            tiempos.clear()
            presiones.clear()
            ns.clear()
            temperaturas.clear()
            tiempo_base = None

            ser.write(COMANDO_IGNICION)
            print("Comando 0x04 enviado")

            medicion_activa = True
            estado_medicion.config(text="Medición: ACTIVA", fg="green")
            btn_start_stop.config(text="STOP")
            valor_label.config(text="¡COMANDO 0x04 ENVIADO!",
                               font=("Arial", 20, "bold"), fg="green")
        except Exception as e:
            messagebox.showerror("Error", f"Error al enviar comando: {e}")


# ---------- PUERTOS ----------
def obtener_puertos():
    return [p.device for p in serial.tools.list_ports.comports()]


def refrescar_puertos():
    global puertos_actuales

    nuevos = obtener_puertos()
    if nuevos != puertos_actuales:
        puertos_actuales = nuevos
        menu = puerto_menu["menu"]
        menu.delete(0, "end")
        if puertos_actuales:
            for p in puertos_actuales:
                menu.add_command(label=p, command=lambda v=p: puerto_var.set(v))
            if puerto_var.get() not in puertos_actuales:
                puerto_var.set(puertos_actuales[0])
        else:
            menu.add_command(label="No hay puertos",
                             command=lambda: puerto_var.set("No hay puertos"))
            puerto_var.set("No hay puertos")

    ventana.after(1000, refrescar_puertos)


# ---------- LECTURA SERIAL (hilo) ----------
# Paquete de 27 bytes:
#   [0:4]   timestamp_ms  (uint32 LE)
#   [4:8]   thrust        (int32  LE) / 100.0
#   [8:24]  temps x8      (int16  LE cada uno) / 100.0   (8 * 2 = 16 bytes)
#   [24:26] transducer    (uint16 LE)
# Total payload = 26 bytes  (+ 1 byte cabecera 0x01 = 27 bytes por paquete)

def leer_datos():
    global contador_paquetes, ultimo_calculo_hz, hz_actual

    while leyendo:
        try:
            b = ser.read(1)
        except (serial.SerialException, OSError):
            data_queue.put({"tipo": "error"})
            break

        if len(b) != 1 or b != b"\x01":
            continue

        try:
            payload = ser.read(26)
        except (serial.SerialException, OSError):
            data_queue.put({"tipo": "error"})
            break

        if len(payload) != 26:
            continue

        ahora = time.time()
        if ultimo_calculo_hz is None:
            ultimo_calculo_hz = ahora
            contador_paquetes = 0
        contador_paquetes += 1
        if ahora - ultimo_calculo_hz >= 1.0:
            hz_actual = contador_paquetes / (ahora - ultimo_calculo_hz)
            contador_paquetes = 0
            ultimo_calculo_hz = ahora

        timestamp_ms   = struct.unpack("<I", payload[0:4])[0]
        thrust         = struct.unpack("<i", payload[4:8])[0] / 100.0

        # 8 termopares: bytes [8:24]
        temps          = [struct.unpack("<h", payload[8 + i*2 : 10 + i*2])[0] / 100.0
                          for i in range(8)]

        transducer_raw = struct.unpack("<H", payload[24:26])[0]

        # Commented out step-by-step calculation — replaced by precalculated constants above
        # v = (transducer_raw / 4095) * 3.3
        # i = v / 150
        # psi = (i - 0.004) * 312500
        # bar = (psi * 0.0689476) + 1.01325
        bar = transducer_raw * _BAR_K + _BAR_OFFSET

        paquete = {
            "tipo":             "datos",
            "timestamp_ms":     timestamp_ms,
            "thrust":           thrust,
            "temps":            temps,
            "transducer":       bar,
            "transducer_raw":   transducer_raw,
            "hz":               hz_actual,
            "ts":               time.time(),
        }

        try:
            data_queue.put_nowait(paquete)
        except:
            pass


# ---------- QUEUE DRAIN (main thread) ----------
_archivo = None


def procesar_queue():
    global tiempo_base, medicion_activa, _archivo

    if not leyendo:
        return

    if _archivo is None or _archivo.closed:
        _archivo = open(archivo_salida, 'w')
        # Cabecera CSV
        header = "Timestamp_ms,Tiempo_s,Thrust_N"
        for i in range(1, 9):
            header += f",Tp{i}_C"
        header += ",Pressure\n"
        _archivo.write(header)

    procesados = 0
    while procesados < 20:
        try:
            paquete = data_queue.get_nowait()
        except Empty:
            break

        if paquete["tipo"] == "error":
            ventana.after(0, desconectar)
            return

        thrust         = paquete["thrust"]
        temps          = paquete["temps"]
        transducer     = paquete["transducer"]
        transducer_raw = paquete["transducer_raw"]
        timestamp_ms   = paquete["timestamp_ms"]
        hz             = paquete["hz"]

        for i in range(8):
            tabla_valores[i].set(f"Tp{i+1}: {temps[i]:.2f}°C")
        ps_var.set(f"Thrust: {thrust:.2f} N")
        n_var.set(f"Pressure: {transducer:.4f} bar")
        raw_var.set(f"Raw ADC: {transducer_raw}")
        timestamp_var.set(f"Timestamp: {timestamp_ms} ms")
        if hz > 0:
            hz_label.config(text=f"Frecuencia: {hz:.1f} Hz")

        if medicion_activa:
            if tiempo_base is None:
                tiempo_base = paquete["ts"]
            tiempo_s    = paquete["ts"] - tiempo_base
            tp_promedio = sum(temps) / 8.0

            if not ignition_countdown:
                valor_label.config(
                    text=f"Thrust: {thrust:.2f} N | T: {tp_promedio:.1f}°C | t: {tiempo_s:.2f}s",
                    font=("Arial", 12), fg="white"
                )

            # Línea CSV
            linea = f"{timestamp_ms},{tiempo_s:.3f},{thrust:.3f}"
            for temp in temps:
                linea += f",{temp:.3f}"
            linea += f",{transducer:.6f}\n"
            _archivo.write(linea)
            _archivo.flush()

            tiempos.append(tiempo_s)
            presiones.append(thrust)
            ns.append(transducer)
            temperaturas.append(tp_promedio)

        procesados += 1

    ventana.after(20, procesar_queue)


# ---------- GRÁFICAS ----------
def actualizar_graficas():
    if not leyendo:
        return

    if len(tiempos) >= 2:
        t = list(tiempos)
        ax_presion.clear()
        ax_n.clear()
        ax_temperatura.clear()

        ax_presion.plot(t, list(presiones), color="#C88A53", label="Thrust")
        ax_presion.set_ylabel("Thrust [N]")
        ax_presion.grid(True)
        ax_presion.legend()

        ax_n.plot(t, list(ns), color="#C88A53", label="Pressure")
        ax_n.set_ylabel("Pressure [bar]")
        ax_n.grid(True)
        ax_n.legend()

        ax_temperatura.plot(t, list(temperaturas), color="#C88A53", label="Temperatura")
        ax_temperatura.set_ylabel("Temp [°C]")
        ax_temperatura.set_xlabel("Tiempo [s]")
        ax_temperatura.grid(True)
        ax_temperatura.legend()

        canvas.draw()

    ventana.after(1000, actualizar_graficas)


def cerrar():
    global _archivo
    desconectar()
    if _archivo and not _archivo.closed:
        _archivo.close()
    ventana.destroy()
    sys.exit()


# ---------------- INTERFAZ ----------------
ventana = tk.Tk()
ventana.title("Interfaz LEEM")
ventana.geometry("900x600")
ventana.configure(bg="#15141B")

style = ttk.Style()
try:
    style.theme_use("clam")
except tk.TclError:
    pass

style.configure("Main.TButton",   foreground="white", background="#C88A53", padding=10)
style.map("Main.TButton",         background=[("active", "#D89A63")])
style.configure("Cancel.TButton", foreground="white", background="#8B2020", padding=10)
style.map("Cancel.TButton",       background=[("active", "#A83030")])
style.configure("Side.TFrame",    background="#2C2A36")
style.configure("Right.TFrame",   background="#15141B")

frame_config = ttk.Frame(ventana, width=240, style="Side.TFrame")
frame_config.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)
frame_config.pack_propagate(False)

frame_right = ttk.Frame(ventana, style="Right.TFrame")
frame_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

frame_graficas = ttk.Frame(frame_right, style="Right.TFrame")
frame_graficas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

frame_tabla = ttk.Frame(frame_right, style="Side.TFrame")
frame_tabla.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

# Controls
tk.Label(frame_config, text="Puerto COM",        bg="#2C2A36", fg="white").pack(anchor="w", pady=2)
puerto_var       = tk.StringVar()
puertos_actuales = obtener_puertos()
puerto_var.set(puertos_actuales[0] if puertos_actuales else "No hay puertos")
puerto_menu = tk.OptionMenu(frame_config, puerto_var,
                            *(puertos_actuales if puertos_actuales else ["No hay puertos"]))
puerto_menu.pack(fill="x")

tk.Label(frame_config, text="Baudrate",          bg="#2C2A36", fg="white").pack(anchor="w", pady=2)
baudrate_var = tk.StringVar(value="115200")
tk.Entry(frame_config, textvariable=baudrate_var, bg="#3C3A46", fg="white",
         insertbackground="white").pack(fill="x", ipady=2)

tk.Label(frame_config, text="Archivo de salida", bg="#2C2A36", fg="white").pack(anchor="w", pady=2)
archivo_var = tk.StringVar(value="datos.txt")
tk.Entry(frame_config, textvariable=archivo_var, bg="#3C3A46", fg="white",
         insertbackground="white").pack(fill="x", ipady=2)

estado_label    = tk.Label(frame_config, text="Estado: Desconectado", fg="red",   bg="#2C2A36")
estado_label.pack(pady=5)
estado_medicion = tk.Label(frame_config, text="Medición: DETENIDA",   fg="red",   bg="#2C2A36")
estado_medicion.pack(pady=5)
hz_label        = tk.Label(frame_config, text="Frecuencia: 0.0 Hz",   fg="white", bg="#2C2A36")
hz_label.pack(pady=5)
valor_label     = tk.Label(frame_config, text="Valor: ---",            fg="white", bg="#2C2A36")
valor_label.pack(pady=10)

btn_conectar    = ttk.Button(frame_config, text="Conectar",            width=15, command=conectar,           style="Main.TButton")
btn_conectar.pack(pady=3)
btn_desconectar = ttk.Button(frame_config, text="Desconectar",         width=15, command=desconectar,        style="Main.TButton")
btn_desconectar.pack(pady=3)
btn_desconectar.config(state="disabled")
btn_start_stop  = ttk.Button(frame_config, text="START",               width=18, command=toggle_medicion,    style="Main.TButton")
btn_start_stop.pack(pady=8)
btn_get_value   = ttk.Button(frame_config, text="GET VALUE",           width=18, command=get_value,          style="Main.TButton")
btn_get_value.pack(pady=6)
btn_ignitar     = ttk.Button(frame_config, text="IGNITAR",             width=18, command=ignitar,            style="Main.TButton")
btn_ignitar.pack(pady=8)
btn_cancel_ign  = ttk.Button(frame_config, text="CANCELAR IGNICIÓN",   width=18, command=cancelar_ignicion,  style="Cancel.TButton")
btn_cancel_ign.pack(pady=4)

# Plots
fig, (ax_presion, ax_n, ax_temperatura) = plt.subplots(3, 1, figsize=(6, 8))
fig.patch.set_facecolor("#5F5A7A")
canvas = FigureCanvasTkAgg(fig, master=frame_graficas)
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

# Sensor table — 8 termopares: 4 en col 0, 4 en col 1
tabla_valores = []
for i in range(8):
    var  = tk.StringVar(value=f"Tp{i+1}: 0.00")
    fila = i % 4
    col  = i // 4
    tk.Label(frame_tabla, textvariable=var, width=16, anchor="w",
             font=("Arial", 12, "bold"), bg="#5F5A7A", fg="white"
             ).grid(row=fila, column=col, padx=4, pady=4, sticky="w")
    tabla_valores.append(var)

ps_var = tk.StringVar(value="Thrust: 0.00 N")
tk.Label(frame_tabla, textvariable=ps_var, width=16, anchor="w",
         font=("Arial", 12, "bold"), bg="#5F5A7A", fg="white"
         ).grid(row=4, column=0, padx=4, pady=6, sticky="w")

n_var = tk.StringVar(value="Pressure: 0.0000 bar")
tk.Label(frame_tabla, textvariable=n_var, width=22, anchor="w",
         font=("Arial", 12, "bold"), bg="#5F5A7A", fg="white"
         ).grid(row=4, column=1, padx=4, pady=6, sticky="w")

# Raw ADC reading from the transducer
raw_var = tk.StringVar(value="Raw Transducer: 0")
tk.Label(frame_tabla, textvariable=raw_var, width=16, anchor="w",
         font=("Arial", 12, "bold"), bg="#5F5A7A", fg="white"
         ).grid(row=5, column=0, padx=4, pady=6, sticky="w")

timestamp_var = tk.StringVar(value="Timestamp: 0 ms")
tk.Label(frame_tabla, textvariable=timestamp_var, width=34, anchor="w",
         font=("Arial", 10, "bold"), bg="#5F5A7A", fg="white"
         ).grid(row=6, column=0, columnspan=2, padx=4, pady=6, sticky="w")

ventana.protocol("WM_DELETE_WINDOW", cerrar)
ventana.after(1000, refrescar_puertos)
ventana.mainloop()