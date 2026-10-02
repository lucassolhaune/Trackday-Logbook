# Bitácora de Trackdays
# Copyright (c) 2026 TU NOMBRE
# Licencia MIT - ver el archivo LICENSE
"""Lectura de CSV de telemetría (RaceChrono y similares) y cálculo de vueltas.

Este módulo NO sabe nada de ventanas ni de la base de datos: solo recibe un
archivo y devuelve vueltas. Por eso es fácil de probar con tests.

El lector es tolerante: detecta el separador, busca la fila de encabezados
(ignorando metadatos al principio del archivo) y sugiere qué columna es la
vuelta, el tiempo y la velocidad. Esas sugerencias se pueden corregir a mano
desde la interfaz, así que funciona aunque el formato cambie un poco.
"""
# Permite escribir anotaciones como "float | None" en versiones viejas de Python
from __future__ import annotations

import csv
import io
import statistics
from dataclasses import dataclass, field
from pathlib import Path


class ErrorTelemetria(Exception):
    """Error pensado para mostrárselo al usuario (mensaje en castellano)."""


# Factor para convertir cada unidad de velocidad a km/h.
# Ejemplo: 50 m/s * 3.6 = 180 km/h
UNIDADES_VEL = {"km/h": 1.0, "m/s": 3.6, "mph": 1.609344}


# ============================================================ tiempos
def formatear_tiempo(segundos: float | None) -> str:
    """Convierte segundos a texto de vuelta. Ejemplo: 83.456 -> '1:23.456'."""
    if segundos is None:
        return ""
    # Trabajamos en milisegundos enteros para evitar errores de redondeo
    # (por ejemplo, que 59.9996 se muestre como '0:60.000').
    total_ms = round(segundos * 1000)
    minutos, ms = divmod(total_ms, 60000)
    return f"{minutos}:{ms / 1000:06.3f}"


def parse_tiempo(texto: str | None) -> float | None:
    """Convierte texto a segundos. Acepta '1:23.456', '1:23,456' o '83.456'.

    Devuelve None si el texto está vacío o no se entiende.
    """
    t = (texto or "").strip().replace(",", ".")  # aceptamos coma decimal
    if not t:
        return None
    try:
        if ":" in t:
            minutos, resto = t.split(":", 1)
            return int(minutos) * 60 + float(resto)
        return float(t)
    except ValueError:
        return None


# ============================================================ estructuras de datos
@dataclass
class Archivo:
    """Un CSV ya leído, listo para que el usuario elija columnas."""

    encabezados: list[str]   # nombres de las columnas, tal cual están en el archivo
    filas: list[list[str]]   # todo lo que viene después del encabezado (texto crudo)
    sugerido: dict = field(default_factory=dict)  # {"vuelta": i, "tiempo": i, "velocidad": i}
    unidad_vel: str = "km/h"


@dataclass
class Vuelta:
    """Resultado de procesar una vuelta."""

    numero: int
    tiempo_s: float
    vel_max: float | None     # km/h
    vel_media: float | None   # km/h
    valida: bool = True       # False para vueltas de boxes o cortes parciales


# ============================================================ detección de columnas
def _norm(texto: str) -> str:
    """Normaliza un nombre de columna: 'Lap_Number ' -> 'lap number'."""
    return texto.strip().lower().replace("_", " ")


def _elegir(cols, exactos, contiene, excluir=()):
    """Busca una columna por nombre.

    1) Primero prueba nombres exactos, en orden de preferencia.
    2) Si no hay, busca la primera que CONTENGA alguna palabra clave
       (y que no tenga ninguna de las palabras a excluir).
    Devuelve el índice de la columna o None.
    """
    for e in exactos:
        for i, c in enumerate(cols):
            if c == e:
                return i
    for i, c in enumerate(cols):
        if any(k in c for k in contiene) and not any(x in c for x in excluir):
            return i
    return None


def _col_vuelta(cols):
    # Excluimos "lap time", "lap distance", etc. porque no son el número de vuelta
    return _elegir(cols, ("lap number", "lap", "lap #", "laps", "lap no", "vuelta"),
                   ("lap", "vuelta"), ("time", "tiempo", "dist", "delta"))


def _col_tiempo(cols):
    # Preferimos "elapsed time" (segundos desde el inicio) antes que "timestamp"
    return _elegir(cols, ("elapsed time", "time", "time (s)", "timestamp", "tiempo"),
                   ("elapsed", "timestamp", "time", "tiempo"), ("lap", "delta"))


def _col_velocidad(cols):
    return _elegir(cols, ("speed", "velocidad", "speed (km/h)", "speed (m/s)"),
                   ("speed", "velocidad"), ("accuracy", "error"))


def _num(texto: str) -> float:
    """Texto a número, aceptando coma decimal. Lanza ValueError si no es número."""
    return float(texto.strip().replace(",", "."))


# ============================================================ lectura del archivo
def _leer_texto(ruta: Path) -> str:
    """Lee el archivo probando UTF-8 y, si falla, Latin-1 (típico de Excel viejo)."""
    datos = ruta.read_bytes()
    for codificacion in ("utf-8-sig", "latin-1"):  # utf-8-sig descarta el BOM
        try:
            return datos.decode(codificacion)
        except UnicodeDecodeError:
            continue
    raise ErrorTelemetria("No pude leer el archivo (codificación desconocida).")


def _detectar_separador(texto: str) -> str:
    """Elige entre coma, punto y coma o tabulación: gana el que más aparece."""
    muestra = texto.splitlines()[:60]
    return max((",", ";", "\t"), key=lambda d: sum(l.count(d) for l in muestra))


def _detectar_unidad(filas, h, i):
    """Busca la unidad de velocidad en el encabezado y las 3 filas siguientes.

    Muchos CSV traen una fila de unidades debajo de los nombres ('km/h', 'm/s').
    Devuelve None si no encuentra ninguna.
    """
    textos = []
    for k in range(0, 4):
        if h + k < len(filas) and len(filas[h + k]) > i:
            textos.append(filas[h + k][i])
    junto = " ".join(textos).lower()
    if "km/h" in junto or "kph" in junto:
        return "km/h"
    if "mph" in junto:
        return "mph"
    if "m/s" in junto:
        return "m/s"
    return None


def leer_csv(ruta) -> Archivo:
    """Lee un CSV de telemetría y sugiere qué columna es cada cosa."""
    ruta = Path(ruta)
    texto = _leer_texto(ruta)
    if not texto.strip():
        raise ErrorTelemetria("El archivo está vacío.")
    sep = _detectar_separador(texto)
    filas = list(csv.reader(io.StringIO(texto), delimiter=sep))

    # Buscamos la fila de encabezados. Al principio puede haber líneas de
    # metadatos ("Session title", "Format", etc.), así que probamos fila por
    # fila hasta encontrar una con >= 3 columnas que parezca un encabezado.
    h = None
    for idx, fila in enumerate(filas[:300]):
        celdas = [_norm(c) for c in fila]
        if sum(1 for c in celdas if c) < 3:
            continue
        t, l, v = _col_tiempo(celdas), _col_vuelta(celdas), _col_velocidad(celdas)
        if t is not None and (l is not None or v is not None):
            h = idx
            break
    if h is None:
        raise ErrorTelemetria(
            "No encontré la fila de encabezados (columnas de tiempo, vuelta y velocidad).\n"
            "¿Es el CSV exportado desde RaceChrono?")

    encabezados = [c.strip() for c in filas[h]]
    celdas = [_norm(c) for c in encabezados]
    sugerido = {"vuelta": _col_vuelta(celdas), "tiempo": _col_tiempo(celdas),
                "velocidad": _col_velocidad(celdas)}
    datos = filas[h + 1:]

    unidad = None
    if sugerido["velocidad"] is not None:
        i = sugerido["velocidad"]
        unidad = _detectar_unidad(filas, h, i)
        if unidad is None:
            # Sin unidad explícita, adivinamos por el valor máximo: a más de 100
            # es casi seguro km/h; si no, m/s. El usuario puede corregirlo luego.
            valores = []
            for f in datos:
                try:
                    valores.append(_num(f[i]))
                except (ValueError, IndexError):
                    pass
            unidad = "km/h" if valores and max(valores) > 100 else "m/s"
    return Archivo(encabezados, datos, sugerido, unidad or "km/h")


# ============================================================ cálculo de vueltas
def calcular_vueltas(archivo: Archivo, col_vuelta, col_tiempo, col_vel=None,
                     unidad: str = "km/h") -> list[Vuelta]:
    """Convierte las filas de telemetría en una lista de vueltas con su tiempo.

    col_vuelta / col_tiempo / col_vel son índices de columna (col_vel es opcional).
    """
    if col_vuelta is None or col_tiempo is None:
        raise ErrorTelemetria("Elegí la columna de vuelta y la de tiempo.")

    # 1) Extraer muestras (vuelta, tiempo, velocidad) de cada fila numérica.
    muestras = []
    for fila in archivo.filas:
        try:
            lap = int(_num(fila[col_vuelta]))
            t = _num(fila[col_tiempo])
        except (ValueError, IndexError):
            continue  # saltea metadatos, fila de unidades y líneas vacías
        v = None
        if col_vel is not None:
            try:
                v = _num(fila[col_vel])
            except (ValueError, IndexError):
                pass
        muestras.append((lap, t, v))
    if len(muestras) < 2:
        raise ErrorTelemetria("No encontré filas con datos numéricos en esas columnas.")

    # 2) Detectar si el tiempo está en milisegundos. Si el paso típico entre
    #    muestras es >= 5, no puede ser segundos (RaceChrono graba a 10-25 Hz,
    #    o sea pasos de 0.04 a 0.1 s) y entonces son milisegundos.
    pasos = [b[1] - a[1] for a, b in zip(muestras, muestras[1:]) if b[1] > a[1]]
    factor_t = 0.001 if pasos and statistics.median(pasos) >= 5 else 1.0
    factor_v = UNIDADES_VEL.get(unidad, 1.0)

    # 3) Agrupar las muestras por número de vuelta (el dict mantiene el orden).
    grupos: dict[int, list] = {}
    for lap, t, v in muestras:
        grupos.setdefault(lap, []).append((t, v))

    # 4) Calcular el tiempo de cada vuelta.
    numeros = list(grupos)
    vueltas = []
    for i, lap in enumerate(numeros):
        pts = grupos[lap]
        t_ini = pts[0][0]
        # La vuelta termina donde empieza la siguiente: es más preciso que usar
        # la última muestra de la vuelta, que se quedaría un paso corto.
        # La última vuelta del archivo no tiene "siguiente", usa su última muestra.
        t_fin = grupos[numeros[i + 1]][0][0] if i + 1 < len(numeros) else pts[-1][0]
        vels = [p[1] * factor_v for p in pts if p[1] is not None]
        vueltas.append(Vuelta(
            numero=lap,
            tiempo_s=(t_fin - t_ini) * factor_t,
            vel_max=max(vels) if vels else None,
            vel_media=sum(vels) / len(vels) if vels else None,
        ))

    # 5) Marcar qué vueltas son "de verdad". La vuelta de salida de boxes, la de
    #    entrada y los cortes parciales no sirven para comparar. Usamos la
    #    mediana (no se deja arrastrar por valores extremos): es válida si
    #    está entre 85% y 130% de la mediana.
    positivos = [v.tiempo_s for v in vueltas if v.tiempo_s > 0]
    if len(vueltas) >= 3 and positivos:
        mediana = statistics.median(positivos)
        for v in vueltas:
            v.valida = 0.85 * mediana <= v.tiempo_s <= 1.3 * mediana
    else:
        # Con pocas vueltas la mediana no es confiable: aceptamos todas
        for v in vueltas:
            v.valida = v.tiempo_s > 0
    return vueltas


def mejor_tiempo(vueltas) -> float | None:
    """Menor tiempo entre las vueltas válidas (None si no hay ninguna)."""
    tiempos = [v.tiempo_s for v in vueltas if v.valida]
    return min(tiempos) if tiempos else None
