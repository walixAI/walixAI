"""
Catálogo de Industry Templates para Walix CRM.

Cada template define la semántica vertical completa de un giro de negocio:
etiqueta humana, nombre de la entidad (contacto/paciente/alumno/etc.),
etapas del pipeline con colores, estatus de contacto y palabras clave para
detección automática durante el onboarding.
"""
from __future__ import annotations

INDUSTRY_TEMPLATES: dict[str, dict] = {
    "salud": {
        "label": "Clínica / Consultorio",
        "entity_name": "Paciente",
        "entity_plural": "Pacientes",
        "pipeline_stages": [
            {"key": "new",           "label": "Nuevo paciente",         "order": 1, "color": "#6B7280"},
            {"key": "first_contact", "label": "Primer contacto",        "order": 2, "color": "#3B82F6"},
            {"key": "appointment",   "label": "Cita confirmada",        "order": 3, "color": "#8B5CF6"},
            {"key": "in_treatment",  "label": "En tratamiento",         "order": 4, "color": "#F59E0B"},
            {"key": "follow_up",     "label": "Seguimiento post-cita",  "order": 5, "color": "#10B981"},
            {"key": "discharged",    "label": "Alta médica",            "order": 6, "color": "#059669"},
            {"key": "lost",          "label": "Perdido / No contactó",  "order": 7, "color": "#EF4444"},
        ],
        "contact_statuses": [
            {"key": "new",      "label": "Nuevo",     "color": "#6B7280"},
            {"key": "active",   "label": "Activo",    "color": "#10B981"},
            {"key": "paused",   "label": "En pausa",  "color": "#F59E0B"},
            {"key": "inactive", "label": "Inactivo",  "color": "#EF4444"},
        ],
        "keywords": [
            "clínica", "consultorio", "médico", "doctor", "paciente", "salud",
            "tratamiento", "cita", "endocrinología", "pediatría", "odontología",
            "dentista", "psicólogo", "fisioterapia", "nutrición",
        ],
    },

    "bienes_raices": {
        "label": "Bienes Raíces",
        "entity_name": "Prospecto",
        "entity_plural": "Prospectos",
        "pipeline_stages": [
            {"key": "new",         "label": "Interesado",           "order": 1, "color": "#6B7280"},
            {"key": "visit",       "label": "Visita agendada",      "order": 2, "color": "#3B82F6"},
            {"key": "visited",     "label": "Visita realizada",     "order": 3, "color": "#8B5CF6"},
            {"key": "proposal",    "label": "Propuesta enviada",    "order": 4, "color": "#F59E0B"},
            {"key": "negotiation", "label": "En negociación",       "order": 5, "color": "#EF4444"},
            {"key": "paperwork",   "label": "Trámites/Escrituras",  "order": 6, "color": "#10B981"},
            {"key": "closed_won",  "label": "Cerrado",              "order": 7, "color": "#059669"},
            {"key": "lost",        "label": "Perdido",              "order": 8, "color": "#9CA3AF"},
        ],
        "contact_statuses": [
            {"key": "new",      "label": "Nuevo",    "color": "#6B7280"},
            {"key": "active",   "label": "Activo",   "color": "#10B981"},
            {"key": "client",   "label": "Cliente",  "color": "#3B82F6"},
            {"key": "inactive", "label": "Inactivo", "color": "#EF4444"},
        ],
        "keywords": [
            "inmueble", "propiedad", "casa", "departamento", "terreno", "renta",
            "venta", "agente", "broker", "bienes raíces", "hipoteca", "escritura",
            "avalúo", "plusvalía", "desarrolladora", "fraccionamiento",
        ],
    },

    "educacion": {
        "label": "Escuela / Academia",
        "entity_name": "Alumno",
        "entity_plural": "Alumnos",
        "pipeline_stages": [
            {"key": "new",       "label": "Interesado",          "order": 1, "color": "#6B7280"},
            {"key": "interview", "label": "Entrevista agendada", "order": 2, "color": "#3B82F6"},
            {"key": "evaluated", "label": "Evaluado",            "order": 3, "color": "#8B5CF6"},
            {"key": "enrolled",  "label": "Inscrito",            "order": 4, "color": "#10B981"},
            {"key": "studying",  "label": "Cursando",            "order": 5, "color": "#059669"},
            {"key": "renewal",   "label": "Por renovar",         "order": 6, "color": "#F59E0B"},
            {"key": "graduated", "label": "Egresado",            "order": 7, "color": "#6366F1"},
            {"key": "dropped",   "label": "Baja",                "order": 8, "color": "#EF4444"},
        ],
        "contact_statuses": [
            {"key": "new",      "label": "Nuevo",    "color": "#6B7280"},
            {"key": "active",   "label": "Activo",   "color": "#10B981"},
            {"key": "alumni",   "label": "Egresado", "color": "#6366F1"},
            {"key": "inactive", "label": "Baja",     "color": "#EF4444"},
        ],
        "keywords": [
            "escuela", "academia", "curso", "alumno", "estudiante", "clase",
            "inscripción", "matrícula", "maestro", "profesor", "taller",
            "capacitación", "certificación", "diplomado", "idiomas", "inglés",
        ],
    },

    "estetica_wellness": {
        "label": "Estética / Spa / Wellness",
        "entity_name": "Cliente",
        "entity_plural": "Clientes",
        "pipeline_stages": [
            {"key": "new",        "label": "Nuevo cliente",     "order": 1, "color": "#6B7280"},
            {"key": "contacted",  "label": "Contactado",        "order": 2, "color": "#3B82F6"},
            {"key": "appointment","label": "Cita agendada",     "order": 3, "color": "#8B5CF6"},
            {"key": "attended",   "label": "Asistió",           "order": 4, "color": "#10B981"},
            {"key": "recurring",  "label": "Cliente frecuente", "order": 5, "color": "#059669"},
            {"key": "reactivate", "label": "Por reactivar",     "order": 6, "color": "#F59E0B"},
            {"key": "lost",       "label": "Perdido",           "order": 7, "color": "#EF4444"},
        ],
        "contact_statuses": [
            {"key": "new",      "label": "Nuevo",    "color": "#6B7280"},
            {"key": "active",   "label": "Activo",   "color": "#10B981"},
            {"key": "vip",      "label": "VIP",      "color": "#F59E0B"},
            {"key": "inactive", "label": "Inactivo", "color": "#EF4444"},
        ],
        "keywords": [
            "estética", "spa", "belleza", "cabello", "uñas", "masaje", "facial",
            "depilación", "wellness", "yoga", "pilates", "gym", "gimnasio",
            "peluquería", "barbería", "maquillaje", "bronceado",
        ],
    },

    "automotriz": {
        "label": "Taller / Agencia Automotriz",
        "entity_name": "Cliente",
        "entity_plural": "Clientes",
        "pipeline_stages": [
            {"key": "new",       "label": "Nuevo cliente",             "order": 1, "color": "#6B7280"},
            {"key": "diagnosis", "label": "Diagnóstico",               "order": 2, "color": "#3B82F6"},
            {"key": "quoted",    "label": "Cotización enviada",        "order": 3, "color": "#8B5CF6"},
            {"key": "approved",  "label": "Aprobado / En taller",     "order": 4, "color": "#F59E0B"},
            {"key": "ready",     "label": "Listo para entrega",       "order": 5, "color": "#10B981"},
            {"key": "delivered", "label": "Entregado",                "order": 6, "color": "#059669"},
            {"key": "follow_up", "label": "Seguimiento post-servicio","order": 7, "color": "#6366F1"},
            {"key": "lost",      "label": "Perdido",                  "order": 8, "color": "#EF4444"},
        ],
        "contact_statuses": [
            {"key": "new",      "label": "Nuevo",    "color": "#6B7280"},
            {"key": "active",   "label": "Activo",   "color": "#10B981"},
            {"key": "vip",      "label": "VIP",      "color": "#F59E0B"},
            {"key": "inactive", "label": "Inactivo", "color": "#EF4444"},
        ],
        "keywords": [
            "taller", "mecánico", "auto", "carro", "vehículo", "agencia",
            "refacciones", "motor", "transmisión", "frenos", "llantas",
            "alineación", "pintura", "hojalatería", "diagnóstico", "servicio automotriz",
        ],
    },

    "restaurante": {
        "label": "Restaurante / Food & Beverage",
        "entity_name": "Cliente",
        "entity_plural": "Clientes",
        "pipeline_stages": [
            {"key": "new",         "label": "Nuevo cliente",    "order": 1, "color": "#6B7280"},
            {"key": "contacted",   "label": "Contactado",       "order": 2, "color": "#3B82F6"},
            {"key": "reservation", "label": "Reservación hecha","order": 3, "color": "#8B5CF6"},
            {"key": "attended",    "label": "Asistió",          "order": 4, "color": "#10B981"},
            {"key": "recurring",   "label": "Cliente frecuente","order": 5, "color": "#059669"},
            {"key": "reactivate",  "label": "Por reactivar",    "order": 6, "color": "#F59E0B"},
            {"key": "lost",        "label": "Perdido",          "order": 7, "color": "#EF4444"},
        ],
        "contact_statuses": [
            {"key": "new",      "label": "Nuevo",     "color": "#6B7280"},
            {"key": "active",   "label": "Frecuente", "color": "#10B981"},
            {"key": "vip",      "label": "VIP",       "color": "#F59E0B"},
            {"key": "inactive", "label": "Inactivo",  "color": "#EF4444"},
        ],
        "keywords": [
            "restaurante", "comida", "cocina", "chef", "menú", "reservación",
            "banquete", "catering", "bar", "cantina", "cafetería", "panadería",
            "pastelería", "taquería", "fonda", "delivery", "pedidos",
        ],
    },

    "servicios_profesionales": {
        "label": "Servicios Profesionales",
        "entity_name": "Cliente",
        "entity_plural": "Clientes",
        "pipeline_stages": [
            {"key": "new",         "label": "Prospecto nuevo",   "order": 1, "color": "#6B7280"},
            {"key": "contacted",   "label": "Contactado",        "order": 2, "color": "#3B82F6"},
            {"key": "proposal",    "label": "Propuesta enviada", "order": 3, "color": "#8B5CF6"},
            {"key": "negotiation", "label": "En negociación",    "order": 4, "color": "#F59E0B"},
            {"key": "active",      "label": "Cliente activo",    "order": 5, "color": "#10B981"},
            {"key": "renewal",     "label": "Por renovar",       "order": 6, "color": "#6366F1"},
            {"key": "lost",        "label": "Perdido",           "order": 7, "color": "#EF4444"},
        ],
        "contact_statuses": [
            {"key": "new",      "label": "Prospecto", "color": "#6B7280"},
            {"key": "active",   "label": "Cliente",   "color": "#10B981"},
            {"key": "paused",   "label": "Pausado",   "color": "#F59E0B"},
            {"key": "inactive", "label": "Inactivo",  "color": "#EF4444"},
        ],
        "keywords": [
            "despacho", "consultoría", "abogado", "contador", "notaría",
            "arquitecto", "ingeniero", "diseñador", "agencia", "marketing",
            "publicidad", "contabilidad", "auditoría", "fiscal", "asesoría",
            "coaching", "reclutamiento",
        ],
    },

    "generico": {
        "label": "Otro negocio",
        "entity_name": "Contacto",
        "entity_plural": "Contactos",
        "pipeline_stages": [
            {"key": "new",        "label": "Nuevo",             "order": 1, "color": "#6B7280"},
            {"key": "contacted",  "label": "Contactado",        "order": 2, "color": "#3B82F6"},
            {"key": "interested", "label": "Interesado",        "order": 3, "color": "#8B5CF6"},
            {"key": "proposal",   "label": "Propuesta enviada", "order": 4, "color": "#F59E0B"},
            {"key": "closed_won", "label": "Cerrado ganado",    "order": 5, "color": "#10B981"},
            {"key": "lost",       "label": "Perdido",           "order": 6, "color": "#EF4444"},
        ],
        "contact_statuses": [
            {"key": "new",      "label": "Nuevo",    "color": "#6B7280"},
            {"key": "active",   "label": "Activo",   "color": "#10B981"},
            {"key": "inactive", "label": "Inactivo", "color": "#EF4444"},
        ],
        "keywords": [],
    },
}

INDUSTRY_KEYS: list[str] = list(INDUSTRY_TEMPLATES.keys())


def get_template(key: str) -> dict:
    """Retorna el template de la industria indicada; cae a 'generico' si no existe."""
    return INDUSTRY_TEMPLATES.get(key, INDUSTRY_TEMPLATES["generico"])


def get_all_keywords() -> dict[str, list[str]]:
    """Retorna un mapa {industry_key: [keywords]} para detección automática."""
    return {key: tmpl["keywords"] for key, tmpl in INDUSTRY_TEMPLATES.items()}
