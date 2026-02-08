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
**Check-in:** 07:00 AM to 10:00 PM.


* 
**Check-out:** 10:00 AM.


* 
**Breakfast:** Not included (Sin desayuno).


* 
* 
**Parking:** Must track if required (Yes/No); strictly subject to availability. [✅ DONE - Vehicle Model/Plate tracking added]



## 4. System Features & Data Requirements

* 
**Reservation Identification:** The reservation number serves as the unique ID.


* 
**Guest Details:** Must capture the **Estimated Arrival Time**.


* 
**Room Management:** Needs a monthly room sheet view (Ficha de habitación de por mes).


* 
**Language:** Support for changing languages, specifically for WhatsApp attention.



## 5. Integrations & Automation

The database and reservation visualization must coordinate and show data from multiple sources:

* Booking.com
* Airbnb
* WhatsApp
* Facebook
* Instagram
* Google

**Automation Requirement:** The system should automatically save/sync reservations made specifically on Booking and Airbnb. [❌ PENDING strategy]