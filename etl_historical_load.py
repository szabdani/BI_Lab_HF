from importlib.resources import path
import os
import pandas as pd
from sqlalchemy.orm import Session
from config import get_db_engine
from models import (
    DimSeason, DimCircuit, DimConstructor, DimDriver, DimRace,
    FactLapTime, FactRaceResult, FactWeather
)

# --- BEÁLLÍTÁSOK ---

F1_WC_DATASET = "rohanrao/formula-1-world-championship-1950-2020"
F1_WEATHER_DATASET = "mariyakostyrya/formula-1-weather-info-1950-2024"
DATA_DIR = "./data"
DOWNLOADED_DATA_DIR = f"./data_from_2026-05-21"
START_YEAR = 2014
END_YEAR = 2024

def download_data_from_kaggle():
    """
    Megpróbálja letölteni az adatokat a Kaggle API-val.
    Ha ez nem sikerül, akkor a letöltött CSV fájlokkal dolgozik.
    """
    global DATA_DIR
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
        print("Kaggle API hitelesítés próbája...")
        api = KaggleApi()
        api.authenticate()
        
        print(f"Kaggle F1 világbajnoksági adatok letöltése: {F1_WC_DATASET}...")
        # A unzip=True automatikusan kicsomagolja a CSV-ket a data mappába
        api.dataset_download_cli(F1_WC_DATASET, path=DATA_DIR, unzip=True)
        print("Kaggle F1 világbajnoksági letöltés sikeres!")

        print(f"Kaggle F1 időjárás adatok letöltése: {F1_WEATHER_DATASET}...")
        api.dataset_download_cli(F1_WEATHER_DATASET, path=DATA_DIR, unzip=True)
        print("Kaggle F1 időjárás adatok letöltés sikeres!")

        print("Kaggle letöltés sikeres!")
    except Exception as e:
        print(f"Kaggle API letöltés sikertelen: {e}")
        DATA_DIR = DOWNLOADED_DATA_DIR # Visszaállás a legutőbb lementett mappára, ahol a CSV fájlok vannak
        print(f"Visszaállás a lokális mappára: ellenőrizd, hogy a CSV fájlok a '{DATA_DIR}' mappában vannak-e.")

def determine_era(year):
    """
    Meghatározza az F1-es érát az adott év alapján.
    """
    if 2014 <= year <= 2021:
        return "Turbo Hybrid"
    elif 2022 <= year <= 2025:
        return "Ground Effect"
    return "Other"

def run_historical_load():
    engine = get_db_engine()
    
    # Adatok letöltése vagy eddigi letöltött fájlok használata
    download_data_from_kaggle()
    
    print("\n--- Adatok betöltése memóriába (Pandas) ---")
    try:
        df_seasons = pd.read_csv(f"{DATA_DIR}/seasons.csv")
        df_races = pd.read_csv(f"{DATA_DIR}/races.csv")
        df_circuits = pd.read_csv(f"{DATA_DIR}/circuits.csv")
        df_constructors = pd.read_csv(f"{DATA_DIR}/constructors.csv")
        df_drivers = pd.read_csv(f"{DATA_DIR}/drivers.csv")
        df_lap_times = pd.read_csv(f"{DATA_DIR}/lap_times.csv")
        df_results = pd.read_csv(f"{DATA_DIR}/results.csv")
        df_status = pd.read_csv(f"{DATA_DIR}/status.csv")
        
        df_weather = pd.read_csv(f"{DATA_DIR}/weather_features_v4.csv")
        
    except FileNotFoundError as e:
        print(f"Kritikus hiba: Hiányzó adatfájl! {e}")
        return

    # Szűrés a 2014-2024 közötti időszakra
    df_races = df_races[(df_races['year'] >= START_YEAR) & (df_races['year'] <= END_YEAR)]
    valid_race_ids = df_races['raceId'].tolist()

    with Session(engine) as session:
        print("\n--- Dimenziók betöltése ---")
        
        # 1. Szezonok (DimSeason)
        print("Szezonok feldolgozása...")
        existing_seasons = [s[0] for s in session.query(DimSeason.year).all()]
        season_mappings = [{"year": y, "era_name": determine_era(y)} for y in range(START_YEAR, END_YEAR + 1) if y not in existing_seasons]
        if season_mappings:
            session.bulk_insert_mappings(DimSeason, season_mappings)
            session.commit()

        # 2. Pályák (DimCircuit)
        print("Pályák feldolgozása...")
        existing_circuits = [c[0] for c in session.query(DimCircuit.circuit_ref).all()]
        df_circuits_filtered = df_circuits[~df_circuits['circuitRef'].isin(existing_circuits)]
        
        circuit_mappings = df_circuits_filtered.rename(columns={
            "circuitId": "circuit_id", "circuitRef": "circuit_ref"
        })[["circuit_id", "circuit_ref", "name", "location", "country"]].to_dict('records')
        session.bulk_insert_mappings(DimCircuit, circuit_mappings)
        session.commit()

        # 3. Konstruktőrök (DimConstructor)
        print("Konstruktőrök feldolgozása...")
        existing_constructors = [c[0] for c in session.query(DimConstructor.constructor_ref).all()]
        df_constructors_filtered = df_constructors[~df_constructors['constructorRef'].isin(existing_constructors)]
        
        constructor_mappings = df_constructors_filtered.rename(columns={
            "constructorId": "constructor_id", "constructorRef": "constructor_ref"
        })[["constructor_id", "constructor_ref", "name", "nationality"]].to_dict('records')
        session.bulk_insert_mappings(DimConstructor, constructor_mappings)
        session.commit()

        # 4. Pilóták (DimDriver)
        print("Pilóták feldolgozása...")
        existing_drivers = [d[0] for d in session.query(DimDriver.driver_ref).all()]
        df_drivers_filtered = df_drivers[~df_drivers['driverRef'].isin(existing_drivers)]

        # A `\N` stringeket null-ra (NaN) cseréljük
        df_drivers_filtered = df_drivers_filtered.replace(r'\\N', None, regex=True)

        driver_mappings = df_drivers_filtered.rename(columns={
            "driverId": "driver_id", "driverRef": "driver_ref", "dob": "date_of_birth"
        })[["driver_id", "driver_ref", "number", "code", "forename", "surname", "nationality", "date_of_birth"]].to_dict('records')
        session.bulk_insert_mappings(DimDriver, driver_mappings)
        session.commit()

        # 5. Futamok (DimRace)
        print("Futamok feldolgozása...")
        existing_races = [r[0] for r in session.query(DimRace.race_id).all()]
        df_races_filtered = df_races[~df_races['raceId'].isin(existing_races)]

        # Beszúrt szezonokból lekérjük a season_id-ket, hogy betudjuk szúrni év alapján
        season_ids = {s.year: s.season_id for s in session.query(DimSeason).all()}
        df_races_filtered['season_id'] = df_races_filtered['year'].map(season_ids)

        race_mappings = df_races_filtered.rename(columns={
            "raceId": "race_id", "circuitId": "circuit_id"
        })[["race_id", "season_id", "circuit_id", "round", "name", "date"]].to_dict('records')
        session.bulk_insert_mappings(DimRace, race_mappings)
        session.commit()

        print("\n--- Ténytáblák betöltése ---")
        
        # Lekérjük az adatbázisban már meglévő futamokat, hogy csak az újakhoz töltsünk be tényeket
        existing_races = [r[0] for r in session.query(FactRaceResult.race_id).distinct().all()]
        new_race_ids = [rid for rid in valid_race_ids if rid not in existing_races]

        if not new_race_ids:
            print("Minden tényadat már fel van dolgozva. Nincs új betöltendő adat.")
            print("\n--- Historikus adatok betöltése SIKERESEN BEFEJEZŐDÖTT! ---")
            return

        # 6. Verseny eredményeinek feldolgozása (FactRaceResult)
        print("Verseny végeredményeinek feldolgozása...")
        df_results_filtered = df_results[df_results['raceId'].isin(new_race_ids)].copy()
        df_results_filtered = df_results_filtered.replace(r'\\N', None, regex=True)
        
        status_dict = dict(zip(df_status['statusId'], df_status['status']))
        df_results_filtered['status'] = df_results_filtered['statusId'].map(status_dict)
        
        result_mappings = df_results_filtered.rename(columns={
            "raceId": "race_id", "driverId": "driver_id", "constructorId": "constructor_id",
            "grid": "starting_position", "position": "finishing_position", "milliseconds": "race_milliseconds",
            "rank": "fastest_lap_rank", "fastestLapTime": "fastest_lap_time"
        })[["race_id", "driver_id", "constructor_id", "starting_position", "finishing_position", "points", "laps", "race_milliseconds", "fastest_lap_rank", "fastest_lap_time", "status"]].to_dict('records')
        session.bulk_insert_mappings(FactRaceResult, result_mappings)
        session.commit()

        # 7. Köridők (FactLapTime)
        print(f"Köridők feldolgozása... (Szűrt futamok száma: {len(new_race_ids)})")
        df_lap_times_filtered = df_lap_times[df_lap_times['raceId'].isin(new_race_ids)].copy()

        df_driver_constructors = df_results_filtered[['raceId', 'driverId', 'constructorId']].drop_duplicates()
        df_lap_times_merged = pd.merge(
            df_lap_times_filtered, 
            df_driver_constructors, 
            on=['raceId', 'driverId'], 
            how='left'
        )

        lap_mappings = df_lap_times_merged.rename(columns={
            "raceId": "race_id", "driverId": "driver_id", "constructorId": "constructor_id"
        })[["race_id", "driver_id", "constructor_id", "lap", "position", "time", "milliseconds"]].to_dict('records')
        session.bulk_insert_mappings(FactLapTime, lap_mappings)
        session.commit()
        
        # 8. Időjárás (FactWeather)
        print("Időjárás adatok szinkronizálása a futamokkal...")
        df_weather['year'] = pd.to_datetime(df_weather['datetime']).dt.year

        # Összekötjük a futamokkal az év és forduló alapján
        df_weather_merged = pd.merge(
            df_weather, 
            df_races[['year', 'round', 'raceId']], 
            on=['year', 'round'], 
            how='inner' # Csak azokat tartjuk meg, amikre van találat
        )
        
        weather_mappings = df_weather_merged.rename(columns={
            "raceId": "race_id"
        })[["race_id", "temperature", "precipitation", "windspeed"]].to_dict('records')
        session.bulk_insert_mappings(FactWeather, weather_mappings)
        session.commit()

        print("\n--- Historikus adatok betöltése SIKERESEN BEFEJEZŐDÖTT! ---")

if __name__ == "__main__":
    run_historical_load()