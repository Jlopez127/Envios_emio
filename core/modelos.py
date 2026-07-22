"""Modelos de dominio del portal (Manifiesto, Tula, Envio, FacturaAerolinea,
CobroDistribucion, Novedad, GastoReal, Tarifario).

Estructura canonica definida en docs/CONTRATO_DATOS.md.
"""

from datetime import date


def construir_novedad(*, usuario, manifiesto_id, tipo, discriminador, campo_disc,
                      valor_esperado, valor_real, delta, justificacion, accion, fecha=None):
    """Construye el dict de una Novedad resuelta (ver docs/CONTRATO_DATOS.md).

    `usuario` es quien justifica: queda REGISTRADO en la novedad (auditoría). `campo_disc`
    indica si `discriminador` va como `tula_codigo` o como `guia`. `fecha` por defecto hoy.
    """
    return {
        "fecha": fecha or date.today().isoformat(),
        "usuario": usuario,
        "manifiesto_id": manifiesto_id,
        "tula_codigo": discriminador if campo_disc == "tula_codigo" else None,
        "guia": discriminador if campo_disc == "guia" else None,
        "tipo": tipo,
        "valor_esperado": valor_esperado,
        "valor_real": valor_real,
        "delta": delta,
        "justificacion": justificacion,
        "accion": accion,
        "estado": "resuelta",
    }
