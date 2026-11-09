"""Parámetros del modelo, leídos desde `parametros.json` (editable a mano).

Los valores que no vienen en los datos (pesos, umbrales de elegibilidad,
ayudantías en otros departamentos) los define el usuario en ese archivo.
"""
import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

MODOS_NO_ELEGIBLES = ("excluir", "dos_pasadas", "penalizar")
CUPOS = ("historico", "todas", "oferta")
TOLERANCIA = 1e-6


@dataclass
class Parametros:
    # --- Pesos del costo de la arista H -> C (a + b + c + d = 1) ---
    a: float = 0.16  # P^O: preferencia de la oferta (ranking del profesor)
    b: float = 0.12  # P^E: preferencia del estudiante (su prioridad)
    c: float = 0.12  # P^A: mérito en la asignatura (nota del ramo y promedio)
    d: float = 0.6   # peso del alumno no elegible (modo "penalizar"); alto = casi excluido

    # --- Capacidades (restricciones duras) ---
    max_ayudantias: int = 3           # c(S, E_i)
    capacidad_correccion: int = 3     # c(E_i, H_i,corr): bloque ficticio de corrección
    cupos: str = "historico"          # qué unidades demandan ayudante
    incluir_no_rankeados: bool = True  # sin ranking del profesor -> orden por defecto

    # --- Elegibilidad ---
    promedio_minimo: float = 5.0
    nota_minima_ramo: float = 5.0
    modo_no_elegibles: str = "penalizar"
    archivo_elegibilidad: str | None = None  # CSV con la columna elegible_manual

    # --- Otros datos de entrada ---
    externas: dict[str, int] = field(default_factory=dict)  # alumno -> ayudantías en otros deptos.
    semilla: int = 0                  # emparejamiento sección reconstruida <-> grupo real

    def __post_init__(self):
        self.validar()

    def validar(self):
        pesos = (self.a, self.b, self.c, self.d)
        if any(w < 0 for w in pesos):
            raise ValueError(f"Los pesos deben ser no negativos: {pesos}")
        if abs(sum(pesos) - 1) > TOLERANCIA:
            raise ValueError(f"a + b + c + d debe ser 1 (es {sum(pesos):.4f})")
        if self.modo_no_elegibles not in MODOS_NO_ELEGIBLES:
            raise ValueError(f"modo_no_elegibles debe ser uno de {MODOS_NO_ELEGIBLES}")
        if self.cupos not in CUPOS:
            raise ValueError(f"cupos debe ser uno de {CUPOS}")
        if self.max_ayudantias < 0 or self.capacidad_correccion < 0:
            raise ValueError("Las capacidades deben ser no negativas")

    def con(self, **cambios):
        """Copia con algunos campos cambiados (valida de nuevo)."""
        return Parametros(**{**asdict(self), **cambios})

    def proporciones(self):
        """(a, b, c) normalizados a suma 1: el punto del triángulo de preferencias."""
        s = self.a + self.b + self.c
        return (self.a / s, self.b / s, self.c / s) if s else (1 / 3, 1 / 3, 1 / 3)

    def con_pesos(self, a=None, b=None, c=None, d=None, **cambios):
        """Copia con otro d y/o otras proporciones a:b:c; reescala para que a + b + c + d = 1."""
        pa, pb, pc = (a, b, c) if a is not None else self.proporciones()
        s = pa + pb + pc
        d = self.d if d is None else d
        ra, rb = round(pa / s * (1 - d), 6), round(pb / s * (1 - d), 6)
        return self.con(a=ra, b=rb, c=round(1 - d - ra - rb, 6), d=d, **cambios)

    @classmethod
    def desde_json(cls, ruta):
        crudo = json.loads(Path(ruta).read_text(encoding="utf-8"))
        plano = {}
        for clave, valor in crudo.items():
            if clave.startswith("_"):
                continue  # comentarios
            if clave == "externas":
                plano[clave] = {k: int(v) for k, v in valor.items() if not k.startswith("_")}
            elif isinstance(valor, dict):
                plano.update({k: v for k, v in valor.items() if not k.startswith("_")})
            else:
                plano[clave] = valor
        validos = {f.name for f in fields(cls)}
        desconocidos = set(plano) - validos
        if desconocidos:
            raise ValueError(f"Claves desconocidas en {ruta}: {sorted(desconocidos)}")
        return cls(**plano)
