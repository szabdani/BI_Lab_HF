import pandas as pd
from sqlalchemy.orm import Session
from config import get_db_engine
from models import (
    DimSeason, DimRace, FactRaceResult, FactLapTime, 
    FactDriverSeasonStat, FactConstructorSeasonStat
)

def calculate_season_standings(session, engine):
    print("\n--- Bajnoki statisztikák számítása ---")
    
    # 1. Adatok lekérése a DWH-ból
    print("Tényadatok lekérése az adatbázisból...")
    query_results = """
        SELECT r.season_id, res.race_id, res.driver_id, res.constructor_id, 
               res.finishing_position, res.points, res.status, res.fastest_lap_rank
        FROM fact_race_results res
        JOIN dim_races r ON res.race_id = r.race_id
    """
    df_results = pd.read_sql(query_results, engine)

    # Kiesések (DNF) felismerése: Minden, ami nem "Finished" vagy "+x Lap"
    df_results['is_dnf'] = ~df_results['status'].str.contains(r'Finished|\+.*Lap', regex=True, na=False)
    # 2. Pilóták Szezonális Statisztikái (FactDriverSeasonStat)
    print("Pilóták szezonális statisztikáinak (ranglista) számítása...")
    
    # Kiszámoljuk a győzelmeket és dobogókat (finishing_position 1, illetve 1-3)
    df_results['is_win'] = (df_results['finishing_position'] == 1).astype(int)
    df_results['is_podium'] = ((df_results['finishing_position'] >= 1) & (df_results['finishing_position'] <= 3)).astype(int)
    df_results['races_entered'] = 1
    df_results['races_finished'] = (~df_results['is_dnf']).astype(int)
    df_results['is_fastest_lap'] = df_results['fastest_lap_rank'] == 1

    driver_stats = df_results.groupby(['season_id', 'driver_id', 'constructor_id']).agg(
        points=('points', 'sum'),
        wins=('is_win', 'sum'),
        podiums=('is_podium', 'sum'),
        races_entered=('races_entered', 'sum'),
        races_finished=('races_finished', 'sum'),
        fastest_laps=('is_fastest_lap', 'sum')
    ).reset_index()

    # Bajnoki helyezés számítása (szezononként, pontok alapján csökkenő sorrendben)
    driver_stats['driver_position'] = driver_stats.groupby('season_id')['points'].rank(ascending=False, method='min').astype(int)

    # 3. Konstruktőrök Szezonális Statisztikái (FactConstructorSeasonStat)
    print("Konstruktőri szezonális statisztikák számítása...")
    constructor_stats = df_results.groupby(['season_id', 'constructor_id']).agg(
        points=('points', 'sum'),
        wins=('is_win', 'sum'),
        podiums=('is_podium', 'sum'),
        races_entered=('races_entered', 'sum'),
        races_finished=('races_finished', 'sum')
    ).reset_index()

    # Bajnoki helyezés számítása (szezononként, pontok alapján csökkenő sorrendben)
    constructor_stats['constructor_position'] = constructor_stats.groupby('season_id')['points'].rank(ascending=False, method='min').astype(int)

    # 4. Adatok betöltése az adatbázisba
    print("Régi aggregációk törlése...")
    session.query(FactDriverSeasonStat).delete()
    session.query(FactConstructorSeasonStat).delete()
    session.commit()

    print("Új aggregációk beszúrása az adatbázisba...")
    session.bulk_insert_mappings(FactDriverSeasonStat, driver_stats.to_dict('records'))
    session.bulk_insert_mappings(FactConstructorSeasonStat, constructor_stats.to_dict('records'))
    session.commit()

    print("--- Aggregációk betöltése SIKERESEN BEFEJEZŐDÖTT! ---")

if __name__ == "__main__":
    engine = get_db_engine()
    with Session(engine) as session:
        calculate_season_standings(session, engine)