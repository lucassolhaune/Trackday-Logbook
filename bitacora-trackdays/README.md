# 🏁 Bitácora de Trackdays

App de escritorio para **registrar tus salidas a pista y analizar la telemetría** exportada
desde [RaceChrono](https://racechrono.com). Hecha en Python, sin instalar librerías extra.

> Proyecto personal hecho por un apasionado de los trackdays, para llevar el control de
> presiones, setups y tiempos de vuelta, y ver si realmente se está mejorando.

## ✨ Qué hace

- **Bitácora de sesiones:** fecha, circuito, clima, temperatura de pista, presiones de neumáticos
  (delantero y trasero), mejor vuelta y notas de setup. Se puede crear, editar y borrar.
- **Importa el CSV de RaceChrono:** detecta las columnas solo, te deja corregirlas y muestra una
  vista previa de las vueltas antes de guardar.
- **Análisis de la sesión:** tiempo de cada vuelta, diferencia contra tu mejor vuelta, velocidad
  máxima y gráfico.
- **Evolución por circuito:** la mejor vuelta de cada trackday, para ver si venís mejorando.

## 📦 Requisitos

- **Python 3.9 o superior** (descarga en [python.org](https://www.python.org/downloads/)).
  En Windows, tildá *"Add Python to PATH"* al instalar.
- **Tkinter**, que ya viene con Python en Windows y macOS. En Linux, si falta:
  `sudo apt install python3-tk`

No hay que instalar nada más.

## 🚀 Cómo usarla

1. Descargá o cloná el proyecto:
   ```
   git clone https://github.com/TU_USUARIO/bitacora-trackdays.git
   cd bitacora-trackdays
   ```
2. Ejecutá:
   ```
   python main.py
   ```
   (en Windows también puede ser `py main.py`; en Mac/Linux, `python3 main.py`)

### Paso a paso

1. **Cargá la sesión:** completá el formulario (al menos el circuito) y tocá **Guardar como nueva**.
   Podés hacerlo antes de salir a pista y completar la mejor vuelta después.
2. **Editá una sesión:** hacé clic en su fila de la tabla, cambiá lo que quieras y tocá
   **Actualizar seleccionada**. Para cargar una nueva, usá **Limpiar formulario**.
3. **Importá la telemetría:**
   - Grabá la salida con RaceChrono. Para que el archivo tenga vueltas, el circuito o la línea de
     meta tienen que estar configurados.
   - Exportá la sesión como **CSV** desde RaceChrono.
   - En la app, seleccioná la sesión y tocá **Importar CSV de RaceChrono…**.
   - Revisá la vista previa y tocá **Importar**. La mejor vuelta de la sesión se completa sola.
4. **Mirá los resultados:** **Ver vueltas y gráfico** muestra el detalle de la sesión, y
   **Evolución en este circuito** compara tus mejores vueltas a lo largo del tiempo.

Tus datos se guardan en un archivo `trackdays.db` dentro de la carpeta del programa. Es solo tuyo
y no se sube a Git.

## 🔧 Cómo funciona por dentro

```
main.py                     punto de entrada: abre la ventana
trackdays/
  ui.py                     pantallas (Tkinter): formulario, tabla, diálogos y gráficos
  telemetry.py              lectura del CSV y cálculo de vueltas (sin ventanas ni base de datos)
  db.py                     base de datos SQLite (sesiones y vueltas)
  charts.py                 gráfico de líneas dibujado a mano sobre un Canvas
tests/test_telemetry.py     tests automáticos
```

La idea es separar responsabilidades: `telemetry.py` calcula, `db.py` guarda y `ui.py` muestra.
Por eso la parte de cálculo se puede probar sin abrir ninguna ventana.

### Cómo se leen los CSV

Cada programa exporta un poco distinto, así que el lector es tolerante:

1. Detecta el separador (coma, punto y coma o tabulación) y la codificación del archivo.
2. Salta los metadatos del principio hasta encontrar la fila de encabezados.
3. Sugiere qué columna es la **vuelta**, el **tiempo** y la **velocidad**, buscando nombres como
   `lap_number`, `elapsed_time` o `speed`.
4. Detecta la unidad de velocidad (km/h, m/s o mph) y si el tiempo viene en segundos o milisegundos.

Si algo se detecta mal, el diálogo de importación permite elegir las columnas y la unidad a mano.

### Cómo se calculan las vueltas

- Las filas se agrupan por número de vuelta.
- El tiempo de una vuelta es el que pasa desde su primera muestra hasta la primera de la siguiente.
- Una vuelta se considera **válida** si está entre el 85% y el 130% de la mediana de todas las
  vueltas. Así quedan afuera las vueltas de salida y entrada de boxes y los cortes parciales, y no
  arruinan tu mejor vuelta ni los gráficos.
- Los tiempos pueden diferir unas centésimas de los que muestra RaceChrono, porque acá se calculan
  a partir de las muestras de datos.

### Base de datos

| Tabla      | Qué guarda                                                              |
|------------|-------------------------------------------------------------------------|
| `sesiones` | Una fila por trackday (fecha, circuito, clima, presiones, notas…)       |
| `vueltas`  | Una fila por vuelta importada, enlazada a su sesión (tiempo, velocidades, si es válida) |

## ✅ Tests

```
pip install -r requirements-dev.txt
pytest
```

Los tests generan CSV de ejemplo (distintos separadores, unidades y codificaciones) y comprueban el
cálculo de vueltas y la base de datos.

## ⚠️ Limitaciones

- Necesita que el CSV traiga **número de vuelta**. Si no, todavía no puede detectar las vueltas
  por GPS.
- El importador se probó con archivos de ejemplo. Si tu CSV no se interpreta bien, abrí un *issue*
  con las primeras líneas del archivo.

## 🗺️ Roadmap

- [ ] Comparar dos vueltas (velocidad vs. distancia)
- [ ] Mapa del recorrido coloreado por velocidad
- [ ] Detección de vueltas por GPS cuando el CSV no trae número de vuelta
- [ ] Exportar un resumen de la sesión

## 📄 Licencia

Distribuido bajo la licencia **MIT**: podés usar, copiar y modificar el código, siempre que
conserves el aviso de copyright. Ver el archivo [LICENSE](LICENSE).

© 2026 TU NOMBRE
