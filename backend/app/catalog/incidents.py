"""Tipos (the six `Category`) and their Subtipos (DESIGN §Paso 5).

The subtipo matters because it changes the instrucciones. A subtipo marked `reclamo` is a
non-urgent complaint: it is the only way an incidente can reach P4.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.catalog.models import Category


class Subtype(StrEnum):
    # INCENDIO_RESCATE
    INCENDIO_VIVIENDA = "incendio_vivienda"
    INCENDIO_COMERCIO = "incendio_comercio"
    INCENDIO_VEHICULO = "incendio_vehiculo"
    INCENDIO_ELECTRICO = "incendio_electrico"
    INCENDIO_PASTIZAL = "incendio_pastizal"
    INCENDIO_RESIDUOS = "incendio_residuos"
    DERRAME_PELIGROSO = "derrame_peligroso"
    RESCATE = "rescate"
    # EMERGENCIA_MEDICA
    DIFICULTAD_RESPIRATORIA = "dificultad_respiratoria"
    ALERGIA_GRAVE = "alergia_grave"
    CONVULSION = "convulsion"
    PERDIDA_CONCIENCIA = "perdida_conciencia"
    TRAUMATISMO = "traumatismo"
    HEMORRAGIA = "hemorragia"
    CARDIACO = "cardiaco"
    # ACCIDENTE_VIAL
    CHOQUE_VEHICULOS = "choque_vehiculos"
    CHOQUE_MOTO = "choque_moto"
    ATROPELLO = "atropello"
    VUELCO = "vuelco"
    OBSTRUCCION_VIA = "obstruccion_via"
    # DEFENSA_CIVIL
    ARBOL_CAIDO = "arbol_caido"
    FUGA_GAS = "fuga_gas"
    DERRUMBE = "derrumbe"
    DESPRENDIMIENTO = "desprendimiento"
    INUNDACION = "inundacion"
    # SERVICIOS_PUBLICOS
    CABLES_ELECTRICOS = "cables_electricos"
    ROTURA_CANO_AGUA = "rotura_cano_agua"
    SOCAVON = "socavon"
    SEMAFOROS = "semaforos"
    CORTE_SUMINISTRO = "corte_suministro"
    ALUMBRADO = "alumbrado"
    PODA = "poda"
    BACHE = "bache"
    # CONVIVENCIA_SEGURIDAD
    RINA = "rina"
    ROBO = "robo"
    ANIMAL_SUELTO = "animal_suelto"
    RUIDOS = "ruidos"


class TypeDef(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: Category
    label: str


class SubtypeDef(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: Subtype
    category: Category
    label: str
    reclamo: bool = False


TYPES: dict[Category, TypeDef] = {
    t.id: t
    for t in (
        TypeDef(id=Category.INCENDIO_RESCATE, label="Incendio y rescate"),
        TypeDef(id=Category.EMERGENCIA_MEDICA, label="Emergencia médica"),
        TypeDef(id=Category.ACCIDENTE_VIAL, label="Accidente vial"),
        TypeDef(id=Category.DEFENSA_CIVIL, label="Defensa civil"),
        TypeDef(id=Category.SERVICIOS_PUBLICOS, label="Servicios públicos"),
        TypeDef(id=Category.CONVIVENCIA_SEGURIDAD, label="Convivencia y seguridad"),
    )
}


def _sub(subtype: Subtype, category: Category, label: str, *, reclamo: bool = False) -> SubtypeDef:
    return SubtypeDef(id=subtype, category=category, label=label, reclamo=reclamo)


_I, _M, _A = Category.INCENDIO_RESCATE, Category.EMERGENCIA_MEDICA, Category.ACCIDENTE_VIAL
_D, _S, _C = Category.DEFENSA_CIVIL, Category.SERVICIOS_PUBLICOS, Category.CONVIVENCIA_SEGURIDAD

SUBTYPES: dict[Subtype, SubtypeDef] = {
    s.id: s
    for s in (
        _sub(Subtype.INCENDIO_VIVIENDA, _I, "Incendio en vivienda"),
        _sub(Subtype.INCENDIO_COMERCIO, _I, "Incendio en comercio"),
        _sub(Subtype.INCENDIO_VEHICULO, _I, "Incendio de vehículo"),
        _sub(Subtype.INCENDIO_ELECTRICO, _I, "Incendio eléctrico o de baterías"),
        _sub(Subtype.INCENDIO_PASTIZAL, _I, "Incendio de pastizal"),
        _sub(Subtype.INCENDIO_RESIDUOS, _I, "Incendio de residuos"),
        _sub(Subtype.DERRAME_PELIGROSO, _I, "Derrame de combustible o químicos"),
        _sub(Subtype.RESCATE, _I, "Rescate de personas"),
        _sub(Subtype.DIFICULTAD_RESPIRATORIA, _M, "Dificultad respiratoria"),
        _sub(Subtype.ALERGIA_GRAVE, _M, "Reacción alérgica grave"),
        _sub(Subtype.CONVULSION, _M, "Convulsión"),
        _sub(Subtype.PERDIDA_CONCIENCIA, _M, "Desmayo o pérdida de conciencia"),
        _sub(Subtype.TRAUMATISMO, _M, "Caída o traumatismo"),
        _sub(Subtype.HEMORRAGIA, _M, "Hemorragia"),
        _sub(Subtype.CARDIACO, _M, "Dolor de pecho o paro"),
        _sub(Subtype.CHOQUE_VEHICULOS, _A, "Choque entre vehículos"),
        _sub(Subtype.CHOQUE_MOTO, _A, "Choque con moto"),
        _sub(Subtype.ATROPELLO, _A, "Atropello de peatón o ciclista"),
        _sub(Subtype.VUELCO, _A, "Vuelco"),
        _sub(Subtype.OBSTRUCCION_VIA, _A, "Vehículo que obstruye la vía"),
        _sub(Subtype.ARBOL_CAIDO, _D, "Árbol caído"),
        _sub(Subtype.FUGA_GAS, _D, "Fuga de gas"),
        _sub(Subtype.DERRUMBE, _D, "Derrumbe"),
        _sub(Subtype.DESPRENDIMIENTO, _D, "Desprendimiento en altura"),
        _sub(Subtype.INUNDACION, _D, "Inundación o anegamiento"),
        _sub(Subtype.CABLES_ELECTRICOS, _S, "Cables o postes eléctricos"),
        _sub(Subtype.ROTURA_CANO_AGUA, _S, "Rotura de caño de agua"),
        _sub(Subtype.SOCAVON, _S, "Socavón o pozo en la calzada"),
        _sub(Subtype.SEMAFOROS, _S, "Semáforos fuera de servicio"),
        _sub(Subtype.CORTE_SUMINISTRO, _S, "Corte de luz, agua o gas"),
        _sub(Subtype.ALUMBRADO, _S, "Luminaria apagada", reclamo=True),
        _sub(Subtype.PODA, _S, "Poda", reclamo=True),
        _sub(Subtype.BACHE, _S, "Bache", reclamo=True),
        _sub(Subtype.RINA, _C, "Riña o pelea"),
        _sub(Subtype.ROBO, _C, "Robo"),
        _sub(Subtype.ANIMAL_SUELTO, _C, "Animal suelto o agresivo"),
        _sub(Subtype.RUIDOS, _C, "Ruidos molestos", reclamo=True),
    )
}


def subtypes_of(category: Category) -> list[SubtypeDef]:
    return [s for s in SUBTYPES.values() if s.category is category]
