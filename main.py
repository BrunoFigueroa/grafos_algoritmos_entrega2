"""Selector de ayudantes: Entrega 2 (versión final).

Lee los parámetros de parametros.json (editable a mano) y escribe la asignación
propuesta en salidas/asignacion.xlsx.

Uso:
  python main.py                              # parámetros de parametros.json
  python main.py --parametros otro.json
  python main.py --cupos oferta               # toda la oferta CIT demanda ayudante
  python main.py --robustez 100               # repite con 100 emparejamientos sección<->grupo
  python main.py --exportar-elegibilidad      # plantilla datos/elegibilidad.csv para revisar a mano
  python main.py --sin-oferta                 # sin programación SAP (sin capa horaria real)
"""
import argparse
from pathlib import Path

import pandas as pd

from ayudantias import costos, datos, metricas, modelo, robustez
from ayudantias.config import Parametros

BASE = Path(__file__).parent


def parsear():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parametros", default=BASE / "parametros.json")
    ap.add_argument("--datos", default=BASE / "postulaciones_ayudantias_anonimo.xlsx")
    ap.add_argument("--oferta", default=BASE / "Horarios Ing_inf.xls", help="programación académica SAP")
    ap.add_argument("--sin-oferta", action="store_true")
    ap.add_argument("--cupos", choices=["historico", "todas", "oferta"], help="sobrescribe el JSON")
    ap.add_argument("--semilla", type=int, help="sobrescribe el JSON")
    ap.add_argument("--robustez", type=int, metavar="N", help="repetir con N semillas de emparejamiento")
    ap.add_argument("--salida", default=BASE / "salidas" / "asignacion.xlsx")
    ap.add_argument("--exportar-elegibilidad", nargs="?", const=BASE / "datos" / "elegibilidad.csv",
                    metavar="CSV", help="escribe la plantilla de elegibilidad por alumno y termina")
    return ap.parse_args()


def plantilla_elegibilidad(post):
    """Una fila por alumno con los criterios básicos y una columna para decidir a mano."""
    g = post.groupby("alumno")
    t = pd.DataFrame({
        "promedio_general": g["promedio"].first(),
        "cumple_promedio": g["cumple_promedio"].first().map({True: "SI", False: "NO"}),
        "postulaciones": g.size(),
        "postulaciones_cumplen_nota": g["cumple_nota"].sum().astype(int),
        "postulaciones_elegibles": g["elegible_calculado"].sum().astype(int),
        "ramos_bajo_nota_minima": g.apply(lambda x: ";".join(sorted(set(x.loc[~x["cumple_nota"], "sigla"])))),
        "elegible_manual": "",
    })
    return t.reset_index()


def main():
    args = parsear()
    p = Parametros.desde_json(args.parametros)
    cambios = {k: getattr(args, k) for k in ("cupos", "semilla") if getattr(args, k) is not None}
    p = p.con(**cambios)

    post = costos.anotar(datos.cargar_postulaciones(args.datos), p)
    if args.exportar_elegibilidad:
        ruta = Path(args.exportar_elegibilidad)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        plantilla_elegibilidad(post).to_csv(ruta, index=False)
        print(f"Plantilla de elegibilidad escrita en {ruta}.\n"
              f"Complete la columna elegible_manual (SI / NO / vacío) y apúntela en "
              f"parametros.json -> elegibilidad.archivo_elegibilidad.")
        return

    oferta = None if args.sin_oferta else datos.cargar_oferta(args.oferta)
    secciones = datos.tabla_secciones(post, p.cupos, oferta, p.semilla)
    horarios = datos.horarios_de_oferta(secciones) if oferta is not None else None

    asign, info = modelo.resolver(post, secciones, p, horarios)
    greedy = modelo.greedy_por_seccion(post, secciones, p, horarios)
    hist = modelo.historico(post)
    comparacion = pd.DataFrame({
        "Histórico (manual)": metricas.calcular(hist, secciones, p, horarios),
        "Greedy por sección": metricas.calcular(greedy, secciones, p, horarios),
        "Flujo costo mínimo": metricas.calcular(asign, secciones, p, horarios),
    })

    print(f"Postulaciones: {len(post)} | alumnos: {post['alumno'].nunique()} | "
          f"secciones: {len(secciones)} | con cupo: {int((secciones['cupos'] > 0).sum())}")
    print(f"Pesos a/b/c/d = {p.a}/{p.b}/{p.c}/{p.d} | modo no elegibles: {p.modo_no_elegibles} | "
          f"elegibles: promedio >= {p.promedio_minimo}, nota >= {p.nota_minima_ramo} "
          f"({int(post['elegible'].sum())} de {len(post)} postulaciones)")
    if oferta is not None:
        print(f"Oferta: {oferta['sigla'].nunique()} cursos, {len(oferta)} unidades | "
              f"secciones con bloque: {len(horarios)} | semilla emparejamiento: {p.semilla}")
    pasadas = f" (1ª pasada {info['flujo_pasada_1']}, 2ª pasada {info['flujo_pasada_2']})" \
        if "flujo_pasada_2" in info else ""
    print(f"Red: {info['nodos']} nodos, {info['aristas']} aristas | flujo={info['flujo']}{pasadas} | "
          f"{info['segundos'] * 1000:.0f} ms\n")
    print(comparacion.to_string())

    sin_cubrir = modelo.no_cubiertas(asign, secciones)
    manual = modelo.decision_manual(post, asign, secciones, p)
    if len(sin_cubrir):
        print(f"\nCupos sin cubrir: {len(sin_cubrir)} -> hoja 'Decisión manual' "
              f"({int((manual['motivo'] == 'no elegible').sum())} candidatos no elegibles)")

    resumen_rob = None
    if args.robustez:
        if oferta is None:
            raise SystemExit("--robustez requiere la oferta académica")
        _, resumen_rob = robustez.analizar(post, p, oferta, range(args.robustez))
        print(f"\nRobustez sobre {args.robustez} emparejamientos (media / mín / máx):")
        print(resumen_rob.T.to_string())

    carga = (asign.groupby("alumno").size().rename("asignadas").to_frame()
             .join(post.groupby("alumno")["total_postulaciones"].first())
             .join(hist.groupby("alumno").size().rename("asignadas_historico"))
             .fillna(0).astype(int).sort_values("asignadas", ascending=False))
    eleg_cols = ["alumno", "sigla", "tipo", "seccion", "promedio", "nota", "cumple_promedio", "cumple_nota",
                 "elegible_calculado", "elegible"]

    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(args.salida) as xls:
        modelo.a_tabla(asign, secciones).to_excel(xls, sheet_name="Asignación", index=False)
        comparacion.to_excel(xls, sheet_name="Comparación")
        manual.to_excel(xls, sheet_name="Decisión manual", index=False)
        post[eleg_cols].to_excel(xls, sheet_name="Elegibilidad", index=False)
        plantilla_elegibilidad(post).to_excel(xls, sheet_name="Elegibilidad por alumno", index=False)
        carga.to_excel(xls, sheet_name="Carga por alumno")
        modelo.a_tabla(greedy, secciones).to_excel(xls, sheet_name="Greedy", index=False)
        secciones.to_excel(xls, sheet_name="Secciones")
        if oferta is not None:
            oferta.to_excel(xls, sheet_name="Oferta")
        if resumen_rob is not None:
            resumen_rob.T.to_excel(xls, sheet_name="Robustez")
        pd.Series(vars(p), name="valor").astype(str).to_frame().to_excel(xls, sheet_name="Parámetros")
    print(f"\nResultado escrito en {args.salida}")


if __name__ == "__main__":
    main()
