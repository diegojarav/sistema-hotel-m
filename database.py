import os
import pandas as pd
from sqlalchemy import create_engine, Column, Integer, String, Date, Float, ForeignKey, DateTime, Time
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
import re

# Base de datos
DB_NAME = "hotel.db"
engine = create_engine(f"sqlite:///{DB_NAME}", echo=False)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)

# ==========================================
# MODELOS (Tablas)
# ==========================================

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False) # Plain text por compatibilidad v1, upgradear a hash después
    role = Column(String)
    real_name = Column(String)

class Room(Base):
    __tablename__ = "rooms"
    id = Column(String, primary_key=True) # "31", "32"
    type = Column(String)
    status = Column(String, default="Active")

class Reservation(Base):
    __tablename__ = "reservations"
    id = Column(String, primary_key=True) # "0001255"
    created_at = Column(DateTime, default=datetime.now)
    
    check_in_date = Column(Date) # Fecha_Entrada
    stay_days = Column(Integer)
    guest_name = Column(String) # A_Nombre_De
    
    room_id = Column(String, ForeignKey("rooms.id"))
    room_type = Column(String)
    
    price = Column(Float)
    arrival_time = Column(Time, nullable=True) # Hora_Llegada
    
    reserved_by = Column(String) # Reservado_Por
    contact_phone = Column(String) # Telefono
    received_by = Column(String) # Recibido_Por
    
    status = Column(String) # Confirmada, Cancelada
    cancellation_reason = Column(String, nullable=True)
    cancelled_by = Column(String, nullable=True)

class CheckIn(Base):
    __tablename__ = "checkins"
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(Date) # Fecha_Ingreso
    
    room_id = Column(String, ForeignKey("rooms.id"))
    check_in_time = Column(Time) # Hora
    
    last_name = Column(String)
    first_name = Column(String)
    nationality = Column(String)
    birth_date = Column(Date, nullable=True)
    
    origin = Column(String)
    destination = Column(String)
    civil_status = Column(String)
    document_number = Column(String, index=True)
    country = Column(String)
    
    billing_name = Column(String) # Facturacion_Nombre
    billing_ruc = Column(String) # Facturacion_RUC
    
    vehicle_model = Column(String)
    vehicle_plate = Column(String)
    
    digital_signature = Column(String) # Base64 o "Pendiente"

# ==========================================
# MIGRACIÓN
# ==========================================

def clean_days(val):
    try:
        match = re.search(r'\d+', str(val))
        return int(match.group()) if match else 1
    except: return 1

def init_db():
    Base.metadata.create_all(engine)
    
    # 1. Migrar Habitaciones (Hardcoded en app anterior)
    session = SessionLocal()
    if session.query(Room).count() == 0:
        rooms_list = [
            "31", "32", "33", "34", "35", "36",
            "21", "22", "23", "24", "25", "26", "27", "28"
        ]
        # Tipos aproximados basados en lógica previa o default
        for r in rooms_list:
            session.add(Room(id=r, type="Standard", status="Active"))
        session.commit()
    
    # 2. Migrar Usuarios
    if session.query(User).count() == 0 and os.path.exists("usuarios.xlsx"):
        df = pd.read_excel("usuarios.xlsx")
        for _, row in df.iterrows():
            u = User(
                username=row['Usuario'],
                password=str(row['Password']),
                role=row['Rol'],
                real_name=row['Nombre_Real']
            )
            session.add(u)
        session.commit()
        print("Usuarios migrados.")

    # 3. Migrar Reservas
    if session.query(Reservation).count() == 0 and os.path.exists("reservas.xlsx"):
        df = pd.read_excel("reservas.xlsx")
        for _, row in df.iterrows():
            # Parse time
            try:
                if pd.isna(row['Hora_Llegada']): t = None
                else: t = datetime.strptime(str(row['Hora_Llegada']), "%H:%M:%S").time()
            except: t = None
            
            # Parse dates
            f_in = pd.to_datetime(row['Fecha_Entrada']).date() if not pd.isna(row['Fecha_Entrada']) else None
            f_reg = pd.to_datetime(row['Fecha_Registro']) if not pd.isna(row['Fecha_Registro']) else datetime.now()

            r = Reservation(
                id=str(row['Nro_Reserva']),
                created_at=f_reg,
                check_in_date=f_in,
                stay_days=clean_days(row['Estadia_Dias']),
                guest_name=row['A_Nombre_De'],
                room_id=str(row['Habitacion']),
                room_type=row['Tipo_Habitacion'] if 'Tipo_Habitacion' in row else "",
                price=float(row['Precio']) if pd.notna(row['Precio']) else 0.0,
                arrival_time=t,
                reserved_by=row['Reservado_Por'] if 'Reservado_Por' in row else "",
                contact_phone=str(row['Telefono']),
                received_by=row['Recibido_Por'] if 'Recibido_Por' in row else "",
                status=row['Estado'],
                cancellation_reason=row.get('Motivo_Cancelacion', ""),
                cancelled_by=row.get('Cancelado_Por', "")
            )
            session.add(r)
        session.commit()
        print("Reservas migradas.")

    # 4. Migrar Fichas/Clientes
    if session.query(CheckIn).count() == 0 and os.path.exists("fichas_huespedes.xlsx"):
        df = pd.read_excel("fichas_huespedes.xlsx")
        for _, row in df.iterrows():
             # Parse time
            try:
                if pd.isna(row['Hora']): t = None
                else: t = datetime.strptime(str(row['Hora']), "%H:%M:%S").time()
            except: t = None
            
            f_nac = pd.to_datetime(row['Fecha_Nacimiento']).date() if pd.notna(row['Fecha_Nacimiento']) else None
            f_ing = pd.to_datetime(row['Fecha_Ingreso']).date() if pd.notna(row['Fecha_Ingreso']) else None

            ch = CheckIn(
                created_at=f_ing,
                room_id=str(row['Habitacion']),
                check_in_time=t,
                last_name=row['Apellidos'],
                first_name=row['Nombres'],
                nationality=row['Nacionalidad'],
                birth_date=f_nac,
                origin=row['Procedencia'],
                destination=row['Destino'],
                civil_status=row['Estado_Civil'],
                document_number=str(row['Nro_Documento']),
                country=row['Pais'],
                billing_name=row.get('Facturacion_Nombre', ""),
                billing_ruc=str(row.get('Facturacion_RUC', "")),
                vehicle_model=row.get('Vehiculo_Modelo', ""),
                vehicle_plate=row.get('Vehiculo_Chapa', ""),
                digital_signature=row.get('Firma_Digital', "Pendiente")
            )
            session.add(ch)
        session.commit()
        print("Fichas migradas.")
    
    session.close()

if __name__ == "__main__":
    init_db()
