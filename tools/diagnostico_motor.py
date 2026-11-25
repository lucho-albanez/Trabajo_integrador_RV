#!/usr/bin/env python3
"""
ArcSim_VR - Diagnóstico del motor háptico
=========================================
Separa un problema de SOFTWARE de uno de HARDWARE:
  1. Verifica que el ESP32 tenga cargado el firmware nuevo (responde al PING con su versión).
  2. Manda pruebas de vibración y lee de la telemetría el valor "h": el duty que el firmware
     está escribiendo REALMENTE en el pin del motor (GPIO 25).
  3. Si "h" llega a 255 y el motor no vibra, el software está bien: el problema está en el
     MOSFET, el diodo, la alimentación de 5 V o el cableado.

Uso: cerrá Godot, el puente y la ventana de la cámara (liberan el puerto COM) y ejecutá
     probar_motor.bat   o   python tools/diagnostico_motor.py [COMx]
"""
import json
import sys
import time

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    sys.exit("Falta pyserial:  py -3 -m pip install pyserial")

ESP32_VIDS = {0x10C4, 0x1A86, 0x0403, 0x303A}
EXPECTED_FW = "2026-11-24c"


def find_port():
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        if p.vid in ESP32_VIDS:
            return p.device
    for p in ports:
        if any(k in (p.description or "").lower() for k in ("usb", "ch340", "cp210", "uart", "serial")):
            return p.device
    return ports[0].device if ports else None


def read_for(ser, seconds):
    """Lee líneas JSON durante `seconds`. Devuelve (telemetrias, acks)."""
    tel, acks = [], []
    end = time.time() + seconds
    buf = b""
    while time.time() < end:
        buf += ser.read(512)
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if not (line.startswith(b"{") and line.endswith(b"}")):
                continue
            try:
                d = json.loads(line.decode("utf-8", "ignore"))
            except Exception:
                continue
            (acks if "ack" in d else tel).append(d)
    return tel, acks


def send(ser, obj):
    ser.write((json.dumps(obj) + "\n").encode())
    ser.flush()


AUTO = "--auto" in sys.argv
LOG = None


def log(*a):
    txt = " ".join(str(x) for x in a)
    print(txt)
    if LOG:
        LOG.write(txt + "\n")
        LOG.flush()


def ask(q):
    if AUTO:
        log(q + " (modo automatico: sin respuesta)")
        time.sleep(1.0)
        return False
    try:
        return input(q + " [s/n]: ").strip().lower().startswith("s")
    except EOFError:
        return False


def main():
    global LOG
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if AUTO:
        import os
        LOG = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "diag_motor.log"), "w", encoding="utf-8")
        log("Diagnostico automatico", time.strftime("%Y-%m-%d %H:%M:%S"))
        try:
            ports = list(serial.tools.list_ports.comports())
            for p in ports:
                log(f"  puerto: {p.device} | {p.description} | vid={p.vid} pid={p.pid}")
        except Exception as e:
            log("  error listando puertos:", e)
    port = args[0] if args else find_port()
    if not port:
        log("No se encontró el ESP32. Conectalo por USB."); return
    log(f"Abriendo {port}... (si falla, cerrá Godot, el puente y la cámara)")
    try:
        ser = serial.Serial()
        ser.port, ser.baudrate, ser.timeout = port, 115200, 0.05
        ser.dtr = False
        ser.rts = False
        ser.open()
    except Exception as e:
        log(f"No se pudo abrir {port}: {e}\nEl puerto está en uso: cerrá Godot, el puente y test_vision_table."); return

    tel, acks = read_for(ser, 1.5)
    if not tel and not acks:
        log("No llega telemetría. Reiniciando el ESP32 (botón EN) puede ayudar. Reintentando 3 s...")
        tel, acks = read_for(ser, 3.0)
    if not tel:
        log("El ESP32 no manda telemetría: revisá el cable USB o volvé a cargar el firmware."); return

    log("  telemetria de ejemplo:", tel[-1] if tel else None)
    for a in acks:
        log("  ack:", a)
    log("\n[1] Versión del firmware")
    send(ser, {"cmd": "PING"})
    _, acks = read_for(ser, 1.0)
    pong = next((a for a in acks if a.get("ack") == "PONG"), None)
    if pong is None or "fw" not in pong:
        log("    ✗ El ESP32 tiene un firmware VIEJO (no informa versión).")
        log("      Cargá el firmware nuevo: en firmware/ ejecutá  pio run -t upload")
        log("      (o el botón 'Upload' de PlatformIO en VS Code) y repetí este diagnóstico.")
        return
    log(f"    Firmware {pong['fw']} (esperado {EXPECTED_FW}) | PWM del motor configurado: "
          f"{'sí' if pong.get('pwm_ok') else 'NO'} | intensidades {pong.get('duty')}")
    if pong["fw"] != EXPECTED_FW:
        log("    ✗ La versión no coincide: cargá el firmware nuevo y repetí.")
        return
    if not pong.get("pwm_ok"):
        log("    ✗ El PWM del GPIO 25 no se pudo configurar en el firmware. Avisá con este mensaje.")

    log("\n[2] Pruebas de vibración (lo que el firmware escribe en el pin)")
    felt_any = False
    for duty in (255, 180, 120):
        send(ser, {"cmd": "SET_HAPTIC", "val": duty, "ms": 1500})
        tel, acks = read_for(ser, 1.6)
        hs = [t.get("h") for t in tel if "h" in t]
        h_max = max(hs) if hs else None
        log(f"    Pedido {duty:3d} -> el firmware escribió en el pin: {h_max}")
        time.sleep(0.4)
        if ask(f"    ¿Sentiste vibrar el motor con {duty}?"):
            felt_any = True
            break

    log("\n[3] Conclusión")
    if felt_any:
        log("    ✓ El motor y el firmware funcionan. Si no vibra durante la simulación, verificá que")
        log("      el puente esté corriendo antes que Godot y mirá el valor h en la consola del puente.")
    elif h_max is not None and h_max >= 120:
        log("    ✗ El firmware SÍ manda la señal al pin (h alto) pero el motor no se mueve:")
        log("      el problema es de HARDWARE. Revisá en este orden:")
        log("      1. 5 V en el cable rojo del motor (pin VIN del ESP32) con el tester.")
        log("      2. Que el cable negro del motor vaya al DRAIN (pata central) del MOSFET.")
        log("      3. GPIO 25 -> resistencia -> GATE (pata izquierda); SOURCE (derecha) a GND.")
        log("      4. El diodo flyback: banda gris hacia +5 V. Si está al revés, cortocircuita el motor.")
        log("      5. El IRFZ44N necesita ~10 V en el gate; con 3,3 V conduce poco. Si nunca anduvo")
        log("         fuerte, reemplazalo por un IRLZ44N o AO3400 (nivel lógico).")
        log("      6. Motor: probalo directo a 5 V y GND (sin el MOSFET).")
    else:
        log("    ✗ El firmware no está escribiendo el pin (h bajo o sin dato). Pasame toda esta salida.")
    send(ser, {"cmd": "SET_HAPTIC", "val": 0, "ms": 10})
    ser.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log("ERROR:", repr(e))
    if not AUTO:
        try:
            input("\nEnter para salir...")
        except EOFError:
            pass
