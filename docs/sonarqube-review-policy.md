# Política de revisión de hallazgos de SonarQube

Contrato para resolver issues de SonarQube en este repositorio. Aplica tanto a Claude Code como a cualquier persona del equipo que corrija issues de Sonar.

## 1. Alcance permitido (lo único que se puede tocar)

- Solo se aplican cambios que correspondan a un **issue concreto reportado por SonarQube** (Code Smell, Bug, Vulnerability, Security Hotspot o Duplication), citando la regla exacta (ej. `python:S1172`, `python:S3776`, etc.).
- Cambios típicos permitidos: reducir complejidad ciclomática, eliminar código muerto/no usado, renombrar variables poco claras, eliminar duplicación, corregir *code smells* de estilo, ajustar manejo de recursos (context managers, cierres de archivos/conexiones), simplificar condicionales sin cambiar su resultado lógico.
- Nada que no tenga un issue asociado se toca, aunque "de paso" se vea algo mejorable.

## 2. Prohibiciones explícitas

- **Nunca modificar lógica de negocio**: reglas de cálculo, condiciones que afecten el resultado, validaciones de negocio, umbrales, flujos de decisión.
- **Nunca cambiar el comportamiento observable**: mismo input debe producir el mismo output antes y después del cambio.
- **Nunca modificar firmas públicas** (funciones, endpoints, contratos de request/response) sin aprobación explícita del usuario.
- **Nunca alterar tests para que "pasen"** ocultando el problema real (cambiar aserciones, comentar tests que fallan, aumentar timeouts para maquillar un fallo).
- **Nunca tocar configuración de infraestructura/despliegue** (CI/CD, variables de entorno, Dockerfiles) salvo que el issue sea explícitamente sobre eso.
- **No borrar código "por sospecha de no uso"** sin verificar referencias reales en todo el repo.

## 3. Zona gris — detenerse y preguntar antes de aplicar

Hay reglas de Sonar que *parecen* de estilo pero pueden cambiar comportamiento. Requieren aprobación explícita antes de aplicarse:

- Cambios en manejo de excepciones (`try/except`, tipos de excepción capturados).
- Cambios en comparaciones (identidad vs igualdad, coerciones de tipo).
- Reordenar condiciones con evaluación de cortocircuito.
- Cualquier "Security Hotspot" que implique cambiar validación de entradas o lógica de autenticación/autorización.
- Cualquier refactor que cruce más de un módulo o límites de capas (ej. de endpoint a service).

## 4. Cuándo NO modificar código (issues cosméticos sin impacto funcional)

Si el hallazgo es puramente de estilo/convención (ej. naming conventions, nombres en español, longitud de comentarios) y corregirlo:

- no aporta ningún beneficio funcional, y
- requiere tocar código que funciona intencionalmente así (ej. nombres elegidos a propósito, documentados en el propio código), o implica un cambio innecesariamente amplio (muchos callers, muchos archivos),

→ no modificar el código. En su lugar, indicar cómo silenciarlo desde la interfaz de SonarQube (marcar como "Won't Fix" / "False Positive") o ajustando la configuración del análisis de Sonar (`sonar-project.properties`, exclusiones de reglas en el pipeline), explicando el motivo.

## 5. Proceso de trabajo obligatorio

1. Un issue de SonarQube = un cambio, en un commit separado y descriptivo (`fix(sonar): S1172 - remove unused parameter in X`).
2. Ejecutar los tests existentes **antes y después** de cada cambio. Si no hay tests para ese código, avisar antes de tocarlo.
3. Trabajar siempre en una rama separada (nunca directo a `main`); el usuario revisa el diff antes de mergear.
4. Documentar cada cambio: regla resuelta, archivo, línea, y una frase de qué se hizo.

## 6. Métrica de éxito

- Baja el número de issues abiertos en SonarQube.
- La cobertura de tests no disminuye.
- Cero regresiones funcionales (los tests que pasaban, siguen pasando).
