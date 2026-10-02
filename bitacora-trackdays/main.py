# Bitácora de Trackdays
# Copyright (c) 2026 TU NOMBRE
# Licencia MIT - ver el archivo LICENSE
"""Punto de entrada: abre la ventana principal.

Ejecutar con:  python main.py
"""
from trackdays.ui import App

# Este "if" hace que la app solo arranque al ejecutar este archivo directamente
# (y no si alguien lo importa desde otro programa o desde los tests).
if __name__ == "__main__":
    App().mainloop()  # mainloop() deja la ventana abierta esperando clics
