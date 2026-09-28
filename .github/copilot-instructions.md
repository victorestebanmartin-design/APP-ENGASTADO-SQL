# Instrucciones para GitHub Copilot en este repo

Ver también `CLAUDE.md` en la raíz: recoge las trampas de este proyecto
(codificación en Windows, firmware OTA de los ESP32, pick-to-light opcional,
etc.). Esto complementa ese fichero con lo que aplica específicamente al
flujo de commits.

## Sube tú la versión (`VERSION`), sin preguntar

El fichero `VERSION` en la raíz (`X.Y.Z`) es la versión de la app, visible
como insignia discreta en cada pantalla (`templates/_version_badge.html`,
`{{ version_app }}`, `app/version.py`) y en Admin → Sistema. El usuario no
la toca a mano.

**Si vas a hacer o proponer un commit que se suba a `main` con cambios de
código de la app, sube `VERSION` como parte de ese commit.** El tamaño del
salto es tu criterio, según lo que pese el cambio:

- Patch (`1.5.3` → `1.5.4`): un cambio normal, un fix.
- Minor (`1.5.4` → `1.6.0`): algo gordo — función nueva, un flujo que cambia.
- Major (`1.6.0` → `2.0.0`): algo gordísimo — cambia cómo se usa la app o
  rompe compatibilidad con lo anterior.

No la dejes igual "por si acaso" — cada commit a `main` que toque código de
la app sube el número, aunque sea un patch. No apliques esto a ramas de
prueba o WIP que no vayan a `main`.
