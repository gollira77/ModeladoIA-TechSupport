# Seguridad del agente — defensa en profundidad

Principio rector: **el LLM nunca es la única barrera**. Un modelo de 4B parámetros se puede confundir;
por eso cada regla importante está implementada en código determinista, y las instrucciones del modelo
son solo una capa más.

```
Mensaje ─► [1] API: auth JWT + límite de tasa + tamaño
        ─► [2] Guardrail de entrada (regex sobre texto normalizado)  ── bloquea sin llamar al LLM
        ─► [3] Bloqueo temporal (3 intentos graves en 15 min)
        ─► [4] LLM con instrucciones reforzadas + token canario
        ─► [5] before_tool_callback: límite de 10 herramientas/turno, herramientas solo-soporte, saneo de args
        ─► [6] Herramienta: identidad desde la sesión (no del modelo) + permisos + transiciones en servicios
        ─► [7] after_model_callback: enmascara secretos/emails, detecta fuga del prompt (canario)
        ─► Respuesta
Adjuntos ─► validación real del formato ─► análisis ─► [8] sanitizado: elimina instrucciones ocultas,
            enmascara contraseñas/tokens ─► se entregan al modelo marcados como DATOS
```

| Amenaza | Control | Dónde |
|---|---|---|
| Prompt injection directa ("ignorá tus instrucciones", "modo desarrollador", roles falsos, base64, leetspeak, separadores) | Patrones sobre texto normalizado y variantes decodificadas; el mensaje no llega al modelo | `services/seguridad.py` · `agent/callbacks.py` |
| Prompt injection **indirecta** (órdenes escondidas en logs o capturas) | Se eliminan las líneas con instrucciones y se registra `ADJUNTO_SOSPECHOSO` | `sanitizar_adjunto()` |
| Suplantación ("soy el supervisor") | El rol sale de la sesión creada por el backend tras el login; las herramientas releen el rol de la BD | `runtime.estado_usuario` · `tools._ejecutar` |
| Escalada de privilegios | Matriz de permisos y transiciones en los servicios (también para el panel web) | `services/permisos.py` |
| Fuga de datos sensibles | Bloqueo de pedidos de credenciales / datos personales; enmascarado de contraseñas, tokens, claves privadas, tarjetas (Luhn) y emails en respuestas y adjuntos | `PATRONES_SENSIBLE` · `redactar_salida()` |
| Fuga del prompt del sistema | Token canario en las instrucciones; si aparece en la salida, se reemplaza la respuesta | `CANARIO` |
| Alucinación de datos | `mensaje_error` debe estar respaldado por lo que escribió el usuario o sus adjuntos; RAG con "si no hay información, no inventes"; temperatura 0.1 | `tools._dato_respaldado` |
| Acciones no confirmadas | Cerrar ticket o crear a pesar de duplicados exige que el **último mensaje del usuario** sea una afirmación | `tools._usuario_confirmo` |
| Temas fuera de alcance | Patrones + instrucción con respuesta fija | `PATRONES_FUERA_DE_TEMA` |
| Ejecución de comandos en equipos | El agente no tiene herramientas para eso; los pedidos agregan una nota de seguridad al modelo | `PATRONES_COMANDO` |
| Loops / abuso de herramientas | Máximo 10 herramientas por mensaje; 12 mensajes por minuto por usuario | `callbacks.py` · `LimitadorTasa` |
| Archivos maliciosos | Lista blanca de extensiones, verificación real de imagen (Pillow), rechazo de binarios, tamaño máximo, nombre de archivo generado (sin path traversal) | `services/adjuntos.py` |
| Sesiones ajenas | Las sesiones del agente se buscan con el `user_id` del token | `runtime.obtener_sesion` |
| Errores que revelan internos | Manejadores genéricos en la API y en herramientas | `api/main.py` |

Todo evento queda en `eventos_seguridad` y el supervisor lo ve en **Seguridad y derivaciones**.
Las pruebas `tests/test_seguridad.py` verifican 28 ataques bloqueados y 18 mensajes legítimos que
**no** deben bloquearse (falsos positivos).
