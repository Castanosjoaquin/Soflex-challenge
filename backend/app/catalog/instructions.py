"""Instrucciones: what the operador reads aloud, written beforehand and never by the IA (ADR 0001).

The seed is the dataset's `instrucciones_prearribo` (EDA §6), rewritten as short imperative
phrases and grouped by the topics that repeat: alejarse, no tirar agua, posición del paciente,
no mover a la víctima, cortar el tránsito, fuentes de ignición.

Each instrucción applies only when its `applies_when` holds. The subtipo matters because it carries
the contraindications (EDA, implicancia 11): "no tire agua" is right for an eléctrico or fuel fire
and wrong in a pastizal, "no le saque el casco" only makes sense with a motociclista, and the
patient's position changes with the cuadro.

`order` sorts them: the instrucciones críticas first (below `PROHIBITION_ORDER`), then the
prohibitions (below `ACTION_ORDER`), then the rest. Lower goes first.

An instrucción `critical` is tied to P1 rules of the tabla: it is the one shown at once, in red,
whatever the etapa (DESIGN §2, regla 3). It needs no tipo, because the señal may come before it.
"""

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

from app.catalog.incidents import Subtype
from app.catalog.models import Category
from app.catalog.priority import SignalCondition
from app.catalog.signals import SignalAnswer, SignalId

PROHIBITION_ORDER = 20  # críticas are below this
ACTION_ORDER = 60  # prohibitions are below this, the rest at or above


class InstructionCondition(BaseModel):
    """When an instrucción applies. Every part that is set must hold; an empty part is "any".

    - `types`: the incidente's tipo is one of these.
    - `subtypes`: the subtipo is one of these (an unknown subtipo does not match).
    - `except_subtypes`: the subtipo is none of these (an unknown subtipo matches).
    - `signals`: every one of these señales has that value.
    - `priority_rules`: at least one of these rules of the tabla fires (for the críticas).
    """

    model_config = ConfigDict(frozen=True)

    types: tuple[Category, ...] = ()
    subtypes: tuple[Subtype, ...] = ()
    except_subtypes: tuple[Subtype, ...] = ()
    signals: tuple[SignalCondition, ...] = ()
    priority_rules: tuple[str, ...] = ()

    def holds(
        self,
        category: Category | None,
        subtype: Subtype | None,
        signals: Mapping[SignalId, SignalAnswer],
        fired_rules: frozenset[str],
    ) -> bool:
        if self.types and category not in self.types:
            return False
        if self.subtypes and subtype not in self.subtypes:
            return False
        if subtype is not None and subtype in self.except_subtypes:
            return False
        if any(signals.get(c.signal_id) is not c.value for c in self.signals):
            return False
        return not self.priority_rules or bool(fired_rules.intersection(self.priority_rules))


class Instruction(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    text: str
    critical: bool = False
    applies_when: InstructionCondition
    order: int


def _i(
    instruction_id: str,
    order: int,
    text: str,
    *,
    critical: bool = False,
    types: tuple[Category, ...] = (),
    subtypes: tuple[Subtype, ...] = (),
    except_subtypes: tuple[Subtype, ...] = (),
    signals: tuple[SignalId, ...] = (),
    priority_rules: tuple[str, ...] = (),
) -> Instruction:
    return Instruction(
        id=instruction_id,
        text=text,
        critical=critical,
        order=order,
        applies_when=InstructionCondition(
            types=types,
            subtypes=subtypes,
            except_subtypes=except_subtypes,
            signals=tuple(SignalCondition(signal_id=s) for s in signals),
            priority_rules=priority_rules,
        ),
    )


S, T = SignalId, Subtype
_I, _M, _A = Category.INCENDIO_RESCATE, Category.EMERGENCIA_MEDICA, Category.ACCIDENTE_VIAL
_D, _S, _C = Category.DEFENSA_CIVIL, Category.SERVICIOS_PUBLICOS, Category.CONVIVENCIA_SEGURIDAD

_ATRAPADA = ("atrapada_humo", "atrapada_fuego")
_EXPUESTOS = ("heridos_humo", "heridos_fuego", "menores_humo", "menores_fuego")

# Instrucciones críticas: one per P1 situation. Their order decides which one is active when two
# P1 rules fire at once: the vital signs first, then whatever keeps the llamante from adding a
# víctima (going back in, moving someone trapped).
_CRITICAS = (
    _i(
        "critica_no_respira",
        1,
        "No corte: quédese a su lado y le indico qué hacer.",
        critical=True,
        priority_rules=("no_respira",),
    ),
    _i(
        "critica_inconsciente",
        2,
        "No le dé nada de tomar ni le ponga nada en la boca.",
        critical=True,
        priority_rules=("inconsciente",),
    ),
    _i(
        "critica_sangrado",
        3,
        "Presione fuerte la herida con un paño limpio y no afloje.",
        critical=True,
        priority_rules=("sangrado_abundante",),
    ),
    _i(
        "critica_no_reingresar_local",
        4,
        "No vuelva a entrar al local por ningún motivo.",
        critical=True,
        subtypes=(T.INCENDIO_COMERCIO,),
        priority_rules=_ATRAPADA,
    ),
    _i(
        "critica_no_reingresar_casa",
        5,
        "No vuelva a entrar a la casa por ningún motivo.",
        critical=True,
        subtypes=(T.INCENDIO_VIVIENDA,),
        priority_rules=_ATRAPADA,
    ),
    _i(
        "critica_no_reingresar",
        6,
        "No vuelva a entrar por ningún motivo.",
        critical=True,
        except_subtypes=(T.INCENDIO_COMERCIO, T.INCENDIO_VIVIENDA),
        priority_rules=_ATRAPADA,
    ),
    _i(
        "critica_no_sacar_casco",
        7,
        "No le saque el casco al motociclista.",
        critical=True,
        signals=(S.MOTOCICLISTA,),
        priority_rules=("motociclista_herido",),
    ),
    _i(
        "critica_no_sacar_del_vehiculo",
        8,
        "No intente sacarlo del vehículo ni lo mueva.",
        critical=True,
        priority_rules=("atrapado_vehiculo",),
    ),
    _i(
        "critica_no_tocar_cable",
        9,
        "No toque el cable: aléjese a más de 15 metros.",
        critical=True,
        priority_rules=("descarga_electrica",),
    ),
    _i(
        "critica_gas",
        10,
        "No encienda nada: salgan ya y dejen la puerta abierta.",
        critical=True,
        priority_rules=("gas_propagacion",),
    ),
    _i(
        "critica_explosion",
        11,
        "No se acerque: aléjense ya del lugar.",
        critical=True,
        priority_rules=("explosion",),
    ),
    _i(
        "critica_humo",
        12,
        "No se queden en el humo: salgan al aire libre.",
        critical=True,
        priority_rules=_EXPUESTOS,
    ),
    _i(
        "critica_arma",
        13,
        "No se acerque ni intervenga: resguárdese.",
        critical=True,
        priority_rules=("arma_fuego",),
    ),
)

# Prohibitions: the "no" that matters most goes first (EDA §6: almost every instrucción has one).
_PROHIBICIONES = (
    # No tire agua: only eléctrico, baterías or aceite (the subtipo says "eléctrico o de baterías";
    # a transformer's oil, caso 030, is eléctrico too) and fuel. Never in a pastizal.
    _i(
        "no_agua_electrico",
        20,
        "No tire agua: con electricidad o baterías es peor.",
        subtypes=(T.INCENDIO_ELECTRICO,),
    ),
    _i(
        "no_agua_combustible",
        21,
        "No tire agua sobre el combustible: lo desparrama.",
        subtypes=(T.DERRAME_PELIGROSO,),
    ),
    _i(
        "no_encender_derrame",
        22,
        "No fume ni use el celular cerca del derrame.",
        subtypes=(T.DERRAME_PELIGROSO,),
    ),
    _i(
        "no_apagar_usted",
        23,
        "No intente apagarlo usted: aléjese.",
        subtypes=(T.INCENDIO_VEHICULO, T.INCENDIO_RESIDUOS, T.INCENDIO_PASTIZAL),
    ),
    _i(
        "no_forzar_rescate",
        24,
        "No fuerce puertas ni intente sacarlos usted.",
        subtypes=(T.RESCATE,),
    ),
    _i(
        "no_mover_herido",
        25,
        "No mueva al herido ni le tire de la ropa.",
        types=(_A,),
        signals=(S.HERIDOS,),
    ),
    _i(
        "no_remolcar",
        26,
        "No intenten moverlo ni remolcarlo sin la grúa.",
        subtypes=(T.OBSTRUCCION_VIA,),
    ),
    # Posición del paciente: each cuadro has its own, and they exclude each other.
    _i(
        "no_acostar",
        27,
        "No lo acueste: siéntelo derecho, inclinado hacia adelante.",
        subtypes=(T.DIFICULTAD_RESPIRATORIA, T.ALERGIA_GRAVE),
    ),
    _i(
        "no_objetos_boca",
        28,
        "No le meta los dedos ni nada en la boca.",
        subtypes=(T.CONVULSION,),
    ),
    _i(
        "no_liquidos",
        29,
        "No le dé líquidos hasta que esté bien despierto.",
        subtypes=(T.PERDIDA_CONCIENCIA,),
    ),
    _i(
        "no_enderezar",
        30,
        "No intente pararlo ni enderezarle la pierna.",
        subtypes=(T.TRAUMATISMO,),
    ),
    _i(
        "no_esfuerzo",
        31,
        "No lo deje caminar ni hacer fuerza: que quede sentado y quieto.",
        subtypes=(T.CARDIACO,),
    ),
    _i(
        "no_tocar_cables",
        32,
        "No toque los cables: tómelos como si tuvieran corriente.",
        signals=(S.CABLES_CAIDOS,),
    ),
    _i(
        "no_pisar_charcos",
        33,
        "No pise charcos cerca de los cables.",
        subtypes=(T.CABLES_ELECTRICOS,),
    ),
    _i(
        "no_encender_gas",
        34,
        "No encienda luces, fósforos ni el celular, ni toque timbres.",
        subtypes=(T.FUGA_GAS,),
    ),
    _i(
        "no_pasar_debajo",
        35,
        "No pase por debajo ni se acerque a la zona.",
        subtypes=(T.DERRUMBE, T.DESPRENDIMIENTO),
    ),
    _i(
        "no_cruzar_agua",
        36,
        "No se meta al agua ni intente cruzarla.",
        subtypes=(T.INUNDACION,),
    ),
    _i(
        "no_bajar_sotano",
        37,
        "No baje a sótanos ni garajes con agua.",
        signals=(S.AGUA_SUBE,),
    ),
    _i(
        "no_borde_pozo",
        38,
        "No se acerque al borde del pozo.",
        subtypes=(T.SOCAVON,),
    ),
    _i(
        "no_intervenir",
        39,
        "No intervenga: resguárdese en un lugar seguro.",
        subtypes=(T.RINA, T.ROBO),
    ),
    _i(
        "no_mirar_animal",
        40,
        "No mire al animal a los ojos ni haga movimientos bruscos.",
        subtypes=(T.ANIMAL_SUELTO,),
    ),
)

_ACCIONES = (
    _i(
        "vereda_enfrente",
        60,
        "Lleve a la gente a la vereda de enfrente y no deje que nadie se acerque a la puerta.",
        subtypes=(T.INCENDIO_COMERCIO, T.INCENDIO_VIVIENDA),
    ),
    _i(
        "evacuar_aire_libre",
        61,
        "Saque a todos al aire libre, lejos del edificio.",
        subtypes=(T.INCENDIO_ELECTRICO,),
    ),
    _i(
        "alejarse_vehiculo",
        62,
        "Aléjese del vehículo: el tanque puede explotar.",
        subtypes=(T.INCENDIO_VEHICULO,),
    ),
    _i(
        "humo_viento",
        63,
        "Póngase del lado del viento para no respirar el humo.",
        subtypes=(T.INCENDIO_PASTIZAL, T.INCENDIO_RESIDUOS),
    ),
    _i(
        "cortar_paso_derrame",
        64,
        "Que nadie se acerque: corte el paso de gente y autos.",
        subtypes=(T.DERRAME_PELIGROSO,),
    ),
    _i(
        "rescate_calma",
        65,
        "Hábleles para que mantengan la calma y esperen.",
        subtypes=(T.RESCATE,),
    ),
    _i(
        "salir_calzada",
        66,
        "Los que puedan caminar, que salgan de la calzada.",
        subtypes=(T.CHOQUE_VEHICULOS, T.VUELCO),
    ),
    _i(
        "apagar_motor",
        67,
        "Si es seguro, apague el motor del vehículo.",
        subtypes=(T.CHOQUE_VEHICULOS, T.VUELCO, T.ATROPELLO),
    ),
    _i(
        "senalizar",
        68,
        "Ponga balizas para desviar el tránsito, sin pararse en la calzada.",
        types=(_A,),
    ),
    _i(
        "epinefrina",
        69,
        "Si tiene un autoinyector de epinefrina, aplíquelo ya en el muslo.",
        subtypes=(T.ALERGIA_GRAVE,),
    ),
    _i(
        "aire_fresco",
        70,
        "Abra las ventanas para que entre aire fresco.",
        subtypes=(T.DIFICULTAD_RESPIRATORIA,),
    ),
    _i(
        "convulsion_espacio",
        71,
        "Aparte los muebles y póngale algo blando bajo la cabeza.",
        subtypes=(T.CONVULSION,),
    ),
    _i(
        "convulsion_lateral",
        72,
        "Cuando paren las sacudidas, póngalo de costado.",
        subtypes=(T.CONVULSION,),
    ),
    _i(
        "piernas_elevadas",
        73,
        "Acuéstelo boca arriba y elévele las piernas.",
        subtypes=(T.PERDIDA_CONCIENCIA,),
    ),
    _i(
        "aflojar_ropa",
        74,
        "Aflójele la ropa del cuello y la cintura.",
        subtypes=(T.PERDIDA_CONCIENCIA,),
    ),
    _i(
        "abrigar",
        75,
        "Abríguelo y no lo deje solo.",
        subtypes=(T.TRAUMATISMO,),
    ),
    _i(
        "presionar_herida",
        76,
        "Presione la herida con un paño limpio.",
        subtypes=(T.HEMORRAGIA,),
    ),
    _i(
        "perimetro",
        77,
        "Aléjese usted y los vecinos al menos 20 metros.",
        subtypes=(T.ARBOL_CAIDO, T.CABLES_ELECTRICOS),
    ),
    _i(
        "gas_salir",
        78,
        "Salgan y aléjense del olor a gas, con la puerta abierta.",
        subtypes=(T.FUGA_GAS,),
    ),
    _i(
        "desviar_peatones",
        79,
        "Desvíe a la gente a la vereda de enfrente.",
        subtypes=(T.DESPRENDIMIENTO,),
    ),
    _i(
        "lugar_alto",
        80,
        "Suba a un lugar alto y espere ahí.",
        subtypes=(T.INUNDACION,),
    ),
    _i(
        "cortar_luz_agua",
        81,
        "Si es seguro, corte la luz antes de que el agua llegue a los enchufes.",
        signals=(S.AGUA_SUBE,),
    ),
    _i(
        "semaforos_esquina",
        82,
        "Cruce por las esquinas donde funcionen los semáforos.",
        subtypes=(T.SEMAFOROS,),
    ),
)

INSTRUCTIONS: tuple[Instruction, ...] = tuple(
    sorted((*_CRITICAS, *_PROHIBICIONES, *_ACCIONES), key=lambda i: i.order)
)
INSTRUCTIONS_BY_ID: dict[str, Instruction] = {i.id: i for i in INSTRUCTIONS}

# Instrucciones that must never be read together: each pair would tell the llamante opposite
# things (here, the patient's position). The integrity test checks they can never both apply.
CONTRADICTORY: tuple[tuple[str, str], ...] = (
    ("no_acostar", "piernas_elevadas"),
    ("no_acostar", "convulsion_lateral"),
    ("piernas_elevadas", "convulsion_lateral"),
    ("no_esfuerzo", "piernas_elevadas"),
    ("no_esfuerzo", "convulsion_lateral"),
)


def instructions_for(
    category: Category | None,
    subtype: Subtype | None,
    signals: Mapping[SignalId, SignalAnswer],
    fired_rules: frozenset[str],
) -> list[Instruction]:
    """Every instrucción that applies, in reading order."""
    return [
        i for i in INSTRUCTIONS if i.applies_when.holds(category, subtype, signals, fired_rules)
    ]
