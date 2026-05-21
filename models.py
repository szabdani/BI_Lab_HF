from sqlalchemy import Column, Integer, String, Date, ForeignKey, Float, DateTime, Boolean
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# --- DIMENZIÓ TÁBLÁK ---

class DimSeason(Base):
    __tablename__ = 'dim_seasons'
    season_id = Column(Integer, primary_key=True, autoincrement=True)
    year = Column(Integer, unique=True, nullable=False)
    era_name = Column(String, nullable=True) # Pl. "Turbo Hybrid", "Ground Effect"

class DimCircuit(Base):
    __tablename__ = 'dim_circuits'
    circuit_id = Column(Integer, primary_key=True, autoincrement=True)
    circuit_ref = Column(String, unique=True)

    name = Column(String, nullable=False)
    location = Column(String, nullable=True)
    country = Column(String, nullable=True)

class DimConstructor(Base):
    __tablename__ = 'dim_constructors'
    constructor_id = Column(Integer, primary_key=True, autoincrement=True)
    constructor_ref = Column(String, unique=True)
    
    name = Column(String, nullable=False)
    nationality = Column(String)

class DimDriver(Base):
    __tablename__ = 'dim_drivers'
    driver_id = Column(Integer, primary_key=True, autoincrement=True)
    driver_ref = Column(String, unique=True)

    number = Column(Integer, nullable=True)
    code = Column(String(3), nullable=True)
    forename = Column(String, nullable=False)
    surname = Column(String, nullable=False)
    nationality = Column(String)
    date_of_birth = Column(Date, nullable=True)

class DimRace(Base):
    __tablename__ ='dim_races'
    race_id = Column(Integer, primary_key=True, autoincrement=True)
    season_id = Column(Integer, ForeignKey('dim_seasons.season_id'))
    circuit_id = Column(Integer, ForeignKey('dim_circuits.circuit_id'))

    round = Column(Integer)
    name = Column(String)
    date = Column(Date)

    season = relationship("DimSeason", backref="races")
    circuit = relationship("DimCircuit", backref="races")


# --- TÉNY TÁBLÁK ---

class FactLapTime(Base):
    """
    Egy versenyző ideje egy adott verseny adott körén.
    """
    __tablename__ = 'fact_lap_times'
    lap_time_id = Column(Integer, primary_key=True, autoincrement=True)

    race_id = Column(Integer, ForeignKey('dim_races.race_id'))
    driver_id = Column(Integer, ForeignKey('dim_drivers.driver_id'))
    constructor_id = Column(Integer, ForeignKey('dim_constructors.constructor_id'))

    lap = Column(Integer)
    position = Column(Integer)
    time = Column(String) # '1:23.456'
    milliseconds = Column(Integer)


class FactRaceResult(Base):
    """
    Egy versenyző helyezése egy adott versenyen.
    """
    __tablename__ = 'fact_race_results'
    race_result_id = Column(Integer, primary_key=True, autoincrement=True)

    race_id = Column(Integer, ForeignKey('dim_races.race_id'))
    driver_id = Column(Integer, ForeignKey('dim_drivers.driver_id'))
    constructor_id = Column(Integer, ForeignKey('dim_constructors.constructor_id'))

    starting_position = Column(Integer)
    finishing_position = Column(Integer)
    points = Column(Integer)
    laps = Column(Integer)
    race_milliseconds = Column(Integer)
    fastest_lap_rank = Column(Integer)
    fastest_lap_time = Column(String)

    status = Column(String)
    
class FactWeather(Base):
    """
    Egy versenynek az időjárási adatai.
    Az értékeke a verseny során mért átlagos értékek.
    """
    __tablename__ = 'fact_weather'
    weather_id = Column(Integer, primary_key=True, autoincrement=True)

    race_id = Column(Integer, ForeignKey('dim_races.race_id'))
    
    temperature = Column(Float)
    precipitation = Column(Float)
    windspeed = Column(Float)

class FactDriverSeasonStat(Base):
    """
    A játékos adott szezonbeli összesített statisztikái egy bajnokságban.
    """
    __tablename__ = 'fact_driver_season_stats'
    drive_season_stat_id = Column(Integer, primary_key=True, autoincrement=True)
    
    driver_id = Column(Integer, ForeignKey('dim_drivers.driver_id'))
    constructor_id = Column(Integer, ForeignKey('dim_constructors.constructor_id'))
    season_id = Column(Integer, ForeignKey('dim_seasons.season_id'))

    driver_position = Column(Integer) # A bajnokságban elért helyezés
    races_entered = Column(Integer)
    races_finished = Column(Integer)

    wins = Column(Integer)
    podiums = Column(Integer)
    points = Column(Integer)
    fastest_laps = Column(Integer)

class FactConstructorSeasonStat(Base):
    """
    Egy csapat adott szezonbeli összesített statisztikái egy bajnokságban.
    """
    __tablename__ = 'fact_constructor_season_stats'
    constructor_season_stat_id = Column(Integer, primary_key=True, autoincrement=True)
    
    constructor_id = Column(Integer, ForeignKey('dim_constructors.constructor_id'))
    season_id = Column(Integer, ForeignKey('dim_seasons.season_id'))

    constructor_position = Column(Integer) # A bajnokságban elért helyezés
    races_entered = Column(Integer)
    races_finished = Column(Integer)

    wins = Column(Integer)
    podiums = Column(Integer)
    points = Column(Integer)


