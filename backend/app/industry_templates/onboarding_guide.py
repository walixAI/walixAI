"""
Guía y constantes para el onboarding conversacional de Walix.

Define los campos que el sistema necesita recolectar del usuario durante
el flujo de onboarding, junto con el prompt de ejemplo y los temas clave.
"""
from __future__ import annotations

REQUIRED_FIELDS: list[dict[str, str]] = [
    {
        "key": "business_name",
        "question": "¿Cuál es el nombre de tu negocio?",
    },
    {
        "key": "business_description",
        "question": "¿A qué se dedica tu negocio? Descríbelo en 2–3 oraciones.",
    },
    {
        "key": "main_goal",
        "question": (
            "¿Qué quieres lograr con Walix? "
            "(ej: dar seguimiento a pacientes, no perder leads de WhatsApp, cerrar más ventas)"
        ),
    },
]

OPTIONAL_FIELDS: list[dict[str, str]] = [
    {
        "key": "city",
        "question": "¿En qué ciudad o ciudades operas?",
    },
    {
        "key": "team_size",
        "question": "¿Cuántas personas atienden a los clientes?",
    },
    {
        "key": "main_pain",
        "question": "¿Cuál es el mayor problema con el seguimiento de clientes hoy?",
    },
    {
        "key": "avg_ticket",
        "question": "¿Cuál es el precio aproximado de tu servicio o producto principal?",
    },
    {
        "key": "sales_cycle",
        "question": "¿Cuánto tiempo tarda normalmente en cerrar una venta o agendar una cita?",
    },
]

PROMPT_EXAMPLE = """
Ejemplo de descripción que funciona bien:

"Tengo una clínica de endocrinología pediátrica en Guadalajara. Atendemos a niños y
adolescentes con problemas de tiroides, diabetes y obesidad. Somos 2 médicos y una
recepcionista. El mayor problema es que los papás nos contactan por WhatsApp, agendamos
la cita, pero luego no vienen y no les damos seguimiento. Queremos que Walix nos ayude
a recordarles la cita y a darle seguimiento a los pacientes que no regresan."
"""

PROMPT_TOPICS: list[str] = [
    "El nombre de tu negocio o clínica",
    "A qué te dedicas y a quién atiendes",
    "Tu mayor problema con el seguimiento de clientes",
    "Cuántas personas atienden WhatsApp hoy",
]

# Mapa field_key → pregunta conversacional para follow-up
_FOLLOW_UP_MAP: dict[str, str] = {
    "business_name": "¿Cómo se llama tu negocio?",
    "business_description": "Cuéntame un poco más: ¿a qué se dedica tu negocio y a quién atiende?",
    "main_goal": "¿Cuál es el mayor reto con tus clientes que quieres resolver con Walix?",
    "city": "¿En qué ciudad o ciudades opera tu negocio?",
    "team_size": "¿Cuántas personas en tu equipo atienden clientes o responden WhatsApp?",
    "main_pain": "¿Qué es lo que más te cuesta trabajo en el seguimiento de clientes hoy?",
    "avg_ticket": "¿Cuánto cobra aproximadamente por tu servicio o producto principal?",
    "sales_cycle": "¿Cuánto tiempo suele pasar desde que un cliente te contacta hasta que cierra o agenda?",
}


def get_missing_required(extracted: dict) -> list[str]:
    """Retorna las keys de REQUIRED_FIELDS que no están en extracted o son None/vacías."""
    return [
        f["key"]
        for f in REQUIRED_FIELDS
        if not extracted.get(f["key"])
    ]


def get_follow_up_question(field_key: str) -> str:
    """Retorna la pregunta conversacional para el campo indicado."""
    return _FOLLOW_UP_MAP.get(field_key, f"¿Podrías contarme más sobre {field_key}?")
