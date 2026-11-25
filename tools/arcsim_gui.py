#!/usr/bin/env python3
"""
ArcSim_VR - Centro de Control y Configuración de la Herramienta SMAW
====================================================================
Interfaz gráfica integral para:
  1. Configuración de colores LED RGB y porcentaje de vibración según estado (Reposo, Homing, Soldadura, Advertencia, Pegado).
  2. Ajuste de límites del sensor láser ToF (distancia de corte, pegado, rango óptimo).
  3. Ajuste de tolerancias SMAW aplicables en el simulador de Godot.
  4. Lanzador unificado de calibración de mesa, puente de sensores y apertura de Godot.
  5. Banco de pruebas en vivo para probar LEDs y vibración háptica con la herramienta conectada.
"""

import sys
import os
import json
import subprocess
import threading
import time
import socket
from pathlib import Path

import tkinter as tk
from tkinter import ttk, colorchooser, messagebox, filedialog

try:
    import serial
    from serial.tools import list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

# Rutas del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = BASE_DIR / "tools"
GODOT_DIR = BASE_DIR / "simulacion_godot" / "trabajo-final-rv"
CONFIG_FILE_TOOLS = TOOLS_DIR / "tool_config.json"
CONFIG_FILE_GODOT = GODOT_DIR / "tool_config.json"
CALIB_FILE = TOOLS_DIR / "mesa_calibration.json"
PROJECT_GODOT = GODOT_DIR / "project.godot"

DEFAULT_CONFIG = {
    "led_colors": {
        "idle": [255, 40, 0],         # Naranja cálido
        "homing": [0, 50, 255],        # Azul eléctrico
        "weld_optimal": [0, 255, 0],   # Verde puro
        "weld_caution": [255, 170, 0], # Amarillo: algún parámetro en zona tolerable
        "weld_warning": [255, 0, 0],   # Rojo advertencia
        "sticking": [255, 0, 0]        # Rojo intenso pegado
    },
    "haptic_intensity_pct": {
        "homing": 78,                  # Pulso de contacto
        "weld_optimal": 28,            # Zumbido suave de plasma
        "weld_warning": 50,            # Pulsos de aviso
        "sticking": 100                # Máxima vibración
    },
    "tof_limits_mm": {
        "extinguish_gap": 12.0,        # Corte de arco superior
        "stick_gap": 0.4,              # Umbral de electrodo pegado
        "reignite_gap": 4.5,           # Reencendido automático por proximidad
        "optimal_min": 1.0,            # Mínimo óptimo
        "optimal_max": 6.0             # Máximo óptimo
    },
    "simulation_tolerances": {
        "roll_max_deg": 25.0,          # Desvío transversal máx
        "pitch_min_deg": -5.0,         # Ángulo de avance mín
        "pitch_max_deg": 35.0,         # Ángulo de avance máx
        "speed_min_mm_s": 1.8,         # Velocidad mínima óptima
        "speed_max_mm_s": 4.5          # Velocidad máxima óptima
    },
    "tool_tip_lever_mm": 115.0,        # Brazo cinemático punta a marcador ArUco
    "homing_required": False,          # True: el arco arranca con el pulsador (homing)
    "godot_executable": ""
}

# Paleta de colores Dark High-Tech
C_BG = "#16181d"
C_PANEL = "#21242c"
C_CARD = "#282c35"
C_BORDER = "#353b47"
C_TXT = "#e0e3eb"
C_MUTED = "#8a91a0"
C_CYAN = "#00d2ff"
C_GREEN = "#2ecc71"
C_ORANGE = "#f39c12"
C_RED = "#e74c3c"
C_BLUE = "#3498db"


class ArcSimControlCenter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ArcSim VR — Centro de Control y Configuración SMAW")
        self.geometry("960x780")
        self.minsize(880, 680)
        self.configure(bg=C_BG)

        self.config_data = self.load_config()
        self.color_swatches = {}
        self.slider_vars = {}
        self.label_badges = {}

        self.serial_conn = None
        self.serial_conn_port = None
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._setup_styles()
        self._build_header()
        self._build_notebook()
        self._build_bottom_bar()

        self.update_status_badges()

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("TNotebook", background=C_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=C_PANEL, foreground=C_TXT, padding=[16, 8], font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", C_CARD)], foreground=[("selected", C_CYAN)])

        style.configure("Card.TFrame", background=C_CARD, relief="flat")
        style.configure("Panel.TFrame", background=C_PANEL, relief="flat")

        style.configure("Action.TButton", font=("Segoe UI", 10, "bold"), padding=[12, 6], background=C_BLUE, foreground="#ffffff")
        style.map("Action.TButton", background=[("active", "#2980b9")])

        style.configure("Green.TButton", font=("Segoe UI", 10, "bold"), padding=[12, 6], background=C_GREEN, foreground="#ffffff")
        style.map("Green.TButton", background=[("active", "#27ae60")])

        style.configure("Orange.TButton", font=("Segoe UI", 10, "bold"), padding=[12, 6], background=C_ORANGE, foreground="#ffffff")
        style.map("Orange.TButton", background=[("active", "#d68910")])

        style.configure("TScale", background=C_CARD, troughcolor=C_BORDER)

    def load_config(self):
        if CONFIG_FILE_TOOLS.exists():
            try:
                with open(CONFIG_FILE_TOOLS, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Fusionar con valores por defecto por si faltan claves
                    merged = dict(DEFAULT_CONFIG)
                    for k, v in data.items():
                        if isinstance(v, dict) and k in merged:
                            merged[k] = {**merged[k], **v}
                        else:
                            merged[k] = v
                    return merged
            except Exception as e:
                print(f"Error cargando tool_config.json: {e}")
        return json.loads(json.dumps(DEFAULT_CONFIG))

    def save_config(self, show_msg=True):
        # Recolectar valores de la UI
        # 1. Colores ya están en self.config_data["led_colors"]
        # 2. Sliders
        for key, var in self.slider_vars.items():
            category, param = key.split("/")
            if category == "haptic":
                self.config_data["haptic_intensity_pct"][param] = int(var.get())
            elif category == "tof":
                self.config_data["tof_limits_mm"][param] = round(float(var.get()), 1)
            elif category == "sim":
                self.config_data["simulation_tolerances"][param] = round(float(var.get()), 1)
            elif category == "tool":
                self.config_data["tool_tip_lever_mm"] = round(float(var.get()), 1)

        # Guardar en tools/ y en simulacion_godot/
        try:
            CONFIG_FILE_TOOLS.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE_TOOLS, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=2)

            CONFIG_FILE_GODOT.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE_GODOT, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=2)

            # Intentar notificar al puente si está corriendo por UDP (puerto 4243)
            self._broadcast_config_udp()

            # Enviar directamente por serie al ESP32 si el puerto está disponible
            active_port = self._get_active_port()
            if active_port:
                cfg_cmd = json.dumps({"cmd": "CONFIG", "config": self.config_data})
                self._send_serial_quick(active_port, cfg_cmd)

            if show_msg:
                self.lbl_save_status.config(
                    text=f"✓ Guardado con éxito ({time.strftime('%H:%M:%S')}) en tools/ y Godot",
                    fg=C_GREEN
                )
                messagebox.showinfo("Guardado Exitoso",
                    "¡Configuración de la herramienta guardada!\n\n"
                    "• Los nuevos límites y colores fueron sincronizados para Godot.\n"
                    "• El puente serial transmitirá los datos a la herramienta."
                )
        except Exception as e:
            messagebox.showerror("Error al Guardar", f"No se pudo guardar la configuración: {e}")

    def _broadcast_config_udp(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            msg = json.dumps({"cmd": "CONFIG", "config": self.config_data})
            sock.sendto(msg.encode("utf-8"), ("127.0.0.1", 4243))
            sock.close()
        except Exception:
            pass

    def reset_defaults(self):
        if messagebox.askyesno("Restablecer", "¿Deseas restablecer todos los parámetros a los valores óptimos estándar?"):
            self.config_data = json.loads(json.dumps(DEFAULT_CONFIG))
            self._update_all_widgets_from_data()
            self.save_config(show_msg=False)
            self.lbl_save_status.config(text="✓ Valores por defecto restablecidos", fg=C_ORANGE)

    def _build_header(self):
        header = tk.Frame(self, bg=C_PANEL, height=80, relief="flat", bd=0)
        header.pack(fill="x", side="top", padx=0, pady=0)

        title_box = tk.Frame(header, bg=C_PANEL)
        title_box.pack(side="left", padx=20, pady=12)

        lbl_title = tk.Label(title_box, text="⚡ ArcSim_VR — Centro de Control SMAW", font=("Segoe UI", 15, "bold"), fg=C_CYAN, bg=C_PANEL)
        lbl_title.pack(anchor="w")

        lbl_sub = tk.Label(title_box, text="Configuración en Tiempo Real de Estados Hápticos, Sensor Láser ToF y Lanzador", font=("Segoe UI", 9), fg=C_MUTED, bg=C_PANEL)
        lbl_sub.pack(anchor="w")

        # Badges de estado en la esquina superior derecha
        self.badge_box = tk.Frame(header, bg=C_PANEL)
        self.badge_box.pack(side="right", padx=20, pady=12)

        self.lbl_badge_mesa = tk.Label(self.badge_box, text="Mesa: Comprobando...", font=("Segoe UI", 9, "bold"), bg=C_CARD, fg=C_MUTED, padx=10, pady=4)
        self.lbl_badge_mesa.pack(side="right", padx=5)

        self.lbl_badge_serial = tk.Label(self.badge_box, text="ESP32: Buscando...", font=("Segoe UI", 9, "bold"), bg=C_CARD, fg=C_MUTED, padx=10, pady=4)
        self.lbl_badge_serial.pack(side="right", padx=5)

    def update_status_badges(self):
        # 1. Comprobar Mesa
        if CALIB_FILE.exists():
            try:
                with open(CALIB_FILE, "r") as f:
                    cal = json.load(f)
                    meas = cal.get("measured_len_mm", 90.0)
                    tgt = cal.get("target_len_mm", 150.0)
                    scale = cal.get("scale_factor", tgt/meas if meas > 0 else 1.0)
                    self.lbl_badge_mesa.config(text=f"Mesa: Calibrada ({meas:.0f}mm → {tgt:.0f}mm | x{scale:.2f})", fg=C_GREEN, bg="#1b3a2b")
            except Exception:
                self.lbl_badge_mesa.config(text="Mesa: Calibrada", fg=C_GREEN, bg="#1b3a2b")
        else:
            self.lbl_badge_mesa.config(text="Mesa: NO Calibrada", fg=C_ORANGE, bg="#3d2a10")

        # 2. Comprobar ESP32 en COM
        if HAS_SERIAL:
            ports = [p.device for p in list_ports.comports() if p.vid in {0x10C4, 0x1A86, 0x0403, 0x303A}]
            if ports:
                self.lbl_badge_serial.config(text=f"ESP32: {ports[0]} Listo", fg=C_CYAN, bg="#102e3d")
            else:
                self.lbl_badge_serial.config(text="ESP32: No detectado", fg=C_MUTED, bg=C_CARD)
        else:
            self.lbl_badge_serial.config(text="PySerial no disponible", fg=C_MUTED, bg=C_CARD)

        # Re-chequear periódicamente cada 4 segundos
        self.after(4000, self.update_status_badges)

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=12)

        # Pestaña 1: Estados y Actuadores
        self.tab_states = self._create_scrollable_tab(self.notebook, "  🎨 Estados y Actuadores (LED / Motor)  ")
        self._populate_states_tab(self.tab_states)

        # Pestaña 2: Umbrales ToF y Tolerancias
        self.tab_limits = self._create_scrollable_tab(self.notebook, "  📏 Sensor ToF y Tolerancias SMAW  ")
        self._populate_limits_tab(self.tab_limits)

        # Pestaña 3: Lanzador y Pruebas
        self.tab_launcher = self._create_scrollable_tab(self.notebook, "  🚀 Lanzador Integrado y Pruebas  ")
        self._populate_launcher_tab(self.tab_launcher)

    def _create_scrollable_tab(self, notebook, title):
        tab_frame = ttk.Frame(notebook)
        notebook.add(tab_frame, text=title)

        canvas = tk.Canvas(tab_frame, bg=C_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(tab_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=C_BG)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        # Soporte para rueda del ratón
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        canvas.configure(xscrollcommand=None, yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        return scrollable_frame

    # --------------------------------------------------------------------------
    # PESTAÑA 1: ESTADOS Y ACTUADORES
    # --------------------------------------------------------------------------
    def _populate_states_tab(self, parent):
        lbl_info = tk.Label(
            parent,
            text="Personaliza el comportamiento de la herramienta según el estado actual en el que se encuentre.",
            font=("Segoe UI", 10), fg=C_MUTED, bg=C_BG
        )
        lbl_info.pack(anchor="w", padx=12, pady=(8, 14))

        # 1. Estado Reposo / Inactivo
        self._create_state_card(
            parent,
            title="1. Estado INACTIVO / REPOSO (Standby)",
            desc="Herramienta en reposo esperando iniciar el ejercicio o con careta levantada.",
            state_key="idle",
            has_haptic=False,
            presets=[("Naranja Cálido", [255, 40, 0]), ("Azul Tenue", [0, 40, 150]), ("Apagado", [0, 0, 0])]
        )

        # 2. Estado Homing / Contacto
        self._create_state_card(
            parent,
            title="2. Momento de HOMING / CONTACTO (Touch Start)",
            desc="Punta del electrodo apoyada en el inicio del cordón (pulsador activado).",
            state_key="homing",
            haptic_key="homing",
            haptic_label="Fuerza de pulso de confirmación de homing (%):",
            presets=[("Azul Eléctrico", [0, 50, 255]), ("Cian / Celeste", [0, 200, 255]), ("Blanco", [255, 255, 255])]
        )

        # 3. Estado Soldadura Óptima
        self._create_state_card(
            parent,
            title="3. Estado SOLDADURA ÓPTIMA (Arco Estable)",
            desc="Distancia de arco y ángulos dentro de los rangos correctos durante el soldeo.",
            state_key="weld_optimal",
            haptic_key="weld_optimal",
            haptic_label="Vibración de zumbido de arco plasma (%):",
            presets=[("Verde Puro", [0, 255, 0]), ("Verde Lima", [80, 255, 0]), ("Azul Foco", [0, 150, 255])]
        )

        # 3b. Zona tolerable (amarillo)
        self._create_state_card(
            parent,
            title="3b. Estado PRECAUCIÓN (Cerca del límite)",
            desc="Distancia, ángulo de trabajo, ángulo de avance o velocidad fuera del rango óptimo pero dentro de la tolerancia del nivel (amarillo en el HUD de Godot).",
            state_key="weld_caution",
            has_haptic=False,
            presets=[("Amarillo", [255, 170, 0]), ("Ámbar", [255, 120, 0]), ("Amarillo Limón", [200, 255, 0])]
        )

        # 4. Estado Advertencia de Técnica
        self._create_state_card(
            parent,
            title="4. Estado FUERA DE TOLERANCIA (Rojo)",
            desc="Algún parámetro (distancia, ángulos o velocidad) superó los límites del nivel.",
            state_key="weld_warning",
            haptic_key="weld_warning",
            haptic_label="Fuerza de vibración pulsante de aviso (%):",
            presets=[("Rojo Alerta", [255, 0, 0]), ("Amarillo / Ámbar", [255, 180, 0]), ("Naranja", [255, 80, 0])]
        )

        # 5. Estado Cortocircuito / Electrodo Pegado
        self._create_state_card(
            parent,
            title="5. Estado ELECTRODO PEGADO (Cortocircuito / Sticking)",
            desc="La punta colisionó o se aproximó a menos de la distancia mínima con la chapa.",
            state_key="sticking",
            haptic_key="sticking",
            haptic_label="Fuerza de vibración violenta de pegado (%):",
            presets=[("Rojo Intenso", [255, 0, 0]), ("Magenta", [255, 0, 120]), ("Amarillo Peligro", [255, 220, 0])]
        )

    def _create_state_card(self, parent, title, desc, state_key, has_haptic=True, haptic_key="", haptic_label="", presets=[]):
        card = tk.Frame(parent, bg=C_CARD, highlightthickness=1, highlightbackground=C_BORDER)
        card.pack(fill="x", padx=12, pady=6)

        # Encabezado de la tarjeta
        header_frame = tk.Frame(card, bg=C_CARD)
        header_frame.pack(fill="x", padx=14, pady=(10, 4))

        lbl_t = tk.Label(header_frame, text=title, font=("Segoe UI", 11, "bold"), fg=C_TXT, bg=C_CARD)
        lbl_t.pack(side="left")

        lbl_d = tk.Label(card, text=desc, font=("Segoe UI", 9), fg=C_MUTED, bg=C_CARD)
        lbl_d.pack(anchor="w", padx=14, pady=(0, 8))

        content = tk.Frame(card, bg=C_CARD)
        content.pack(fill="x", padx=14, pady=(0, 12))

        # --- SECCIÓN COLOR LED ---
        color_box = tk.Frame(content, bg=C_CARD)
        color_box.pack(side="left", fill="y", padx=(0, 20))

        tk.Label(color_box, text="Color LED RGB:", font=("Segoe UI", 9, "bold"), fg=C_TXT, bg=C_CARD).pack(anchor="w")

        btn_row = tk.Frame(color_box, bg=C_CARD)
        btn_row.pack(anchor="w", pady=4)

        # Muestra del color actual
        rgb = self.config_data["led_colors"].get(state_key, [0, 255, 0])
        hex_color = self._rgb_to_hex(rgb)

        swatch = tk.Label(btn_row, width=4, height=1, bg=hex_color, relief="ridge", bd=2)
        swatch.pack(side="left", padx=(0, 8))
        self.color_swatches[state_key] = swatch

        btn_pick = ttk.Button(
            btn_row, text="Elegir Color...",
            command=lambda k=state_key: self._pick_color_for_state(k)
        )
        btn_pick.pack(side="left")

        btn_test_led = ttk.Button(
            btn_row, text="💡 Probar", width=8,
            command=lambda k=state_key: self._test_specific_led(k)
        )
        btn_test_led.pack(side="left", padx=(6, 0))

        # Botones presets rápidos
        preset_frame = tk.Frame(color_box, bg=C_CARD)
        preset_frame.pack(anchor="w", pady=(2, 0))
        for p_name, p_rgb in presets:
            btn_p = tk.Button(
                preset_frame, text=p_name, font=("Segoe UI", 7), bg=C_PANEL, fg=C_TXT, relief="flat", bd=1,
                padx=5, pady=1,
                command=lambda k=state_key, c=p_rgb: self._set_color_preset(k, c)
            )
            btn_p.pack(side="left", padx=2)

        # --- SECCIÓN VIBRACIÓN HÁPTICA ---
        if has_haptic:
            haptic_box = tk.Frame(content, bg=C_CARD)
            haptic_box.pack(side="left", fill="both", expand=True)

            val_init = self.config_data["haptic_intensity_pct"].get(haptic_key, 50)
            var_scale = tk.DoubleVar(value=val_init)
            self.slider_vars[f"haptic/{haptic_key}"] = var_scale

            val_lbl = tk.Label(haptic_box, text=f"{val_init}%", font=("Segoe UI", 9, "bold"), fg=C_CYAN, bg=C_CARD)
            val_lbl.pack(side="right", padx=(4, 0))

            btn_test_hap = ttk.Button(
                haptic_box, text="⚡ Probar", width=8,
                command=lambda k=haptic_key: self._test_specific_haptic(k)
            )
            btn_test_hap.pack(side="right", padx=(6, 4))

            tk.Label(haptic_box, text=haptic_label, font=("Segoe UI", 9, "bold"), fg=C_TXT, bg=C_CARD).pack(anchor="w")

            scale = ttk.Scale(
                haptic_box, from_=0, to=100, orient="horizontal", variable=var_scale,
                command=lambda v, l=val_lbl: l.config(text=f"{int(float(v))}%")
            )
            scale.pack(fill="x", pady=4)

    def _rgb_to_hex(self, rgb):
        return f"#{int(rgb[0]):02x}{int(rgb[1]):02x}{int(rgb[2]):02x}"

    def _pick_color_for_state(self, state_key):
        curr_rgb = self.config_data["led_colors"].get(state_key, [255, 255, 255])
        curr_hex = self._rgb_to_hex(curr_rgb)
        color = colorchooser.askcolor(color=curr_hex, title=f"Seleccionar color para {state_key}")
        if color and color[0]:
            r, g, b = int(color[0][0]), int(color[0][1]), int(color[0][2])
            self.config_data["led_colors"][state_key] = [r, g, b]
            self.color_swatches[state_key].config(bg=color[1])

    def _set_color_preset(self, state_key, rgb):
        self.config_data["led_colors"][state_key] = list(rgb)
        self.color_swatches[state_key].config(bg=self._rgb_to_hex(rgb))

    # --------------------------------------------------------------------------
    # PESTAÑA 2: UMBRALES DEL SENSOR ToF Y TOLERANCIAS
    # --------------------------------------------------------------------------
    def _populate_limits_tab(self, parent):
        tk.Label(
            parent,
            text="Calibra los límites de distancia punta-chapa del sensor ToF láser y las tolerancias en Godot.",
            font=("Segoe UI", 10), fg=C_MUTED, bg=C_BG
        ).pack(anchor="w", padx=12, pady=(8, 14))

        # Tarjeta 1: Límites ToF (Extinción y Sticking)
        card_tof = tk.Frame(parent, bg=C_CARD, highlightthickness=1, highlightbackground=C_BORDER)
        card_tof.pack(fill="x", padx=12, pady=6)

        tk.Label(card_tof, text="1. Límites Críticos del Sensor ToF Láser", font=("Segoe UI", 11, "bold"), fg=C_TXT, bg=C_CARD).pack(anchor="w", padx=14, pady=(10, 4))
        tk.Label(card_tof, text="Determinan cuándo el arco se apaga por alejarse mucho o cuándo se pega el electrodo por contacto excesivo.", font=("Segoe UI", 9), fg=C_MUTED, bg=C_CARD).pack(anchor="w", padx=14, pady=(0, 10))

        # Extinción de arco
        self._create_slider_row(
            card_tof,
            title="Distancia de Extinción / Corte de Arco (Límite Superior):",
            desc="Si la distancia punta-chapa supera este valor (y no hay contacto), el arco se extingue y el ejercicio finaliza o se interrumpe.",
            key="tof/extinguish_gap",
            min_val=6.0, max_val=25.0, step=0.5, unit="mm",
            default_val=self.config_data["tof_limits_mm"].get("extinguish_gap", 12.0)
        )

        # Sticking / Pegado
        self._create_slider_row(
            card_tof,
            title="Distancia de Electrodo Pegado (Sticking / Límite Inferior):",
            desc="Si la punta se aproxima a la chapa a menos de esta distancia durante el soldeo (o se presiona el botón), se dispara el pegado y vibración 100%.",
            key="tof/stick_gap",
            min_val=0.1, max_val=2.5, step=0.1, unit="mm",
            default_val=self.config_data["tof_limits_mm"].get("stick_gap", 0.4)
        )

        # Reencendido automático por proximidad
        self._create_slider_row(
            card_tof,
            title="Distancia de Reencendido por Proximidad (Auto-Strike):",
            desc="Si el arco se extingue al levantar la herramienta, al volver a aproximarla a esta cota o menor, el arco se reactiva automáticamente sin requerir pulsar de nuevo.",
            key="tof/reignite_gap",
            min_val=2.0, max_val=8.0, step=0.1, unit="mm",
            default_val=self.config_data["tof_limits_mm"].get("reignite_gap", 4.5)
        )

        # Rango Óptimo ToF
        card_opt = tk.Frame(parent, bg=C_CARD, highlightthickness=1, highlightbackground=C_BORDER)
        card_opt.pack(fill="x", padx=12, pady=6)

        tk.Label(card_opt, text="2. Rango de Distancia de Arco Óptimo (SMAW)", font=("Segoe UI", 11, "bold"), fg=C_TXT, bg=C_CARD).pack(anchor="w", padx=14, pady=(10, 4))
        tk.Label(card_opt, text="Intervalo en el cual el LED luce verde y se deposita el cordón perfecto con máxima puntuación en Godot.", font=("Segoe UI", 9), fg=C_MUTED, bg=C_CARD).pack(anchor="w", padx=14, pady=(0, 10))

        self._create_slider_row(
            card_opt,
            title="Distancia Óptima Mínima:",
            desc="Por debajo de esta cota el arco comienza a considerarse demasiado corto (riesgo de inclusión de escoria).",
            key="tof/optimal_min",
            min_val=0.5, max_val=3.0, step=0.1, unit="mm",
            default_val=self.config_data["tof_limits_mm"].get("optimal_min", 1.0)
        )

        self._create_slider_row(
            card_opt,
            title="Distancia Óptima Máxima:",
            desc="Por encima de esta cota el arco pasa a ser largo (genera chisporroteo, porosidad y cordón ancho).",
            key="tof/optimal_max",
            min_val=3.0, max_val=10.0, step=0.5, unit="mm",
            default_val=self.config_data["tof_limits_mm"].get("optimal_max", 6.0)
        )

        # Tarjeta 3: Tolerancias de Simulación en Godot
        card_sim = tk.Frame(parent, bg=C_CARD, highlightthickness=1, highlightbackground=C_BORDER)
        card_sim.pack(fill="x", padx=12, pady=6)

        tk.Label(card_sim, text="3. Tolerancias de Ángulos y Velocidad (Evaluación Godot)", font=("Segoe UI", 11, "bold"), fg=C_TXT, bg=C_CARD).pack(anchor="w", padx=14, pady=(10, 4))
        tk.Label(card_sim, text="Rango pedagógico permitido para evaluar al operario según la norma AWS D1.1.", font=("Segoe UI", 9), fg=C_MUTED, bg=C_CARD).pack(anchor="w", padx=14, pady=(0, 10))

        self._create_slider_row(
            card_sim,
            title="Tolerancia de Ángulo de Trabajo (Roll / Desvío transversal):",
            desc="Grados máximos permitidos respecto de 90° (perpendicular a la chapa).",
            key="sim/roll_max_deg",
            min_val=10.0, max_val=45.0, step=1.0, unit="°",
            default_val=self.config_data["simulation_tolerances"].get("roll_max_deg", 25.0)
        )

        self._create_slider_row(
            card_sim,
            title="Velocidad Óptima Mínima de Avance:",
            desc="Velocidad mínima en el cordón para no sobrecargar el baño de fusión.",
            key="sim/speed_min_mm_s",
            min_val=0.5, max_val=3.0, step=0.1, unit="mm/s",
            default_val=self.config_data["simulation_tolerances"].get("speed_min_mm_s", 1.8)
        )

        self._create_slider_row(
            card_sim,
            title="Velocidad Óptima Máxima de Avance:",
            desc="Velocidad máxima antes de generar mordedura (undercut) o falta de penetración.",
            key="sim/speed_max_mm_s",
            min_val=3.0, max_val=8.0, step=0.1, unit="mm/s",
            default_val=self.config_data["simulation_tolerances"].get("speed_max_mm_s", 4.5)
        )

        # Tarjeta 4: Compensación Cinemática 3D de la Punta (Brazo ArUco)
        card_lever = tk.Frame(parent, bg=C_CARD, highlightthickness=1, highlightbackground=C_BORDER)
        card_lever.pack(fill="x", padx=12, pady=6)

        tk.Label(card_lever, text="4. Compensación Cinemática 3D de la Punta (Brazo ArUco)", font=("Segoe UI", 11, "bold"), fg=C_TXT, bg=C_CARD).pack(anchor="w", padx=14, pady=(10, 4))
        tk.Label(card_lever, text="Desacopla la inclinación de la herramienta para que al variar el ángulo de avance o de trabajo, la punta no se desplace del cordón.", font=("Segoe UI", 9), fg=C_MUTED, bg=C_CARD).pack(anchor="w", padx=14, pady=(0, 10))

        self._create_slider_row(
            card_lever,
            title="Distancia Punta a Marcador ArUco (Brazo Cinemático):",
            desc="Distancia física [mm] medida a lo largo del vástago desde la punta de contacto del electrodo hasta el centro del marcador ArUco ID 0.",
            key="tool/tip_lever",
            min_val=50.0, max_val=250.0, step=1.0, unit="mm",
            default_val=self.config_data.get("tool_tip_lever_mm", 115.0)
        )

    def _create_slider_row(self, parent, title, desc, key, min_val, max_val, step, unit, default_val):
        row = tk.Frame(parent, bg=C_CARD)
        row.pack(fill="x", padx=14, pady=6)

        header = tk.Frame(row, bg=C_CARD)
        header.pack(fill="x")

        tk.Label(header, text=title, font=("Segoe UI", 9, "bold"), fg=C_TXT, bg=C_CARD).pack(side="left")

        val_var = tk.DoubleVar(value=default_val)
        self.slider_vars[key] = val_var

        lbl_val = tk.Label(header, text=f"{default_val:.1f} {unit}", font=("Segoe UI", 9, "bold"), fg=C_CYAN, bg=C_CARD)
        lbl_val.pack(side="right")

        tk.Label(row, text=desc, font=("Segoe UI", 8), fg=C_MUTED, bg=C_CARD, wraplength=800, justify="left").pack(anchor="w", pady=(1, 3))

        scale = ttk.Scale(
            row, from_=min_val, to=max_val, orient="horizontal", variable=val_var,
            command=lambda v, l=lbl_val, u=unit, s=step: self._update_slider_label(v, l, u, s)
        )
        scale.pack(fill="x", pady=(0, 4))

    def _update_slider_label(self, val_str, label, unit, step):
        v = float(val_str)
        if step >= 1.0:
            label.config(text=f"{int(round(v))} {unit}")
        else:
            label.config(text=f"{v:.1f} {unit}")

    # --------------------------------------------------------------------------
    # PESTAÑA 3: LANZADOR INTEGRADO Y PRUEBAS EN VIVO
    # --------------------------------------------------------------------------
    def _populate_launcher_tab(self, parent):
        tk.Label(
            parent,
            text="Lanzador unificado de subsistemas y banco de pruebas directo para la herramienta física.",
            font=("Segoe UI", 10), fg=C_MUTED, bg=C_BG
        ).pack(anchor="w", padx=12, pady=(8, 14))

        # --- INICIO DEL ARCO (HOMING) ---
        card_arc = tk.Frame(parent, bg=C_CARD, highlightthickness=1, highlightbackground=C_BORDER)
        card_arc.pack(fill="x", padx=12, pady=6)
        tk.Label(card_arc, text="Inicio del Arco", font=("Segoe UI", 11, "bold"), fg=C_TXT, bg=C_CARD).pack(anchor="w", padx=14, pady=(10, 4))
        self.var_homing = tk.BooleanVar(value=bool(self.config_data.get("homing_required", False)))
        row_h = tk.Frame(card_arc, bg=C_CARD)
        row_h.pack(fill="x", padx=14, pady=(0, 12))
        self.btn_homing = tk.Button(row_h, width=34, font=("Segoe UI", 10, "bold"), relief="flat",
                                    cursor="hand2", command=self._toggle_homing)
        self.btn_homing.pack(side="left")
        self.lbl_homing = tk.Label(row_h, font=("Segoe UI", 9), fg=C_MUTED, bg=C_CARD, justify="left", wraplength=480)
        self.lbl_homing.pack(side="left", padx=12)
        self._refresh_homing_widgets()

        # --- SECCIÓN LANZADORES ---
        card_launch = tk.Frame(parent, bg=C_CARD, highlightthickness=1, highlightbackground=C_BORDER)
        card_launch.pack(fill="x", padx=12, pady=6)

        tk.Label(card_launch, text="Acciones Principales del Simulador", font=("Segoe UI", 11, "bold"), fg=C_TXT, bg=C_CARD).pack(anchor="w", padx=14, pady=(10, 4))

        btn_grid = tk.Frame(card_launch, bg=C_CARD)
        btn_grid.pack(fill="x", padx=14, pady=(6, 16))

        # Botón 1: Calibración
        b1_frame = tk.Frame(btn_grid, bg=C_PANEL, padx=12, pady=12, relief="groove", bd=1)
        b1_frame.pack(side="left", fill="both", expand=True, padx=4)

        tk.Label(b1_frame, text="🎯 Calibrar Mesa ArUco", font=("Segoe UI", 11, "bold"), fg=C_ORANGE, bg=C_PANEL).pack(anchor="w")
        tk.Label(b1_frame, text="Ejecuta el asistente de visión para fijar Inicio [ESPACIO] y Fin [F] en tu cartón.", font=("Segoe UI", 8), fg=C_MUTED, bg=C_PANEL, wraplength=240, justify="left").pack(anchor="w", pady=(2, 8))
        ttk.Button(b1_frame, text="Abrir Calibración...", style="Orange.TButton", command=self._launch_calibration).pack(fill="x")

        # Botón 2: Iniciar Simulador Puente
        b2_frame = tk.Frame(btn_grid, bg=C_PANEL, padx=12, pady=12, relief="groove", bd=1)
        b2_frame.pack(side="left", fill="both", expand=True, padx=4)

        tk.Label(b2_frame, text="⚡ Iniciar Puente Integrado", font=("Segoe UI", 11, "bold"), fg=C_GREEN, bg=C_PANEL).pack(anchor="w")
        tk.Label(b2_frame, text="Inicia en segundo plano la cámara ArUco y el enlace serie del ESP32 con Godot.", font=("Segoe UI", 8), fg=C_MUTED, bg=C_PANEL, wraplength=240, justify="left").pack(anchor="w", pady=(2, 8))
        ttk.Button(b2_frame, text="Iniciar Puente (UDP 4242)", style="Green.TButton", command=self._launch_integrated_bridge).pack(fill="x")

        # Botón 3: Abrir Godot
        b3_frame = tk.Frame(btn_grid, bg=C_PANEL, padx=12, pady=12, relief="groove", bd=1)
        b3_frame.pack(side="left", fill="both", expand=True, padx=4)

        tk.Label(b3_frame, text="🎮 Abrir Simulador Godot", font=("Segoe UI", 11, "bold"), fg=C_CYAN, bg=C_PANEL).pack(anchor="w")
        tk.Label(b3_frame, text="Abre el proyecto 'project.godot' directamente en el motor 3D listo para soldar.", font=("Segoe UI", 8), fg=C_MUTED, bg=C_PANEL, wraplength=240, justify="left").pack(anchor="w", pady=(2, 8))
        ttk.Button(b3_frame, text="Abrir Godot 3D", style="Action.TButton", command=self._launch_godot).pack(fill="x")

        # Configurar ejecutable Godot opcional
        godot_row = tk.Frame(card_launch, bg=C_CARD)
        godot_row.pack(fill="x", padx=14, pady=(0, 10))
        tk.Label(godot_row, text="Ruta Ejecutable Godot (Opcional):", font=("Segoe UI", 8), fg=C_MUTED, bg=C_CARD).pack(side="left")
        self.entry_godot_exe = ttk.Entry(godot_row, font=("Segoe UI", 8))
        self.entry_godot_exe.insert(0, self.config_data.get("godot_executable", ""))
        self.entry_godot_exe.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(godot_row, text="Examinar...", command=self._browse_godot_exe).pack(side="right")

        # --- SECCIÓN BANCO DE PRUEBAS EN VIVO ---
        card_test = tk.Frame(parent, bg=C_CARD, highlightthickness=1, highlightbackground=C_BORDER)
        card_test.pack(fill="x", padx=12, pady=6)

        tk.Label(card_test, text="Banco de Pruebas de Hardware en Vivo", font=("Segoe UI", 11, "bold"), fg=C_TXT, bg=C_CARD).pack(anchor="w", padx=14, pady=(10, 4))
        tk.Label(card_test, text="Permite probar los actuadores de la herramienta física directamente para sentir la vibración y ver el LED.", font=("Segoe UI", 9), fg=C_MUTED, bg=C_CARD).pack(anchor="w", padx=14, pady=(0, 10))

        test_row = tk.Frame(card_test, bg=C_CARD)
        test_row.pack(fill="x", padx=14, pady=(0, 14))

        # Selector de Puerto COM
        tk.Label(test_row, text="Puerto Serial ESP32:", font=("Segoe UI", 9, "bold"), fg=C_TXT, bg=C_CARD).pack(side="left")
        self.combo_ports = ttk.Combobox(test_row, width=12, state="readonly")
        self._refresh_serial_ports()
        self.combo_ports.pack(side="left", padx=8)

        btn_ref_port = ttk.Button(test_row, text="🔄", width=3, command=self._refresh_serial_ports)
        btn_ref_port.pack(side="left", padx=(0, 15))

        # Botón prueba LED
        ttk.Button(test_row, text="Probar Color LED en Vivo", command=self._test_hardware_led).pack(side="left", padx=5)

        # Botón prueba Vibración
        ttk.Button(test_row, text="Probar Vibración al 100% (2000ms)", command=self._test_hardware_haptic).pack(side="left", padx=5)

    def _refresh_homing_widgets(self):
        on = self.var_homing.get()
        if on:
            self.btn_homing.config(text="HOMING ACTIVADO (pulsador)", bg=C_ORANGE, fg="#111111", activebackground=C_ORANGE)
            self.lbl_homing.config(text="El arco arranca solo después de apoyar la punta en el inicio del cordón "
                                        "y presionar el pulsador. Clic para desactivar.")
        else:
            self.btn_homing.config(text="HOMING DESACTIVADO (arco automático)", bg=C_GREEN, fg="#111111", activebackground=C_GREEN)
            r = self.config_data.get("tof_limits_mm", {}).get("reignite_gap", 4.5)
            self.lbl_homing.config(text=f"El arco se enciende solo cuando la punta se acerca a {r:.1f} mm o menos "
                                        "de la chapa, sin presionar el pulsador. Clic para activar el homing.")

    def _toggle_homing(self):
        self.var_homing.set(not self.var_homing.get())
        self.config_data["homing_required"] = bool(self.var_homing.get())
        self._refresh_homing_widgets()
        # Guarda en tools/ y en Godot (Godot relee el archivo solo, en ~1 s) y avisa a la herramienta
        self.save_config(show_msg=False)
        msg = json.dumps({"cmd": "SET_HOMING", "enabled": self.config_data["homing_required"]})
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto((msg + "\n").encode("utf-8"), ("127.0.0.1", 4243))
            sock.close()
        except Exception:
            pass
        estado = "ACTIVADO" if self.config_data["homing_required"] else "DESACTIVADO"
        self.lbl_save_status.config(text=f"✓ Homing {estado} (guardado y enviado a Godot y a la herramienta)", fg=C_GREEN)

    def _refresh_serial_ports(self):
        if HAS_SERIAL:
            ports = [p.device for p in list_ports.comports()]
            self.combo_ports["values"] = ports
            if ports:
                # Preferir COM4 o el primero
                if "COM4" in ports:
                    self.combo_ports.set("COM4")
                else:
                    self.combo_ports.set(ports[0])
            else:
                self.combo_ports.set("Sin puertos")
        else:
            self.combo_ports.set("COM4")

    def _get_active_port(self):
        if hasattr(self, 'combo_ports'):
            port = self.combo_ports.get()
            if port and not port.startswith("Sin"):
                return port
        if HAS_SERIAL:
            ports = [p.device for p in list_ports.comports()]
            if "COM4" in ports:
                return "COM4"
            if ports:
                return ports[0]
        return "COM4"

    def _on_close(self):
        self._close_serial()
        self.destroy()

    def _close_serial(self):
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except Exception:
                pass
            self.serial_conn = None
            self.serial_conn_port = None

    def _test_specific_led(self, state_key):
        port = self._get_active_port()
        if not port:
            messagebox.showwarning("Puerto no seleccionado", "Conecta el ESP32 o selecciona un puerto COM válido.")
            return
        rgb = self.config_data["led_colors"].get(state_key, [0, 255, 0])
        cmd = json.dumps({"cmd": "TEST_ACTUATOR", "r": rgb[0], "g": rgb[1], "b": rgb[2], "ms": 2500})
        if self._send_serial_quick(port, cmd):
            self.lbl_save_status.config(text=f"💡 Probando LED ({state_key}: RGB {rgb}) durante 2.5 s...", fg=C_CYAN)

    def _test_specific_haptic(self, haptic_key):
        port = self._get_active_port()
        if not port:
            messagebox.showwarning("Puerto no seleccionado", "Conecta el ESP32 o selecciona un puerto COM válido.")
            return
        var = self.slider_vars.get(f"haptic/{haptic_key}")
        pct = int(var.get()) if var else self.config_data["haptic_intensity_pct"].get(haptic_key, 50)
        duty = int(min(max(pct, 0), 100) * 2.55)
        # El firmware gestiona el temporizador de apagado de 2000 ms de forma autónoma
        cmd_on = json.dumps({"cmd": "SET_HAPTIC", "val": duty, "ms": 2000})
        if self._send_serial_quick(port, cmd_on):
            self.lbl_save_status.config(text=f"⚡ Vibrando motor al {pct}% ({haptic_key}) durante 2 s...", fg=C_CYAN)
            self.after(2100, lambda: self.lbl_save_status.config(text="Listo.", fg=C_MUTED))

    def _test_hardware_led(self):
        port = self.combo_ports.get()
        if not port or port.startswith("Sin"):
            messagebox.showwarning("Puerto no seleccionado", "Conecta el ESP32 o selecciona un puerto COM válido.")
            return

        rgb = self.config_data["led_colors"].get("weld_optimal", [0, 255, 0])
        cmd = json.dumps({"cmd": "TEST_ACTUATOR", "r": rgb[0], "g": rgb[1], "b": rgb[2], "ms": 2500})
        if self._send_serial_quick(port, cmd):
            self.lbl_save_status.config(text=f"💡 LED Probado en vivo (Verde Óptimo RGB {rgb})", fg=C_CYAN)

    def _test_hardware_haptic(self):
        port = self.combo_ports.get()
        if not port or port.startswith("Sin"):
            messagebox.showwarning("Puerto no seleccionado", "Conecta el ESP32 o selecciona un puerto COM válido.")
            return

        pct = 100   # prueba al máximo: si así no vibra, el problema es de hardware
        duty = 255
        cmd_on = json.dumps({"cmd": "SET_HAPTIC", "val": duty, "ms": 2000})
        if self._send_serial_quick(port, cmd_on):
            self.lbl_save_status.config(text=f"⚡ Motor vibrando en vivo al {pct}% durante 2000ms...", fg=C_CYAN)
            self.after(2100, lambda: self.lbl_save_status.config(text="Listo.", fg=C_MUTED))

    def _send_serial_quick(self, port, line):
        payload = (line + "\n").encode("utf-8")
        sent_serial = False
        sent_udp = False

        # 1. Intentar enviar por la conexión Serie persistente directa (si pySerial está disponible)
        if HAS_SERIAL:
            try:
                if not self.serial_conn or self.serial_conn_port != port or not self.serial_conn.is_open:
                    self._close_serial()
                    ser = serial.Serial()
                    ser.port = port
                    ser.baudrate = 115200
                    ser.timeout = 0.05
                    ser.dtr = False
                    ser.rts = False
                    ser.open()
                    self.serial_conn = ser
                    self.serial_conn_port = port
                    time.sleep(0.3)  # Estabilización inicial de conexión

                self.serial_conn.write(payload)
                self.serial_conn.flush()
                sent_serial = True
                # Liberar el puerto: si la GUI lo deja abierto, el puente no puede conectarse
                # al ESP32 y Godot no recibe telemetría ni puede mandar la vibración.
                time.sleep(0.05)
                self._close_serial()
            except Exception:
                # El puerto COM puede estar en uso por el puente serial_bridge
                self._close_serial()

        # 2. Reenviar siempre por UDP (puerto 4243) para el puente serial_bridge si estuviera corriendo
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(payload, ("127.0.0.1", 4243))
            sock.close()
            sent_udp = True
        except Exception:
            pass

        if not sent_serial and not sent_udp:
            messagebox.showerror("Error de Comunicación", f"No se pudo acceder a {port} ni transmitir por UDP.")
            return False
        return True

    def _launch_calibration(self):
        self._close_serial()  # Liberar COM para el proceso de calibración
        bat = BASE_DIR / "probar_mesa.bat"
        if bat.exists():
            subprocess.Popen(["cmd.exe", "/c", str(bat)], cwd=str(BASE_DIR))
        else:
            py = TOOLS_DIR / "test_vision_table.py"
            subprocess.Popen([sys.executable, str(py)], cwd=str(BASE_DIR))

    def _launch_integrated_bridge(self):
        self._close_serial()  # Liberar COM para serial_bridge.py
        bat = BASE_DIR / "iniciar_simulador.bat"
        if bat.exists():
            subprocess.Popen(["cmd.exe", "/c", str(bat)], cwd=str(BASE_DIR))
        else:
            messagebox.showerror("Error", "No se encontró iniciar_simulador.bat")

    def _browse_godot_exe(self):
        fn = filedialog.askopenfilename(
            title="Seleccionar ejecutable de Godot Engine",
            filetypes=[("Ejecutable Godot", "*.exe"), ("Todos los archivos", "*.*")]
        )
        if fn:
            self.entry_godot_exe.delete(0, tk.END)
            self.entry_godot_exe.insert(0, fn)
            self.config_data["godot_executable"] = fn

    def _launch_godot(self):
        exe = self.entry_godot_exe.get().strip()
        if exe and os.path.exists(exe):
            subprocess.Popen([exe, "--path", str(GODOT_DIR)], cwd=str(GODOT_DIR))
        elif PROJECT_GODOT.exists():
            try:
                os.startfile(str(PROJECT_GODOT))
            except Exception as e:
                messagebox.showerror("Error al abrir Godot", f"No se pudo abrir automáticamente project.godot: {e}")
        else:
            messagebox.showerror("Error", f"No se encontró {PROJECT_GODOT}")

    # --------------------------------------------------------------------------
    # BARRA INFERIOR DE ACCIONES
    # --------------------------------------------------------------------------
    def _build_bottom_bar(self):
        bar = tk.Frame(self, bg=C_PANEL, height=65, relief="flat")
        bar.pack(fill="x", side="bottom", padx=0, pady=0)

        # Estado a la izquierda
        self.lbl_save_status = tk.Label(bar, text="Listo.", font=("Segoe UI", 9), fg=C_MUTED, bg=C_PANEL)
        self.lbl_save_status.pack(side="left", padx=20, pady=16)

        # Botones a la derecha
        btn_save = ttk.Button(bar, text="💾 Guardar y Aplicar a Godot y Herramienta", style="Green.TButton", command=self.save_config)
        btn_save.pack(side="right", padx=(10, 20), pady=12)

        btn_reset = ttk.Button(bar, text="🔄 Restablecer Valores por Defecto", command=self.reset_defaults)
        btn_reset.pack(side="right", padx=5, pady=12)

    def _update_all_widgets_from_data(self):
        if hasattr(self, "var_homing"):
            self.var_homing.set(bool(self.config_data.get("homing_required", False)))
            self._refresh_homing_widgets()
        # Actualizar colores
        for k, swatch in self.color_swatches.items():
            rgb = self.config_data["led_colors"].get(k, [255, 255, 255])
            swatch.config(bg=self._rgb_to_hex(rgb))

        # Actualizar sliders
        for key, var in self.slider_vars.items():
            category, param = key.split("/")
            if category == "haptic":
                val = self.config_data["haptic_intensity_pct"].get(param, 50)
            elif category == "tof":
                val = self.config_data["tof_limits_mm"].get(param, 10.0)
            elif category == "sim":
                val = self.config_data["simulation_tolerances"].get(param, 20.0)
            var.set(val)


def main():
    app = ArcSimControlCenter()
    app.mainloop()


if __name__ == "__main__":
    main()
