# Bitácora de Trackdays
# Copyright (c) 2026 TU NOMBRE
# Licencia MIT - ver el archivo LICENSE
"""Tests automáticos. Usan CSV sintéticos generados al vuelo (no hace falta ningún archivo real)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trackdays import db  # noqa: E402
from trackdays.telemetry import (ErrorTelemetria, calcular_vueltas,  # noqa: E402
                                 formatear_tiempo, leer_csv, mejor_tiempo, parse_tiempo)

# Tiempos de vuelta de la sesión de prueba: out lap, 5 vueltas rápidas, in lap
TIEMPOS = [130.0, 92.40, 91.15, 90.80, 91.60, 92.10, 120.0]


def generar(sep=",", hz=20, ms=False, unidad="m/s", metadatos=True, factor_vel=1 / 3.6):
    """Genera un CSV parecido a los de RaceChrono (metadatos + encabezado + unidades + datos)."""
    lineas = []
    if metadatos:
        lineas += [f'This file is created using RaceChrono v9{sep}', f'Format{sep}3', f'Session title{sep}Test']
    cab = ["timestamp", "lap_number", "elapsed_time", "speed", "latitude", "longitude"]
    lineas.append(sep.join(cab))
    lineas.append(sep.join(["s", "", "s", unidad, "deg", "deg"]))
    t = 0.0
    paso = 1 / hz
    for n, dur in enumerate(TIEMPOS):
        fin = t + dur
        while t < fin - 1e-9:
            vel_kmh = 120 + 80 * ((t * 7) % 10) / 10 if n else 60
            v = vel_kmh * factor_vel
            val_t = t * 1000 if ms else t
            lineas.append(sep.join([f"{1.7e9 + val_t:.3f}", str(n), f"{val_t:.3f}", f"{v:.3f}", "-32.9", "-60.7"]))
            t += paso
    return "\n".join(lineas)


@pytest.fixture
def escribir(tmp_path):
    def _escribir(texto, nombre="sesion.csv", codificacion="utf-8"):
        ruta = tmp_path / nombre
        ruta.write_bytes(texto.encode(codificacion))
        return ruta
    return _escribir


def procesar(ruta):
    a = leer_csv(ruta)
    s = a.sugerido
    return a, calcular_vueltas(a, s["vuelta"], s["tiempo"], s["velocidad"], a.unidad_vel)


def test_formato_tiempos():
    assert formatear_tiempo(83.456) == "1:23.456"
    assert formatear_tiempo(59.9996) == "1:00.000"
    assert parse_tiempo("1:23,456") == pytest.approx(83.456)
    assert parse_tiempo("83.456") == pytest.approx(83.456)
    assert parse_tiempo("abc") is None and parse_tiempo("") is None


def test_formato_racechrono_ms_con_metadatos(escribir):
    a, vueltas = procesar(escribir(generar()))
    assert a.unidad_vel == "m/s"
    assert a.sugerido == {"vuelta": 1, "tiempo": 2, "velocidad": 3}
    assert len(vueltas) == len(TIEMPOS)
    assert mejor_tiempo(vueltas) == pytest.approx(90.80, abs=0.06)
    assert [v.valida for v in vueltas] == [False, True, True, True, True, True, False]
    # velocidad máxima convertida de m/s a km/h
    assert max(v.vel_max for v in vueltas[1:-1]) == pytest.approx(200, abs=1)


def test_punto_y_coma_kmh_y_latin1(escribir):
    texto = generar(sep=";", unidad="km/h", factor_vel=1)
    a, vueltas = procesar(escribir(texto, codificacion="latin-1"))
    assert a.unidad_vel == "km/h"
    assert mejor_tiempo(vueltas) == pytest.approx(90.80, abs=0.06)


def test_tiempo_en_milisegundos(escribir):
    _, vueltas = procesar(escribir(generar(ms=True)))
    assert mejor_tiempo(vueltas) == pytest.approx(90.80, abs=0.06)


def test_unidad_adivinada_sin_fila_de_unidades(escribir):
    texto = generar(unidad="")  # fila de unidades vacía
    a, _ = procesar(escribir(texto))
    assert a.unidad_vel == "m/s"  # máx ~55 -> no pasa de 100
    texto = generar(unidad="", factor_vel=1)
    a, _ = procesar(escribir(texto))
    assert a.unidad_vel == "km/h"


def test_archivo_invalido(escribir):
    with pytest.raises(ErrorTelemetria):
        leer_csv(escribir("hola\nesto no es un csv de telemetria\n"))
    with pytest.raises(ErrorTelemetria):
        leer_csv(escribir(""))


def test_sin_columna_elegida(escribir):
    a = leer_csv(escribir(generar()))
    with pytest.raises(ErrorTelemetria):
        calcular_vueltas(a, None, 2)


def test_base_de_datos(tmp_path, escribir):
    con = db.conectar(tmp_path / "t.db")
    base = {"fecha": "2026-10-03", "circuito": "Rosario", "mejor_vuelta": "1:35.000"}
    s1 = db.insertar_sesion(con, base)
    s2 = db.insertar_sesion(con, {**base, "fecha": "2026-11-01", "circuito": "rosario", "mejor_vuelta": ""})
    db.insertar_sesion(con, {**base, "circuito": "Otro"})
    _, vueltas = procesar(escribir(generar()))
    db.reemplazar_vueltas(con, s2, vueltas)
    assert len(db.listar_vueltas(con, s2)) == len(TIEMPOS)

    ev = db.evolucion(con, "ROSARIO")
    assert [f for f, _ in ev] == ["2026-10-03", "2026-11-01"]
    assert ev[0][1] == pytest.approx(95.0)
    assert ev[1][1] == pytest.approx(90.80, abs=0.06)

    datos = db.obtener_sesion(con, s1)
    datos["clima"] = "Sol"
    db.actualizar_sesion(con, s1, datos)
    assert db.obtener_sesion(con, s1)["clima"] == "Sol"

    db.borrar_sesion(con, s2)
    assert db.listar_vueltas(con, s2) == [] and db.obtener_sesion(con, s2) is None
