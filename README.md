# Selector de ayudantes: flujo máximo de costo mínimo

Prototipo para asignar ayudantes a las unidades de ayudantía (cátedra, corrector y laboratorio) de la Escuela
de Informática y Telecomunicaciones (UDP). El problema se modela como una red de flujo `S → E → H → C → T` y
se resuelve con **Successive Shortest Paths** (Ford–Fulkerson aumentando por el camino de menor costo, con
Dijkstra y potenciales), implementado desde cero en [ayudantias/flujo.py](ayudantias/flujo.py).

- Las **restricciones duras** son capacidades: máximo de ayudantías por alumno, una ayudantía por bloque
  horario y cupos por unidad.
- El único **costo** está en la arista de postulación `H → C`: `c = a·P^O + b·P^E + c·P^A + d·[no elegible]`,
  con `a + b + c + d = 1`. Combina el ranking del profesor, la prioridad del alumno, el orden por notas y una
  penalización para los postulantes no elegibles.
- El resultado cubre primero la mayor cantidad posible de cupos y, entre esas asignaciones, elige la de menor
  costo.

Los datos de postulación están anonimizados (`P001`, `P002`, ...).

## Requisitos

Python 3.10 o superior (los resultados se generaron con Python 3.12).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Ejecución

Todos los comandos se ejecutan desde la raíz del repositorio.

```bash
.venv/bin/python main.py                          # asignación propuesta -> salidas/asignacion.xlsx
.venv/bin/python main.py --exportar-elegibilidad  # plantilla de elegibilidad -> datos/elegibilidad.csv
.venv/bin/python experimentos.py                  # experimentos E1–E7 -> salidas/resultados.xlsx (~3 min)
.venv/bin/python informe/generar_figuras.py       # figuras y tablas del informe (~3 min)
.venv/bin/python -m pytest tests                  # 31 pruebas
```

Para compilar el informe (requiere una distribución de LaTeX):

```bash
cd informe && latexmk -pdf informe.tex
```

Opciones de `main.py`:

| Opción | Efecto |
|---|---|
| `--parametros otro.json` | Usa otro archivo de parámetros |
| `--cupos historico\|todas\|oferta` | Escenario de cupos: unidades con ayudante en 2026-2, secciones con ranking, o toda la oferta |
| `--semilla N` | Emparejamiento entre secciones reconstruidas y grupos reales |
| `--robustez 100` | Repite con 100 emparejamientos y agrega una hoja de robustez |
| `--exportar-elegibilidad [CSV]` | Escribe la plantilla de elegibilidad por alumno y termina |
| `--sin-oferta` | Ejecuta sin la programación académica (sin capa horaria real) |

## Parámetros (`parametros.json`)

Todo lo que no viene en los datos se configura en este archivo. El programa valida que los pesos sean no
negativos y sumen 1, y que los modos sean válidos.

| Clave | Valor base | Qué controla |
|---|---|---|
| `pesos.a`, `pesos.b`, `pesos.c` | 0,16 / 0,12 / 0,12 | Peso del profesor, del estudiante y de la asignatura |
| `pesos.d` | 0,6 | Penalización de los no elegibles (modo `penalizar`) |
| `capacidades.max_ayudantias` | 3 | Máximo de ayudantías por alumno |
| `capacidades.capacidad_correccion` | 3 | Correcciones por alumno (bloque ficticio, sin horario) |
| `capacidades.cupos` | `historico` | Escenario de cupos |
| `capacidades.incluir_no_rankeados` | `true` | Usa el orden por notas si el profesor no rankeó |
| `elegibilidad.promedio_minimo`, `nota_minima_ramo` | 5,0 / 5,0 | Umbrales de elegibilidad |
| `elegibilidad.modo_no_elegibles` | `penalizar` | `penalizar`, `dos_pasadas` o `excluir` |
| `elegibilidad.archivo_elegibilidad` | `null` | CSV con la decisión manual por alumno (`SI` / `NO`) |
| `externas` | vacío | Ayudantías en otros departamentos, p. ej. `"P001": 1` |
| `semilla` | 0 | Emparejamiento sección ↔ grupo |

## Entradas y salidas

| Archivo | Tipo | Contenido |
|---|---|---|
| `postulaciones_ayudantias_anonimo.xlsx` | Entrada | Postulaciones 2026-2 anonimizadas (1.245 postulaciones, 149 alumnos) |
| `Horarios Ing_inf.xls` | Entrada | Programación académica 2026-2 exportada de SAP |
| `parametros.json` | Entrada | Parámetros del modelo |
| `datos/elegibilidad.csv` | Entrada / salida | Plantilla de elegibilidad por alumno, editable |
| `salidas/asignacion.xlsx` | Salida | Asignación propuesta, comparación con el proceso manual y el greedy, cupos para decisión manual |
| `salidas/resultados.xlsx`, `salidas/resultados.txt` | Salida | Resultados de los experimentos E1–E7 |
| `informe/figuras/`, `informe/tablas/` | Salida | Figuras y tablas generadas para el informe |
| `informe/informe.tex`, `informe/informev9.pdf` | Informe | Fuente y PDF final de la Entrega 2 |

## Estructura

```
├── main.py                 asignación -> salidas/asignacion.xlsx
├── experimentos.py         experimentos E1–E7 -> salidas/resultados.xlsx
├── parametros.json         parámetros del modelo
├── requirements.txt
├── ayudantias/
│   ├── config.py           lectura y validación de parametros.json
│   ├── flujo.py            Successive Shortest Paths
│   ├── datos.py            postulaciones, reconstrucción de secciones, oferta SAP
│   ├── costos.py           rankings normalizados, orden por defecto, elegibilidad, costo
│   ├── modelo.py           red, modos de no elegibles, greedy, decisión manual
│   ├── metricas.py         métricas de evaluación
│   └── robustez.py         análisis sobre múltiples emparejamientos
├── tests/test_modelo.py    31 pruebas
├── datos/                  plantilla de elegibilidad
├── salidas/                resultados obtenidos
└── informe/                fuente LaTeX, generador de figuras, figuras, tablas y PDF final
```
