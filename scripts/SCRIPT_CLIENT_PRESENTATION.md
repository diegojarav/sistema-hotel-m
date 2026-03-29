# Script: Presentacion al Cliente - Hotel PMS v1.2.0
**Fecha:** 18 de Marzo 2026
**Presentador:** Diego
**Duracion estimada:** 20-25 minutos
**Audiencia:** Propietarios/Administradores de Hospedaje Los Monges

---

## SLIDE 1 — Portada (30 seg)

**[Mostrar logo + nombre del sistema]**

> "Buenos dias. Hoy les presento el sistema de gestion hotelera que hemos desarrollado para Hospedaje Los Monges. Un sistema completo, listo para usar, que va a simplificar toda la operacion diaria del hotel."

---

## SLIDE 2 — El Problema (1 min)

**[Mostrar iconos: papel, WhatsApp, Excel, confusion]**

> "Actualmente, la gestion se hace de forma manual o semi-manual: reservas por WhatsApp, control en papel o Excel, sin integracion con Booking.com ni Airbnb, sin documentos estandarizados para los huespedes, y sin una vision clara de ocupacion y revenue mes a mes."
>
> "Esto genera problemas reales: sobreventa de habitaciones, perdida de reservas, falta de control financiero, y mucho tiempo perdido en tareas repetitivas."

---

## SLIDE 3 — La Solucion (1 min)

**[Mostrar diagrama de arquitectura simplificado: PC + Celular + Servidor]**

> "Lo que hemos construido es un sistema con tres partes que trabajan juntas:"
>
> "**Primero**, una aplicacion de escritorio para administracion — aca se gestionan habitaciones, usuarios, precios, reportes, y documentos."
>
> "**Segundo**, una aplicacion movil para recepcion — desde el celular pueden crear reservas, hacer check-in, y descargar comprobantes en PDF."
>
> "**Tercero**, un servidor que conecta todo, sincroniza con Booking.com y Airbnb automaticamente, y guarda todos los datos de forma segura."

---

## SLIDE 4 — Demo: Crear una Reserva desde el Celular (3 min)

**[Demo en vivo en el celular o emulador]**

> "Vamos a ver como funciona en la practica. Imaginen que llega una reserva por telefono."

**Pasos en vivo:**
1. Abrir la app movil → Login con usuario recepcion
2. Ir a "Nueva Reserva"
3. Seleccionar fechas (mostrar que la fecha es correcta, hoy)
4. Elegir categoria de habitacion → ver habitaciones disponibles
5. Seleccionar habitacion(es) — mostrar que se puede elegir varias categorias
6. Llenar datos del huesped (nombre, documento, telefono)
7. Ver el calculo automatico de precio
8. Crear la reserva
9. **Mostrar el boton "Descargar PDF"** — descargar el comprobante

> "En menos de un minuto, la reserva esta creada, el PDF de confirmacion esta guardado en el servidor, y pueden descargarlo o enviarlo por WhatsApp al huesped."

---

## SLIDE 5 — Demo: Ver el Calendario y Ocupacion (2 min)

**[Mostrar calendario en PC]**

> "Ahora, si vamos al escritorio, pueden ver todo de un vistazo."

**Mostrar:**
1. Calendario mensual — colores por estado (confirmada, check-in, check-out, cancelada)
2. Vista semanal — las 15 habitaciones con sus reservas
3. Ficha mensual (Gantt) — ocupacion completa del mes, dia por dia
4. Grafico de ocupacion — porcentaje diario con promedio

> "Ya no necesitan revisar cuadernos ni Excel. Todo esta aca, actualizado en tiempo real."

---

## SLIDE 6 — Demo: Documentos del Hotel (2 min)

**[Mostrar Streamlit → Documentos del Hotel]**

> "Cada reserva genera automaticamente un documento PDF. Lo mismo cuando se registra un huesped."

**Mostrar:**
1. Pestana "Reservas" — lista de PDFs con boton de descarga
2. Pestana "Clientes" — lista de fichas de registro
3. Abrir un PDF de ejemplo — mostrar el formato con datos del hotel, huesped, fechas, precio

> "Estos documentos se pueden imprimir para archivo o enviar al huesped. Estan siempre disponibles en el servidor, organizados por carpeta."

---

## SLIDE 7 — Integracion con Booking.com y Airbnb (2 min)

**[Mostrar configuracion iCal en Admin]**

> "El sistema se conecta automaticamente con Booking.com y Airbnb a traves de calendarios iCal."

**Mostrar:**
1. Configuracion → seccion iCal
2. Agregar URL de feed de Booking.com para una habitacion
3. Sincronizacion automatica cada 15 minutos
4. Las reservas de Booking aparecen directamente en el calendario

> "Cuando alguien reserva en Booking.com, aparece automaticamente en su sistema. Y lo mismo al reves — si reservan directo, Booking.com ve que la habitacion esta ocupada. Esto elimina la sobreventa."

---

## SLIDE 8 — Precios Inteligentes (1 min)

**[Mostrar tabla de precios por categoria y tipo de cliente]**

> "El sistema maneja 7 categorias de habitacion con precios diferenciados por tipo de cliente."

**Mostrar:**
- Categorias: Doble Familiar, Doble Comun, Suite Simple, Suite Doble, Triple, Cuadruple, Quintuple
- Tipos de cliente: Normal, Paraguayo, Extranjero, Empresarial, etc.
- Calculo automatico segun noches seleccionadas

> "El precio se calcula solo. No hay errores de calculo manual."

---

## SLIDE 9 — Seguridad (1 min)

**[Mostrar slide con iconos de seguridad]**

> "La seguridad es fundamental porque manejan datos personales de huespedes."
>
> "El sistema tiene:"
> - **Acceso con usuario y contrasena** — cada empleado tiene su propia cuenta
> - **Roles diferenciados** — el administrador puede todo, recepcion solo lo necesario
> - **Datos encriptados** — las contrasenas se guardan con encriptacion bcrypt
> - **Sesiones controladas** — se puede ver quien esta conectado y cerrar sesiones

---

## SLIDE 10 — Asistente IA (1 min)

**[Mostrar chat con IA en el escritorio]**

> "Incluimos un asistente de inteligencia artificial integrado. Pueden hacerle preguntas en espanol."

**Mostrar ejemplo:**
- "Que habitaciones estan libres hoy?"
- "Cuantas reservas hay para marzo?"
- "Cual es el ingreso total de este mes?"

> "El asistente tiene acceso a todos los datos del sistema y responde al instante. Es como tener un empleado mas que conoce todo."

---

## SLIDE 11 — Monitoreo y Mantenimiento (1 min)

**[Mostrar slide con logos: Discord, GitHub, Healthchecks]**

> "El sistema se monitorea automaticamente:"
> - **Si hay un error**, me llega una notificacion a Discord al instante
> - **Si el servidor se cae**, recibo una alerta por email en menos de una hora
> - **Cada mes**, se ejecuta una evaluacion automatica de rendimiento y calidad
>
> "No necesitan preocuparse por el mantenimiento. Yo recibo las alertas y puedo intervenir remotamente."

---

## SLIDE 12 — Reportes y Analisis (2 min)

**[Mostrar reportes en Admin Habitaciones]**

> "Para la gestion financiera, el sistema incluye varios reportes:"

**Mostrar:**
1. **Resumen por habitacion** — ingreso, noches ocupadas, tasa de ocupacion por habitacion
2. **Mapa de calor de ingresos** — que habitaciones generan mas por mes (verde = mas ingreso)
3. **Distribucion por canal** — cuantas reservas vienen de Booking, Airbnb, directo, WhatsApp
4. **Uso de estacionamiento** — cuantos espacios se usan por dia

> "Con estos datos pueden tomar decisiones informadas: que habitaciones promocionar, que canales funcionan mejor, cuando subir o bajar precios."

---

## SLIDE 13 — Infraestructura y Despliegue (1 min)

**[Mostrar diagrama: PC local + GCP + Internet]**

> "El sistema funciona en su PC local del hotel. Los datos quedan ahi, en su control."
>
> "Tambien tenemos un servidor de respaldo en Google Cloud por si necesitan acceso remoto."
>
> "La app movil funciona en cualquier celular conectado a la red WiFi del hotel."
>
> "Hay respaldos automaticos de la base de datos. Si algo pasa, se puede restaurar."

---

## SLIDE 14 — Resumen de Funcionalidades (1 min)

**[Checklist visual]**

| Funcion | Estado |
|---------|--------|
| Gestion de reservas (PC y movil) | Listo |
| Calendario visual (mensual, semanal, diario) | Listo |
| Check-in / Check-out con registro de huesped | Listo |
| Documentos PDF automaticos (reservas y clientes) | Listo |
| Integracion Booking.com y Airbnb | Listo |
| Precios por categoria y tipo de cliente | Listo |
| Reportes financieros y de ocupacion | Listo |
| Asistente IA | Listo |
| Seguridad con roles y sesiones | Listo |
| Monitoreo automatico 24/7 | Listo |
| Estacionamiento | Listo |

---

## SLIDE 15 — Proximos Pasos (1 min)

> "Para empezar a usar el sistema necesitamos:"
>
> 1. **Instalar en la PC del hotel** — el sistema queda corriendo como servicio
> 2. **Configurar las habitaciones** — ya estan las 15 habitaciones con sus categorias
> 3. **Crear los usuarios** — admin para ustedes, recepcion para el personal
> 4. **Conectar los iCal** — pegar las URLs de Booking.com y Airbnb por habitacion
> 5. **Capacitacion** — 1-2 horas para que el equipo sepa usar todo
>
> "Todo esto lo podemos hacer hoy mismo o manana. El sistema esta listo."

---

## SLIDE 16 — Cierre (30 seg)

> "Este sistema fue construido especificamente para Hospedaje Los Monges. No es un software generico — conoce sus habitaciones, sus precios, su forma de trabajar."
>
> "Tiene 313 pruebas automatizadas que garantizan que todo funciona correctamente. Fue validado en todas las funcionalidades antes de esta presentacion."
>
> "Alguna pregunta?"

---

## NOTAS PARA EL PRESENTADOR

### Antes de la presentacion:
- [ ] Verificar que los 3 servidores estan corriendo (backend, PC, mobile)
- [ ] Tener una reserva de ejemplo ya creada para mostrar
- [ ] Tener el PDF de ejemplo listo para mostrar
- [ ] Verificar la conexion a internet (para la demo de iCal)
- [ ] Preparar credenciales: admin/admin123 y recepcion/recep123

### Tips:
- Hablar siempre en terminos de beneficio para el hotel, no tecnico
- Si preguntan algo tecnico, simplificar: "eso lo manejo yo, ustedes solo usan la interfaz"
- Enfatizar: "Aca se ahorra tiempo" y "Aca se evitan errores"
- Si la demo falla, tener screenshots de respaldo
- Dejar que toquen el celular y prueben crear una reserva

### Preguntas frecuentes anticipadas:
- **"Que pasa si se corta la luz?"** → Los datos se guardan automaticamente. Al encender, todo sigue igual.
- **"Funciona sin internet?"** → Si, excepto la sincronizacion con Booking/Airbnb. Las reservas directas funcionan sin internet.
- **"Cuanto cuesta mantenerlo?"** → Solo el costo del servidor en la nube (~$16/mes) si lo quieren. El software no tiene costo mensual.
- **"Se puede usar en tablet?"** → Si, la app movil funciona en cualquier navegador.
- **"Quien me ayuda si hay un problema?"** → Yo recibo alertas automaticas y puedo conectarme remotamente para solucionarlo.
