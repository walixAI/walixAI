import type { MessageOut } from "@/lib/api";
import type { ServiceWindow } from "./serviceWindow";

export interface GuidanceCard {
  title: string;
  steps: string[];
  tooltip: string;
  hint: string; // compact hint for Composer banner
}

export function getGuidance(messages: MessageOut[], sw: ServiceWindow): GuidanceCard {
  if (!sw.open) {
    return {
      title: "Ventana de servicio cerrada",
      steps: [
        "Solo puedes contactar al cliente con una plantilla aprobada por Meta.",
        "Espera a que el cliente te escriba para reabrir la ventana.",
      ],
      tooltip:
        "Meta exige plantillas aprobadas fuera del período de 24 h tras el último mensaje entrante del cliente.",
      hint: "Ventana cerrada · se requiere plantilla aprobada para responder",
    };
  }

  if (messages.length === 0) {
    return {
      title: "Sin mensajes aún",
      steps: [
        "El cliente no ha enviado mensajes todavía.",
        "Cuando escriba, tendrás 24 h para responder libremente.",
      ],
      tooltip:
        "La ventana de 24 h se abre con el primer mensaje entrante del cliente.",
      hint: "Esperando el primer mensaje del cliente",
    };
  }

  const lastRole = messages[messages.length - 1].role;

  if (lastRole === "user") {
    return {
      title: "El cliente espera tu respuesta",
      steps: [
        "Revisa el contexto y responde al cliente.",
        `Tienes ${sw.remainingLabel} restantes en la ventana de servicio.`,
        "Usa 'Sugerir respuesta' si quieres que la IA te ayude a redactar.",
      ],
      tooltip:
        "El último mensaje es del cliente. Responde pronto para mantener la conversación activa.",
      hint: "El cliente espera tu respuesta",
    };
  }

  return {
    title: "Esperando respuesta del cliente",
    steps: [
      "Ya enviaste un mensaje. Ahora espera la respuesta del cliente.",
      `Tienes ${sw.remainingLabel} restantes en la ventana de servicio.`,
      "Si no hay respuesta, considera un mensaje de seguimiento.",
    ],
    tooltip: "El último mensaje fue tuyo. El cliente aún no ha contestado.",
    hint: "Esperando que el cliente responda",
  };
}
