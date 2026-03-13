import serial
import serial.tools.list_ports
import time
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from queue import Queue, Empty
import struct
import sys
import csv
import os
from collections import deque

# ---------- CONFIGURACIÓN ----------
TIMEOUT        = 1
SYNC1          = 0xFE
SYNC2          = 0xFB
PACKET_SIZE    = 28
MAX_ROWS       = 200
DEDUP_WINDOW   = 3      # si el timestamp_ms es igual N veces seguidas, descarta
CSV_FILE       = "packets.csv"
# -----------------------------------

ser           = None
leyendo       = False
data_queue    = Queue(maxsize=1000)
paquete_count = 0
last_ts_ms    = None   # para deduplicación
dup_count     = 0      # contador de duplicados descartados
selected_payload = None  # payload de la fila seleccionada

FIELDS = [
    ("timestamp_ms", "I"),
    ("tempTP[0]",    "h"),
    ("tempTP[1]",    "h"),
    ("tempTP[2]",    "h"),
    ("tempTP[3]",    "h"),
    ("thrust",       "h"),
    ("pressure",     "h"),
    ("flags",        "H"),
    ("adc1",         "H"),
    ("adc2",         "H"),
    ("adc3",         "H"),
    ("adc4",         "H"),
]
STRUCT_FMT  = "<" + "".join(t for _, t in FIELDS)
FIELD_NAMES = [n for n, _ in FIELDS]


def make_button(parent, text, command, bg="#C88A53", fg="white",
                font=("Arial", 10, "bold"), state="normal"):
    frame = tk.Frame(parent, bg=bg, cursor="hand2")
    label = tk.Label(frame, text=text, bg=bg, fg=fg, font=font,
                     anchor="center", pady=6)
    label.pack(fill="both")

    def _on_click(e):
        if frame._enabled:
            command()

    def _on_enter(e):
        if frame._enabled:
            r, g, b_ = ventana.winfo_rgb(bg)
            lighter = "#{:02x}{:02x}{:02x}".format(
                min(255, (r >> 8) + 25),
                min(255, (g >> 8) + 25),
                min(255, (b_ >> 8) + 25))
            frame.config(bg=lighter)
            label.config(bg=lighter)

    def _on_leave(e):
        c = bg if frame._enabled else "#555555"
        frame.config(bg=c); label.config(bg=c)

    def _set_state(s):
        frame._enabled = (s == "normal")
        c   = bg    if frame._enabled else "#555555"
        fg_ = fg    if frame._enabled else "#888888"
        cur = "hand2" if frame._enabled else "arrow"
        frame.config(bg=c, cursor=cur)
        label.config(bg=c, fg=fg_, cursor=cur)

    frame._enabled = True
    frame.config   = lambda **kw: (_set_state(kw["state"]) if "state" in kw else None)

    for widget in (frame, label):
        widget.bind("<Button-1>", _on_click)
        widget.bind("<Enter>",    _on_enter)
        widget.bind("<Leave>",    _on_leave)

    _set_state(state)
    return frame


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


def conectar():
    global ser, leyendo, paquete_count, last_ts_ms, dup_count

    puerto = puerto_var.get()
    if puerto == "No hay puertos":
        return

    try:
        ser = serial.Serial(puerto, int(baudrate_var.get()), timeout=TIMEOUT)
        time.sleep(1)

        leyendo      = True
        paquete_count = 0
        last_ts_ms   = None
        dup_count    = 0

        while not data_queue.empty():
            try: data_queue.get_nowait()
            except Empty: break

        for row in tree.get_children():
            tree.delete(row)

        threading.Thread(target=leer_datos, daemon=True).start()
        ventana.after(50, procesar_queue)

        estado_label.config(text="Conectado", fg="#00FF88")
        btn_conectar.config(state="disabled")
        btn_desconectar.config(state="normal")
        btn_clear.config(state="normal")
        btn_export.config(state="normal")

    except Exception as e:
        estado_label.config(text=f"Error: {e}", fg="red")


def desconectar():
    global ser, leyendo

    leyendo = False
    if ser and ser.is_open:
        try: ser.close()
        except: pass
    ser = None

    estado_label.config(text="Desconectado", fg="red")
    count_label.config(text="Paquetes: 0")
    dup_label.config(text="Dups: 0")
    btn_conectar.config(state="normal")
    btn_desconectar.config(state="disabled")
    btn_clear.config(state="disabled")


def leer_datos():
    global leyendo

    while leyendo:
        try:
            b = ser.read(1)
        except (serial.SerialException, OSError):
            data_queue.put({"tipo": "error"}); break

        if len(b) != 1 or b[0] != SYNC1:
            continue

        try:
            b2 = ser.read(1)
        except (serial.SerialException, OSError):
            data_queue.put({"tipo": "error"}); break

        if len(b2) != 1 or b2[0] != SYNC2:
            continue

        try:
            payload = ser.read(PACKET_SIZE)
        except (serial.SerialException, OSError):
            data_queue.put({"tipo": "error"}); break

        if len(payload) != PACKET_SIZE:
            continue

        ts = time.time()
        try:
            data_queue.put_nowait({"tipo": "datos", "payload": payload, "ts": ts})
        except:
            pass


def payload_to_hex(payload: bytes) -> str:
    return " ".join(f"{b:02X}" for b in payload)


def payload_to_nums(payload: bytes) -> list:
    try:
        values = struct.unpack(STRUCT_FMT, payload)
        result = []
        for i, (name, _) in enumerate(FIELDS):
            v = values[i]
            if name in ("thrust", "pressure") or name.startswith("tempTP"):
                result.append(f"{v / 100.0:.2f}")
            else:
                result.append(str(v))
        return result
    except struct.error:
        return ["ERR"] * len(FIELDS)


def is_duplicate(payload: bytes) -> bool:
    """Descarta paquete si el timestamp_ms es idéntico al anterior."""
    global last_ts_ms, dup_count
    ts_ms = struct.unpack_from("<I", payload, 0)[0]
    if ts_ms == last_ts_ms:
        dup_count += 1
        dup_label.config(text=f"Dups: {dup_count}")
        return True
    last_ts_ms = ts_ms
    return False


def procesar_queue():
    global paquete_count

    if not leyendo:
        return

    modo = view_mode.get()
    procesados = 0

    while procesados < 30:
        try:
            paquete = data_queue.get_nowait()
        except Empty:
            break

        if paquete["tipo"] == "error":
            ventana.after(0, desconectar)
            return

        payload = paquete["payload"]
        ts      = paquete["ts"]

        # --- Filtro de duplicados ---
        if dedup_var.get() and is_duplicate(payload):
            continue

        paquete_count += 1
        ts_str = time.strftime("%H:%M:%S", time.localtime(ts)) + \
                 f".{int((ts % 1) * 1000):03d}"

        if modo == "hex":
            cols = (paquete_count, ts_str, payload_to_hex(payload))
        else:
            nums = payload_to_nums(payload)
            cols = (paquete_count, ts_str, *nums)

        tag = "odd" if paquete_count % 2 else "even"
        tree.insert("", 0, values=cols, tags=(tag,))

        children = tree.get_children()
        if len(children) > MAX_ROWS:
            tree.delete(children[-1])

        count_label.config(text=f"Paquetes: {paquete_count}")
        procesados += 1

    ventana.after(50, procesar_queue)


# ---- Copiar / Exportar ----

def copiar_seleccion():
    """Copia las filas seleccionadas al portapapeles."""
    items = tree.selection()
    if not items:
        messagebox.showinfo("Info", "Selecciona al menos una fila.")
        return

    lines = []
    modo = view_mode.get()
    if modo == "hex":
        header = "#\tTimestamp\tPayload (hex)"
    else:
        header = "\t".join(["#", "Timestamp"] + FIELD_NAMES)
    lines.append(header)

    for item in items:
        vals = tree.item(item, "values")
        lines.append("\t".join(str(v) for v in vals))

    text = "\n".join(lines)
    ventana.clipboard_clear()
    ventana.clipboard_append(text)
    ventana.update()
    messagebox.showinfo("Copiado", f"{len(items)} fila(s) copiadas al portapapeles.")


def copiar_todo():
    """Copia TODAS las filas visibles (en orden cronológico) al portapapeles."""
    children = tree.get_children()
    if not children:
        messagebox.showinfo("Info", "No hay datos en la tabla.")
        return

    lines = []
    modo = view_mode.get()
    if modo == "hex":
        header = "#\tTimestamp\tPayload (hex)"
    else:
        header = "\t".join(["#", "Timestamp"] + FIELD_NAMES)
    lines.append(header)

    for item in reversed(children):   # reversed = cronológico (más viejo primero)
        vals = tree.item(item, "values")
        lines.append("\t".join(str(v) for v in vals))

    text = "\n".join(lines)
    ventana.clipboard_clear()
    ventana.clipboard_append(text)
    ventana.update()
    messagebox.showinfo("Copiado", f"{len(children)} filas copiadas al portapapeles.\nPega directamente en Excel/Sheets.")


def exportar_csv():
    """Exporta todas las filas visibles a CSV."""
    children = tree.get_children()
    if not children:
        messagebox.showinfo("Info", "No hay datos para exportar.")
        return

    modo = view_mode.get()
    if modo == "hex":
        header = ["#", "Timestamp", "Payload (hex)"]
    else:
        header = ["#", "Timestamp"] + FIELD_NAMES

    with open(CSV_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for item in reversed(children):
            writer.writerow(tree.item(item, "values"))

    messagebox.showinfo("Exportado",
                        f"Guardado en:\n{os.path.abspath(CSV_FILE)}\n({len(children)} filas)")


def on_row_select(event):
    """Al seleccionar una fila en modo hex, muestra el detalle parseado abajo."""
    items = tree.selection()
    if not items or view_mode.get() != "hex":
        detail_text.config(state="normal")
        detail_text.delete("1.0", tk.END)
        detail_text.config(state="disabled")
        return

    vals = tree.item(items[0], "values")
    if len(vals) < 3:
        return

    # Reconstruir payload desde hex string
    try:
        raw = bytes(int(h, 16) for h in vals[2].split())
        nums = payload_to_nums(raw)
        lines = [f"  {name:<15} = {val}" for name, val in zip(FIELD_NAMES, nums)]
        detail_str = f"Paquete #{vals[0]}  @  {vals[1]}\n" + "\n".join(lines)
    except Exception as e:
        detail_str = f"Error parseando: {e}"

    detail_text.config(state="normal")
    detail_text.delete("1.0", tk.END)
    detail_text.insert(tk.END, detail_str)
    detail_text.config(state="disabled")


def cambiar_modo():
    modo = view_mode.get()
    for col in tree["columns"]:
        tree.heading(col, text="")
    tree.delete(*tree.get_children())

    if modo == "hex":
        cols = ("#", "Timestamp", "Payload (hex)")
        tree["columns"] = cols
        tree.column("#",             width=50,  anchor="e",  stretch=False)
        tree.column("Timestamp",     width=110, anchor="w",  stretch=False)
        tree.column("Payload (hex)", width=600, anchor="w",  stretch=True)
        for c in cols:
            tree.heading(c, text=c)
        detail_frame.pack(fill=tk.X, pady=(4, 0))
    else:
        cols = ("#", "Timestamp", *FIELD_NAMES)
        tree["columns"] = cols
        tree.column("#",         width=50,  anchor="e",  stretch=False)
        tree.column("Timestamp", width=110, anchor="w",  stretch=False)
        for name in FIELD_NAMES:
            tree.column(name, width=90, anchor="e", stretch=True)
        for c in cols:
            tree.heading(c, text=c)
        detail_frame.pack_forget()


def limpiar_tabla():
    global paquete_count, last_ts_ms, dup_count
    for row in tree.get_children():
        tree.delete(row)
    paquete_count = 0
    last_ts_ms    = None
    dup_count     = 0
    count_label.config(text="Paquetes: 0")
    dup_label.config(text="Dups: 0")
    detail_text.config(state="normal")
    detail_text.delete("1.0", tk.END)
    detail_text.config(state="disabled")


def cerrar():
    desconectar()
    ventana.destroy()
    sys.exit()


# ================== INTERFAZ ==================
ventana = tk.Tk()
ventana.title("Serial Packet Inspector")
ventana.geometry("1150x640")
ventana.configure(bg="#15141B")

# ---- Panel izquierdo ----
frame_left = tk.Frame(ventana, bg="#2C2A36", width=185)
frame_left.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)
frame_left.pack_propagate(False)

tk.Label(frame_left, text="Puerto COM", bg="#2C2A36", fg="white").pack(anchor="w", pady=(10, 2))
puerto_var       = tk.StringVar()
puertos_actuales = obtener_puertos()
puerto_var.set(puertos_actuales[0] if puertos_actuales else "No hay puertos")
puerto_menu = tk.OptionMenu(frame_left, puerto_var,
                            *(puertos_actuales if puertos_actuales else ["No hay puertos"]))
puerto_menu.pack(fill="x", padx=5)

tk.Label(frame_left, text="Baudrate", bg="#2C2A36", fg="white").pack(anchor="w", pady=(10, 2))
baudrate_var = tk.StringVar(value="115200")
tk.Entry(frame_left, textvariable=baudrate_var, bg="#3C3A46", fg="white",
         insertbackground="white").pack(fill="x", padx=5)

tk.Frame(frame_left, height=2, bg="#555555").pack(fill="x", pady=10)

estado_label = tk.Label(frame_left, text="Desconectado", fg="red",
                        bg="#2C2A36", font=("Arial", 10, "bold"))
estado_label.pack(pady=5)

count_label = tk.Label(frame_left, text="Paquetes: 0", fg="#C88A53",
                       bg="#2C2A36", font=("Arial", 13, "bold"))
count_label.pack(pady=(4, 0))

dup_label = tk.Label(frame_left, text="Dups: 0", fg="#888888",
                     bg="#2C2A36", font=("Arial", 10))
dup_label.pack(pady=(0, 4))

tk.Frame(frame_left, height=2, bg="#555555").pack(fill="x", pady=6)

# Modo visualización
tk.Label(frame_left, text="Modo de visualización", bg="#2C2A36",
         fg="#AAAAAA", font=("Arial", 9)).pack(anchor="w", padx=5, pady=(4, 2))

view_mode   = tk.StringVar(value="hex")
mode_frame  = tk.Frame(frame_left, bg="#2C2A36")
mode_frame.pack(fill="x", padx=5, pady=4)

tk.Radiobutton(mode_frame, text="HEX",      variable=view_mode, value="hex",
               command=cambiar_modo,
               bg="#2C2A36", fg="white", selectcolor="#3C3A46",
               activebackground="#2C2A36", activeforeground="white").pack(side=tk.LEFT)
tk.Radiobutton(mode_frame, text="Numérico", variable=view_mode, value="num",
               command=cambiar_modo,
               bg="#2C2A36", fg="white", selectcolor="#3C3A46",
               activebackground="#2C2A36", activeforeground="white").pack(side=tk.LEFT)

# Filtro duplicados
dedup_var = tk.BooleanVar(value=True)
tk.Checkbutton(frame_left, text="Filtrar duplicados", variable=dedup_var,
               bg="#2C2A36", fg="#AAAAAA", selectcolor="#3C3A46",
               activebackground="#2C2A36", activeforeground="white",
               font=("Arial", 9)).pack(anchor="w", padx=5, pady=(6, 2))

tk.Frame(frame_left, height=2, bg="#555555").pack(fill="x", pady=6)

btn_conectar = make_button(frame_left, "Conectar", conectar,
                           bg="#C88A53", fg="white")
btn_conectar.pack(pady=3, fill="x", padx=5)

btn_desconectar = make_button(frame_left, "Desconectar", desconectar,
                              bg="#C88A53", fg="white", state="disabled")
btn_desconectar.pack(pady=3, fill="x", padx=5)

tk.Frame(frame_left, height=2, bg="#555555").pack(fill="x", pady=6)

btn_copy_sel = make_button(frame_left, "📋 Copiar selección", copiar_seleccion,
                           bg="#4A90D9", fg="white")
btn_copy_sel.pack(pady=3, fill="x", padx=5)

btn_copy_all = make_button(frame_left, "📋 Copiar todo", copiar_todo,
                           bg="#4A90D9", fg="white")
btn_copy_all.pack(pady=3, fill="x", padx=5)

btn_export = make_button(frame_left, "💾 Exportar CSV", exportar_csv,
                         bg="#4A90D9", fg="white", state="disabled")
btn_export.pack(pady=3, fill="x", padx=5)

btn_clear = make_button(frame_left, "🗑 Limpiar", limpiar_tabla,
                        bg="#555555", fg="white", state="disabled")
btn_clear.pack(pady=3, fill="x", padx=5)

# ---- Panel derecho ----
frame_right = tk.Frame(ventana, bg="#15141B")
frame_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

# Tabla
style = ttk.Style()
style.theme_use("clam")
style.configure("Packet.Treeview",
                background="#1E1D26", foreground="#E0E0E0",
                fieldbackground="#1E1D26", rowheight=22,
                font=("Courier New", 10))
style.configure("Packet.Treeview.Heading",
                background="#2C2A36", foreground="#C88A53",
                font=("Arial", 10, "bold"), relief="flat")
style.map("Packet.Treeview",
          background=[("selected", "#3C3A56")],
          foreground=[("selected", "white")])

sb_y = ttk.Scrollbar(frame_right, orient="vertical")
sb_x = ttk.Scrollbar(frame_right, orient="horizontal")

tree = ttk.Treeview(frame_right, show="headings", style="Packet.Treeview",
                    yscrollcommand=sb_y.set, xscrollcommand=sb_x.set,
                    selectmode="extended")   # permite selección múltiple con Shift/Ctrl

sb_y.config(command=tree.yview)
sb_x.config(command=tree.xview)

sb_y.pack(side=tk.RIGHT,  fill=tk.Y)
sb_x.pack(side=tk.BOTTOM, fill=tk.X)
tree.pack(fill=tk.BOTH, expand=True)

tree.tag_configure("odd",  background="#1E1D26")
tree.tag_configure("even", background="#252430")
tree.bind("<<TreeviewSelect>>", on_row_select)

# Panel de detalle (sólo en modo hex)
detail_frame = tk.Frame(frame_right, bg="#2C2A36")
tk.Label(detail_frame, text="Detalle del paquete seleccionado",
         bg="#2C2A36", fg="#C88A53", font=("Arial", 9, "bold")).pack(anchor="w", padx=6)
detail_text = tk.Text(detail_frame, height=7, bg="#1A1924", fg="#00FF88",
                      font=("Courier New", 10), state="disabled",
                      insertbackground="white", relief="flat")
detail_text.pack(fill=tk.X, padx=4, pady=4)

cambiar_modo()

ventana.protocol("WM_DELETE_WINDOW", cerrar)
ventana.after(1000, refrescar_puertos)
ventana.mainloop()
