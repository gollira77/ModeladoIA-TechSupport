# Estados del ticket y transiciones permitidas — TechSupport S.A.

Documento ficticio de uso interno para pruebas.

## Estados
- Abierto: el ticket fue registrado y todavía no comenzó su atención.
- En revisión: el equipo de soporte está analizando la incidencia.
- En progreso: se están realizando tareas para resolver el problema.
- Pendiente: se requiere información adicional del usuario o una acción externa (proveedor, repuesto) para continuar.
- Resuelto: el inconveniente fue solucionado; se espera la confirmación del solicitante.
- Cerrado: el ticket fue finalizado administrativamente. Es un estado final.

## Transiciones permitidas y quién puede hacerlas
- Abierto → En revisión (técnico o supervisor). Si el técnico no estaba asignado, queda como responsable.
- Abierto → Cerrado (solo supervisor; por ejemplo, ticket duplicado o anulado).
- En revisión → En progreso (técnico responsable o supervisor).
- En revisión → Pendiente (técnico responsable o supervisor; requiere motivo).
- En revisión → Cerrado (solo supervisor).
- En progreso → Pendiente (técnico responsable o supervisor; requiere motivo).
- En progreso → Resuelto (técnico responsable o supervisor; requiere detalle de la solución).
- Pendiente → En progreso / En revisión (técnico responsable o supervisor).
- Pendiente → Cerrado (solo supervisor; por ejemplo, el usuario no respondió en 10 días hábiles).
- Resuelto → Cerrado (el solicitante confirma la solución, o el técnico/supervisor).
- Resuelto → En progreso (reapertura: el solicitante indica que el problema sigue; requiere motivo).
- Cerrado: no admite cambios.

## Reglas generales
- Cada cambio de estado queda registrado en el historial con fecha, hora, responsable y origen (agente o panel).
- Cerrar un ticket es definitivo y requiere confirmación.
- Un técnico solo puede cambiar el estado de los tickets asignados a él o de tickets sin responsable.
