from prefect import flow, task
import subprocess
import os
import sys

@task(name="Run_Historical_Load")
def run_historical_load():
    """
    Lefuttatja az etl_historical_load.py-t az új Kaggle adatok letöltéséhez és betöltéséhez.
    """
    python_executable = sys.executable 
    command = [
        python_executable, 
        os.path.join(os.path.dirname(__file__), "etl_historical_load.py")
    ]
    
    print(f"Futtatás indítása: {' '.join(command)}")
    
    # A subprocess futtatja az ETL-t
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    
    print(f"stdout: {result.stdout}")
    if result.stderr:
        print(f"HIBA (stderr): {result.stderr}")
        
    return result.returncode

@task(name="Run_Season_Stats_Aggregation")
def run_season_stats():
    """
    Lefuttatja az etl_create_season_stats.py-t a frissített tényadatok aggregálásához.
    """
    python_executable = sys.executable
    command = [
        python_executable, 
        os.path.join(os.path.dirname(__file__), "etl_create_season_stats.py")
    ]
    
    print(f"Futtatás indítása: {' '.join(command)}")
    
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    
    print(f"stdout: {result.stdout}")
    if result.stderr:
        print(f"HIBA (stderr): {result.stderr}")
        
    return result.returncode

@flow(name="Kaggle_Dataset_Update_Flow")
def kaggle_update_flow():
    """
    A fő folyamat, amit a Kaggle adatbázis frissülésekor futtatunk.
    """
    print("--- Kaggle adatfrissítési folyamat (ETL) elindítva ---")

    load_result = run_historical_load()
    if load_result == 0:
        print("Adatbetöltés sikeres! Szezonális aggregációk indítása...")
        run_season_stats()
    else:
        print("KRITIKUS HIBA: Hiba történt a historikus adatok betöltése során, az aggregáció megszakítva!")

if __name__ == "__main__":
    kaggle_update_flow()