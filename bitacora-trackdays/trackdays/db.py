# Bitácora de Trackdays
# Copyright (c) 2026 TU NOMBRE
# Licencia MIT - ver el archivo LICENSE
"""Acceso a la base de datos SQLite (sesiones y vueltas).

SQLite guarda todo en un único archivo (trackdays.db), sin instalar ningún
servidor. Este módulo es el único que escribe SQL: el resto del programa
usa estas funciones.
"""
import sqlite3
from pathlib import Path

from .telemetry import parse_tiempo

# El archivo de la base queda en la carpeta raíz del proyecto, al lado de main.py
DB_PATH = Path(__file__).resolve().parent.parent / "trackdays.db"

# Campos de una sesión: (nombre de la columna en la base, texto que ve el usuario)
CAMPOS = [
    ("fecha", "Fecha (AAAA-MM-DD)"),
    ("circuito", "Circuito"),
    ("clima", "Clima"),
    ("temp_pista", "Temp. pista (°C)"),
    ("presion_del", "Presión del. (psi)"),
    ("presion_tras", "Presión tras. (psi)"),
    ("mejor_vuelta", "Mejor vuelta (m:ss.xxx)"),
    ("notas", "Notas / setup"),
]
NOMBRES = [c for c, _ in CAMPOS]  # solo los nombres de columna


def conectar(ruta=DB_PATH):
    """Abre la base (la crea si no existe) y se asegura de que estén las tablas."""
    con = sqlite3.connect(ruta)
    # SQLite no hace cumplir las relaciones entre tablas salvo que se lo pidamos
    con.execute("PRAGMA foreign_keys = ON")
    # Una fila por trackday
    con.execute(
        """CREATE TABLE IF NOT EXISTS sesiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT, circuito TEXT, clima TEXT, temp_pista TEXT,
            presion_del TEXT, presion_tras TEXT, mejor_vuelta TEXT, notas TEXT
        )"""
    )
    # Una fila por vuelta importada; sesion_id apunta a la sesión a la que pertenece
    con.execute(
        """CREATE TABLE IF NOT EXISTS vueltas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sesion_id INTEGER NOT NULL REFERENCES sesiones(id) ON DELETE CASCADE,
            numero INTEGER, tiempo_s REAL, vel_max REAL, vel_media REAL, valida INTEGER
        )"""
    )
    con.commit()
    return con


# ============================================================ sesiones
def listar_sesiones(con):
    """Todas las sesiones, la más reciente primero, con la cantidad de vueltas importadas."""
    cols = ", ".join(f"s.{c}" for c in NOMBRES)
    return con.execute(
        f"""SELECT s.id, {cols},
                   (SELECT COUNT(*) FROM vueltas v WHERE v.sesion_id = s.id)
            FROM sesiones s ORDER BY s.fecha DESC, s.id DESC"""
    ).fetchall()


def obtener_sesion(con, id_):
    """Una sesión como diccionario {columna: valor}, o None si no existe."""
    fila = con.execute(f"SELECT {', '.join(NOMBRES)} FROM sesiones WHERE id = ?", (id_,)).fetchone()
    return dict(zip(NOMBRES, fila)) if fila else None


def insertar_sesion(con, datos):
    """Crea una sesión nueva y devuelve su id. 'datos' es un diccionario."""
    cols = ", ".join(NOMBRES)
    marcas = ", ".join("?" for _ in NOMBRES)
    # Los '?' los completa SQLite de forma segura (evita inyección SQL)
    cur = con.execute(f"INSERT INTO sesiones ({cols}) VALUES ({marcas})",
                      [datos.get(c, "") for c in NOMBRES])
    con.commit()
    return cur.lastrowid


def actualizar_sesion(con, id_, datos):
    """Reemplaza todos los campos de una sesión existente."""
    sets = ", ".join(f"{c} = ?" for c in NOMBRES)
    con.execute(f"UPDATE sesiones SET {sets} WHERE id = ?", [datos.get(c, "") for c in NOMBRES] + [id_])
    con.commit()


def actualizar_mejor_vuelta(con, id_, texto):
    """Cambia solo la mejor vuelta (lo usa la importación de telemetría)."""
    con.execute("UPDATE sesiones SET mejor_vuelta = ? WHERE id = ?", (texto, id_))
    con.commit()


def borrar_sesion(con, id_):
    """Borra una sesión junto con sus vueltas."""
    con.execute("DELETE FROM vueltas WHERE sesion_id = ?", (id_,))
    con.execute("DELETE FROM sesiones WHERE id = ?", (id_,))
    con.commit()


# ============================================================ vueltas
def reemplazar_vueltas(con, sesion_id, vueltas):
    """Guarda las vueltas de una sesión, descartando las que había antes."""
    con.execute("DELETE FROM vueltas WHERE sesion_id = ?", (sesion_id,))
    con.executemany(
        "INSERT INTO vueltas (sesion_id, numero, tiempo_s, vel_max, vel_media, valida) VALUES (?,?,?,?,?,?)",
        [(sesion_id, v.numero, v.tiempo_s, v.vel_max, v.vel_media, int(v.valida)) for v in vueltas],
    )
    con.commit()


def listar_vueltas(con, sesion_id):
    """Vueltas de una sesión en el orden en que se importaron."""
    return con.execute(
        "SELECT numero, tiempo_s, vel_max, vel_media, valida FROM vueltas WHERE sesion_id = ? ORDER BY id",
        (sesion_id,),
    ).fetchall()


def evolucion(con, circuito):
    """Mejor vuelta de cada sesión en un circuito, en orden de fecha: [(fecha, segundos)].

    Usa la telemetría importada y, si no hay, la mejor vuelta anotada a mano.
    """
    objetivo = (circuito or "").strip().casefold()
    filas = con.execute(
        """SELECT s.fecha, s.circuito, s.mejor_vuelta,
                  (SELECT MIN(v.tiempo_s) FROM vueltas v WHERE v.sesion_id = s.id AND v.valida = 1)
           FROM sesiones s ORDER BY s.fecha, s.id"""
    ).fetchall()
    resultado = []
    for fecha, circ, manual, telem in filas:
        # Comparamos el circuito en Python (sin distinguir mayúsculas ni tildes
        # raras) para que "Rosario" y "rosario " cuenten como el mismo.
        if (circ or "").strip().casefold() != objetivo:
            continue
        mejor = telem if telem is not None else parse_tiempo(manual)
        if mejor is not None:
            resultado.append((fecha, mejor))
    return resultado
