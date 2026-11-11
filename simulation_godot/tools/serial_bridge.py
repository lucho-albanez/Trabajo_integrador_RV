#!/usr/bin/env python3
"""
==============================================================================
ArcSim_VR - Puente de Comunicación USB-Serial a UDP para Godot 4.7
==============================================================================
Permite conectar el ESP32 por cable USB (simulando el lead de soldadura)
y transmitir la telemetría a Godot sin requerir plugins ni GDExtension externas.

Requisitos:
    pip install pyserial

Uso:
    python serial_bridge.py
    python serial_bridge.py --port COM3 --baud 115200
"""

import argparse
import socket
import sys
import time
import serial
import serial.tools.list_ports

GODOT_UDP_IP = "127.0.0.1"
GODOT_TELEMETRY_PORT = 4242   # Envío hacia Godot
GODOT_COMMAND_PORT = 4243     # Recepción de comandos desde Godot

def autodetect_esp32_port():
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        desc = (p.description or "").lower()
        hwid = (p.hwid or "").lower()
        if "cp210" in desc or "ch340" in desc or "usb-serial" in desc or "uart" in desc:
            return p.device
        if "cp210" in hwid or "ch340" in hwid or "10c4:ea60" in hwid or "1a86:7523" in hwid:
            return p.device
    if ports:
        return ports[0].device
    return None

def main():
    parser = argparse.ArgumentParser(description="ArcSim_VR Serial to UDP Bridge")
    parser.add_argument("--port", type=str, default=None, help="Puerto Serie (ej. COM3, /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=115200, help="Baudrate (default 115200)")
    args = parser.parse_args()

    port = args.port
    if not port:
        port = autodetect_esp32_port()
        if not port:
            print("[ERROR] No se detectó ningún puerto serie disponible.")
            print("Conecte el ESP32 o especifique el puerto manualmente con --port COMx")
            sys.exit(1)
        print(f"[INFO] Puerto ESP32 autodetectado: {port}")

    print(f"[INFO] Abriendo puerto serie {port} a {args.baud} baud...")
    try:
        ser = serial.Serial(port, args.baud, timeout=0.01)
        ser.reset_input_buffer()
    except Exception as e:
        print(f"[ERROR] No se pudo abrir el puerto serie {port}: {e}")
        sys.exit(1)

    # Socket UDP para enviar telemetría a Godot
    udp_out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Socket UDP no bloqueante para recibir comandos desde Godot y reenviarlos al ESP32
    udp_in = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_in.setblocking(False)
    udp_in.bind((GODOT_UDP_IP, GODOT_COMMAND_PORT))

    print(f"[INFO] Puente activo:")
    print(f"       ESP32 ({port}) -> UDP -> Godot 4.7 ({GODOT_UDP_IP}:{GODOT_TELEMETRY_PORT})")
    print(f"       Godot Comandos ({GODOT_COMMAND_PORT}) -> ESP32")
    print("[INFO] Presione Ctrl+C para detener.")

    packet_counter = 0
    start_time = time.time()

    try:
        while True:
            # 1. Leer telemetría desde ESP32 y reenviar a Godot
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line.startswith("{") and line.endswith("}"):
                    udp_out.sendto(line.encode('utf-8'), (GODOT_UDP_IP, GODOT_TELEMETRY_PORT))
                    packet_counter += 1

            # 2. Leer comandos de retorno desde Godot y enviar a ESP32
            try:
                cmd_data, _ = udp_in.recvfrom(1024)
                if cmd_data:
                    ser.write(cmd_data + b"\n")
            except BlockingIOError:
                pass

            # Monitor de rendimiento en consola cada 5 segundos
            if time.time() - start_time >= 5.0:
                fps = packet_counter / (time.time() - start_time)
                print(f"[TELEMETRÍA] Rendimiento actual: {fps:.1f} paquetes/segundo")
                packet_counter = 0
                start_time = time.time()

            time.sleep(0.001)

    except KeyboardInterrupt:
        print("\n[INFO] Cerrando puente de comunicaciones...")
    finally:
        ser.close()
        udp_out.close()
        udp_in.close()

if __name__ == "__main__":
    main()
