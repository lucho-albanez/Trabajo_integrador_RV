#!/usr/bin/env python3
"""Puente USB-serie <-> UDP entre el ESP32 y el simulador de Godot.

  ESP32 --(JSON por USB, 115200)--> este puente --(UDP 127.0.0.1:4242)--> Godot
  ESP32 <--(JSON por USB)---------- este puente <--(UDP :4243)------------ Godot

Uso:
    pip install pyserial
    python serial_bridge.py                  # detecta el puerto automaticamente
    python serial_bridge.py --port COM5      # puerto explicito
    python serial_bridge.py --mock           # telemetria sintetica (sin hardware)

El firmware actual envia una linea JSON por paquete; cada linea se reenvia tal
cual como un datagrama UDP. Los comandos que llegan por UDP (CALIBRATE,
RESET_YAW, SET_HAPTIC, PING) se escriben en el puerto serie terminados en "\\n".
Se reconecta solo si se desenchufa el cable.
"""
import argparse
import os
import json
import math
import socket
import sys
import time

GODOT_ADDR = ("127.0.0.1", 4242)
VISION_ADDR = ("127.0.0.1", 4244)
COMMAND_PORT = 4243
BAUD = 115200
ESP32_VIDS = {0x10C4, 0x1A86, 0x0403, 0x303A}  # CP210x, CH340, FTDI, Espressif


def find_port():
    from serial.tools import list_ports
    ports = list(list_ports.comports())
    if not ports:
        return None
    # 1. VID conocido
    for p in ports:
        if p.vid in ESP32_VIDS:
            return p.device
    # 2. Descripcion con palabras clave USB / Serial
    for p in ports:
        desc = (p.description or "").lower()
        if any(k in desc for k in ["usb", "ch340", "cp210", "uart", "serial", "esp32"]):
            return p.device
    # 3. Candidato que no sea puerto COM1/COM2 de placa madre
    usb_candidates = [p.device for p in ports if p.device.upper() not in ["COM1", "COM2"]]
    if usb_candidates:
        return usb_candidates[0]
    return ports[0].device


LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "tools", "puente_log.txt")


def log(msg):
    """Imprime y guarda en tools/puente_log.txt (diagnóstico)."""
    line = time.strftime("%H:%M:%S ") + msg
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def open_command_socket():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Uso EXCLUSIVO del puerto de comandos: con SO_REUSEADDR, en Windows un segundo puente
    # (abierto desde la GUI y desde un .bat) se quedaba con los comandos de Godot (vibración,
    # LED) sin tener el puerto del ESP32, y la herramienta nunca los recibía.
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        s.bind(("0.0.0.0", COMMAND_PORT))
    except OSError:
        log(f"ERROR: el puerto UDP {COMMAND_PORT} ya está en uso: hay OTRO puente abierto. "
            "Cerrá todas las ventanas del puente y abrí uno solo.")
        time.sleep(8)
        sys.exit(1)
    s.setblocking(False)
    return s


def run_serial(port_name):
    import serial
    out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    cmd = open_command_socket()
    while True:
        port = port_name or find_port()
        if not port:
            print("No encuentro el ESP32. Conectalo o usa --port COMx. Reintentando...")
            time.sleep(2.0)
            continue
        try:
            with serial.Serial(port, BAUD, timeout=0.02) as ser:
                log(f"Conectado a {port}. Reenviando a UDP {GODOT_ADDR[0]}:{GODOT_ADDR[1]} (Ctrl+C para salir)")
                ser.write(b'{"cmd":"PING"}\n')
                
                # Enviar configuración de herramienta si existe
                cfg_candidates = [
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tool_config.json"),
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools", "tool_config.json"),
                ]
                for cp in cfg_candidates:
                    if os.path.exists(cp):
                        try:
                            with open(cp, "r") as f:
                                cfg = json.load(f)
                            cfg_msg = {"cmd": "CONFIG", "config": cfg}
                            ser.write((json.dumps(cfg_msg) + "\n").encode())
                            print(f"  -> Configuracion de herramienta enviada al ESP32 desde {os.path.basename(cp)}")
                            break
                        except Exception as e:
                            print(f"  -> Aviso al cargar configuracion: {e}")

                buf = b""
                last_h = None
                max_h = 0
                n_hap = n_led = max_hap = 0
                count, t0 = 0, time.time()
                while True:
                    chunk = ser.read(256)
                    if chunk:
                        buf += chunk
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            line = line.strip()
                            if line.startswith(b"{") and line.endswith(b"}"):
                                if b'"ack"' in line:
                                    log("  ESP32: " + line.decode(errors="replace"))
                                else:
                                    i = line.find(b'"h":')
                                    if i >= 0:
                                        try:
                                            last_h = int(line[i + 4:].split(b",")[0].split(b"}")[0])
                                            max_h = max(max_h, last_h)
                                        except ValueError:
                                            pass
                                out.sendto(line, GODOT_ADDR)
                                try:
                                    out.sendto(line, VISION_ADDR)
                                except Exception:
                                    pass
                                count += 1
                        if len(buf) > 2048:
                            buf = b""
                    try:
                        while True:
                            data, src = cmd.recvfrom(8192)   # CONFIG mide ~700 bytes (antes se cortaba en 512)
                            ser.write(data.strip() + b"\n")
                            if b"SET_HAPTIC" in data:
                                n_hap += 1
                                try:
                                    v = int(json.loads(data.decode()).get("val", 0))
                                    max_hap = max(max_hap, v)
                                except Exception:
                                    pass
                            elif b"SET_LED" in data:
                                n_led += 1
                            else:
                                log(f"  -> ESP32 ({src[0]}:{src[1]}): " + data.decode(errors="replace").strip()[:200])
                    except BlockingIOError:
                        pass
                    if time.time() - t0 >= 5.0:
                        h_txt = "sin dato (firmware viejo)" if last_h is None else f"{last_h}/255 (max {max_h})"
                        log(f"  {count / (time.time() - t0):.0f} paquetes/s | motor en el pin: {h_txt} | "
                            f"de Godot: {n_hap} SET_HAPTIC (max {max_hap}), {n_led} SET_LED")
                        max_h = n_hap = n_led = max_hap = 0
                        count, t0 = 0, time.time()
        except (OSError, serial.SerialException) as e:
            log(f"Puerto {port} no disponible o perdido ({e}). Reintentando...")
            time.sleep(1.5)


def run_mock():
    """Herramienta simulada: oscila suavemente y alterna el gatillo."""
    out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    cmd = open_command_socket()
    print(f"Modo MOCK: telemetria sintetica a UDP {GODOT_ADDR[0]}:{GODOT_ADDR[1]} (Ctrl+C para salir)")
    t = 0.0
    dt = 1.0 / 60.0
    while True:
        work = math.radians(4.0 * math.sin(t * 0.7))
        travel = math.radians(10.0 + 3.0 * math.sin(t * 0.4))
        # Rotacion: cabeceo (eje X) por el angulo de trabajo y balanceo (eje Y) por el de avance.
        cw, sw = math.cos(work / 2), math.sin(work / 2)
        ct, st = math.cos(travel / 2), math.sin(travel / 2)
        qw = cw * ct
        qx = sw * ct
        qy = cw * st
        qz = -sw * st
        gap = 2.5 + 0.6 * math.sin(t * 1.3)
        pkt = {"qw": round(qw, 4), "qx": round(qx, 4), "qy": round(qy, 4), "qz": round(qz, 4),
               "d": round(gap, 1), "b": 1 if int(t) % 20 >= 3 else 0, "t": int(t * 1000)}
        out.sendto(json.dumps(pkt).encode(), GODOT_ADDR)
        try:
            while True:
                data, _ = cmd.recvfrom(512)
                print("  comando recibido:", data.decode(errors="replace").strip())
        except BlockingIOError:
            pass
        t += dt
        time.sleep(dt)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", help="puerto serie (COM5, /dev/ttyUSB0...)")
    ap.add_argument("--mock", action="store_true", help="enviar telemetria sintetica")
    args = ap.parse_args()
    try:
        if args.mock:
            run_mock()
        else:
            try:
                import serial  # noqa: F401
            except ImportError:
                sys.exit("Falta pyserial: pip install pyserial")
            run_serial(args.port)
    except KeyboardInterrupt:
        print("\nPuente detenido.")


if __name__ == "__main__":
    main()
