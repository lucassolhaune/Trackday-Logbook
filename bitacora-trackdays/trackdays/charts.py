# Bitácora de Trackdays
# Copyright (c) 2026 TU NOMBRE
# Licencia MIT - ver el archivo LICENSE
"""Gráfico de líneas dibujado directo sobre un Canvas de Tkinter.

Se dibuja a mano (líneas, círculos y textos) para no depender de librerías
externas como matplotlib: así el programa corre en cualquier compu con Python.
"""
import math

from .telemetry import formatear_tiempo

COLOR_LINEA = "#1f6feb"
COLOR_MEJOR = "#d1242f"
COLOR_GRILLA = "#d0d7de"


def dibujar_tiempos(canvas, etiquetas, valores, titulo=""):
    """Dibuja tiempos (en segundos) contra etiquetas del eje X. El menor va en rojo.

    canvas    -- el tk.Canvas donde dibujar
    etiquetas -- texto de cada punto en el eje X (nº de vuelta o fecha)
    valores   -- tiempos en segundos, uno por etiqueta
    """
    canvas.delete("all")  # borra el dibujo anterior (se redibuja al cambiar el tamaño)
    w, h = canvas.winfo_width(), canvas.winfo_height()
    if w < 120 or h < 100:
        return  # la ventana todavía no tiene tamaño real
    # Márgenes alrededor del área del gráfico: izquierda, derecha, arriba, abajo
    izq, der, arriba, abajo = 75, 20, 35, 40
    canvas.create_text(w / 2, 16, text=titulo, font=("TkDefaultFont", 10, "bold"))
    if not valores:
        canvas.create_text(w / 2, h / 2, text="Sin datos para mostrar")
        return

    # Rango del eje Y: del menor al mayor tiempo, con 10% de aire arriba y abajo.
    # Si todos los tiempos son casi iguales, abrimos el rango para no dividir por cero.
    vmin, vmax = min(valores), max(valores)
    if vmax - vmin < 0.5:
        vmin, vmax = vmin - 0.5, vmax + 0.5
    pad = (vmax - vmin) * 0.1
    vmin, vmax = vmin - pad, vmax + pad
    n = len(valores)
    x0, x1, y0, y1 = izq, w - der, arriba, h - abajo  # esquinas del área de dibujo

    # Funciones que convierten un dato en una posición de pantalla.
    def X(i):  # reparte los puntos en partes iguales a lo ancho
        return x0 + (x1 - x0) * (i / (n - 1) if n > 1 else 0.5)

    def Y(v):  # en pantalla Y crece hacia abajo, por eso se resta desde y1
        return y1 - (v - vmin) / (vmax - vmin) * (y1 - y0)

    # Líneas horizontales de la grilla con su tiempo a la izquierda
    for k in range(5):
        v = vmin + (vmax - vmin) * k / 4
        y = Y(v)
        canvas.create_line(x0, y, x1, y, fill=COLOR_GRILLA)
        canvas.create_text(x0 - 6, y, text=formatear_tiempo(v), anchor="e", font=("TkDefaultFont", 8))

    # Línea que une los puntos (necesita al menos 2 puntos)
    if n > 1:
        puntos = [c for i, v in enumerate(valores) for c in (X(i), Y(v))]
        canvas.create_line(*puntos, fill=COLOR_LINEA, width=2)

    # Un círculo por punto; el de menor tiempo es más grande y rojo
    mejor = valores.index(min(valores))
    for i, v in enumerate(valores):
        color = COLOR_MEJOR if i == mejor else COLOR_LINEA
        r = 5 if i == mejor else 3
        canvas.create_oval(X(i) - r, Y(v) - r, X(i) + r, Y(v) + r, fill=color, outline=color)

    # Etiquetas del eje X: como mucho unas 10, salteando si hay más puntos
    paso = max(1, math.ceil(n / 10))
    for i in range(0, n, paso):
        canvas.create_text(X(i), y1 + 14, text=str(etiquetas[i]), font=("TkDefaultFont", 8))
    # Tiempo de la mejor vuelta escrito arriba de su punto
    canvas.create_text(X(mejor), Y(valores[mejor]) - 14,
                       text=formatear_tiempo(valores[mejor]), fill=COLOR_MEJOR,
                       font=("TkDefaultFont", 9, "bold"))
