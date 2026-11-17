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
import json
import math
import socket
import sys
import time

GODOT_ADDR = ("127.0.0.1", 4242)
COMMAND_PORT = 4243
BAUD = 115200
ESP32_VIDS = {0x10C4, 0x1A86, 0x0403, 0x303A}  # CP210x, CH340, FTDI, Espressif


def find_port():
    from serial.tools import list_ports
    ports = list(list_ports.comports())
    for p in ports:
        if p.vid in ESP32_VIDS:
            return p.device
    return ports[0].device if len(ports) == 1 else None


def open_command_socket():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", COMMAND_PORT))
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
                print(f"Conectado a {port}. Reenviando a UDP {GODOT_ADDR[0]}:{GODOT_ADDR[1]} (Ctrl+C para salir)")
                buf = b""
                count, t0 = 0, time.time()
                while True:
                    chunk = ser.read(256)
                    if chunk:
                        buf += chunk
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            line = line.strip()
                            if line.startswith(b"{") and line.endswith(b"}"):
                                out.sendto(line, GODOT_ADDR)
                                count += 1
                        if len(buf) > 2048:
                            buf = b""
                    try:
                        while True:
                            data, _ = cmd.recvfrom(512)
                            ser.write(data.strip() + b"\n")
                    except BlockingIOError:
                        pass
                    if time.time() - t0 >= 5.0:
                        print(f"  {count / (time.time() - t0):.0f} paquetes/s")
                        count, t0 = 0, time.time()
        except (OSError, serial.SerialException) as e:
            print(f"Puerto perdido ({e}). Reintentando...")
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
