# 🏨 Hospedaje Los Monges Apart Hotel - System Requirements

## 1. General Information

* 
**Capacity:** 15 rooms in total.


* 
**Numbering:** Rooms do not have fixed numbering.


* 
* 
**Design Theme:** White background with black text. [✅ DONE]



## 2. Room Categories & Pricing

The hotel operates based on specific categories rather than room numbers.

| Category Name | Description / Amenities | Capacity | Price (Guaraníes) |
| --- | --- | --- | --- |
| **Departamento Familiar** | 2 rooms, 4 beds | 6 people | 400,000 Gs |
| **Departamento Familiar 2** | 2 environments, 1 double bed + 1 bunk bed | 4 people | 250,000 Gs |
| **Departamento Ejecutivo** | 3 environments, 3 beds | 4 people | 300,000 Gs |
| **Departamento Doble** | 2 environments, 2 beds | 3 people | 200,000 Gs |
| **Departamento Superior** | 2 environments, double bed | 2 people | 200,000 Gs |
| **Departamento Superior** | 2 environments, double bed | 2 people | 200,000 Gs |
| **Departamento Estándar** | Mono-environment, double bed | 2 people | 150,000 Gs |

> [!NOTE]
> ✅ **Status:** Implemented in Database (room_categories table) and verified via Seed Script.

## 3. Operational Policies

* 
**Check-in:** 07:00 AM to 10:00 PM. [✅ DONE - Stored in properties table, displayed on reservation confirmation]


*
**Check-out:** 10:00 AM. [✅ DONE - Stored in properties table, displayed on reservation confirmation]


*
**Breakfast:** Not included (Sin desayuno). [✅ DONE - Stored in properties table, displayed on reservation confirmation]


* 
* 
**Parking:** Must track if required (Yes/No); strictly subject to availability. [✅ DONE - Vehicle Model/Plate tracking added]



## 4. System Features & Data Requirements

* 
**Reservation Identification:** The reservation number serves as the unique ID.


* 
**Guest Details:** Must capture the **Estimated Arrival Time**. [✅ DONE - Time picker in mobile form, stored in DB]


* 
**Room Management:** Needs a monthly room sheet view (Ficha de habitación de por mes).


* 
**Language:** Support for changing languages, specifically for WhatsApp attention.



## 5. Integrations & Automation

The database and reservation visualization must coordinate and show data from multiple sources:

* Booking.com [✅ DONE - iCal import/export sync]
* Airbnb [✅ DONE - iCal import/export sync]
* WhatsApp [✅ DONE - Source label in reservation form]
* Facebook [✅ DONE - Source label in reservation form]
* Instagram [✅ DONE - Source label in reservation form]
* Google [✅ DONE - Source label in reservation form]

**Automation Requirement:** The system should automatically save/sync reservations made specifically on Booking and Airbnb. [✅ DONE - iCal sync: import from OTA feeds every 15 min, export .ics for OTAs to pull. Admin UI in Configuración page.]

## 6. Document Generation

* **Reservation Confirmations:** Printable PDF auto-generated when a reservation is created (both PC and mobile). [✅ DONE - saved to `hotel/Reservas/`, filename: `{guest_name}_{dd-mm-yy}_{reservation_id}.pdf`]

* **Client Registration Sheets:** Printable PDF auto-generated when a check-in is created. [✅ DONE - saved to `hotel/Clientes/`, filename: `{last_name}_{first_name}_{dd-mm-yy}.pdf`]

* **Mobile Download:** Staff can download reservation PDFs from mobile after creation. [✅ DONE - "Descargar PDF" button appears after reservation creation, uses JWT-authenticated download]

* **PC Document Browser:** "Documentos del Hotel" page in sidebar with Reservas and Clientes tabs. [✅ DONE - direct filesystem read with download buttons]

* **On-Demand Regeneration:** If a PDF is missing, the download endpoint regenerates it automatically. [✅ DONE]

* **API Endpoints:** `GET /documents/reservations/{id}`, `GET /documents/clients/{id}`, `GET /documents/download/{folder}/{filename}`, `GET /documents/list/{folder}`. [✅ DONE - all authenticated, path traversal protected]
