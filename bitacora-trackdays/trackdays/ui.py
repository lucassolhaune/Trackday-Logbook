# Bitácora de Trackdays
# Copyright (c) 2026 TU NOMBRE
# Licencia MIT - ver el archivo LICENSE
"""Interfaz de escritorio (Tkinter).

Contiene 4 ventanas:
  - App               ventana principal: formulario + tabla de sesiones
  - DialogoImportar   elegir columnas del CSV y previsualizar vueltas
  - VentanaVueltas    tabla de vueltas + gráfico de una sesión
  - VentanaGrafico    gráfico de evolución en un circuito

La interfaz solo "arma pantallas": los cálculos viven en telemetry.py y el
guardado en db.py.
"""
import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, ttk

from . import db
from .charts import dibujar_tiempos
from .db import CAMPOS
from .telemetry import (UNIDADES_VEL, ErrorTelemetria, calcular_vueltas,
                        formatear_tiempo, leer_csv, mejor_tiempo, parse_tiempo)

# Campos que deben ser números si el usuario los completa
CAMPOS_NUMERICOS = ("temp_pista", "presion_del", "presion_tras")


def _fmt_vel(v):
    """Velocidad para mostrar en tabla: sin decimales, o vacío si no hay dato."""
    return "" if v is None else f"{v:.0f}"


class App(tk.Tk):
    """Ventana principal."""

    def __init__(self):
        super().__init__()
        self.title("Bitácora de Trackdays")
        self.geometry("1100x620")
        self.minsize(950, 520)
        self.con = db.conectar()   # conexión a la base, compartida por toda la app
        self.entradas = {}         # {nombre_de_campo: cuadro de texto}
        self._armar_formulario()
        self._armar_tabla()
        self.protocol("WM_DELETE_WINDOW", self._cerrar)  # al cerrar la ventana, cerrar la base
        self.refrescar()

    # ------------------------------------------------------------ armado de pantalla
    def _armar_formulario(self):
        """Formulario de arriba (8 campos en grilla de 4 columnas) y botones."""
        marco = ttk.LabelFrame(self, text="Sesión")
        marco.pack(fill="x", padx=10, pady=(10, 5))
        for i, (col, texto) in enumerate(CAMPOS):
            fila, columna = divmod(i, 4)  # i=0..3 -> fila 0; i=4..7 -> fila 1
            # Cada campo ocupa 2 filas de la grilla: la etiqueta y debajo el cuadro de texto
            ttk.Label(marco, text=texto).grid(row=fila * 2, column=columna, sticky="w", padx=6, pady=(4, 0))
            e = ttk.Entry(marco, width=26)
            e.grid(row=fila * 2 + 1, column=columna, padx=6, pady=(0, 4))
            self.entradas[col] = e
        self.entradas["fecha"].insert(0, date.today().isoformat())  # fecha de hoy por defecto

        botones = ttk.Frame(marco)
        botones.grid(row=4, column=0, columnspan=4, sticky="we", pady=6, padx=6)
        ttk.Button(botones, text="Guardar como nueva", command=self.guardar_nueva).pack(side="left", padx=3)
        ttk.Button(botones, text="Actualizar seleccionada", command=self.actualizar).pack(side="left", padx=3)
        ttk.Button(botones, text="Limpiar formulario", command=self.limpiar).pack(side="left", padx=3)
        ttk.Button(botones, text="Borrar seleccionada", command=self.borrar).pack(side="left", padx=3)

        telem = ttk.LabelFrame(self, text="Telemetría (sesión seleccionada)")
        telem.pack(fill="x", padx=10, pady=5)
        ttk.Button(telem, text="Importar CSV de RaceChrono…", command=self.importar).pack(side="left", padx=6, pady=6)
        ttk.Button(telem, text="Ver vueltas y gráfico", command=self.ver_vueltas).pack(side="left", padx=6, pady=6)
        ttk.Button(telem, text="Evolución en este circuito", command=self.ver_evolucion).pack(side="left", padx=6, pady=6)

    def _armar_tabla(self):
        """Tabla con todas las sesiones guardadas."""
        cols = ["id"] + [c for c, _ in CAMPOS] + ["telem"]
        marco = ttk.Frame(self)
        marco.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.tabla = ttk.Treeview(marco, columns=cols, show="headings", selectmode="browse")
        self.tabla.heading("id", text="#")
        self.tabla.column("id", width=35, anchor="center", stretch=False)
        anchos = {"fecha": 90, "circuito": 130, "clima": 80, "temp_pista": 90, "presion_del": 95,
                  "presion_tras": 95, "mejor_vuelta": 100, "notas": 200}
        for col, texto in CAMPOS:
            # texto.split(" (")[0] saca las unidades del título: "Temp. pista (°C)" -> "Temp. pista"
            self.tabla.heading(col, text=texto.split(" (")[0])
            self.tabla.column(col, width=anchos.get(col, 100))
        self.tabla.heading("telem", text="Telemetría")
        self.tabla.column("telem", width=85, anchor="center", stretch=False)
        barra = ttk.Scrollbar(marco, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=barra.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        # Al hacer clic en una fila, se carga esa sesión en el formulario
        self.tabla.bind("<<TreeviewSelect>>", self._al_seleccionar)

    # ------------------------------------------------------------ utilidades internas
    def _cerrar(self):
        self.con.close()
        self.destroy()

    def _seleccionada(self):
        """Id de la sesión elegida en la tabla, o None si no hay ninguna."""
        sel = self.tabla.selection()
        return int(sel[0]) if sel else None

    def _al_seleccionar(self, _evento=None):
        id_ = self._seleccionada()
        if id_ is None:
            return
        # Leemos de la base y no de la tabla: Tkinter convertiría "38" en el
        # número 38 y "007" en 7, y perderíamos el formato original.
        datos = db.obtener_sesion(self.con, id_)
        if datos:
            self._poner_formulario(datos)

    def _poner_formulario(self, datos):
        """Vuelca un diccionario en los cuadros de texto (los que faltan quedan vacíos)."""
        for col, e in self.entradas.items():
            e.delete(0, "end")
            e.insert(0, datos.get(col) or "")

    def _leer_formulario(self):
        """Lee y valida el formulario. Devuelve un diccionario, o None si hay un error
        (en ese caso ya le mostró el motivo al usuario)."""
        datos = {c: self.entradas[c].get().strip() for c, _ in CAMPOS}
        if not datos["circuito"]:
            messagebox.showwarning("Falta un dato", "Poné al menos el circuito.")
            return None
        try:
            date.fromisoformat(datos["fecha"])  # exige AAAA-MM-DD
        except ValueError:
            messagebox.showwarning("Fecha inválida", "Usá el formato AAAA-MM-DD, por ejemplo 2026-10-03.")
            return None
        for c in CAMPOS_NUMERICOS:
            if datos[c]:
                try:
                    # Aceptamos "31,5" y lo guardamos como "31.5"; "38.0" queda "38"
                    datos[c] = str(float(datos[c].replace(",", ".")))
                    if datos[c].endswith(".0"):
                        datos[c] = datos[c][:-2]
                except ValueError:
                    messagebox.showwarning("Número inválido", f"'{datos[c]}' no es un número (campo: {c}).")
                    return None
        if datos["mejor_vuelta"]:
            t = parse_tiempo(datos["mejor_vuelta"])
            if t is None:
                messagebox.showwarning("Tiempo inválido", "Escribí la vuelta como 1:23.456 o 83.456.")
                return None
            datos["mejor_vuelta"] = formatear_tiempo(t)  # lo guardamos siempre con el mismo formato
        return datos

    def refrescar(self, seleccionar=None):
        """Vuelve a cargar la tabla desde la base. Opcionalmente deja una sesión seleccionada."""
        self.tabla.delete(*self.tabla.get_children())
        for fila in db.listar_sesiones(self.con):
            id_, *campos, n_vueltas = fila
            valores = [id_] + [c or "" for c in campos] + [f"{n_vueltas} vueltas" if n_vueltas else "—"]
            # iid = id de la sesión en la base: así sabemos cuál es sin buscarla
            self.tabla.insert("", "end", iid=str(id_), values=valores)
        if seleccionar is not None and self.tabla.exists(str(seleccionar)):
            self.tabla.selection_set(str(seleccionar))
            self.tabla.see(str(seleccionar))

    # ------------------------------------------------------------ acciones de los botones
    def guardar_nueva(self):
        datos = self._leer_formulario()
        if datos is None:
            return
        nuevo = db.insertar_sesion(self.con, datos)
        self.refrescar(nuevo)

    def actualizar(self):
        id_ = self._seleccionada()
        if id_ is None:
            messagebox.showinfo("Elegí una sesión", "Seleccioná una sesión de la tabla para actualizarla.")
            return
        datos = self._leer_formulario()
        if datos is None:
            return
        db.actualizar_sesion(self.con, id_, datos)
        self.refrescar(id_)

    def limpiar(self):
        """Deja el formulario vacío (con la fecha de hoy) para cargar una sesión nueva."""
        self.tabla.selection_remove(self.tabla.selection())
        self._poner_formulario({"fecha": date.today().isoformat()})

    def borrar(self):
        id_ = self._seleccionada()
        if id_ is None:
            return
        if messagebox.askyesno("Confirmar", "¿Borrar la sesión seleccionada y sus vueltas importadas?"):
            db.borrar_sesion(self.con, id_)
            self.limpiar()
            self.refrescar()

    def importar(self):
        """Elige un CSV y abre el diálogo de importación para la sesión seleccionada."""
        id_ = self._seleccionada()
        if id_ is None:
            messagebox.showinfo("Elegí una sesión",
                                "Primero guardá la sesión y seleccionala en la tabla; "
                                "la telemetría se asocia a esa sesión.")
            return
        ruta = filedialog.askopenfilename(
            title="CSV exportado de RaceChrono",
            filetypes=[("CSV / texto", "*.csv *.txt"), ("Todos los archivos", "*.*")])
        if not ruta:
            return  # el usuario canceló
        try:
            archivo = leer_csv(ruta)
        except (ErrorTelemetria, OSError) as e:
            messagebox.showerror("No pude leer el archivo", str(e))
            return
        # Le pasamos al diálogo qué hacer cuando el usuario confirme (callback)
        DialogoImportar(self, archivo, lambda vueltas: self._guardar_vueltas(id_, vueltas))

    def _guardar_vueltas(self, id_, vueltas):
        """Guarda las vueltas importadas. Devuelve False si el usuario se arrepiente."""
        if db.listar_vueltas(self.con, id_) and not messagebox.askyesno(
                "Reemplazar", "Esta sesión ya tiene vueltas importadas. ¿Reemplazarlas?"):
            return False
        db.reemplazar_vueltas(self.con, id_, vueltas)
        mejor = mejor_tiempo(vueltas)
        if mejor is not None:
            db.actualizar_mejor_vuelta(self.con, id_, formatear_tiempo(mejor))
        self.refrescar(id_)
        messagebox.showinfo("Listo", f"Importé {len(vueltas)} vueltas. Mejor vuelta: {formatear_tiempo(mejor)}")
        return True

    def ver_vueltas(self):
        id_ = self._seleccionada()
        if id_ is None:
            messagebox.showinfo("Elegí una sesión", "Seleccioná una sesión de la tabla.")
            return
        vueltas = db.listar_vueltas(self.con, id_)
        if not vueltas:
            messagebox.showinfo("Sin telemetría", "Esta sesión no tiene vueltas importadas todavía.")
            return
        datos = db.obtener_sesion(self.con, id_)
        VentanaVueltas(self, f"{datos['circuito']} · {datos['fecha']}", vueltas)

    def ver_evolucion(self):
        id_ = self._seleccionada()
        # Circuito de la sesión elegida o, si no hay, el que esté escrito en el formulario
        circuito = (db.obtener_sesion(self.con, id_)["circuito"] if id_ is not None
                    else self.entradas["circuito"].get().strip())
        if not circuito:
            messagebox.showinfo("Elegí un circuito", "Seleccioná una sesión o escribí el circuito en el formulario.")
            return
        puntos = db.evolucion(self.con, circuito)
        if not puntos:
            messagebox.showinfo("Sin datos", f"Todavía no hay mejores vueltas registradas en {circuito}.")
            return
        VentanaGrafico(self, f"Evolución de la mejor vuelta · {circuito}",
                       [f for f, _ in puntos], [t for _, t in puntos])


class DialogoImportar(tk.Toplevel):
    """Muestra qué columnas detectó, deja corregirlas y previsualiza las vueltas.

    Es el "seguro" del importador: si la detección automática se equivoca, el
    usuario lo ve antes de guardar y puede elegir las columnas correctas.
    """

    def __init__(self, padre, archivo, al_confirmar):
        super().__init__(padre)
        self.title("Importar telemetría")
        self.geometry("720x520")
        self.transient(padre)          # se muestra encima de la ventana principal
        self.archivo = archivo
        self.al_confirmar = al_confirmar
        self.vueltas = []

        # Lista de columnas del archivo como "0: timestamp", "1: lap_number", ...
        opciones = [f"{i}: {n or '(sin nombre)'}" for i, n in enumerate(archivo.encabezados)]
        sug = archivo.sugerido
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=10)
        self.cb_vuelta = self._combo(top, "Columna de vuelta", opciones, sug.get("vuelta"), 0)
        self.cb_tiempo = self._combo(top, "Columna de tiempo", opciones, sug.get("tiempo"), 1)
        vel = sug.get("velocidad")
        # La velocidad es opcional: agregamos "(ninguna)" como primera opción (por eso el +1)
        self.cb_vel = self._combo(top, "Columna de velocidad", ["(ninguna)"] + opciones,
                                  None if vel is None else vel + 1, 2, por_defecto=0)
        ttk.Label(top, text="Unidad de velocidad").grid(row=3, column=0, sticky="w", pady=2)
        self.cb_unidad = ttk.Combobox(top, values=list(UNIDADES_VEL), state="readonly", width=12)
        self.cb_unidad.set(archivo.unidad_vel)
        self.cb_unidad.grid(row=3, column=1, sticky="w", padx=6)
        self.cb_unidad.bind("<<ComboboxSelected>>", self.recalcular)

        self.resumen = ttk.Label(self, text="", font=("TkDefaultFont", 10, "bold"))
        self.resumen.pack(anchor="w", padx=10)

        # Vista previa de las vueltas calculadas
        marco = ttk.Frame(self)
        marco.pack(fill="both", expand=True, padx=10, pady=8)
        cols = ("n", "tiempo", "vmax", "vmed", "valida")
        self.tabla = ttk.Treeview(marco, columns=cols, show="headings")
        for c, t, a in (("n", "Vuelta", 60), ("tiempo", "Tiempo", 110), ("vmax", "Vel. máx", 90),
                        ("vmed", "Vel. media", 90), ("valida", "Estado", 230)):
            self.tabla.heading(c, text=t)
            self.tabla.column(c, width=a, anchor="center")
        barra = ttk.Scrollbar(marco, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=barra.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")

        ttk.Label(self, wraplength=680, foreground="#57606a",
                  text="Las vueltas muy lentas o muy cortas (entrada/salida de boxes, cortes) se marcan como "
                       "no válidas y no cuentan para la mejor vuelta. Los tiempos pueden diferir unas "
                       "centésimas de los que muestra RaceChrono.").pack(anchor="w", padx=10)

        botones = ttk.Frame(self)
        botones.pack(fill="x", padx=10, pady=10)
        self.btn_ok = ttk.Button(botones, text="Importar", command=self.confirmar)
        self.btn_ok.pack(side="right", padx=4)
        ttk.Button(botones, text="Cancelar", command=self.destroy).pack(side="right", padx=4)

        self.recalcular()
        self.grab_set()  # bloquea la ventana principal hasta cerrar este diálogo

    def _combo(self, padre, texto, opciones, indice, fila, por_defecto=None):
        """Crea una etiqueta + lista desplegable. 'indice' es la opción sugerida."""
        ttk.Label(padre, text=texto).grid(row=fila, column=0, sticky="w", pady=2)
        cb = ttk.Combobox(padre, values=opciones, state="readonly", width=48)  # readonly: solo elegir
        if indice is not None:
            cb.current(indice)
        elif por_defecto is not None:
            cb.current(por_defecto)
        cb.grid(row=fila, column=1, sticky="w", padx=6)
        cb.bind("<<ComboboxSelected>>", self.recalcular)  # al cambiar, recalcula la vista previa
        return cb

    def recalcular(self, _evento=None):
        """Calcula las vueltas con las columnas elegidas y actualiza la vista previa."""
        self.tabla.delete(*self.tabla.get_children())
        self.vueltas = []
        i_vuelta = self.cb_vuelta.current()   # índice elegido, -1 si no hay nada
        i_tiempo = self.cb_tiempo.current()
        i_vel = self.cb_vel.current() - 1     # -1 por la opción "(ninguna)"; <0 = sin velocidad
        try:
            self.vueltas = calcular_vueltas(
                self.archivo,
                i_vuelta if i_vuelta >= 0 else None,
                i_tiempo if i_tiempo >= 0 else None,
                i_vel if i_vel >= 0 else None,
                self.cb_unidad.get() or "km/h")
        except ErrorTelemetria as e:
            self.resumen.config(text=str(e))
            self.btn_ok.state(["disabled"])
            return
        mejor = mejor_tiempo(self.vueltas)
        for v in self.vueltas:
            estado = "válida" if v.valida else "no válida (boxes/parcial)"
            if v.valida and v.tiempo_s == mejor:
                estado = "★ mejor vuelta"
            self.tabla.insert("", "end", values=(v.numero, formatear_tiempo(v.tiempo_s),
                                                 _fmt_vel(v.vel_max), _fmt_vel(v.vel_media), estado))
        validas = sum(v.valida for v in self.vueltas)
        self.resumen.config(text=f"{len(self.vueltas)} vueltas encontradas · {validas} válidas · "
                                 f"mejor {formatear_tiempo(mejor) or '—'}")
        # Solo se puede importar si hay al menos una vuelta válida
        self.btn_ok.state(["!disabled"] if validas else ["disabled"])

    def confirmar(self):
        # El callback devuelve False si el usuario decidió no reemplazar: en ese caso no cerramos
        if self.al_confirmar(self.vueltas) is not False:
            self.destroy()


class VentanaVueltas(tk.Toplevel):
    """Tabla de vueltas de una sesión (izquierda) y gráfico (derecha)."""

    def __init__(self, padre, titulo, filas):
        super().__init__(padre)
        self.title(f"Vueltas · {titulo}")
        self.geometry("1000x480")
        # 'filas' vienen de la base: (numero, tiempo, vel_max, vel_media, valida)
        validas = [(n, t) for n, t, _vm, _vd, ok in filas if ok]
        mejor = min((t for _, t in validas), default=None)

        izq = ttk.Frame(self)
        izq.pack(side="left", fill="y", padx=10, pady=10)
        cols = ("n", "tiempo", "delta", "vmax", "ok")
        tabla = ttk.Treeview(izq, columns=cols, show="headings", height=18)
        for c, t, a in (("n", "Vuelta", 55), ("tiempo", "Tiempo", 85), ("delta", "Δ mejor", 70),
                        ("vmax", "V. máx", 65), ("ok", "Válida", 55)):
            tabla.heading(c, text=t)
            tabla.column(c, width=a, anchor="center")
        for n, t, vmax, _vmed, ok in filas:
            # Diferencia contra la mejor vuelta: "+0.350", o ★ para la mejor
            delta = f"+{t - mejor:.3f}" if ok and mejor is not None and t != mejor else ("★" if ok and t == mejor else "")
            tabla.insert("", "end", values=(n, formatear_tiempo(t), delta, _fmt_vel(vmax), "sí" if ok else "no"))
        tabla.pack(side="left", fill="y")

        self.canvas = tk.Canvas(self, bg="white", highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=10)
        # El gráfico muestra solo las vueltas válidas, para que la salida/entrada de
        # boxes (muy lentas) no aplasten la escala
        self.etiquetas = [n for n, _ in validas]
        self.valores = [t for _, t in validas]
        self.canvas.bind("<Configure>", self._dibujar)  # redibuja al cambiar el tamaño de la ventana

    def _dibujar(self, _evento=None):
        dibujar_tiempos(self.canvas, self.etiquetas, self.valores, "Tiempo por vuelta (vueltas válidas)")


class VentanaGrafico(tk.Toplevel):
    """Ventana con un único gráfico (se usa para la evolución entre trackdays)."""

    def __init__(self, padre, titulo, etiquetas, valores):
        super().__init__(padre)
        self.title(titulo)
        self.geometry("800x450")
        self.titulo, self.etiquetas, self.valores = titulo, etiquetas, valores
        self.canvas = tk.Canvas(self, bg="white", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)
        self.canvas.bind("<Configure>", self._dibujar)

    def _dibujar(self, _evento=None):
        dibujar_tiempos(self.canvas, self.etiquetas, self.valores, self.titulo)
